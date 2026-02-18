"""
Booking models for the application.

Этот модуль содержит модели для:
1. Бронирований
2. Временных слотов
3. Платежей
4. Отзывов
5. Отмен бронирований
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from pets.models import Pet
from providers.models import Employee, Provider
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from catalog.models import Service
from users.models import User
from django.contrib.auth import get_user_model
from datetime import time

User = get_user_model()


class BookingStatus(models.Model):
    """
    Модель статуса бронирования.
    """
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('cancelled_by_client', _('Cancelled by Client')),
        ('cancelled_by_provider', _('Cancelled by Provider')),
        ('completed', _('Completed')),
        ('no_show_by_client', _('No Show by Client')),
        ('no_show_by_provider', _('No Show by Provider')),
        ('pending_confirmation', _('Pending Confirmation'))
    ]

    name = models.CharField(
        _('Status Name'),
        max_length=50,
        unique=True,
        choices=STATUS_CHOICES
    )
    name_en = models.CharField(
        _('Name (English)'),
        max_length=50,
        blank=True,
        help_text=_('Name in English')
    )
    name_ru = models.CharField(
        _('Name (Russian)'),
        max_length=50,
        blank=True,
        help_text=_('Name in Russian')
    )
    name_me = models.CharField(
        _('Name (Montenegrian)'),
        max_length=50,
        blank=True,
        help_text=_('Name in Montenegrian')
    )
    name_de = models.CharField(
        _('Name (German)'),
        max_length=50,
        blank=True,
        help_text=_('Name in German')
    )
    description = models.TextField(_('Description'), blank=True)

    class Meta:
        app_label = 'booking'
        verbose_name = _('Booking Status')
        verbose_name_plural = _('Booking Statuses')

    def __str__(self):
        return self.get_localized_name()
    
    def get_localized_name(self, language_code=None):
        """
        Получает локализованное название статуса бронирования.
        
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
            return self.get_name_display()


class TimeSlot(models.Model):
    """
    Модель временного слота для бронирования.
    """
    start_time = models.DateTimeField(
        verbose_name=_('Start Time'),
        help_text=_('Start time of the slot')
    )
    end_time = models.DateTimeField(
        verbose_name=_('End Time'),
        help_text=_('End time of the slot')
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='time_slots',
        verbose_name=_('Employee'),
        help_text=_('Employee working in this slot')
    )
    # ВРЕМЕННО: оставляем для обратной совместимости, будет удалено после миграции данных
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='time_slots',
        verbose_name=_('Provider (Legacy)'),
        null=True,
        blank=True,
        help_text=_('Legacy field - use provider_location instead')
    )
    provider_location = models.ForeignKey(
        'providers.ProviderLocation',
        on_delete=models.CASCADE,
        related_name='time_slots',
        verbose_name=_('Provider Location'),
        null=True,
        blank=True,
        help_text=_('Location where the employee works')
    )
    is_available = models.BooleanField(
        default=True,
        verbose_name=_('Is Available'),
        help_text=_('Whether the slot is available for booking')
    )

    class Meta:
        verbose_name = _('Time Slot')
        verbose_name_plural = _('Time Slots')
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['start_time', 'end_time']),
            models.Index(fields=['is_available']),
        ]

    def __str__(self):
        return f'{self.employee} - {self.start_time}'

    def clean(self):
        if self.start_time >= self.end_time:
            raise models.ValidationError(
                _("End time must be after start time")
            )
        if self.start_time < timezone.now():
            raise models.ValidationError(
                _("Cannot create time slots in the past")
            )


class Booking(models.Model):
    """
    Модель бронирования.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('User')
    )
    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('Pet')
    )
    # ВРЕМЕННО: оставляем для обратной совместимости, будет удалено после миграции данных
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('Provider (Legacy)'),
        null=True,
        blank=True,
        help_text=_('Legacy field - use provider_location instead')
    )
    provider_location = models.ForeignKey(
        'providers.ProviderLocation',
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('Provider Location'),
        null=True,
        blank=True,
        help_text=_('Location where the service is provided')
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('Employee')
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('Service')
    )
    status = models.ForeignKey(
        BookingStatus,
        on_delete=models.PROTECT,
        related_name='bookings',
        verbose_name=_('Status')
    )
    start_time = models.DateTimeField(_('Start Time'))
    end_time = models.DateTimeField(_('End Time'))
    notes = models.TextField(_('Notes'), blank=True)
    price = models.DecimalField(
        _('Price'),
        max_digits=10,
        decimal_places=2
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    code = models.CharField(
        _('Booking Code'),
        max_length=10,
        unique=True,
        help_text=_('Unique booking code')
    )
    
    # Поля для отслеживания завершения и отмены
    completed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_bookings',
        verbose_name=_('Completed By'),
        help_text=_('User who completed the booking')
    )
    
    completed_at = models.DateTimeField(
        _('Completed At'),
        null=True,
        blank=True,
        help_text=_('When the booking was completed')
    )
    
    cancellation_reason = models.TextField(
        _('Cancellation Reason'),
        blank=True,
        help_text=_('Reason for cancellation')
    )
    
    cancelled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_bookings',
        verbose_name=_('Cancelled By'),
        help_text=_('User who cancelled the booking')
    )
    
    cancelled_at = models.DateTimeField(
        _('Cancelled At'),
        null=True,
        blank=True,
        help_text=_('When the booking was cancelled')
    )

    class Meta:
        verbose_name = _('Booking')
        verbose_name_plural = _('Bookings')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.service.name} ({self.start_time})"

    def clean(self):
        if self.end_time <= self.start_time:
            raise models.ValidationError(
                _("End time must be later than start time")
            )
    
    def complete_booking(self, user, status='completed'):
        """
        Завершить бронирование
        
        Args:
            user: Пользователь, завершающий бронирование
            status: Статус завершения ('completed', 'no_show', 'auto_completed')
        """
        from django.utils import timezone
        
        if self.status.name in ['cancelled_by_client', 'cancelled_by_provider']:
            raise ValueError(_("Cannot complete cancelled booking"))
        
        if self.completed_at:
            raise ValueError(_("Booking is already completed"))
        
        # Обновляем статус
        status_obj, created = BookingStatus.objects.get_or_create(name=status)
        self.status = status_obj
        
        # Записываем информацию о завершении
        self.completed_by = user
        self.completed_at = timezone.now()
        
        self.save()
        
        # Освобождаем слот
        self._free_time_slot()
    
    def cancel_booking(self, user, reason=''):
        """
        Отменить бронирование
        
        Args:
            user: Пользователь, отменяющий бронирование
            reason: Причина отмены
        """
        from django.utils import timezone
        
        if self.status.name in ['cancelled_by_client', 'cancelled_by_provider']:
            raise ValueError(_("Booking is already cancelled"))
        
        if self.completed_at:
            raise ValueError(_("Cannot cancel completed booking"))
        
        # Определяем тип отмены
        if user.has_role('pet_owner') and user == self.user:
            status_name = 'cancelled_by_client'
        else:
            status_name = 'cancelled_by_provider'
        
        # Обновляем статус
        status_obj, created = BookingStatus.objects.get_or_create(name=status_name)
        self.status = status_obj
        
        # Записываем информацию об отмене
        self.cancelled_by = user
        self.cancelled_at = timezone.now()
        self.cancellation_reason = reason
        
        self.save()
        
        # Освобождаем слот
        self._free_time_slot()
    
    def _free_time_slot(self):
        """Освободить временной слот"""
        # При новом подходе слоты рассчитываются на лету
        # Дополнительных действий не требуется
        pass
    
    @property
    def is_cancelled(self):
        """Проверка, отменено ли бронирование"""
        return self.status.name in ['cancelled_by_client', 'cancelled_by_provider']
    
    @property
    def is_completed(self):
        """Проверка, завершено ли бронирование"""
        return self.completed_at is not None
    
    @property
    def can_be_cancelled(self):
        """Проверка, можно ли отменить бронирование"""
        return not self.is_cancelled and not self.is_completed
    
    @property
    def can_be_completed(self):
        """Проверка, можно ли завершить бронирование"""
        return not self.is_cancelled and not self.is_completed


class BookingPayment(models.Model):
    """
    Модель платежа за бронирование.
    """
    PAYMENT_METHOD_CHOICES = [
        ('cash', _('Cash')),
        ('card', _('Card')),
        ('online', _('Online payment')),
    ]

    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name='payment',
        verbose_name=_('Booking')
    )
    amount = models.DecimalField(
        _('Amount'),
        max_digits=10,
        decimal_places=2
    )
    payment_method = models.CharField(
        _('Payment Method'),
        max_length=50,
        choices=PAYMENT_METHOD_CHOICES
    )
    transaction_id = models.CharField(
        _('Transaction ID'),
        max_length=100,
        blank=True
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Booking Payment')
        verbose_name_plural = _('Booking Payments')

    def __str__(self):
        return f"{self.booking} - {self.amount}"


class BookingReview(models.Model):
    """
    Модель отзыва о бронировании.
    """
    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name='review',
        verbose_name=_('Booking')
    )
    rating = models.PositiveIntegerField(_('Rating'))
    comment = models.TextField(_('Comment'))
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Booking Review')
        verbose_name_plural = _('Booking Reviews')

    def __str__(self):
        return f"{self.booking} - {self.rating}"


class BookingNote(models.Model):
    """
    Модель заметки к бронированию.
    """
    booking = models.ForeignKey(
        'Booking',
        on_delete=models.CASCADE,
        verbose_name=_('Booking'),
        related_name='booking_notes'
    )
    text = models.TextField(
        _('Text'),
        help_text=_('Content of the note')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('Created By'),
        related_name='booking_notes',
        help_text=_('User who created the note')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _('Booking Note')
        verbose_name_plural = _('Booking Notes')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.booking} - {self.created_at}"


class AbuseRule(models.Model):
    """
    Модель правила для определения злоупотреблений.
    """
    PERIOD_CHOICES = [
        ('day', _('Day')),
        ('week', _('Week')),
        ('month', _('Month')),
        ('year', _('Year')),
    ]

    name = models.CharField(_('Name'), max_length=100)
    description = models.TextField(_('Description'), blank=True)
    period = models.CharField(
        _('Period'),
        max_length=10,
        choices=PERIOD_CHOICES,
        help_text=_('Period for counting cancellations')
    )
    max_cancellations = models.PositiveIntegerField(
        _('Max Cancellations'),
        help_text=_('Maximum number of cancellations allowed in the period')
    )
    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Abuse Rule')
        verbose_name_plural = _('Abuse Rules')
        ordering = ['-is_active', 'period']

    def __str__(self):
        return self.name

    def check_user(self, user):
        """
        Проверяет, нарушает ли пользователь правило злоупотреблений.
        """
        from datetime import timedelta
        from django.utils import timezone

        now = timezone.now()

        if self.period == 'day':
            start_date = now - timedelta(days=1)
        elif self.period == 'week':
            start_date = now - timedelta(weeks=1)
        elif self.period == 'month':
            start_date = now - timedelta(days=30)
        else:  # year
            start_date = now - timedelta(days=365)

        cancellations = BookingCancellation.objects.filter(
            booking__user=user,
            created_at__gte=start_date,
            is_abuse=True
        ).count()

        return cancellations >= self.max_cancellations


class BookingCancellation(models.Model):
    """
    Модель отмены бронирования.
    """
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        verbose_name=_('Booking'),
        related_name='cancellations'
    )
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('Cancelled By'),
        related_name='booking_cancellations'
    )
    reason = models.TextField(_('Reason'), blank=True)
    is_abuse = models.BooleanField(_('Is Abuse'), default=False)
    abuse_rule = models.ForeignKey(
        AbuseRule,
        on_delete=models.SET_NULL,
        verbose_name=_('Abuse Rule'),
        related_name='cancellations',
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Booking Cancellation')
        verbose_name_plural = _('Booking Cancellations')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.booking} - {self.created_at}"

    def save(self, *args, **kwargs):
        """
        Сохраняет объект отмены бронирования. Проверяет, является ли отмена злоупотреблением по активным правилам.
        """
        if not self.is_abuse:
            for rule in AbuseRule.objects.filter(is_active=True):
                if rule.check_user(self.booking.user):
                    self.is_abuse = True
                    self.abuse_rule = rule
                    break
        super().save(*args, **kwargs)


class BookingAutoCompleteSettings(models.Model):
    """Глобальные настройки автоматического завершения бронирований"""
    
    STATUS_CHOICES = [
        ('completed', _('Completed')),
        ('no_show', _('No Show')),
        ('auto_completed', _('Auto Completed')),
    ]
    
    auto_complete_enabled = models.BooleanField(
        default=True,
        verbose_name=_("Auto Complete Enabled")
    )
    
    auto_complete_days = models.PositiveIntegerField(
        default=7,
        verbose_name=_("Days to Auto Complete"),
        help_text=_("How many days to wait before auto-completing bookings")
    )
    
    auto_complete_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='auto_completed',
        verbose_name=_("Auto Complete Status")
    )
    
    # Глобальные параметры запуска сервиса
    service_periodicity_hours = models.PositiveIntegerField(
        default=24,
        verbose_name=_("Service Periodicity (hours)"),
        help_text=_("How often to run the auto-completion service")
    )
    
    service_start_time = models.TimeField(
        default=time(3, 0),  # 03:00 по умолчанию
        verbose_name=_("Service Start Time"),
        help_text=_("When to start the auto-completion service")
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Auto Complete Setting")
        verbose_name_plural = _("Auto Complete Settings")
    
    def __str__(self):
        return f"Auto Complete: {self.auto_complete_days} days, status: {self.get_auto_complete_status_display()}"
    
    @classmethod
    def get_settings(cls):
        """Получить настройки автозавершения (создать по умолчанию, если не существует)"""
        settings, created = cls.objects.get_or_create(
            id=1,  # Всегда одна запись настроек
            defaults={
                'auto_complete_enabled': True,
                'auto_complete_days': 7,
                'auto_complete_status': 'auto_completed',
                'service_periodicity_hours': 24,
                'service_start_time': time(3, 0),
            }
        )
        return settings