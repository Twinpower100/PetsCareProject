"""
Admin configuration for the scheduling module.

Этот модуль содержит административные интерфейсы для системы автоматического планирования расписания.

Основные компоненты:
1. WorkplaceAdmin - управление рабочими местами
2. WorkplaceAllowedServicesAdmin - управление разрешенными услугами
3. ServicePriorityAdmin - управление приоритетами услуг
4. VacationAdmin - управление отпусками
5. SickLeaveAdmin - управление больничными
6. DayOffAdmin - управление отгулами
7. EmployeeScheduleAdmin - управление предпочтениями расписания
8. StaffingRequirementAdmin - управление потребностями в специалистах

Особенности реализации:
- Фильтры по учреждениям и сотрудникам
- Поиск по названиям и описаниям
- Действия для массовых операций
- Интеграция с существующими админками
- Админские действия для автоматического планирования
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.shortcuts import render
from datetime import date, timedelta
from .models import (
    Workplace, WorkplaceAllowedServices, ServicePriority,
    Vacation, SickLeave, DayOff, EmployeeSchedule, StaffingRequirement
)
from .services import SchedulePlannerService


@admin.register(Workplace)
class WorkplaceAdmin(admin.ModelAdmin):
    """
    Административная панель для управления рабочими местами.
    
    Основные функции:
    - Просмотр и редактирование рабочих мест
    - Фильтрация по учреждениям и типам
    - Поиск по названию и описанию
    - Массовые операции
    """
    list_display = [
        'name', 'provider', 'workplace_type', 'is_active', 
        'created_at', 'updated_at'
    ]
    list_filter = [
        'provider', 'workplace_type', 'is_active', 
        'created_at', 'updated_at'
    ]
    search_fields = ['name', 'description', 'provider__name']
    list_editable = ['is_active']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['provider', 'name']
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'description', 'provider', 'workplace_type')
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """
        Возвращает QuerySet с оптимизированными запросами.
        
        Args:
            request: HTTP запрос
            
        Returns:
            QuerySet: Оптимизированный QuerySet
        """
        return super().get_queryset(request).select_related('provider')

    actions = ['activate_workplaces', 'deactivate_workplaces', 'plan_schedule_for_provider']

    def activate_workplaces(self, request, queryset):
        """
        Активирует выбранные рабочие места.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        updated = queryset.update(is_active=True)
        self.message_user(
            request, 
            _('{} workplace(s) have been activated successfully.').format(updated)
        )
    activate_workplaces.short_description = _('Activate selected workplaces')

    def deactivate_workplaces(self, request, queryset):
        """
        Деактивирует выбранные рабочие места.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        updated = queryset.update(is_active=False)
        self.message_user(
            request, 
            _('{} workplace(s) have been deactivated successfully.').format(updated)
        )
    deactivate_workplaces.short_description = _('Deactivate selected workplaces')

    def plan_schedule_for_provider(self, request, queryset):
        """
        Запускает автоматическое планирование расписания для учреждения.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        # Получаем уникальные учреждения из выбранных рабочих мест
        providers = queryset.values_list('provider', flat=True).distinct()
        
        if len(providers) > 1:
            self.message_user(
                request,
                _('Please select workplaces for only one provider at a time.'),
                level=messages.ERROR
            )
            return
        
        provider_id = providers[0]
        from providers.models import Provider
        provider = Provider.objects.get(id=provider_id)
        
        # Перенаправляем на форму планирования
        return HttpResponseRedirect(
            f'/admin/scheduling/staffingrequirement/plan-schedule/{provider_id}/'
        )
    plan_schedule_for_provider.short_description = _('Plan schedule for provider')


@admin.register(WorkplaceAllowedServices)
class WorkplaceAllowedServicesAdmin(admin.ModelAdmin):
    """
    Административная панель для управления разрешенными услугами в рабочих местах.
    
    Основные функции:
    - Просмотр и редактирование разрешенных услуг
    - Фильтрация по рабочим местам и услугам
    - Поиск по названиям
    - Массовые операции
    """
    list_display = [
        'workplace', 'service', 'priority', 'is_active', 
        'created_at', 'updated_at'
    ]
    list_filter = [
        'workplace__provider', 'workplace', 'service', 'is_active', 
        'created_at', 'updated_at'
    ]
    search_fields = [
        'workplace__name', 'service__name', 'workplace__provider__name'
    ]
    list_editable = ['priority', 'is_active']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['workplace', 'priority', 'service']
    
    fieldsets = (
        (_('Service Assignment'), {
            'fields': ('workplace', 'service', 'priority')
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """
        Возвращает QuerySet с оптимизированными запросами.
        
        Args:
            request: HTTP запрос
            
        Returns:
            QuerySet: Оптимизированный QuerySet
        """
        return super().get_queryset(request).select_related(
            'workplace', 'workplace__provider', 'service'
        )

    actions = ['activate_services', 'deactivate_services']

    def activate_services(self, request, queryset):
        """
        Активирует выбранные разрешенные услуги.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        updated = queryset.update(is_active=True)
        self.message_user(
            request, 
            _('{} service(s) have been activated successfully.').format(updated)
        )
    activate_services.short_description = _('Activate selected services')

    def deactivate_services(self, request, queryset):
        """
        Деактивирует выбранные разрешенные услуги.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        updated = queryset.update(is_active=False)
        self.message_user(
            request, 
            _('{} service(s) have been deactivated successfully.').format(updated)
        )
    deactivate_services.short_description = _('Deactivate selected services')


@admin.register(ServicePriority)
class ServicePriorityAdmin(admin.ModelAdmin):
    """
    Административная панель для управления приоритетами услуг.
    
    Основные функции:
    - Просмотр и редактирование приоритетов услуг
    - Фильтрация по учреждениям и услугам
    - Поиск по названиям
    - Массовые операции
    """
    list_display = [
        'provider', 'service', 'priority', 'is_active', 
        'created_at', 'updated_at'
    ]
    list_filter = [
        'provider', 'service', 'is_active', 
        'created_at', 'updated_at'
    ]
    search_fields = ['provider__name', 'service__name']
    list_editable = ['priority', 'is_active']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['provider', 'priority', 'service']
    
    fieldsets = (
        (_('Priority Assignment'), {
            'fields': ('provider', 'service', 'priority')
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """
        Возвращает QuerySet с оптимизированными запросами.
        
        Args:
            request: HTTP запрос
            
        Returns:
            QuerySet: Оптимизированный QuerySet
        """
        return super().get_queryset(request).select_related('provider', 'service')

    actions = ['activate_priorities', 'deactivate_priorities', 'plan_schedule_for_provider']

    def activate_priorities(self, request, queryset):
        """
        Активирует выбранные приоритеты услуг.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        updated = queryset.update(is_active=True)
        self.message_user(
            request, 
            _('{} priority(ies) have been activated successfully.').format(updated)
        )
    activate_priorities.short_description = _('Activate selected priorities')

    def deactivate_priorities(self, request, queryset):
        """
        Деактивирует выбранные приоритеты услуг.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        updated = queryset.update(is_active=False)
        self.message_user(
            request, 
            _('{} priority(ies) have been deactivated successfully.').format(updated)
        )
    deactivate_priorities.short_description = _('Deactivate selected priorities')

    def plan_schedule_for_provider(self, request, queryset):
        """
        Запускает автоматическое планирование расписания для учреждения.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        # Получаем уникальные учреждения из выбранных приоритетов
        providers = queryset.values_list('provider', flat=True).distinct()
        
        if len(providers) > 1:
            self.message_user(
                request,
                _('Please select priorities for only one provider at a time.'),
                level=messages.ERROR
            )
            return
        
        provider_id = providers[0]
        from providers.models import Provider
        provider = Provider.objects.get(id=provider_id)
        
        # Перенаправляем на форму планирования
        return HttpResponseRedirect(
            f'/admin/scheduling/staffingrequirement/plan-schedule/{provider_id}/'
        )
    plan_schedule_for_provider.short_description = _('Plan schedule for provider')


@admin.register(Vacation)
class VacationAdmin(admin.ModelAdmin):
    """
    Административная панель для управления отпусками сотрудников.
    
    Основные функции:
    - Просмотр и редактирование отпусков
    - Фильтрация по сотрудникам и типам
    - Поиск по сотрудникам
    - Массовые операции
    """
    list_display = [
        'employee', 'start_date', 'end_date', 'vacation_type', 
        'is_approved', 'approved_by', 'created_at'
    ]
    list_filter = [
        'employee__providers', 'vacation_type', 'is_approved', 
        'start_date', 'end_date', 'created_at'
    ]
    search_fields = [
        'employee__user__first_name', 'employee__user__last_name',
        'employee__user__email', 'comment'
    ]
    list_editable = ['is_approved']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-start_date']
    
    fieldsets = (
        (_('Vacation Information'), {
            'fields': ('employee', 'start_date', 'end_date', 'vacation_type')
        }),
        (_('Approval'), {
            'fields': ('is_approved', 'approved_by', 'approved_at')
        }),
        (_('Additional Information'), {
            'fields': ('comment',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """
        Возвращает QuerySet с оптимизированными запросами.
        
        Args:
            request: HTTP запрос
            
        Returns:
            QuerySet: Оптимизированный QuerySet
        """
        return super().get_queryset(request).select_related(
            'employee__user', 'approved_by'
        )

    def save_model(self, request, obj, form, change):
        """
        Сохраняет модель с автоматическим заполнением полей одобрения.
        
        Args:
            request: HTTP запрос
            obj: Объект для сохранения
            form: Форма
            change: Флаг изменения
        """
        if obj.is_approved and not obj.approved_by:
            obj.approved_by = request.user
        super().save_model(request, obj, form, change)

    actions = ['approve_vacations', 'reject_vacations']

    def approve_vacations(self, request, queryset):
        """
        Одобряет выбранные отпуска.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        from django.utils import timezone
        updated = queryset.update(
            is_approved=True, 
            approved_by=request.user,
            approved_at=timezone.now()
        )
        self.message_user(
            request, 
            _('{} vacation(s) have been approved successfully.').format(updated)
        )
    approve_vacations.short_description = _('Approve selected vacations')

    def reject_vacations(self, request, queryset):
        """
        Отклоняет выбранные отпуска.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        updated = queryset.update(is_approved=False)
        self.message_user(
            request, 
            _('{} vacation(s) have been rejected successfully.').format(updated)
        )
    reject_vacations.short_description = _('Reject selected vacations')


@admin.register(SickLeave)
class SickLeaveAdmin(admin.ModelAdmin):
    """
    Административная панель для управления больничными листами.
    
    Основные функции:
    - Просмотр и редактирование больничных
    - Фильтрация по сотрудникам и типам
    - Поиск по сотрудникам
    - Массовые операции
    """
    list_display = [
        'employee', 'start_date', 'end_date', 'sick_leave_type', 
        'is_confirmed', 'confirmed_by', 'created_at'
    ]
    list_filter = [
        'employee__providers', 'sick_leave_type', 'is_confirmed', 
        'start_date', 'end_date', 'created_at'
    ]
    search_fields = [
        'employee__user__first_name', 'employee__user__last_name',
        'employee__user__email', 'comment'
    ]
    list_editable = ['is_confirmed']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-start_date']
    
    fieldsets = (
        (_('Sick Leave Information'), {
            'fields': ('employee', 'start_date', 'end_date', 'sick_leave_type')
        }),
        (_('Confirmation'), {
            'fields': ('is_confirmed', 'confirmed_by', 'confirmed_at')
        }),
        (_('Additional Information'), {
            'fields': ('comment',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """
        Возвращает QuerySet с оптимизированными запросами.
        
        Args:
            request: HTTP запрос
            
        Returns:
            QuerySet: Оптимизированный QuerySet
        """
        return super().get_queryset(request).select_related(
            'employee__user', 'confirmed_by'
        )

    def save_model(self, request, obj, form, change):
        """
        Сохраняет модель с автоматическим заполнением полей подтверждения.
        
        Args:
            request: HTTP запрос
            obj: Объект для сохранения
            form: Форма
            change: Флаг изменения
        """
        if obj.is_confirmed and not obj.confirmed_by:
            obj.confirmed_by = request.user
        super().save_model(request, obj, form, change)

    actions = ['confirm_sick_leaves', 'unconfirm_sick_leaves']

    def confirm_sick_leaves(self, request, queryset):
        """
        Подтверждает выбранные больничные.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        from django.utils import timezone
        updated = queryset.update(
            is_confirmed=True, 
            confirmed_by=request.user,
            confirmed_at=timezone.now()
        )
        self.message_user(
            request, 
            _('{} sick leave(s) have been confirmed successfully.').format(updated)
        )
    confirm_sick_leaves.short_description = _('Confirm selected sick leaves')

    def unconfirm_sick_leaves(self, request, queryset):
        """
        Отменяет подтверждение выбранных больничных.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        updated = queryset.update(is_confirmed=False)
        self.message_user(
            request, 
            _('{} sick leave(s) have been unconfirmed successfully.').format(updated)
        )
    unconfirm_sick_leaves.short_description = _('Unconfirm selected sick leaves')


@admin.register(DayOff)
class DayOffAdmin(admin.ModelAdmin):
    """
    Административная панель для управления отгулами сотрудников.
    
    Основные функции:
    - Просмотр и редактирование отгулов
    - Фильтрация по сотрудникам и типам
    - Поиск по сотрудникам
    - Массовые операции
    """
    list_display = [
        'employee', 'date', 'day_off_type', 'is_approved', 
        'approved_by', 'created_at'
    ]
    list_filter = [
        'employee__providers', 'day_off_type', 'is_approved', 
        'date', 'created_at'
    ]
    search_fields = [
        'employee__user__first_name', 'employee__user__last_name',
        'employee__user__email', 'comment'
    ]
    list_editable = ['is_approved']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-date']
    
    fieldsets = (
        (_('Day Off Information'), {
            'fields': ('employee', 'date', 'day_off_type')
        }),
        (_('Approval'), {
            'fields': ('is_approved', 'approved_by', 'approved_at')
        }),
        (_('Additional Information'), {
            'fields': ('comment',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """
        Возвращает QuerySet с оптимизированными запросами.
        
        Args:
            request: HTTP запрос
            
        Returns:
            QuerySet: Оптимизированный QuerySet
        """
        return super().get_queryset(request).select_related(
            'employee__user', 'approved_by'
        )

    def save_model(self, request, obj, form, change):
        """
        Сохраняет модель с автоматическим заполнением полей одобрения.
        
        Args:
            request: HTTP запрос
            obj: Объект для сохранения
            form: Форма
            change: Флаг изменения
        """
        if obj.is_approved and not obj.approved_by:
            obj.approved_by = request.user
        super().save_model(request, obj, form, change)

    actions = ['approve_days_off', 'reject_days_off']

    def approve_days_off(self, request, queryset):
        """
        Одобряет выбранные отгулы.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        from django.utils import timezone
        updated = queryset.update(
            is_approved=True, 
            approved_by=request.user,
            approved_at=timezone.now()
        )
        self.message_user(
            request, 
            _('{} day(s) off have been approved successfully.').format(updated)
        )
    approve_days_off.short_description = _('Approve selected days off')

    def reject_days_off(self, request, queryset):
        """
        Отклоняет выбранные отгулы.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        updated = queryset.update(is_approved=False)
        self.message_user(
            request, 
            _('{} day(s) off have been rejected successfully.').format(updated)
        )
    reject_days_off.short_description = _('Reject selected days off')


@admin.register(EmployeeSchedule)
class EmployeeScheduleAdmin(admin.ModelAdmin):
    """
    Административная панель для управления предпочтениями расписания сотрудников.
    
    Основные функции:
    - Просмотр и редактирование предпочтений
    - Фильтрация по сотрудникам и дням недели
    - Поиск по сотрудникам
    - Массовые операции
    """
    list_display = [
        'employee', 'day_of_week', 'preferred_start_time', 
        'preferred_end_time', 'is_available', 'priority', 'created_at'
    ]
    list_filter = [
        'employee__providers', 'day_of_week', 'is_available', 
        'priority', 'created_at'
    ]
    search_fields = [
        'employee__user__first_name', 'employee__user__last_name',
        'employee__user__email', 'comment'
    ]
    list_editable = ['is_available', 'priority']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['employee', 'day_of_week']
    
    fieldsets = (
        (_('Schedule Preference'), {
            'fields': ('employee', 'day_of_week', 'preferred_start_time', 'preferred_end_time')
        }),
        (_('Availability'), {
            'fields': ('is_available', 'priority')
        }),
        (_('Additional Information'), {
            'fields': ('comment',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """
        Возвращает QuerySet с оптимизированными запросами.
        
        Args:
            request: HTTP запрос
            
        Returns:
            QuerySet: Оптимизированный QuerySet
        """
        return super().get_queryset(request).select_related('employee__user')

    actions = ['make_available', 'make_unavailable']

    def make_available(self, request, queryset):
        """
        Делает выбранные дни доступными.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        updated = queryset.update(is_available=True)
        self.message_user(
            request, 
            _('{} schedule preference(s) have been made available.').format(updated)
        )
    make_available.short_description = _('Make selected preferences available')

    def make_unavailable(self, request, queryset):
        """
        Делает выбранные дни недоступными.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        updated = queryset.update(is_available=False)
        self.message_user(
            request, 
            _('{} schedule preference(s) have been made unavailable.').format(updated)
        )
    make_unavailable.short_description = _('Make selected preferences unavailable')


@admin.register(StaffingRequirement)
class StaffingRequirementAdmin(admin.ModelAdmin):
    """
    Административная панель для управления потребностями в специалистах.
    
    Основные функции:
    - Просмотр и редактирование потребностей
    - Фильтрация по учреждениям и услугам
    - Поиск по названиям
    - Массовые операции
    - Автоматическое планирование расписания
    """
    list_display = [
        'provider', 'service', 'day_of_week', 'required_count', 
        'priority', 'is_active', 'created_at'
    ]
    list_filter = [
        'provider', 'service', 'day_of_week', 'is_active', 
        'priority', 'created_at'
    ]
    search_fields = ['provider__name', 'service__name', 'comment']
    list_editable = ['required_count', 'priority', 'is_active']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['provider', 'day_of_week', 'priority', 'service']
    
    fieldsets = (
        (_('Requirement Information'), {
            'fields': ('provider', 'service', 'day_of_week', 'required_count', 'priority')
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
        (_('Additional Information'), {
            'fields': ('comment',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """
        Возвращает QuerySet с оптимизированными запросами.
        
        Args:
            request: HTTP запрос
            
        Returns:
            QuerySet: Оптимизированный QuerySet
        """
        return super().get_queryset(request).select_related('provider', 'service')

    actions = ['activate_requirements', 'deactivate_requirements', 'plan_schedule_for_provider']

    def activate_requirements(self, request, queryset):
        """
        Активирует выбранные потребности.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        updated = queryset.update(is_active=True)
        self.message_user(
            request, 
            _('{} requirement(s) have been activated successfully.').format(updated)
        )
    activate_requirements.short_description = _('Activate selected requirements')

    def deactivate_requirements(self, request, queryset):
        """
        Деактивирует выбранные потребности.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        updated = queryset.update(is_active=False)
        self.message_user(
            request, 
            _('{} requirement(s) have been deactivated successfully.').format(updated)
        )
    deactivate_requirements.short_description = _('Deactivate selected requirements')

    def plan_schedule_for_provider(self, request, queryset):
        """
        Запускает автоматическое планирование расписания для учреждения.
        
        Args:
            request: HTTP запрос
            queryset: Выбранные объекты
        """
        # Получаем уникальные учреждения из выбранных требований
        providers = queryset.values_list('provider', flat=True).distinct()
        
        if len(providers) > 1:
            self.message_user(
                request,
                _('Please select requirements for only one provider at a time.'),
                level=messages.ERROR
            )
            return
        
        provider_id = providers[0]
        from providers.models import Provider
        provider = Provider.objects.get(id=provider_id)
        
        # Перенаправляем на форму планирования
        return HttpResponseRedirect(
            f'/admin/scheduling/staffingrequirement/plan-schedule/{provider_id}/'
        )
    plan_schedule_for_provider.short_description = _('Plan schedule for provider')

    def get_urls(self):
        """
        Добавляет кастомные URL для планирования расписания.
        
        Returns:
            List: Список URL паттернов
        """
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                'plan-schedule/<int:provider_id>/',
                self.admin_site.admin_view(self.plan_schedule_view),
                name='plan_schedule'
            ),
        ]
        return custom_urls + urls

    def plan_schedule_view(self, request, provider_id):
        """
        Отображает форму для планирования расписания.
        
        Args:
            request: HTTP запрос
            provider_id: ID учреждения
            
        Returns:
            HttpResponse: Ответ с формой планирования
        """
        from providers.models import Provider
        from django import forms
        
        try:
            provider = Provider.objects.get(id=provider_id)
        except Provider.DoesNotExist:
            self.message_user(request, _('Provider not found.'), level=messages.ERROR)
            return HttpResponseRedirect('/admin/scheduling/staffingrequirement/')
        
        class SchedulePlanningForm(forms.Form):
            """Форма для настройки планирования расписания."""
            start_date = forms.DateField(
                label=_('Start Date'),
                initial=date.today(),
                help_text=_('Start date for schedule planning')
            )
            end_date = forms.DateField(
                label=_('End Date'),
                initial=date.today() + timedelta(days=7),
                help_text=_('End date for schedule planning')
            )
            optimize_preferences = forms.BooleanField(
                label=_('Optimize for Employee Preferences'),
                initial=True,
                required=False,
                help_text=_('Try to satisfy employee schedule preferences')
            )
        
        if request.method == 'POST':
            form = SchedulePlanningForm(request.POST)
            if form.is_valid():
                # Запускаем планирование
                start_date = form.cleaned_data['start_date']
                end_date = form.cleaned_data['end_date']
                optimize_preferences = form.cleaned_data['optimize_preferences']
                
                try:
                    planner = SchedulePlannerService(provider)
                    result = planner.plan_schedule(start_date, end_date)
                    
                    # Отображаем результаты
                    context = {
                        'title': _('Schedule Planning Results for {}').format(provider.name),
                        'provider': provider,
                        'result': result,
                        'start_date': start_date,
                        'end_date': end_date,
                        'opts': self.model._meta,
                        'has_change_permission': True,
                    }
                    
                    return render(request, 'admin/scheduling/staffingrequirement/planning_results.html', context)
                    
                except Exception as e:
                    self.message_user(
                        request,
                        _('Error during schedule planning: {}').format(str(e)),
                        level=messages.ERROR
                    )
        else:
            form = SchedulePlanningForm()
        
        context = {
            'title': _('Plan Schedule for {}').format(provider.name),
            'provider': provider,
            'form': form,
            'opts': self.model._meta,
            'has_change_permission': True,
        }
        
        return render(request, 'admin/scheduling/staffingrequirement/planning_form.html', context)



