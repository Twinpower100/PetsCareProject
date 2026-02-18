from django.contrib import admin
from django.contrib.admin import widgets as admin_widgets
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .models import Provider, Employee, Schedule, SchedulePattern, PatternDay, EmployeeWorkSlot, EmployeeJoinRequest, EmployeeProvider, LocationSchedule, HolidayShift, ManagerTransferInvite, ProviderOwnerManagerInvite, ProviderLocation, ProviderLocationService, EmployeeLocationService
from django import forms
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
import datetime
import openpyxl
from django.http import HttpResponse
from custom_admin import custom_admin_site


def _is_system_admin(user):
    """
    Безопасная проверка, является ли пользователь системным администратором.
    Работает с AnonymousUser и реальными пользователями.
    """
    from django.contrib.auth.models import AnonymousUser
    if isinstance(user, AnonymousUser):
        return False
    if not hasattr(user, 'is_system_admin'):
        return False
    try:
        return user.is_system_admin()
    except (AttributeError, TypeError):
        return False


class ViewOnlyRelatedFieldWidgetWrapper(admin_widgets.RelatedFieldWidgetWrapper):
    """
    Обёртка для FK: ссылка «Просмотреть» добавляет ?_view=1, чтобы форма Address
    открывалась в режиме только просмотра (без кнопок Сохранить/Удалить).
    """

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if context.get('can_view_related') and 'view_related_url_params' in context:
            context['view_related_url_params'] = (
                context['view_related_url_params'].rstrip('&') + '&_view=1'
            )
        return context


def _has_role(user, role_name):
    """
    Безопасная проверка роли пользователя.
    Работает с AnonymousUser и реальными пользователями.
    """
    from django.contrib.auth.models import AnonymousUser
    if isinstance(user, AnonymousUser):
        return False
    if not hasattr(user, 'has_role'):
        return False
    try:
        return user.has_role(role_name)
    except (AttributeError, TypeError):
        return False


class EmployeeInline(admin.TabularInline):
    model = Employee.providers.through
    extra = 0
    verbose_name = _('Employee')
    verbose_name_plural = _('Employees')


class ProviderLocationInline(admin.TabularInline):
    """
    Инлайн для локаций организации.
    """
    model = ProviderLocation
    extra = 0
    fields = ('name', 'structured_address', 'phone_number', 'email', 'is_active')
    verbose_name = _('Location')
    verbose_name_plural = _('Locations')


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


class ProviderAdmin(admin.ModelAdmin):
    """
    Админка для провайдеров. Стандартный список + отдельная страница-отчет для экспорта расписания.
    - Стандартный changelist
    - Кнопка для перехода на страницу экспорта расписания
    - Отдельный URL для отчета
    """
    list_display = ('name', 'email', 'phone_number', 'get_address', 'activation_status', 'is_active', 'get_application_categories', 'created_at')
    list_filter = ('activation_status', 'is_active', 'created_at', 'vat_verification_status')
    search_fields = ('name', 'email', 'phone_number', 'tax_id', 'registration_number', 'vat_number')
    readonly_fields = ('created_at', 'updated_at', 'get_application_categories', 'get_address', 'vat_verification_status_display', 'vat_verification_result_display', 'vat_verification_date', 'vat_verification_manual_by', 'vat_verification_manual_at')
    filter_horizontal = ('available_category_levels',)
    actions = ['check_vat_id_selected']
    
    def get_form(self, request, obj=None, **kwargs):
        """Ограничивает доступные категории - всегда только категории уровня 0"""
        from catalog.models import Service
        
        form = super().get_form(request, obj, **kwargs)
        
        # По умолчанию для всех пользователей показываем только категории уровня 0
        if 'available_category_levels' in form.base_fields:
            # Базовый queryset - только категории уровня 0
            base_queryset = Service.objects.filter(
                level=0,
                parent__isnull=True
            ).order_by('hierarchy_order', 'name')
            
            # Для провайдер-админа ограничиваем категориями из их заявки
            if _has_role(request.user, 'provider_admin'):
                managed_providers = request.user.get_managed_providers()
                if managed_providers.exists() and obj in managed_providers:
                    from users.models import ProviderForm
                    try:
                        # Находим заявку провайдера
                        provider_form = ProviderForm.objects.filter(
                            provider_name=obj.name,
                            status='approved'
                        ).first()
                        
                        if provider_form and provider_form.selected_categories.exists():
                            # Получаем только категории уровня 0 из заявки
                            approved_categories = provider_form.selected_categories.filter(
                                level=0,
                                parent__isnull=True
                            )
                            category_ids = approved_categories.values_list('id', flat=True)
                            base_queryset = base_queryset.filter(id__in=category_ids)
                            
                            form.base_fields['available_category_levels'].queryset = base_queryset
                            form.base_fields['available_category_levels'].help_text = _(
                                'Select service categories (level 0) from your approved application. '
                                'To add new categories, contact the billing manager or system administrator.'
                            )
                        else:
                            # Если заявка не найдена, скрываем поле
                            form.base_fields['available_category_levels'].widget = forms.HiddenInput()
                    except Exception:
                        # Если ошибка, скрываем поле
                        form.base_fields['available_category_levels'].widget = forms.HiddenInput()
                else:
                    # Провайдер-админ не может редактировать чужие провайдеры
                    form.base_fields['available_category_levels'].widget = forms.HiddenInput()
            else:
                # Для системного админа, биллинг-менеджера и остальных - все категории уровня 0
                form.base_fields['available_category_levels'].queryset = base_queryset
                if request.user.is_superuser or _is_system_admin(request.user):
                    form.base_fields['available_category_levels'].help_text = _(
                        'System administrator can add any service categories (level 0) to the provider.'
                    )
                elif _has_role(request.user, 'billing_manager'):
                    form.base_fields['available_category_levels'].help_text = _(
                        'Billing manager can add service categories (level 0) to the provider upon request.'
                    )
        
        # Ограничиваем доступные статусы в зависимости от роли
        if 'activation_status' in form.base_fields:
            if _has_role(request.user, 'billing_manager'):
                # Биллинг-менеджер может: pending -> activation_required или rejected
                # Может вернуть: activation_required -> pending
                # Может вернуть: rejected -> pending (через изменение статуса)
                if obj and obj.activation_status:
                    current_status = obj.activation_status
                    if current_status == 'pending':
                        # Из pending можно перейти в activation_required или rejected
                        form.base_fields['activation_status'].choices = [
                            ('pending', _('Pending')),
                            ('activation_required', _('Activation Required')),
                            ('rejected', _('Rejected')),
                        ]
                    elif current_status == 'activation_required':
                        # Из activation_required можно вернуться в pending или оставить
                        form.base_fields['activation_status'].choices = [
                            ('pending', _('Pending')),
                            ('activation_required', _('Activation Required')),
                        ]
                    elif current_status == 'rejected':
                        # Из rejected можно вернуться в pending
                        form.base_fields['activation_status'].choices = [
                            ('pending', _('Pending')),
                            ('rejected', _('Rejected')),
                        ]
                    else:
                        # Для других статусов биллинг-менеджер не может изменять
                        form.base_fields['activation_status'].widget = forms.HiddenInput()
                else:
                    # Новый провайдер - только pending
                    form.base_fields['activation_status'].choices = [
                        ('pending', _('Pending')),
                    ]
            elif request.user.is_superuser or _is_system_admin(request.user):
                # Системный админ может все статусы
                pass  # Все статусы доступны
            else:
                # Остальные не могут изменять статус
                if 'activation_status' in form.base_fields:
                    form.base_fields['activation_status'].widget = forms.HiddenInput()
        
        return form
    
    def get_readonly_fields(self, request, obj=None):
        """
        Определяет readonly поля в зависимости от роли пользователя.
        """
        readonly = list(self.readonly_fields)
        
        # Биллинг-менеджер не может изменять is_active и настройки блокировки
        if _has_role(request.user, 'billing_manager'):
            if 'is_active' not in readonly:
                readonly.append('is_active')
            if 'exclude_from_blocking_checks' not in readonly:
                readonly.append('exclude_from_blocking_checks')
            if 'blocking_exclusion_reason' not in readonly:
                readonly.append('blocking_exclusion_reason')
        
        return readonly
    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """
        Добавляет кнопку проверки VAT ID в контекст формы редактирования.
        """
        extra_context = extra_context or {}
        
        if object_id:
            try:
                provider = Provider.objects.get(pk=object_id)
                # Добавляем ссылку на VIES сайт
                if provider.vat_number and provider.country:
                    vies_url = f"https://ec.europa.eu/taxation_customs/vies/?locale=en#/vat-validation"
                    extra_context['vies_url'] = vies_url
                    extra_context['vat_number'] = provider.vat_number
                    extra_context['check_vat_id_url'] = reverse('admin:providers_provider_check_vat_id', args=[object_id])
            except Provider.DoesNotExist:
                pass
        
        return super().changeform_view(request, object_id, form_url, extra_context)
    
    def save_model(self, request, obj, form, change):
        """
        Сохраняет модель учреждения с транзакционной защитой и валидацией реквизитов.
        Валидирует переходы статусов в зависимости от роли пользователя.
        """
        from .provider_services import ProviderTransactionService
        from django.contrib import messages
        
        # Валидация переходов статусов в зависимости от роли
        if change and obj:
            # Получаем старый статус из базы данных перед изменением
            from .models import Provider
            old_provider = Provider.objects.get(pk=obj.pk)
            old_status = old_provider.activation_status
            new_status = form.cleaned_data.get('activation_status', obj.activation_status)
            
            if old_status != new_status:
                # Проверяем права на изменение статуса
                if _has_role(request.user, 'billing_manager'):
                    # Биллинг-менеджер может переводить только в определенные статусы
                    allowed_transitions = {
                        'pending': ['activation_required', 'rejected'],
                        'activation_required': ['pending'],
                        'rejected': ['pending'],
                    }
                    if old_status not in allowed_transitions or new_status not in allowed_transitions.get(old_status, []):
                        messages.error(request, _('Billing manager cannot change status from "%(old)s" to "%(new)s".') % {
                            'old': obj.get_activation_status_display(),
                            'new': dict(obj.ACTIVATION_STATUS_CHOICES).get(new_status, new_status)
                        })
                        return
                
                elif request.user.is_superuser or _is_system_admin(request.user):
                    # Системный админ может переводить в любые статусы
                    # Но проверяем логику: из activation_required можно в active или rejected
                    # Из active можно в inactive или rejected
                    # Из rejected можно в activation_required
                    # Из inactive можно в active
                    pass  # Админ может все
                else:
                    # Остальные не могут изменять статус
                    messages.error(request, _('You do not have permission to change activation status.'))
                    return
        
        # Валидация реквизитов перед сохранением
        try:
            obj.full_clean()
        except ValidationError as e:
            messages.error(request, _('Validation error: %(error)s') % {'error': str(e)})
            return
        
        try:
            if change:
                # Обновление существующего учреждения
                ProviderTransactionService.update_provider_settings(
                    provider_id=obj.id,
                    name=obj.name,
                    phone=obj.phone_number,
                    email=obj.email,
                    is_active=obj.is_active
                )
        except ValidationError as e:
            messages.error(request, str(e))
            return
        except Exception as e:
            messages.error(request, f"Error saving provider: {str(e)}")
            return
        
        super().save_model(request, obj, form, change)
    
    def get_point(self, obj):
        """Возвращает координаты точки из структурированного адреса."""
        if obj.structured_address and obj.structured_address.point:
            return f"Point({obj.structured_address.longitude}, {obj.structured_address.latitude})"
        return _('No coordinates')
    get_point.short_description = _('Point')
    
    def get_latitude(self, obj):
        """Возвращает широту из структурированного адреса."""
        if obj.structured_address and obj.structured_address.latitude:
            return str(obj.structured_address.latitude)
        return _('No latitude')
    get_latitude.short_description = _('Latitude')
    
    def get_longitude(self, obj):
        """Возвращает долготу из структурированного адреса."""
        if obj.structured_address and obj.structured_address.longitude:
            return str(obj.structured_address.longitude)
        return _('No longitude')
    get_longitude.short_description = _('Longitude')
    
    def get_address(self, obj):
        """Возвращает адрес организации из структурированного адреса."""
        if obj.structured_address:
            return obj.structured_address.formatted_address or str(obj.structured_address)
        return _('No address')
    get_address.short_description = _('Address')
    
    def get_application_categories(self, obj):
        """Возвращает категории, выбранные в заявке провайдера"""
        from users.models import ProviderForm
        try:
            provider_form = ProviderForm.objects.filter(
                provider_name=obj.name,
                status='approved'
            ).first()
            
            if provider_form and provider_form.selected_categories.exists():
                return ', '.join([cat.name for cat in provider_form.selected_categories.all()])
            return _('No application found')
        except Exception:
            return _('Error loading categories')
    get_application_categories.short_description = _('Application Categories')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'email', 'phone_number', 'website', 'logo')
        }),
        (_('Legal Address'), {
            'fields': ('structured_address',),
            'description': _('Legal address of the organization (for documents, contracts)')
        }),
        (_('Organization Details'), {
            'fields': ('tax_id', 'registration_number', 'country', 'organization_type', 'director_name'),
            'description': _('Required for approval (filled by billing managers)')
        }),
        (_('VAT Information'), {
            'fields': ('is_vat_payer', 'vat_number', 'vat_verification_status_display', 'vat_verification_result_display', 'vat_verification_date', 'vat_verification_manual_override', 'vat_verification_manual_comment', 'vat_verification_manual_by', 'vat_verification_manual_at'),
            'description': _('VAT payer status and VAT ID verification. Use "Check VAT ID" button to verify via VIES API.')
        }),
        (_('Financial Details'), {
            'fields': ('invoice_currency', 'iban', 'swift_bic', 'bank_name', 'kpp'),
            'description': _('Financial information for invoicing')
        }),
        (_('Activation Status'), {
            'fields': ('activation_status', 'is_active'),
            'description': _('Provider activation status. Billing manager can set to "activation_required" or "rejected". System admin can activate or reject.')
        }),
        (_('Settings'), {
            'fields': ('available_category_levels',),
            'classes': ('collapse',)
        }),
        (_('Application Information'), {
            'fields': ('get_application_categories',),
            'description': _('Categories selected in the original application'),
            'classes': ('collapse',)
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
        queryset = super().get_queryset(request).prefetch_related('available_category_levels').select_related('structured_address')
        
        # Биллинг-менеджер видит только назначенных провайдеров через BillingManagerProvider
        if _has_role(request.user, 'billing_manager'):
            from billing.models import BillingManagerProvider
            # Получаем провайдеров, назначенных этому биллинг-менеджеру
            managed_providers = BillingManagerProvider.objects.filter(
                billing_manager=request.user,
                status__in=['active', 'vacation', 'temporary']
            ).values_list('provider_id', flat=True)
            return queryset.filter(id__in=managed_providers)
        
        # Провайдер-админ видит только свои провайдеры
        if _has_role(request.user, 'provider_admin'):
            managed_providers = request.user.get_managed_providers()
            return queryset.filter(id__in=managed_providers.values_list('id', flat=True))
        
        return queryset
    
    def has_view_permission(self, request, obj=None):
        """
        Проверяет права на просмотр провайдера.
        """
        if request.user.is_superuser or _is_system_admin(request.user):
            return True
        
        if _has_role(request.user, 'billing_manager'):
            return True
        
        if _has_role(request.user, 'provider_admin'):
            if obj is None:
                return True
            managed_providers = request.user.get_managed_providers()
            return obj in managed_providers
        
        return False
    
    def has_add_permission(self, request):
        """
        Проверяет права на добавление провайдера.
        Только системные админы могут добавлять провайдеров вручную.
        """
        return request.user.is_superuser or _is_system_admin(request.user)
    
    def has_change_permission(self, request, obj=None):
        """
        Проверяет права на изменение провайдера.
        Биллинг-менеджер может изменять реквизиты (ИНН, регистрационный номер).
        Провайдер-админ может изменять только свои провайдеры (ограниченные поля).
        """
        if request.user.is_superuser or _is_system_admin(request.user):
            return True
        
        if _has_role(request.user, 'billing_manager'):
            return True
        
        if _has_role(request.user, 'provider_admin'):
            if obj is None:
                return True
            managed_providers = request.user.get_managed_providers()
            return obj in managed_providers
        
        return False
    
    def has_delete_permission(self, request, obj=None):
        """
        Проверяет права на удаление провайдера.
        Только системные админы могут удалять провайдеров.
        """
        return request.user.is_superuser or _is_system_admin(request.user)
    
    def delete_model(self, request, obj):
        """
        Удаляет провайдера и все связанные объекты.
        Обходит проверку прав на удаление BillingManagerEvent для каскадного удаления.
        """
        from django.db import transaction
        from billing.models import BillingManagerEvent
        
        with transaction.atomic():
            # Получаем все связанные BillingManagerProvider
            billing_manager_providers = obj.billing_managers.all()
            
            # Удаляем все связанные BillingManagerEvent напрямую через ORM
            # Это обходит проверку прав админки, так как удаление происходит каскадно
            for bmp in billing_manager_providers:
                BillingManagerEvent.objects.filter(billing_manager_provider=bmp).delete()
            
            # Удаляем сам провайдера (каскадно удалит BillingManagerProvider и другие связи)
            super().delete_model(request, obj)
    
    def delete_queryset(self, request, queryset):
        """
        Удаляет несколько провайдеров и все связанные объекты.
        Обходит проверку прав на удаление BillingManagerEvent для каскадного удаления.
        """
        from django.db import transaction
        from billing.models import BillingManagerEvent
        
        with transaction.atomic():
            # Получаем все связанные BillingManagerProvider для всех выбранных провайдеров
            provider_ids = list(queryset.values_list('id', flat=True))
            from billing.models import BillingManagerProvider
            billing_manager_providers = BillingManagerProvider.objects.filter(provider_id__in=provider_ids)
            
            # Удаляем все связанные BillingManagerEvent напрямую через ORM
            for bmp in billing_manager_providers:
                BillingManagerEvent.objects.filter(billing_manager_provider=bmp).delete()
            
            # Удаляем провайдеров (каскадно удалит BillingManagerProvider и другие связи)
            super().delete_queryset(request, queryset)
    
    def has_module_permission(self, request):
        """
        Проверяет права на просмотр модуля провайдеров в индексе админки.
        """
        if request.user.is_superuser or _is_system_admin(request.user):
            return True
        
        if _has_role(request.user, 'billing_manager'):
            return True
        
        if _has_role(request.user, 'provider_admin'):
            return True
        
        return False


    def get_urls(self):
        """
        Добавляет кастомные URL для страницы экспорта расписания и проверки VAT ID.
        """
        urls = super().get_urls()
        custom_urls = [
            path('provider-schedule-export/', self.admin_site.admin_view(self.provider_schedule_export_view), name='provider-schedule-export'),
            path('<path:object_id>/check-vat-id/', self.admin_site.admin_view(self.check_vat_id_view), name='providers_provider_check_vat_id'),
        ]
        return custom_urls + urls
    
    def check_vat_id_view(self, request, object_id):
        """
        Проверяет VAT ID провайдера через VIES API.
        """
        from django.http import JsonResponse
        from django.contrib import messages
        
        try:
            provider = Provider.objects.get(pk=object_id)
        except Provider.DoesNotExist:
            return JsonResponse({'success': False, 'error': _('Provider not found')}, status=404)
        
        # Проверяем права доступа
        if _has_role(request.user, 'billing_manager'):
            # Биллинг-менеджер может проверять только своих провайдеров
            from billing.models import BillingManagerProvider
            if not BillingManagerProvider.objects.filter(
                billing_manager=request.user,
                provider=provider,
                status='active'
            ).exists():
                return JsonResponse({'success': False, 'error': _('Access denied')}, status=403)
        elif not (request.user.is_superuser or _is_system_admin(request.user)):
            return JsonResponse({'success': False, 'error': _('Access denied')}, status=403)
        
        # Выполняем проверку
        result = provider.check_vat_id_now(user=request.user)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # AJAX запрос - возвращаем JSON
            return JsonResponse(result)
        else:
            # Обычный запрос - редирект с сообщением
            if result['success']:
                messages.success(request, _('VAT ID is valid. Company: {company}').format(company=result.get('company_name', '')))
            elif result['status'] == 'invalid':
                messages.error(request, _('VAT ID not found in EU registry'))
            else:
                messages.warning(request, _('VIES API is unavailable. Please try again later or verify manually.'))
            
            from django.shortcuts import redirect
            return redirect('admin:providers_provider_change', object_id)
    
    def check_vat_id_selected(self, request, queryset):
        """
        Action для массовой проверки VAT ID выбранных провайдеров.
        """
        from django.contrib import messages
        
        checked = 0
        failed = 0
        errors = []
        
        for provider in queryset:
            if not provider.vat_number or not provider.country:
                failed += 1
                errors.append(_('{name}: VAT number or country is not specified').format(name=provider.name))
                continue
            
            result = provider.check_vat_id_now(user=request.user)
            if result['success']:
                checked += 1
            else:
                failed += 1
                errors.append(_('{name}: {error}').format(name=provider.name, error=result.get('message', '')))
        
        if checked > 0:
            messages.success(request, _('Successfully checked {count} VAT ID(s)').format(count=checked))
        if failed > 0:
            messages.warning(request, _('Failed to check {count} VAT ID(s)').format(count=failed))
            if len(errors) <= 10:
                for error in errors:
                    messages.error(request, error)
    
    check_vat_id_selected.short_description = _('Check VAT ID via VIES API')
    
    def vat_verification_status_display(self, obj):
        """Отображает статус проверки VAT ID с цветовой индикацией"""
        if not obj.vat_number:
            return '-'
        
        status_map = {
            'pending': ('⚠️', 'orange'),
            'valid': ('✅', 'green'),
            'invalid': ('❌', 'red'),
            'failed': ('⚠️', 'orange'),
        }
        
        icon, color = status_map.get(obj.vat_verification_status, ('❓', 'gray'))
        status_display = obj.get_vat_verification_status_display()
        
        if obj.vat_verification_manual_override:
            return f'{icon} {status_display} (✓ {_("Manually confirmed")})'
        return f'{icon} {status_display}'
    
    vat_verification_status_display.short_description = _('VAT Verification Status')
    
    def vat_verification_result_display(self, obj):
        """Отображает результат проверки VAT ID"""
        if not obj.vat_verification_result:
            return '-'
        
        result = obj.vat_verification_result
        if isinstance(result, dict):
            if result.get('company_name'):
                return f"{result.get('company_name')}\n{result.get('address', '')}"
            elif result.get('error'):
                return f"Error: {result.get('error')}"
        
        return str(result)
    
    vat_verification_result_display.short_description = _('VAT Verification Result')

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
        if _has_role(request.user, 'billing_manager'):
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
            response['Content-Disposition'] = f'attachment; filename={_("LocationScheduleExport")}.xlsx'
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
        response['Content-Disposition'] = f'attachment; filename={_("LocationSchedule")}_{provider.id}.xlsx'
        wb.save(response)
        return response


class EmployeeAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для модели сотрудника.
    """
    list_display = [
        'id', 'user', 'is_active',
        'created_at'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = [
        'user__username', 'user__email',
    ]
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('user',)
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
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


# ProviderServiceAdmin удален - используйте ProviderLocationServiceAdmin


@admin.register(SchedulePattern)
class SchedulePatternAdmin(admin.ModelAdmin):
    inlines = [PatternDayInline]
    list_display = ('name', 'get_provider_location', 'get_provider', 'created_at')
    list_filter = ('provider_location', 'created_at')
    search_fields = ('name', 'provider_location__name', 'provider_location__provider__name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'provider_location', 'description')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_provider_location(self, obj):
        """Отображает название локации."""
        return obj.provider_location.name if obj.provider_location else '-'
    get_provider_location.short_description = _('Location')
    
    def get_provider(self, obj):
        """Отображает название организации."""
        return obj.provider_location.provider.name if obj.provider_location else '-'
    get_provider.short_description = _('Provider')
    
    def get_queryset(self, request):
        """Ограничивает queryset для provider_admin."""
        queryset = super().get_queryset(request).select_related('provider_location', 'provider_location__provider')
        
        if _has_role(request.user, 'provider_admin'):
            managed_providers = request.user.get_managed_providers()
            queryset = queryset.filter(provider_location__provider__in=managed_providers)
        
        return queryset
    
    def get_form(self, request, obj=None, **kwargs):
        """Ограничивает доступные локации для provider_admin."""
        form = super().get_form(request, obj, **kwargs)
        
        if _has_role(request.user, 'provider_admin'):
            managed_providers = request.user.get_managed_providers()
            if 'provider_location' in form.base_fields:
                form.base_fields['provider_location'].queryset = ProviderLocation.objects.filter(
                    provider__in=managed_providers
                )
                form.base_fields['provider_location'].help_text = _(
                    'You can only create schedule patterns for locations of your own organization.'
                )
        
        return form


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


class EmployeeJoinRequestAdmin(admin.ModelAdmin):
    """
    Админка для заявок на вступление в учреждение.
    """
    list_display = ('user', 'provider', 'position', 'status', 'created_at')
    list_filter = ('status', 'created_at', 'provider')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'provider__name', 'position')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('user', 'provider', 'position', 'comment')
        }),
        (_('Status'), {
            'fields': ('status',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


class EmployeeProviderAdmin(admin.ModelAdmin):
    """
    Админка для связей сотрудник-учреждение.
    """
    list_display = ('employee', 'provider', 'start_date', 'end_date', 'is_manager', 'is_confirmed')
    list_filter = ('is_manager', 'is_confirmed', 'start_date', 'end_date', 'provider')
    search_fields = ('employee__user__email', 'employee__user__first_name', 'employee__user__last_name', 'provider__name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('employee', 'provider', 'start_date', 'end_date')
        }),
        (_('Status'), {
            'fields': ('is_manager', 'is_confirmed', 'confirmation_requested_at', 'confirmed_at')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


class LocationScheduleAdmin(admin.ModelAdmin):
    """
    Админка для расписания локаций.
    """
    list_display = ('provider_location', 'weekday', 'open_time', 'close_time', 'is_closed')
    list_filter = ('weekday', 'is_closed', 'provider_location__provider')
    search_fields = ('provider_location__name', 'provider_location__provider__name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('provider_location', 'weekday', 'is_closed')
        }),
        (_('Working Hours'), {
            'fields': ('open_time', 'close_time')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


class HolidayShiftAdmin(admin.ModelAdmin):
    """
    Админка смен в праздничные дни (работа в дату, объявленную праздником в глобальном календаре).
    """
    list_display = ('provider_location', 'date', 'start_time', 'end_time')
    list_filter = ('date', 'provider_location__provider')
    search_fields = ('provider_location__name',)
    date_hierarchy = 'date'
    ordering = ('-date', 'provider_location')


class ManagerTransferInviteAdmin(admin.ModelAdmin):
    """
    Админка для приглашений на передачу полномочий менеджера (старый поток: from_manager → to_employee).
    """
    list_display = ('from_manager', 'to_employee', 'provider', 'is_accepted', 'is_declined', 'created_at')
    list_filter = ('is_accepted', 'is_declined', 'created_at', 'provider')
    search_fields = ('from_manager__user__email', 'to_employee__user__email', 'provider__name')
    readonly_fields = ('created_at',)
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('from_manager', 'to_employee', 'provider')
        }),
        (_('Status'), {
            'fields': ('is_accepted', 'is_declined', 'accepted_at', 'declined_at')
        }),
        (_('Metadata'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )


class ProviderOwnerManagerInviteAdmin(admin.ModelAdmin):
    """
    Админка для приглашений владельца/менеджера по email (6-значный код).
    Создаются через API; после принятия инвайт удаляется.
    """
    list_display = ('provider', 'email', 'role', 'expires_at', 'created_at')
    list_filter = ('role', 'created_at', 'provider')
    search_fields = ('email', 'provider__name')
    readonly_fields = ('created_at', 'token', 'expires_at')
    ordering = ['-created_at']
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('provider', 'email', 'role')
        }),
        (_('Token'), {
            'fields': ('token', 'expires_at'),
            'description': _('6-digit code sent by email. Invite is deleted after accept.')
        }),
        (_('Metadata'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )


class ProviderLocationServiceInline(admin.TabularInline):
    """Инлайн записей услуги локации (услуга + тип животного + размер + цена/длительность)."""
    model = ProviderLocationService
    extra = 0
    fields = ('service', 'pet_type', 'size_code', 'price', 'duration_minutes', 'tech_break_minutes', 'is_active')
    verbose_name = _('Location Service')
    verbose_name_plural = _('Location Services')


class EmployeeLocationServiceInline(admin.TabularInline):
    """Услуги сотрудников в этой локации (кто какие услуги оказывает в филиале)."""
    model = EmployeeLocationService
    extra = 0
    fields = ('employee', 'service')
    verbose_name = _('Employee service at location')
    verbose_name_plural = _('Employee services at this location')
    autocomplete_fields = ('employee', 'service')


class ProviderLocationAdmin(admin.ModelAdmin):
    """
    Админка для локаций провайдера (точек предоставления услуг).
    
    Основные возможности:
    - Просмотр списка локаций
    - Создание и редактирование локаций
    - Управление услугами локации через инлайн
    - Фильтрация по провайдеру и статусу активности
    """
    list_display = ('name', 'provider', 'get_full_address_display', 'phone_number', 'email', 'get_manager_display', 'is_active', 'created_at')
    list_filter = ('is_active', 'provider', 'created_at')
    search_fields = ('name', 'provider__name', 'phone_number', 'email')
    readonly_fields = ('created_at', 'updated_at', 'get_full_address_display')
    filter_horizontal = ('served_pet_types',)
    inlines = [ProviderLocationServiceInline, EmployeeLocationServiceInline]
    actions = ['plan_schedule_for_locations']
    
    def plan_schedule_for_locations(self, request, queryset):
        """
        Запускает автоматическое планирование расписания для выбранных локаций.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные локации
        """
        if queryset.count() > 1:
            self.message_user(
                request,
                _('Please select only one location at a time for planning.'),
                level=messages.ERROR
            )
            return
        
        location = queryset.first()
        
        # Проверяем готовность к планированию
        from scheduling.models import StaffingRequirement
        requirements_count = StaffingRequirement.objects.filter(
            provider_location=location, is_active=True
        ).count()
        
        if requirements_count == 0:
            self.message_user(
                request,
                _('Location "{}" has no staffing requirements configured.').format(location.name),
                level=messages.ERROR
            )
            return
        
        # Перенаправляем на форму планирования для локации
        # Используем provider_id для совместимости с существующим URL
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(
            f'/admin/scheduling/staffingrequirement/plan-schedule/{location.provider.id}/?location_id={location.id}'
        )
    plan_schedule_for_locations.short_description = _('Plan schedule for selected locations')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('provider', 'name', 'is_active')
        }),
        (_('Address'), {
            'fields': ('structured_address', 'get_full_address_display'),
            'description': _('Address of the location (coordinates are in Structured Address)')
        }),
        (_('Contact Information'), {
            'fields': ('phone_number', 'email')
        }),
        (_('Served pet types'), {
            'fields': ('served_pet_types',),
            'description': _('Types of animals this branch serves. Required before adding services and prices. Also editable via provider admin (API).')
        }),
        (_('Location manager'), {
            'fields': ('manager',),
            'description': _('User responsible for this location (support/escalation). Set via API or invite flow.')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_full_address_display(self, obj):
        """
        Отображает полный адрес локации.
        """
        return obj.get_full_address() or _('No address')
    get_full_address_display.short_description = _('Full Address')
    
    def get_manager_display(self, obj):
        """
        Отображает менеджера локации (имя, email).
        """
        if not obj or not obj.manager_id:
            return _('No manager')
        u = obj.manager
        name = f'{u.first_name or ""} {u.last_name or ""}'.strip() or u.email
        return f'{name} ({u.email})'
    get_manager_display.short_description = _('Location manager')

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Для structured_address используем обёртку, чтобы «Просмотреть» открывал форму с _view=1."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if (
            db_field.name == 'structured_address'
            and formfield
            and isinstance(formfield.widget, admin_widgets.RelatedFieldWidgetWrapper)
        ):
            formfield.widget = ViewOnlyRelatedFieldWidgetWrapper(
                formfield.widget.widget,
                formfield.widget.rel,
                formfield.widget.admin_site,
                can_add_related=formfield.widget.can_add_related,
                can_change_related=formfield.widget.can_change_related,
                can_delete_related=formfield.widget.can_delete_related,
                can_view_related=formfield.widget.can_view_related,
            )
        return formfield

    def get_queryset(self, request):
        """
        Оптимизированный запрос с предзагрузкой связанных данных.
        """
        return super().get_queryset(request).select_related(
            'provider', 'structured_address', 'manager'
        ).prefetch_related('available_services')
    
    def get_form(self, request, obj=None, **kwargs):
        """
        Ограничивает доступные провайдеры для provider_admin.
        """
        form = super().get_form(request, obj, **kwargs)
        
        # Provider admin может создавать локации только для своей организации
        if _has_role(request.user, 'provider_admin'):
            managed_providers = request.user.get_managed_providers()
            if 'provider' in form.base_fields:
                form.base_fields['provider'].queryset = managed_providers
                form.base_fields['provider'].help_text = _(
                    'You can only create locations for your own organization.'
                )
        
        return form
    
    def save_model(self, request, obj, form, change):
        """
        Сохраняет модель локации с проверкой прав доступа.
        """
        # Проверяем права доступа для provider_admin
        if _has_role(request.user, 'provider_admin'):
            managed_providers = request.user.get_managed_providers()
            if obj.provider not in managed_providers:
                messages.error(request, _('You can only manage locations of your own organization.'))
                return
        
        super().save_model(request, obj, form, change)


class ProviderLocationServiceAdmin(admin.ModelAdmin):
    """
    Админка для записей услуг локаций (локация + услуга + тип животного + размер).
    """
    list_display = ('location', 'service', 'pet_type', 'size_code', 'price', 'duration_minutes', 'tech_break_minutes', 'is_active', 'created_at')
    list_filter = ('is_active', 'location', 'service', 'pet_type', 'size_code', 'created_at')
    search_fields = ('location__name', 'service__name', 'location__provider__name', 'pet_type__code')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('location', 'service', 'pet_type', 'size_code', 'is_active')
        }),
        (_('Pricing and Duration'), {
            'fields': ('price', 'duration_minutes', 'tech_break_minutes')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'location', 'location__provider', 'service', 'pet_type'
        )
    
    def get_form(self, request, obj=None, **kwargs):
        """
        Ограничивает доступные локации и услуги для provider_admin.
        """
        from catalog.models import Service
        
        form = super().get_form(request, obj, **kwargs)
        
        # Provider admin может управлять услугами только для локаций своей организации
        if _has_role(request.user, 'provider_admin'):
            managed_providers = request.user.get_managed_providers()
            
            if 'location' in form.base_fields:
                form.base_fields['location'].queryset = ProviderLocation.objects.filter(
                    provider__in=managed_providers
                )
                form.base_fields['location'].help_text = _(
                    'You can only manage services for locations of your own organization.'
                )
            
            if 'service' in form.base_fields:
                # Ограничиваем услуги только теми, которые доступны для организации
                if obj and obj.location:
                    provider = obj.location.provider
                    available_categories = provider.available_category_levels.filter(level=0, parent__isnull=True)
                    from django.db.models import Q
                    category_ids = available_categories.values_list('id', flat=True)
                    services_queryset = Service.objects.filter(
                        Q(id__in=category_ids) | Q(parent_id__in=category_ids)
                    ).order_by('hierarchy_order', 'name')
                    form.base_fields['service'].queryset = services_queryset
                elif not obj:
                    # При создании новой услуги - показываем все услуги
                    # (валидация произойдет при сохранении)
                    pass
        
        return form
    
    def save_model(self, request, obj, form, change):
        """
        Сохраняет модель услуги локации с проверкой прав доступа и валидацией.
        """
        # Проверяем права доступа для provider_admin
        if _has_role(request.user, 'provider_admin'):
            managed_providers = request.user.get_managed_providers()
            if obj.location.provider not in managed_providers:
                messages.error(request, _('You can only manage services for locations of your own organization.'))
                return
        
        # Валидация: услуга должна быть из категорий уровня 0 организации
        provider = obj.location.provider
        available_categories = provider.available_category_levels.filter(level=0, parent__isnull=True)
        from catalog.models import Service
        from django.db.models import Q
        category_ids = available_categories.values_list('id', flat=True)
        
        if not Service.objects.filter(
            Q(id=obj.service.id) & (
                Q(id__in=category_ids) | Q(parent_id__in=category_ids)
            )
        ).exists():
            messages.error(
                request,
                _('Service must be from provider\'s available category levels (level 0).')
            )
            return
        
        super().save_model(request, obj, form, change)


class ApplyPatternForm(forms.Form):
    pattern = forms.ModelChoiceField(queryset=SchedulePattern.objects.all(), label=_('Schedule pattern'))
    date_from = forms.DateField(label=_('Date from'))
    date_to = forms.DateField(label=_('Date to'))


custom_admin_site.register(Provider, ProviderAdmin)
custom_admin_site.register(Employee, EmployeeAdmin)
custom_admin_site.register(Schedule, ScheduleAdmin)
# ProviderService удален из админки - используйте ProviderLocationService
custom_admin_site.register(SchedulePattern, SchedulePatternAdmin)
custom_admin_site.register(PatternDay, PatternDayAdmin)
custom_admin_site.register(EmployeeWorkSlot, EmployeeWorkSlotAdmin)
custom_admin_site.register(EmployeeJoinRequest, EmployeeJoinRequestAdmin)
custom_admin_site.register(EmployeeProvider, EmployeeProviderAdmin)
custom_admin_site.register(LocationSchedule, LocationScheduleAdmin)
custom_admin_site.register(HolidayShift, HolidayShiftAdmin)
custom_admin_site.register(ManagerTransferInvite, ManagerTransferInviteAdmin)
custom_admin_site.register(ProviderOwnerManagerInvite, ProviderOwnerManagerInviteAdmin)
custom_admin_site.register(ProviderLocation, ProviderLocationAdmin)
custom_admin_site.register(ProviderLocationService, ProviderLocationServiceAdmin)


class EmployeeLocationServiceAdmin(admin.ModelAdmin):
    """Услуги сотрудника в локации (связь работник — филиал — услуга)."""
    list_display = ('employee', 'provider_location', 'service')
    list_filter = ('provider_location', 'provider_location__provider', 'service')
    search_fields = ('employee__user__email', 'employee__user__first_name', 'employee__user__last_name', 'provider_location__name', 'service__name')
    autocomplete_fields = ('employee', 'provider_location', 'service')
    ordering = ('provider_location', 'employee', 'service')


custom_admin_site.register(EmployeeLocationService, EmployeeLocationServiceAdmin)
