"""
Models for the scheduling module.

Этот модуль содержит модели для системы автоматического планирования расписания.

Основные компоненты:
1. Vacation - отпуска сотрудников
2. SickLeave - больничные листы
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from providers.models import Provider, Employee, ProviderLocation
from catalog.models import Service
from datetime import date, datetime, time





class Vacation(models.Model):
    """
    Модель отпуска сотрудника.
    
    Основные характеристики:
    - Связь с сотрудником
    - Период отпуска
    - Тип отпуска
    - Статус одобрения
    
    Технические особенности:
    - Планируется заранее, известна дата окончания
    - Управление статусом одобрения
    - Автоматическое отслеживание времени создания и обновления
    """
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='vacations',
        verbose_name=_('Employee'),
        help_text=_('Employee taking the vacation')
    )
    provider_location = models.ForeignKey(
        ProviderLocation,
        on_delete=models.CASCADE,
        related_name='vacations',
        null=True,
        blank=True,
        verbose_name=_('Provider Location'),
        help_text=_('Optional: specific location for this absence. If null, applies to all locations.')
    )
    start_date = models.DateField(
        _('Start Date'),
        help_text=_('Start date of the vacation')
    )
    end_date = models.DateField(
        _('End Date'),
        help_text=_('End date of the vacation')
    )
    vacation_type = models.CharField(
        _('Vacation Type'),
        max_length=50,
        choices=[
            ('annual', _('Annual Leave')),
            ('sick', _('Sick Leave')),
            ('maternity', _('Maternity Leave')),
            ('paternity', _('Paternity Leave')),
            ('unpaid', _('Unpaid Leave')),
            ('other', _('Other')),
        ],
        default='annual',
        help_text=_('Type of vacation')
    )
    is_approved = models.BooleanField(
        _('Is Approved'),
        default=False,
        help_text=_('Whether the vacation is approved')
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_vacations',
        verbose_name=_('Approved By'),
        help_text=_('User who approved the vacation')
    )
    approved_at = models.DateTimeField(
        _('Approved At'),
        null=True,
        blank=True,
        help_text=_('When the vacation was approved')
    )
    comment = models.TextField(
        _('Comment'),
        blank=True,
        help_text=_('Additional comment about the vacation')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Vacation')
        verbose_name_plural = _('Vacations')
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['employee']),
            models.Index(fields=['start_date']),
            models.Index(fields=['end_date']),
            models.Index(fields=['is_approved']),
            models.Index(fields=['vacation_type']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление отпуска.
        
        Returns:
            str: Сотрудник и период отпуска
        """
        return f"{self.employee} - {self.start_date} to {self.end_date}"

    def clean(self):
        """
        Валидация модели.
        
        Raises:
            ValidationError: Если дата окончания раньше даты начала
        """
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(_('End date cannot be earlier than start date'))

    def is_active(self):
        """
        Проверяет, активен ли отпуск в текущий момент.
        
        Returns:
            bool: True если отпуск активен, False в противном случае
        """
        today = date.today()
        return self.start_date <= today <= self.end_date


class SickLeave(models.Model):
    """
    Модель больничного листа сотрудника.
    
    Основные характеристики:
    - Связь с сотрудником
    - Период больничного
    - Тип больничного
    - Статус подтверждения
    
    Технические особенности:
    - Может быть экстренным, дата окончания может быть неизвестна
    - Управление статусом подтверждения
    - Автоматическое отслеживание времени создания и обновления
    """
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='sick_leaves',
        verbose_name=_('Employee'),
        help_text=_('Employee on sick leave')
    )
    provider_location = models.ForeignKey(
        ProviderLocation,
        on_delete=models.CASCADE,
        related_name='sick_leaves',
        null=True,
        blank=True,
        verbose_name=_('Provider Location'),
        help_text=_('Optional: specific location for this absence. If null, applies to all locations.')
    )
    start_date = models.DateField(
        _('Start Date'),
        help_text=_('Start date of the sick leave')
    )
    end_date = models.DateField(
        _('End Date'),
        null=True,
        blank=True,
        help_text=_('End date of the sick leave (may be unknown initially)')
    )
    sick_leave_type = models.CharField(
        _('Sick Leave Type'),
        max_length=50,
        choices=[
            ('illness', _('Illness')),
            ('injury', _('Injury')),
            ('pregnancy', _('Pregnancy Related')),
            ('other', _('Other')),
        ],
        default='illness',
        help_text=_('Type of sick leave')
    )
    is_confirmed = models.BooleanField(
        _('Is Confirmed'),
        default=False,
        help_text=_('Whether the sick leave is confirmed')
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_sick_leaves',
        verbose_name=_('Confirmed By'),
        help_text=_('User who confirmed the sick leave')
    )
    confirmed_at = models.DateTimeField(
        _('Confirmed At'),
        null=True,
        blank=True,
        help_text=_('When the sick leave was confirmed')
    )
    comment = models.TextField(
        _('Comment'),
        blank=True,
        help_text=_('Additional comment about the sick leave')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Sick Leave')
        verbose_name_plural = _('Sick Leaves')
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['employee']),
            models.Index(fields=['start_date']),
            models.Index(fields=['end_date']),
            models.Index(fields=['is_confirmed']),
            models.Index(fields=['sick_leave_type']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление больничного.
        
        Returns:
            str: Сотрудник и период больничного
        """
        end_str = f" to {self.end_date}" if self.end_date else " (ongoing)"
        return f"{self.employee} - {self.start_date}{end_str}"

    def clean(self):
        """
        Валидация модели.
        
        Raises:
            ValidationError: Если дата окончания раньше даты начала
        """
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(_('End date cannot be earlier than start date'))

    def is_active(self):
        """
        Проверяет, активен ли больничный в текущий момент.
        
        Returns:
            bool: True если больничный активен, False в противном случае
        """
        today = date.today()
        if self.end_date:
            return self.start_date <= today <= self.end_date
        else:
            return self.start_date <= today






 