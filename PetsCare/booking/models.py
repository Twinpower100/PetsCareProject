"""
Booking models for the application.

Этот модуль содержит модели для:
1. Бронирований
2. Временных слотов
3. Платежей
4. Отзывов
5. Отмен бронирований
"""

import random
import string

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.core.exceptions import ValidationError
from pets.models import Pet, VisitRecord
from providers.models import Employee, Provider
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from catalog.models import Service
from users.models import User
from django.contrib.auth import get_user_model
from datetime import time, timedelta
from .constants import (
    BOOKING_STATUS_ACTIVE,
    BOOKING_STATUS_CANCELLED,
    BOOKING_STATUS_COMPLETED,
    BOOKING_SERVICE_ISSUE_REPORT_WINDOW_DAYS,
    CANONICAL_BOOKING_STATUS_NAMES,
    CANCELLED_BY_CLIENT,
    CANCELLED_BY_PROVIDER,
    CANCELLATION_SIDE_CHOICES,
    CLIENT_ATTENDANCE_ARRIVED,
    CLIENT_ATTENDANCE_CHOICES,
    CLIENT_ATTENDANCE_NO_SHOW,
    CLIENT_ATTENDANCE_UNKNOWN,
    COMPLETED_BY_SYSTEM,
    COMPLETED_BY_USER,
    COMPLETION_ACTOR_CHOICES,
    COMPLETION_REASON_AUTO_TIMEOUT,
    COMPLETION_REASON_CHOICES,
    COMPLETION_REASON_MANUAL,
    CANCELLATION_REASON_CLIENT_NO_SHOW,
    CANCELLATION_REASON_CLIENT_REFUSED_ON_SITE,
    CANCELLATION_REASON_CHANGED_MIND,
    CANCELLATION_REASON_DUPLICATE_BOOKING,
    CANCELLATION_REASON_NO_LONGER_NEEDED,
    CANCELLATION_REASON_OTHER,
    CANCELLATION_REASON_PROVIDER_PROBLEM,
    CANCELLATION_REASON_PROVIDER_UNAVAILABLE,
    CANCELLATION_REASON_SERVICE_NOT_POSSIBLE,
    CANCELLATION_REASON_TECHNICAL_ISSUE,
    CANCELLATION_REASON_WRONG_TIME,
    ISSUE_TYPE_CHOICES,
    ISSUE_TYPE_SERVICE_NOT_PROVIDED,
    ISSUE_STATUS_CHOICES,
    ISSUE_STATUS_ACKNOWLEDGED,
    ISSUE_STATUS_OPEN,
    RESOLUTION_OUTCOME_CHOICES,
    RESOLUTION_ACTOR_CHOICES,
    REPORTED_BY_CLIENT,
)

User = get_user_model()


class BookingStatus(models.Model):
    """
    Модель статуса бронирования.
    """
    STATUS_CHOICES = [
        (BOOKING_STATUS_ACTIVE, _('Active')),
        (BOOKING_STATUS_COMPLETED, _('Completed')),
        (BOOKING_STATUS_CANCELLED, _('Cancelled')),
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

    @classmethod
    def ensure_canonical_statuses(cls):
        for status_name in CANONICAL_BOOKING_STATUS_NAMES:
            cls.objects.get_or_create(name=status_name)


class BookingCancellationReason(models.Model):
    """Справочник структурированных причин отмены бронирования."""

    scope = models.CharField(
        _('Scope'),
        max_length=20,
        choices=CANCELLATION_SIDE_CHOICES,
    )
    code = models.CharField(
        _('Code'),
        max_length=50,
        unique=True,
    )
    label = models.CharField(
        _('Label'),
        max_length=100,
    )
    description = models.TextField(_('Description'), blank=True)
    is_active = models.BooleanField(_('Is Active'), default=True)
    sort_order = models.PositiveIntegerField(_('Sort Order'), default=0)

    class Meta:
        app_label = 'booking'
        verbose_name = _('Booking Cancellation Reason')
        verbose_name_plural = _('Booking Cancellation Reasons')
        ordering = ['scope', 'sort_order', 'label']

    def __str__(self):
        return f'{self.label} ({self.scope})'

    @classmethod
    def ensure_default_reasons(cls):
        defaults = [
            (CANCELLED_BY_PROVIDER, CANCELLATION_REASON_CLIENT_NO_SHOW, _('Client did not arrive'), 10),
            (CANCELLED_BY_PROVIDER, CANCELLATION_REASON_PROVIDER_UNAVAILABLE, _('Provider unavailable'), 20),
            (CANCELLED_BY_PROVIDER, CANCELLATION_REASON_SERVICE_NOT_POSSIBLE, _('Service could not be delivered'), 30),
            (CANCELLED_BY_PROVIDER, CANCELLATION_REASON_DUPLICATE_BOOKING, _('Duplicate booking'), 40),
            (CANCELLED_BY_PROVIDER, CANCELLATION_REASON_TECHNICAL_ISSUE, _('Technical issue'), 50),
            (CANCELLED_BY_PROVIDER, CANCELLATION_REASON_OTHER, _('Other'), 60),
            (CANCELLED_BY_CLIENT, CANCELLATION_REASON_CHANGED_MIND, _('Changed mind'), 10),
            (CANCELLED_BY_CLIENT, CANCELLATION_REASON_WRONG_TIME, _('Wrong time'), 20),
            (CANCELLED_BY_CLIENT, CANCELLATION_REASON_NO_LONGER_NEEDED, _('No longer needed'), 30),
            (CANCELLED_BY_CLIENT, CANCELLATION_REASON_PROVIDER_PROBLEM, _('Provider problem'), 40),
            (CANCELLED_BY_CLIENT, CANCELLATION_REASON_CLIENT_REFUSED_ON_SITE, _('Client refused on site'), 50),
            (CANCELLED_BY_CLIENT, CANCELLATION_REASON_OTHER, _('Other'), 60),
        ]
        for scope, code, label, sort_order in defaults:
            cls.objects.update_or_create(
                code=code,
                defaults={
                    'scope': scope,
                    'label': label,
                    'sort_order': sort_order,
                    'is_active': True,
                },
            )

    @classmethod
    def get_default_reason(cls, scope):
        return cls.objects.filter(
            scope=scope,
            code=CANCELLATION_REASON_OTHER,
            is_active=True,
        ).first()


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
    escort_owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='escorted_bookings',
        verbose_name=_('Escort Owner'),
        blank=True,
        help_text=_('Owner escorting the pet to the booking')
    )
    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('Pet')
    )
    visit_record = models.ForeignKey(
        VisitRecord,
        on_delete=models.SET_NULL,
        related_name='source_bookings',
        verbose_name=_('Visit Record'),
        null=True,
        blank=True,
        help_text=_('Structured visit record linked to this completed booking')
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
    occupied_duration_minutes = models.PositiveIntegerField(
        _('Occupied Duration Minutes'),
        default=0,
        help_text=_('Immutable occupied duration snapshot stored at booking creation time')
    )
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

    completed_by_actor = models.CharField(
        _('Completed By Actor'),
        max_length=20,
        choices=COMPLETION_ACTOR_CHOICES,
        blank=True,
        help_text=_('Actor that completed the booking'),
    )
    completed_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_bookings',
        verbose_name=_('Completed By User'),
        help_text=_('User who manually completed the booking')
    )
    completed_at = models.DateTimeField(
        _('Completed At'),
        null=True,
        blank=True,
        help_text=_('When the booking was completed')
    )
    completion_reason_code = models.CharField(
        _('Completion Reason Code'),
        max_length=20,
        choices=COMPLETION_REASON_CHOICES,
        blank=True,
        help_text=_('How the booking was completed'),
    )
    cancelled_by = models.CharField(
        _('Cancelled By'),
        max_length=20,
        choices=CANCELLATION_SIDE_CHOICES,
        blank=True,
        help_text=_('Which side cancelled the booking'),
    )
    cancelled_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_bookings',
        verbose_name=_('Cancelled By User'),
        help_text=_('User who recorded the cancellation'),
    )
    cancelled_at = models.DateTimeField(
        _('Cancelled At'),
        null=True,
        blank=True,
        help_text=_('When the booking was cancelled')
    )
    cancellation_reason = models.ForeignKey(
        BookingCancellationReason,
        on_delete=models.PROTECT,
        related_name='bookings',
        verbose_name=_('Cancellation Reason'),
        null=True,
        blank=True,
    )
    cancellation_reason_text = models.TextField(
        _('Cancellation Reason Text'),
        blank=True,
        help_text=_('Optional free-text explanation for cancellation'),
    )
    client_attendance = models.CharField(
        _('Client Attendance'),
        max_length=20,
        choices=CLIENT_ATTENDANCE_CHOICES,
        default=CLIENT_ATTENDANCE_UNKNOWN,
        help_text=_('Whether the client arrived to the booking'),
    )

    class Meta:
        verbose_name = _('Booking')
        verbose_name_plural = _('Bookings')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['escort_owner', 'start_time']),
            models.Index(fields=['pet', 'start_time']),
            models.Index(fields=['employee', 'start_time']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.service.name} ({self.start_time})"

    def clean(self):
        if self.end_time <= self.start_time:
            raise models.ValidationError(
                _("End time must be later than start time")
            )

        if not self.escort_owner_id and self.user_id:
            self.escort_owner = self.user

        if self.escort_owner_id and self.pet_id:
            if not self.pet.owners.filter(id=self.escort_owner_id).exists():
                raise models.ValidationError(
                    {"escort_owner": _("Escort owner must be one of the pet owners")}
                )

        if not self.occupied_duration_minutes and self.start_time and self.end_time:
            duration_seconds = (self.end_time - self.start_time).total_seconds()
            self.occupied_duration_minutes = max(int(duration_seconds // 60), 1)

        status_name = self.status.name if self.status_id else None
        errors = {}

        if status_name == BOOKING_STATUS_COMPLETED:
            if not self.completed_at:
                errors['completed_at'] = _('Completed bookings must have completed_at.')
            if not self.completed_by_actor:
                errors['completed_by_actor'] = _('Completed bookings must have completed_by_actor.')
            if self.completed_by_actor == COMPLETED_BY_SYSTEM and self.completed_by_user_id:
                errors['completed_by_user'] = _('System completion must not reference a human user.')
            if self.visit_record_id and self.visit_record.pet_id != self.pet_id:
                errors['visit_record'] = _('Linked visit record must belong to the same pet.')
        elif self.completed_at or self.completed_by_actor or self.completed_by_user_id or self.completion_reason_code:
            errors['status'] = _('Only completed bookings may have completion metadata.')
        elif self.visit_record_id:
            errors['visit_record'] = _('Only completed bookings may have a linked visit record.')

        if status_name == BOOKING_STATUS_CANCELLED:
            if not self.cancelled_at:
                errors['cancelled_at'] = _('Cancelled bookings must have cancelled_at.')
            if not self.cancelled_by:
                errors['cancelled_by'] = _('Cancelled bookings must have cancelled_by.')
            if not self.cancellation_reason_id:
                errors['cancellation_reason'] = _('Cancellation reason is required.')
            elif self.cancellation_reason.scope != self.cancelled_by:
                errors['cancellation_reason'] = _('Cancellation reason scope does not match cancelled_by.')
        elif (
            self.cancelled_at
            or self.cancelled_by
            or self.cancelled_by_user_id
            or self.cancellation_reason_id
            or self.cancellation_reason_text
        ):
            errors['status'] = _('Only cancelled bookings may have cancellation metadata.')

        if (
            status_name == BOOKING_STATUS_CANCELLED
            and self.client_attendance == CLIENT_ATTENDANCE_NO_SHOW
            and self.cancellation_reason_id
            and self.cancellation_reason.code != CANCELLATION_REASON_CLIENT_NO_SHOW
        ):
            errors['cancellation_reason'] = _('Attendance "no_show" requires reason client_no_show.')

        if (
            status_name == BOOKING_STATUS_CANCELLED
            and self.cancellation_reason_id
            and self.cancellation_reason.code == CANCELLATION_REASON_CLIENT_NO_SHOW
            and self.client_attendance != CLIENT_ATTENDANCE_NO_SHOW
        ):
            errors['client_attendance'] = _('client_no_show reason requires client attendance no_show.')

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Подготавливает производные поля перед сохранением бронирования."""
        if not self.code:
            self.code = self._generate_booking_code()

        if not self.provider_id and self.provider_location_id:
            self.provider = self.provider_location.provider

        if not self.escort_owner_id and self.user_id:
            self.escort_owner = self.user

        if not self.occupied_duration_minutes and self.start_time and self.end_time:
            duration_seconds = (self.end_time - self.start_time).total_seconds()
            self.occupied_duration_minutes = max(int(duration_seconds // 60), 1)

        super().save(*args, **kwargs)

    @staticmethod
    def _generate_booking_code():
        """Генерирует уникальный код бронирования."""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not Booking.objects.filter(code=code).exists():
                return code

    @classmethod
    def get_status(cls, status_name):
        status_obj, _ = BookingStatus.objects.get_or_create(name=status_name)
        return status_obj

    def complete_booking(
        self,
        user=None,
        *,
        actor=COMPLETED_BY_USER,
        reason_code=COMPLETION_REASON_MANUAL,
    ):
        if self.status.name != BOOKING_STATUS_ACTIVE:
            if self.status.name == BOOKING_STATUS_CANCELLED:
                raise ValueError(_("Cannot complete cancelled booking"))
            raise ValueError(_("Only active bookings can be completed"))

        if timezone.now() < self.start_time:
            raise ValueError(_("Booking cannot be completed before start time"))

        if actor == COMPLETED_BY_SYSTEM and user is not None:
            raise ValueError(_("System completion must not reference a human user"))

        self.status = self.get_status(BOOKING_STATUS_COMPLETED)
        self.completed_at = timezone.now()
        self.completed_by_actor = actor
        self.completed_by_user = user if actor == COMPLETED_BY_USER else None
        self.completion_reason_code = reason_code
        self.visit_record = None
        self.cancelled_by = ''
        self.cancelled_by_user = None
        self.cancelled_at = None
        self.cancellation_reason = None
        self.cancellation_reason_text = ''
        self.save()
        self._free_time_slot()

    def cancel_booking(
        self,
        *,
        cancelled_by,
        cancelled_by_user,
        cancellation_reason,
        cancellation_reason_text='',
        client_attendance=CLIENT_ATTENDANCE_UNKNOWN,
    ):
        if self.status.name != BOOKING_STATUS_ACTIVE:
            if self.status.name == BOOKING_STATUS_COMPLETED:
                raise ValueError(_("Cannot cancel completed booking"))
            raise ValueError(_("Only active bookings can be cancelled"))

        if cancelled_by == CANCELLED_BY_CLIENT and timezone.now() > self.end_time:
            raise ValueError(_("Clients cannot cancel bookings after end time"))

        if cancellation_reason.scope != cancelled_by:
            raise ValueError(_("Cancellation reason scope does not match cancellation side"))

        if cancellation_reason.code == CANCELLATION_REASON_CLIENT_NO_SHOW:
            if cancelled_by != CANCELLED_BY_PROVIDER:
                raise ValueError(_("client_no_show can only be recorded by provider"))
            client_attendance = CLIENT_ATTENDANCE_NO_SHOW

        if client_attendance == CLIENT_ATTENDANCE_NO_SHOW and cancellation_reason.code != CANCELLATION_REASON_CLIENT_NO_SHOW:
            raise ValueError(_("Attendance no_show requires client_no_show reason"))

        self.status = self.get_status(BOOKING_STATUS_CANCELLED)
        self.cancelled_by = cancelled_by
        self.cancelled_by_user = cancelled_by_user
        self.cancelled_at = timezone.now()
        self.cancellation_reason = cancellation_reason
        self.cancellation_reason_text = cancellation_reason_text
        self.client_attendance = client_attendance
        self.visit_record = None
        self.completed_at = None
        self.completed_by_actor = ''
        self.completed_by_user = None
        self.completion_reason_code = ''
        self.save()
        BookingCancellation.objects.create(
            booking=self,
            cancelled_by=cancelled_by_user,
            cancelled_by_side=cancelled_by,
            reason=cancellation_reason_text,
            reason_code=cancellation_reason,
            client_attendance=client_attendance,
        )
        self._free_time_slot()
    
    def _free_time_slot(self):
        """Освободить временной слот"""
        # При новом подходе слоты рассчитываются на лету
        # Дополнительных действий не требуется
        pass

    @property
    def is_cancelled(self):
        """Проверка, отменено ли бронирование"""
        return self.status.name == BOOKING_STATUS_CANCELLED
    
    @property
    def is_completed(self):
        """Проверка, завершено ли бронирование"""
        return self.status.name == BOOKING_STATUS_COMPLETED
    
    @property
    def can_be_cancelled(self):
        """Проверка, можно ли отменить бронирование"""
        return self.status.name == BOOKING_STATUS_ACTIVE
    
    @property
    def can_be_completed(self):
        """Проверка, можно ли завершить бронирование"""
        return self.status.name == BOOKING_STATUS_ACTIVE and timezone.now() >= self.start_time

    @property
    def is_overdue(self):
        return self.status.name == BOOKING_STATUS_ACTIVE and timezone.now() > self.end_time

    @property
    def service_issue_report_deadline(self):
        return self.end_time + timedelta(days=BOOKING_SERVICE_ISSUE_REPORT_WINDOW_DAYS)

    @property
    def has_open_service_issue(self):
        return self.service_issues.filter(
            status__in=(ISSUE_STATUS_OPEN, ISSUE_STATUS_ACKNOWLEDGED)
        ).exists()

    @property
    def latest_service_issue(self):
        return self.service_issues.order_by('-created_at').first()


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
        related_name='booking_cancellations',
        null=True,
        blank=True,
    )
    cancelled_by_side = models.CharField(
        _('Cancelled By Side'),
        max_length=20,
        choices=CANCELLATION_SIDE_CHOICES,
        blank=True,
        default='',
    )
    reason = models.TextField(_('Reason'), blank=True)
    reason_code = models.ForeignKey(
        BookingCancellationReason,
        on_delete=models.PROTECT,
        verbose_name=_('Reason Code'),
        related_name='cancellation_events',
        null=True,
        blank=True,
    )
    client_attendance = models.CharField(
        _('Client Attendance'),
        max_length=20,
        choices=CLIENT_ATTENDANCE_CHOICES,
        default=CLIENT_ATTENDANCE_UNKNOWN,
    )
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

    auto_complete_enabled = models.BooleanField(
        default=True,
        verbose_name=_("Auto Complete Enabled")
    )
    
    auto_complete_days = models.PositiveIntegerField(
        default=7,
        verbose_name=_("Days to Auto Complete"),
        help_text=_("How many days to wait before auto-completing bookings")
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
        return f"Auto Complete: {self.auto_complete_days} days"

    @classmethod
    def get_settings(cls):
        """Получить настройки автозавершения (создать по умолчанию, если не существует)"""
        settings, created = cls.objects.get_or_create(
            id=1,  # Всегда одна запись настроек
            defaults={
                'auto_complete_enabled': True,
                'auto_complete_days': 7,
                'service_periodicity_hours': 24,
                'service_start_time': time(3, 0),
            }
        )
        return settings


class BookingServiceIssue(models.Model):
    """
    Модель инцидента по бронированию (например, клиент пришел, но услуга не оказана).
    """
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name='service_issues',
        verbose_name=_('Booking')
    )
    issue_type = models.CharField(
        _('Issue Type'),
        max_length=50,
        choices=ISSUE_TYPE_CHOICES,
        default=ISSUE_TYPE_SERVICE_NOT_PROVIDED,
    )
    reported_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='reported_service_issues',
        verbose_name=_('Reported By User')
    )
    reported_by_side = models.CharField(
        _('Reported By Side'),
        max_length=20,
        default=REPORTED_BY_CLIENT,
    )
    client_attendance_snapshot = models.CharField(
        _('Client Attendance Snapshot'),
        max_length=20,
        choices=CLIENT_ATTENDANCE_CHOICES,
        default=CLIENT_ATTENDANCE_UNKNOWN,
    )
    description = models.TextField(_('Description'), blank=True)
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=ISSUE_STATUS_CHOICES,
        default=ISSUE_STATUS_OPEN,
    )
    resolution_outcome = models.CharField(
        _('Resolution Outcome'),
        max_length=50,
        choices=RESOLUTION_OUTCOME_CHOICES,
        blank=True,
    )
    resolved_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_service_issues',
        verbose_name=_('Resolved By User')
    )
    resolved_by_actor = models.CharField(
        _('Resolved By Actor'),
        max_length=20,
        choices=RESOLUTION_ACTOR_CHOICES,
        blank=True,
    )
    resolved_at = models.DateTimeField(
        _('Resolved At'),
        null=True,
        blank=True,
    )
    resolution_note = models.TextField(
        _('Resolution Note'),
        blank=True,
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Booking Service Issue')
        verbose_name_plural = _('Booking Service Issues')
        ordering = ['-created_at']

    def __str__(self):
        return f"Issue {self.id} for Booking {self.booking.code}"
