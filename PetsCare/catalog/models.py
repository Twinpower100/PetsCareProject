"""
Catalog models for the application.

Этот модуль содержит модели для:
1. Услуг
2. Управления периодичностью и напоминаниями
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator


class Service(models.Model):
    """
    Модель услуги/категории.
    
    Используется для создания иерархической структуры услуг.
    Если parent=None, то это категория верхнего уровня.
    Если parent указан, то это либо подкатегория, либо услуга.
    """
    code = models.CharField(
        _('Code'),
        max_length=50,
        unique=True,
        validators=[RegexValidator(
            regex=r'^[a-zA-Z0-9_]+$',
            message=_('Code must contain only Latin letters, numbers and underscores.')
        )],
        help_text=_('Unique technical code (Latin letters, numbers, underscores). Used for integrations and business logic.')
    )
    name = models.CharField(
        _('Name'),
        max_length=200,
        help_text=_('Name of the service or category')
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name=_('Parent'),
        help_text=_('Parent service or category in the hierarchy')
    )
    level = models.PositiveIntegerField(
        _('Level'),
        default=0,
        help_text=_('Level in the hierarchy')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of the service or category')
    )
    icon = models.CharField(
        _('Icon'),
        max_length=50,
        blank=True,
        help_text=_('Icon class or identifier')
    )
    
    # Поля для услуг (заполняются только для конечных услуг)
    is_mandatory = models.BooleanField(
        _('Is Mandatory'),
        default=False,
        help_text=_('Whether this service is mandatory for pets')
    )
    is_periodic = models.BooleanField(
        _('Is Periodic'),
        default=False,
        help_text=_('Whether this service needs to be repeated periodically')
    )
    period_days = models.PositiveIntegerField(
        _('Period In Days'),
        null=True,
        blank=True,
        help_text=_('Number of days between periodic procedures')
    )
    send_reminders = models.BooleanField(
        _('Send Reminders'),
        default=False,
        help_text=_('Whether to send reminders for this service')
    )
    reminder_days_before = models.PositiveIntegerField(
        _('Reminder Days Before'),
        null=True,
        blank=True,
        help_text=_('Days before the procedure to send a reminder')
    )
    
    requires_license = models.BooleanField(
        _('Requires License'),
        default=False,
        help_text=_('Whether this service requires special licensing or certification')
    )
    
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether the service or category is currently active')
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
        verbose_name = _('Service')
        verbose_name_plural = _('Services')
        ordering = ['level', 'name']
        indexes = [
            models.Index(fields=['parent', 'level']),
            models.Index(fields=['level']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """
        Переопределение метода сохранения для автоматического расчета уровня.
        """
        if self.parent:
            self.level = self.parent.level + 1
        else:
            self.level = 0
        super().save(*args, **kwargs)

    def get_ancestors(self):
        """
        Получает всех предков.
        
        Returns:
            QuerySet: QuerySet с предками
        """
        ancestors = []
        current = self
        while current.parent:
            current = current.parent
            ancestors.append(current)
        return ancestors

    def get_descendants(self):
        """
        Получает всех потомков.
        
        Returns:
            QuerySet: QuerySet с потомками
        """
        return Service.objects.filter(parent=self)

    def get_full_path(self):
        """
        Получает полный путь.
        
        Returns:
            str: Полный путь
        """
        path = [self.name]
        current = self
        while current.parent:
            current = current.parent
            path.append(current.name)
        return ' > '.join(reversed(path))

    def get_next_date(self, from_date):
        """
        Рассчитывает дату следующей процедуры.
        
        Args:
            from_date: Дата, от которой считать следующую процедуру
            
        Returns:
            date: Дата следующей процедуры или None, если процедура не периодическая
        """
        if self.is_periodic and self.period_days:
            from datetime import timedelta
            return from_date + timedelta(days=self.period_days)
        return None

    @property
    def is_category(self):
        """
        Проверяет, является ли запись категорией.
        
        Returns:
            bool: True если это категория (нет потомков)
        """
        return not self.children.exists()

    @property
    def is_service(self):
        """
        Проверяет, является ли запись услугой.
        
        Returns:
            bool: True если это услуга (есть потомки)
        """
        return self.children.exists()

