"""
Admin configuration for the scheduling module.

Этот модуль содержит административные интерфейсы для системы автоматического планирования расписания.

Основные компоненты:
1. VacationAdmin - управление отпусками
2. SickLeaveAdmin - управление больничными
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
from .models import Vacation, SickLeave
from custom_admin import custom_admin_site





@admin.register(Vacation, site=custom_admin_site)
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
        'employee', 'provider_location', 'start_date', 'end_date', 'vacation_type', 
        'is_approved', 'approved_by', 'created_at'
    ]
    list_filter = [
        'employee__providers', 'provider_location', 'vacation_type', 'is_approved', 
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
            'fields': ('employee', 'provider_location', 'start_date', 'end_date', 'vacation_type')
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


@admin.register(SickLeave, site=custom_admin_site)
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
        'employee', 'provider_location', 'start_date', 'end_date', 'sick_leave_type', 
        'is_confirmed', 'confirmed_by', 'created_at'
    ]
    list_filter = [
        'employee__providers', 'provider_location', 'sick_leave_type', 'is_confirmed', 
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
            'fields': ('employee', 'provider_location', 'start_date', 'end_date', 'sick_leave_type')
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









