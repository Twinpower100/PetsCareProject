"""
Models for the scheduling module.

Этот модуль содержит модели для системы автоматического планирования расписания.

Основные компоненты:
1. Workplace - рабочие места учреждений
2. WorkplaceAllowedServices - разрешенные одновременные услуги в рабочих местах
3. ServicePriority - приоритеты услуг для планирования
4. Vacation - отпуска сотрудников
5. SickLeave - больничные листы
6. DayOff - отгулы сотрудников
7. EmployeeSchedule - желаемое расписание работника
8. LocationSchedule - расписание локаций
9. StaffingRequirement - потребность в специалистах

Особенности реализации:
- Автоматическое планирование расписаний с учетом ограничений
- Управление отсутствиями сотрудников
- Приоритизация услуг при планировании
- Интеграция с существующими моделями Provider и Employee
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from providers.models import Provider, Employee
from catalog.models import Service
from datetime import date, datetime, time


class Workplace(models.Model):
    """
    Модель рабочего места учреждения.
    
    Основные характеристики:
    - Название и описание рабочего места
    - Связь с учреждением
    - Специализация рабочего места
    - Статус активности
    
    Технические особенности:
    - Абстрактный термин для кабинета, зала, студии и т.д.
    - Поддержка различных типов учреждений
    - Автоматическое отслеживание времени создания и обновления
    """
    name = models.CharField(
        _('Name'),
        max_length=200,
        help_text=_('Name of the workplace')
    )
    name_en = models.CharField(
        _('Name (English)'),
        max_length=200,
        blank=True,
        help_text=_('Name in English')
    )
    name_ru = models.CharField(
        _('Name (Russian)'),
        max_length=200,
        blank=True,
        help_text=_('Name in Russian')
    )
    name_me = models.CharField(
        _('Name (Montenegrian)'),
        max_length=200,
        blank=True,
        help_text=_('Name in Montenegrian')
    )
    name_de = models.CharField(
        _('Name (German)'),
        max_length=200,
        blank=True,
        help_text=_('Name in German')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of the workplace')
    )
    # ВРЕМЕННО: оставляем для обратной совместимости, будет удалено после миграции данных
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='workplaces',
        verbose_name=_('Provider (Legacy)'),
        null=True,
        blank=True,
        help_text=_('Legacy field - use provider_location instead')
    )
    provider_location = models.ForeignKey(
        'providers.ProviderLocation',
        on_delete=models.CASCADE,
        related_name='workplaces',
        verbose_name=_('Provider Location'),
        null=True,
        blank=True,
        help_text=_('Location this workplace belongs to')
    )
    workplace_type = models.CharField(
        _('Workplace Type'),
        max_length=100,
        choices=[
            ('office', _('Office')),
            ('room', _('Room')),
            ('hall', _('Hall')),
            ('studio', _('Studio')),
            ('area', _('Area')),
            ('other', _('Other')),
        ],
        default='room',
        help_text=_('Type of workplace')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this workplace is currently active')
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
        verbose_name = _('Workplace')
        verbose_name_plural = _('Workplaces')
        ordering = ['provider', 'name']
        indexes = [
            models.Index(fields=['provider']),
            models.Index(fields=['is_active']),
            models.Index(fields=['workplace_type']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление рабочего места.
        
        Returns:
            str: Название рабочего места и учреждения
        """
        provider = self.provider
        if not provider and self.provider_location:
            provider = self.provider_location.provider
        provider_name = provider.name if provider else _('Unknown Provider')
        return f"{self.get_localized_name()} ({provider_name})"
    
    def get_localized_name(self, language_code=None):
        """
        Получает локализованное название рабочего места.
        
        Args:
            language_code: Код языка (en, ru, me, de). Если None, используется текущий язык.
            
        Returns:
            str: Локализованное название
        """
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()
        
        if language_code == 'en' and self.name_en:
            return self.name_en
        elif language_code == 'ru' and self.name_ru:
            return self.name_ru
        elif language_code == 'me' and self.name_me:
            return self.name_me
        elif language_code == 'de' and self.name_de:
            return self.name_de
        else:
            return self.name

    def get_allowed_services(self):
        """
        Возвращает список разрешенных услуг для рабочего места.
        
        Returns:
            QuerySet: Список разрешенных услуг
        """
        return self.allowed_services.all()


class WorkplaceAllowedServices(models.Model):
    """
    Модель разрешенных одновременных услуг в рабочем месте.
    
    Основные характеристики:
    - Связь с рабочим местом
    - Список услуг, которые можно оказывать одновременно
    - Приоритет услуг в рабочем месте
    
    Технические особенности:
    - Уникальная связь по рабочему месту и услуге
    - Управление приоритетами услуг в конкретном рабочем месте
    - Автоматическое отслеживание времени создания и обновления
    """
    workplace = models.ForeignKey(
        Workplace,
        on_delete=models.CASCADE,
        related_name='allowed_services',
        verbose_name=_('Workplace'),
        help_text=_('Workplace where these services can be provided')
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        verbose_name=_('Service'),
        help_text=_('Service that can be provided in this workplace')
    )
    priority = models.PositiveIntegerField(
        _('Priority'),
        default=1,
        help_text=_('Priority of this service in this workplace (lower number = higher priority)')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this service is currently available in this workplace')
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
        verbose_name = _('Workplace Allowed Service')
        verbose_name_plural = _('Workplace Allowed Services')
        unique_together = ['workplace', 'service']
        ordering = ['workplace', 'priority', 'service']
        indexes = [
            models.Index(fields=['workplace']),
            models.Index(fields=['service']),
            models.Index(fields=['priority']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление разрешенной услуги.
        
        Returns:
            str: Название услуги и рабочего места
        """
        return f"{self.service.name} in {self.workplace.name}"

    def clean(self):
        """
        Валидация модели.
        
        Raises:
            ValidationError: Если приоритет меньше 1
        """
        if self.priority < 1:
            raise ValidationError(_('Priority must be at least 1'))


class ServicePriority(models.Model):
    """
    Модель приоритетов услуг для планирования.
    
    Основные характеристики:
    - Связь с учреждением и услугой
    - Приоритет услуги при планировании
    - Статус активности
    
    Технические особенности:
    - Уникальная связь по учреждению и услуге
    - Управление приоритетами для автоматического планирования
    - Автоматическое отслеживание времени создания и обновления
    """
    # ВРЕМЕННО: оставляем для обратной совместимости, будет удалено после миграции данных
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='service_priorities',
        verbose_name=_('Provider (Legacy)'),
        null=True,
        blank=True,
        help_text=_('Legacy field - use provider_location instead')
    )
    provider_location = models.ForeignKey(
        'providers.ProviderLocation',
        on_delete=models.CASCADE,
        related_name='service_priorities',
        verbose_name=_('Provider Location'),
        null=True,
        blank=True,
        help_text=_('Location this priority applies to')
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        verbose_name=_('Service'),
        help_text=_('Service this priority applies to')
    )
    priority = models.PositiveIntegerField(
        _('Priority'),
        default=1,
        help_text=_('Priority of this service for scheduling (lower number = higher priority)')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this priority is currently active')
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
        verbose_name = _('Service Priority')
        verbose_name_plural = _('Service Priorities')
        unique_together = [['provider_location', 'service'], ['provider', 'service']]  # ВРЕМЕННО: поддержка обоих полей
        ordering = ['provider', 'priority', 'service']
        indexes = [
            models.Index(fields=['provider']),
            models.Index(fields=['service']),
            models.Index(fields=['priority']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление приоритета услуги.
        
        Returns:
            str: Название услуги, учреждения и приоритет
        """
        provider = self.provider
        if not provider and self.provider_location:
            provider = self.provider_location.provider
        provider_name = provider.name if provider else _('Unknown Provider')
        return f"{self.service.name} at {provider_name} (Priority: {self.priority})"

    def clean(self):
        """
        Валидация модели.
        
        Raises:
            ValidationError: Если приоритет меньше 1
        """
        if self.priority < 1:
            raise ValidationError(_('Priority must be at least 1'))


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


class DayOff(models.Model):
    """
    Модель отгула сотрудника.
    
    Основные характеристики:
    - Связь с сотрудником
    - Дата отгула
    - Тип отгула
    - Статус одобрения
    
    Технические особенности:
    - Планируется заранее, известна дата
    - Управление статусом одобрения
    - Автоматическое отслеживание времени создания и обновления
    """
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='days_off',
        verbose_name=_('Employee'),
        help_text=_('Employee taking the day off')
    )
    date = models.DateField(
        _('Date'),
        help_text=_('Date of the day off')
    )
    day_off_type = models.CharField(
        _('Day Off Type'),
        max_length=50,
        choices=[
            ('personal', _('Personal Day')),
            ('compensation', _('Compensation Day')),
            ('holiday', _('Holiday')),
            ('other', _('Other')),
        ],
        default='personal',
        help_text=_('Type of day off')
    )
    is_approved = models.BooleanField(
        _('Is Approved'),
        default=False,
        help_text=_('Whether the day off is approved')
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_days_off',
        verbose_name=_('Approved By'),
        help_text=_('User who approved the day off')
    )
    approved_at = models.DateTimeField(
        _('Approved At'),
        null=True,
        blank=True,
        help_text=_('When the day off was approved')
    )
    comment = models.TextField(
        _('Comment'),
        blank=True,
        help_text=_('Additional comment about the day off')
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
        verbose_name = _('Day Off')
        verbose_name_plural = _('Days Off')
        ordering = ['-date']
        indexes = [
            models.Index(fields=['employee']),
            models.Index(fields=['date']),
            models.Index(fields=['is_approved']),
            models.Index(fields=['day_off_type']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление отгула.
        
        Returns:
            str: Сотрудник и дата отгула
        """
        return f"{self.employee} - {self.date}"

    def is_active(self):
        """
        Проверяет, активен ли отгул в текущий момент.
        
        Returns:
            bool: True если отгул активен, False в противном случае
        """
        return self.date == date.today()


class EmployeeSchedule(models.Model):
    """
    Модель желаемого расписания работника.
    
    Основные характеристики:
    - Связь с сотрудником
    - День недели
    - Желаемое время работы
    - Приоритет предпочтения
    
    Технические особенности:
    - Гибкие предпочтения (пожелания, не жесткие требования)
    - Уникальная связь по сотруднику и дню недели
    - Автоматическое отслеживание времени создания и обновления
    """
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='preferred_schedules',
        verbose_name=_('Employee'),
        help_text=_('Employee this schedule preference belongs to')
    )
    day_of_week = models.PositiveSmallIntegerField(
        _('Day Of Week'),
        choices=[
            (0, _('Monday')),
            (1, _('Tuesday')),
            (2, _('Wednesday')),
            (3, _('Thursday')),
            (4, _('Friday')),
            (5, _('Saturday')),
            (6, _('Sunday')),
        ],
        help_text=_('Day of the week')
    )
    preferred_start_time = models.TimeField(
        _('Preferred Start Time'),
        null=True,
        blank=True,
        help_text=_('Preferred start time for this day')
    )
    preferred_end_time = models.TimeField(
        _('Preferred End Time'),
        null=True,
        blank=True,
        help_text=_('Preferred end time for this day')
    )
    is_available = models.BooleanField(
        _('Is Available'),
        default=True,
        help_text=_('Whether the employee is available on this day')
    )
    priority = models.PositiveIntegerField(
        _('Priority'),
        default=1,
        help_text=_('Priority of this preference (lower number = higher priority)')
    )
    comment = models.TextField(
        _('Comment'),
        blank=True,
        help_text=_('Additional comment about this schedule preference')
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
        verbose_name = _('Employee Schedule Preference')
        verbose_name_plural = _('Employee Schedule Preferences')
        unique_together = ['employee', 'day_of_week']
        ordering = ['employee', 'day_of_week']
        indexes = [
            models.Index(fields=['employee']),
            models.Index(fields=['day_of_week']),
            models.Index(fields=['is_available']),
            models.Index(fields=['priority']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление предпочтения расписания.
        
        Returns:
            str: Сотрудник, день недели и доступность
        """
        day_name = self.get_day_of_week_display()
        if self.is_available:
            time_str = f" {self.preferred_start_time}-{self.preferred_end_time}" if self.preferred_start_time and self.preferred_end_time else ""
            return f"{self.employee} - {day_name}{time_str}"
        else:
            return f"{self.employee} - {day_name} (not available)"

    def clean(self):
        """
        Валидация модели.
        
        Raises:
            ValidationError: Если время окончания раньше времени начала
        """
        if (self.preferred_start_time and self.preferred_end_time and 
            self.preferred_start_time >= self.preferred_end_time):
            raise ValidationError(_('End time must be later than start time'))


class StaffingRequirement(models.Model):
    """
    Модель потребности в специалистах.
    
    Основные характеристики:
    - Связь с учреждением и услугой
    - День недели
    - Количество необходимых специалистов
    - Приоритет потребности
    
    Технические особенности:
    - Настройка потребности по дням недели
    - Уникальная связь по учреждению, услуге и дню недели
    - Автоматическое отслеживание времени создания и обновления
    """
    # ВРЕМЕННО: оставляем для обратной совместимости, будет удалено после миграции данных
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='staffing_requirements',
        verbose_name=_('Provider (Legacy)'),
        null=True,
        blank=True,
        help_text=_('Legacy field - use provider_location instead')
    )
    provider_location = models.ForeignKey(
        'providers.ProviderLocation',
        on_delete=models.CASCADE,
        related_name='staffing_requirements',
        verbose_name=_('Provider Location'),
        null=True,
        blank=True,
        help_text=_('Location this requirement applies to')
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        verbose_name=_('Service'),
        help_text=_('Service this requirement applies to')
    )
    day_of_week = models.PositiveSmallIntegerField(
        _('Day Of Week'),
        choices=[
            (0, _('Monday')),
            (1, _('Tuesday')),
            (2, _('Wednesday')),
            (3, _('Thursday')),
            (4, _('Friday')),
            (5, _('Saturday')),
            (6, _('Sunday')),
        ],
        help_text=_('Day of the week')
    )
    required_count = models.PositiveIntegerField(
        _('Required Count'),
        default=1,
        help_text=_('Number of specialists required for this service on this day')
    )
    priority = models.PositiveIntegerField(
        _('Priority'),
        default=1,
        help_text=_('Priority of this requirement (lower number = higher priority)')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this requirement is currently active')
    )
    comment = models.TextField(
        _('Comment'),
        blank=True,
        help_text=_('Additional comment about this requirement')
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
        verbose_name = _('Staffing Requirement')
        verbose_name_plural = _('Staffing Requirements')
        unique_together = [['provider_location', 'service', 'day_of_week'], ['provider', 'service', 'day_of_week']]  # ВРЕМЕННО: поддержка обоих полей
        ordering = ['provider', 'day_of_week', 'priority', 'service']
        indexes = [
            models.Index(fields=['provider']),
            models.Index(fields=['service']),
            models.Index(fields=['day_of_week']),
            models.Index(fields=['required_count']),
            models.Index(fields=['priority']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление потребности в специалистах.
        
        Returns:
            str: Учреждение, услуга, день недели и количество
        """
        day_name = self.get_day_of_week_display()
        return f"{self.provider} - {self.service.name} on {day_name} ({self.required_count} specialists)"

    def clean(self):
        """
        Валидация модели.
        
        Raises:
            ValidationError: Если количество специалистов меньше 1
        """
        if self.required_count < 1:
            raise ValidationError(_('Required count must be at least 1')) 