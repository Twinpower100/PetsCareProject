from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .models import Provider, Employee, Schedule, ProviderService, SchedulePattern, PatternDay, EmployeeWorkSlot
from django import forms
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.contrib import messages
import datetime
import openpyxl
from django.http import HttpResponse
from custom_admin import custom_admin_site


class EmployeeInline(admin.TabularInline):
    model = Employee.providers.through
    extra = 0
    verbose_name = _('Employee')
    verbose_name_plural = _('Employees')


class ScheduleInline(admin.TabularInline):
    model = Schedule
    extra = 0
    fields = ('day_of_week', 'start_time', 'end_time', 'break_start', 'break_end', 'is_working')
    verbose_name = _('Schedule')
    verbose_name_plural = _('Schedules')


class PatternDayInline(admin.TabularInline):
    model = PatternDay
    extra = 1
    verbose_name = _('Pattern Day')
    verbose_name_plural = _('Pattern Days')


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    """
    Админка для провайдеров. Стандартный список + отдельная страница-отчет для экспорта расписания.
    - Стандартный changelist
    - Кнопка для перехода на страницу экспорта расписания
    - Отдельный URL для отчета
    """
    list_display = ('name', 'email', 'phone', 'address', 'rating', 'is_active', 'created_at')
    list_filter = ('is_active', 'rating', 'created_at')
    search_fields = ('name', 'email', 'phone', 'address')
    readonly_fields = ('created_at', 'updated_at')
    
    def save_model(self, request, obj, form, change):
        """
        Сохраняет модель учреждения с транзакционной защитой.
        """
        from .provider_services import ProviderTransactionService
        
        try:
            if change:
                # Обновление существующего учреждения
                ProviderTransactionService.update_provider_settings(
                    provider_id=obj.id,
                    name=obj.name,
                    description=obj.description,
                    address=obj.address,
                    phone=obj.phone,
                    email=obj.email,
                    is_active=obj.is_active
                )
        except ValidationError as e:
            from django.contrib import messages
            messages.error(request, str(e))
            return
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f"Error saving provider: {str(e)}")
            return
        
        super().save_model(request, obj, form, change)
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'description', 'email', 'phone', 'website')
        }),
        (_('Location'), {
            'fields': ('address', 'latitude', 'longitude')
        }),
        (_('Settings'), {
            'fields': ('rating', 'is_active', 'available_category_levels')
        }),
        (_('Blocking Settings'), {
            'fields': ('exclude_from_blocking_checks', 'blocking_exclusion_reason'),
            'classes': ('collapse',),
            'description': _('Configure automatic blocking check exclusions.')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        """
        Оптимизированный запрос с предзагрузкой связанных данных.
        """
        return super().get_queryset(request).prefetch_related('available_category_levels')

    actions = ['plan_schedule_for_providers']

    def plan_schedule_for_providers(self, request, queryset):
        """
        Запускает автоматическое планирование расписания для выбранных учреждений.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        if queryset.count() > 1:
            self.message_user(
                request,
                _('Please select only one provider at a time for planning.'),
                level=messages.ERROR
            )
            return
        
        provider = queryset.first()
        
        # Проверяем готовность к планированию
        from scheduling.models import StaffingRequirement
        requirements_count = StaffingRequirement.objects.filter(
            provider=provider, is_active=True
        ).count()
        
        if requirements_count == 0:
            self.message_user(
                request,
                _('Provider "{}" has no staffing requirements configured.').format(provider.name),
                level=messages.ERROR
            )
            return
        
        # Перенаправляем на форму планирования
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(
            f'/admin/scheduling/staffingrequirement/plan-schedule/{provider.id}/'
        )
    plan_schedule_for_providers.short_description = _('Plan schedule for selected providers')

    def get_urls(self):
        """
        Добавляет кастомный URL для страницы экспорта расписания.
        """
        urls = super().get_urls()
        custom_urls = [
            path('provider-schedule-export/', self.admin_site.admin_view(self.provider_schedule_export_view), name='provider-schedule-export'),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        """
        Добавляет ссылку на отчет в контекст changelist.
        """
        if extra_context is None:
            extra_context = {}
        extra_context['provider_schedule_export_url'] = reverse('admin:provider-schedule-export')
        return super().changelist_view(request, extra_context=extra_context)

    def provider_schedule_export_view(self, request):
        """
        Кастомная страница-отчет для экспорта расписания провайдеров.
        """
        from django.db.models import Q
        if request.user.has_role('billing_manager'):
            # Менеджер по биллингу видит все активные провайдеры
            providers = Provider.objects.filter(is_active=True)
        else:
            providers = Provider.objects.all()
        employees = Employee.objects.filter(is_active=True).prefetch_related('providers', 'user')
        employees_for_template = []
        for emp in employees:
            provider_ids = list(emp.providers.values_list('id', flat=True))
            employees_for_template.append({
                'id': emp.id,
                'provider_ids': provider_ids,
                '__str__': str(emp),
            })
        if request.method == 'POST':
            provider_ids = request.POST.getlist('provider_ids')
            employee_ids = request.POST.getlist('employee_ids')
            if not employee_ids:
                employees_qs = Employee.objects.filter(providers__id__in=provider_ids).distinct()
            else:
                employees_qs = Employee.objects.filter(id__in=employee_ids)
            slots = EmployeeWorkSlot.objects.filter(employee__in=employees_qs).select_related('employee')
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = _("Schedule")
            ws.append([_("Employee"), _("Date"), _("Start Time"), _("End Time"), _("Slot Type"), _("Provider(s)")])
            for slot in slots:
                ws.append([
                    str(slot.employee),
                    slot.date.strftime('%Y-%m-%d'),
                    slot.start_time.strftime('%H:%M'),
                    slot.end_time.strftime('%H:%M'),
                    slot.get_slot_type_display(),
                    ", ".join([p.name for p in slot.employee.providers.all()]),
                ])
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename={_("ProviderScheduleExport")}.xlsx'
            wb.save(response)
            return response
        context = dict(
            self.admin_site.each_context(request),
            providers=providers,
            employees=employees_for_template,
        )
        return render(request, "admin/providers/provider_schedule_export.html", context)

    def export_schedule_excel(self, request, provider_id):
        provider = Provider.objects.get(id=provider_id)
        slots = EmployeeWorkSlot.objects.filter(employee__providers=provider).select_related('employee')
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = _("Schedule")
        ws.append([_("Employee"), _("Date"), _("Start Time"), _("End Time"), _("Slot Type"), _("Provider")])
        for slot in slots:
            ws.append([
                str(slot.employee),
                slot.date.strftime('%Y-%m-%d'),
                slot.start_time.strftime('%H:%M'),
                slot.end_time.strftime('%H:%M'),
                slot.get_slot_type_display(),
                str(provider),
            ])
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename={_("ProviderSchedule")}_{provider.id}.xlsx'
        wb.save(response)
        return response


class EmployeeAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для модели сотрудника.
    """
    list_display = [
        'id', 'user', 'position', 'is_active',
        'created_at'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = [
        'user__username', 'user__email',
        'position', 'bio'
    ]
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('user', 'position', 'bio', 'photo')
        }),
        (_('Services'), {
            'fields': ('services',)
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    filter_horizontal = ('services',)
    inlines = [ScheduleInline]
    actions = ['apply_schedule_pattern']

    def get_providers(self, obj):
        return ", ".join([provider.name for provider in obj.providers.all()])
    get_providers.short_description = _('Providers')

    def apply_schedule_pattern(self, request, queryset):
        """
        Кастомное действие для применения паттерна расписания к выбранным сотрудникам на указанный период.
        """
        if 'apply' in request.POST:
            form = ApplyPatternForm(request.POST)
            if form.is_valid():
                pattern = form.cleaned_data['pattern']
                date_from = form.cleaned_data['date_from']
                date_to = form.cleaned_data['date_to']
                days = {d.weekday: d for d in pattern.days.all()}
                created = 0
                skipped = 0
                for employee in queryset:
                    current = date_from
                    while current <= date_to:
                        weekday = current.weekday()
                        if weekday in days and not days[weekday].is_day_off:
                            # Проверка на пересечение слотов
                            exists = EmployeeWorkSlot.objects.filter(
                                employee=employee,
                                date=current,
                                start_time=days[weekday].start_time,
                                end_time=days[weekday].end_time,
                            ).exists()
                            if not exists:
                                EmployeeWorkSlot.objects.create(
                                    employee=employee,
                                    date=current,
                                    start_time=days[weekday].start_time,
                                    end_time=days[weekday].end_time,
                                    slot_type='work',
                                    comment=_('Pattern: {}').format(pattern.name)
                                )
                                created += 1
                            else:
                                skipped += 1
                        current += datetime.timedelta(days=1)
                self.message_user(request, _('Created {} work slots, skipped {} due to overlap.').format(created, skipped))
                return redirect(request.get_full_path())
        else:
            form = ApplyPatternForm()
        return render(request, 'admin/apply_pattern.html', context={'form': form, 'employees': queryset})
    apply_schedule_pattern.short_description = _('Apply schedule pattern to selected employees')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('apply-pattern/', self.admin_site.admin_view(self.apply_schedule_pattern), name='apply-pattern'),
        ]
        return custom_urls + urls


class ScheduleAdmin(admin.ModelAdmin):
    list_display = ('employee', 'get_provider', 'day_of_week', 'start_time', 'end_time', 'is_working')
    list_filter = ('day_of_week', 'is_working', 'employee__providers')
    search_fields = ('employee__user__first_name', 'employee__user__last_name')
    ordering = ('employee', 'day_of_week')
    
    def save_model(self, request, obj, form, change):
        """
        Сохраняет модель расписания с транзакционной защитой.
        """
        from .services import ScheduleTransactionService
        
        try:
            # Получаем учреждение сотрудника
            provider = obj.employee.providers.first()
            if not provider:
                from django.contrib import messages
                messages.error(request, "Employee is not assigned to any provider")
                return
            
            if change:
                # Обновление существующего расписания
                ScheduleTransactionService.update_employee_schedule(
                    employee=obj.employee,
                    provider=provider,
                    target_date=obj.date,
                    start_time=obj.start_time,
                    end_time=obj.end_time,
                    is_available=obj.is_working
                )
            else:
                # Создание нового расписания
                ScheduleTransactionService.update_employee_schedule(
                    employee=obj.employee,
                    provider=provider,
                    target_date=obj.date,
                    start_time=obj.start_time,
                    end_time=obj.end_time,
                    is_available=obj.is_working
                )
        except ValidationError as e:
            from django.contrib import messages
            messages.error(request, str(e))
            return
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f"Error saving schedule: {str(e)}")
            return
        
        super().save_model(request, obj, form, change)

    def get_provider(self, obj):
        return ", ".join([provider.name for provider in obj.employee.providers.all()])
    get_provider.short_description = _('Providers')


@admin.register(ProviderService)
class ProviderServiceAdmin(admin.ModelAdmin):
    list_display = ['provider', 'service', 'duration_minutes', 'tech_break_minutes', 'base_price', 'price', 'is_active']
    list_filter = ['is_active', 'provider', 'service']
    search_fields = ['provider__name', 'service__name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('provider', 'service', 'is_active')
        }),
        ('Время и стоимость', {
            'fields': ('duration_minutes', 'tech_break_minutes', 'base_price', 'price')
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('provider', 'service')
    
    def save_model(self, request, obj, form, change):
        # Автоматически устанавливаем базовую цену равной цене, если она не указана
        if not obj.base_price:
            obj.base_price = obj.price
        
        # Автоматически устанавливаем длительность услуги, если не указана
        if not obj.duration_minutes:
            obj.duration_minutes = 60  # По умолчанию 1 час
        
        super().save_model(request, obj, form, change)


@admin.register(SchedulePattern)
class SchedulePatternAdmin(admin.ModelAdmin):
    inlines = [PatternDayInline]
    list_display = ('name', 'provider', 'created_at')
    search_fields = ('name', 'provider__name')
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'provider', 'description')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(PatternDay)
class PatternDayAdmin(admin.ModelAdmin):
    list_display = ('pattern', 'weekday', 'is_day_off')
    list_filter = ('pattern', 'weekday', 'is_day_off')
    search_fields = ('pattern__name',)
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('pattern', 'weekday', 'is_day_off')
        }),
        (_('Time'), {
            'fields': ('start_time', 'end_time')
        })
    )


@admin.register(EmployeeWorkSlot)
class EmployeeWorkSlotAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'start_time', 'end_time', 'slot_type', 'comment')
    list_filter = ('employee', 'date', 'slot_type')
    search_fields = ('employee__user__first_name', 'employee__user__last_name', 'comment')
    ordering = ('employee', 'date', 'start_time')
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('employee', 'date', 'start_time', 'end_time')
        }),
        (_('Details'), {
            'fields': ('slot_type', 'comment')
        })
    )


class ApplyPatternForm(forms.Form):
    pattern = forms.ModelChoiceField(queryset=SchedulePattern.objects.all(), label=_('Schedule pattern'))
    date_from = forms.DateField(label=_('Date from'))
    date_to = forms.DateField(label=_('Date to'))


custom_admin_site.register(Employee, EmployeeAdmin)
custom_admin_site.register(Schedule, ScheduleAdmin)
custom_admin_site.register(ProviderService, ProviderServiceAdmin)
custom_admin_site.register(SchedulePattern, SchedulePatternAdmin)
custom_admin_site.register(PatternDay, PatternDayAdmin)
custom_admin_site.register(EmployeeWorkSlot, EmployeeWorkSlotAdmin)
