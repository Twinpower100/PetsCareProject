"""Provider-owned модели для Manual Booking V2."""

from __future__ import annotations

import random
import string

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField

from booking.constants import (
    BOOKING_STATUS_ACTIVE,
    BOOKING_STATUS_CANCELLED,
    BOOKING_STATUS_COMPLETED,
    CANCELLED_BY_PROVIDER,
    CANCELLATION_SIDE_CHOICES,
    COMPLETED_BY_SYSTEM,
    COMPLETED_BY_USER,
    COMPLETION_ACTOR_CHOICES,
    COMPLETION_REASON_CHOICES,
    COMPLETION_REASON_MANUAL,
)
from pets.models import Breed, PetType, SIZE_CATEGORY_CHOICES
from providers.models import Employee, Provider, ProviderLocation


class ProviderClientLead(models.Model):
    """Provider-owned контакт для manual flow без создания platform User."""

    class LeadSource(models.TextChoices):
        MANUAL_BOOKING = 'manual_booking', _('Manual booking')

    class InvitationStatus(models.TextChoices):
        NOT_INVITED = 'not_invited', _('Not invited')
        INVITED = 'invited', _('Invited')
        REGISTERED = 'registered', _('Registered')

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='manual_leads',
        verbose_name=_('Provider'),
    )
    provider_location = models.ForeignKey(
        ProviderLocation,
        on_delete=models.PROTECT,
        related_name='manual_leads',
        verbose_name=_('Provider Location'),
    )
    first_name = models.CharField(_('First Name'), max_length=100)
    last_name = models.CharField(_('Last Name'), max_length=100)
    phone_number = PhoneNumberField(_('Phone Number'))
    normalized_phone_number = models.CharField(_('Normalized Phone Number'), max_length=32)
    email = models.EmailField(_('Email'), blank=True)
    source = models.CharField(
        _('Source'),
        max_length=32,
        choices=LeadSource.choices,
        default=LeadSource.MANUAL_BOOKING,
    )
    invitation_status = models.CharField(
        _('Invitation Status'),
        max_length=32,
        choices=InvitationStatus.choices,
        default=InvitationStatus.NOT_INVITED,
    )
    version = models.PositiveIntegerField(_('Version'), default=1)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Provider Client Lead')
        verbose_name_plural = _('Provider Client Leads')
        ordering = ['last_name', 'first_name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'normalized_phone_number'],
                name='unique_provider_manual_lead_phone',
            ),
        ]
        indexes = [
            models.Index(fields=['provider', 'provider_location']),
            models.Index(fields=['provider', 'normalized_phone_number']),
        ]

    def __str__(self):
        return f'{self.last_name} {self.first_name}'.strip() or self.normalized_phone_number


class ManualBooking(models.Model):
    """Отдельная write-model сущность для provider-owned manual booking."""

    class Source(models.TextChoices):
        MANUAL_ENTRY = 'manual_entry', _('Manual entry')

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='manual_bookings',
        verbose_name=_('Provider'),
    )
    provider_location = models.ForeignKey(
        ProviderLocation,
        on_delete=models.PROTECT,
        related_name='manual_bookings',
        verbose_name=_('Provider Location'),
    )
    lead = models.ForeignKey(
        ProviderClientLead,
        on_delete=models.PROTECT,
        related_name='manual_bookings',
        verbose_name=_('Provider Client Lead'),
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name='manual_bookings',
        verbose_name=_('Employee'),
        null=True,
        blank=True,
    )
    service = models.ForeignKey(
        'catalog.Service',
        on_delete=models.PROTECT,
        related_name='manual_bookings',
        verbose_name=_('Service'),
    )
    pet_type = models.ForeignKey(
        PetType,
        on_delete=models.PROTECT,
        related_name='manual_bookings',
        verbose_name=_('Pet Type'),
    )
    breed = models.ForeignKey(
        Breed,
        on_delete=models.PROTECT,
        related_name='manual_bookings',
        verbose_name=_('Breed'),
    )
    size_code = models.CharField(
        _('Size Code'),
        max_length=10,
        choices=SIZE_CATEGORY_CHOICES,
    )
    owner_first_name = models.CharField(_('Owner First Name'), max_length=100)
    owner_last_name = models.CharField(_('Owner Last Name'), max_length=100)
    owner_phone_number = PhoneNumberField(_('Owner Phone Number'))
    owner_email = models.EmailField(_('Owner Email'), blank=True)
    pet_name = models.CharField(_('Pet Name'), max_length=100)
    notes = models.TextField(_('Notes'), blank=True)
    is_emergency = models.BooleanField(_('Is Emergency'), default=False)
    source = models.CharField(
        _('Source'),
        max_length=32,
        choices=Source.choices,
        default=Source.MANUAL_ENTRY,
    )
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=[
            (BOOKING_STATUS_ACTIVE, _('Active')),
            (BOOKING_STATUS_COMPLETED, _('Completed')),
            (BOOKING_STATUS_CANCELLED, _('Cancelled')),
        ],
        default=BOOKING_STATUS_ACTIVE,
    )
    start_time = models.DateTimeField(_('Start Time'))
    end_time = models.DateTimeField(_('End Time'))
    occupied_duration_minutes = models.PositiveIntegerField(_('Occupied Duration Minutes'))
    price = models.DecimalField(_('Price'), max_digits=10, decimal_places=2)
    code = models.CharField(_('Manual Booking Code'), max_length=12, unique=True, blank=True)
    version = models.PositiveIntegerField(_('Version'), default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_manual_bookings',
        verbose_name=_('Created By'),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='updated_manual_bookings',
        verbose_name=_('Updated By'),
        null=True,
        blank=True,
    )
    completed_by_actor = models.CharField(
        _('Completed By Actor'),
        max_length=20,
        choices=COMPLETION_ACTOR_CHOICES,
        blank=True,
    )
    completed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='completed_manual_bookings',
        verbose_name=_('Completed By User'),
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(_('Completed At'), null=True, blank=True)
    completion_reason_code = models.CharField(
        _('Completion Reason Code'),
        max_length=20,
        choices=COMPLETION_REASON_CHOICES,
        blank=True,
    )
    cancelled_by = models.CharField(
        _('Cancelled By'),
        max_length=20,
        choices=CANCELLATION_SIDE_CHOICES,
        blank=True,
    )
    cancelled_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='cancelled_manual_bookings',
        verbose_name=_('Cancelled By User'),
        null=True,
        blank=True,
    )
    cancelled_at = models.DateTimeField(_('Cancelled At'), null=True, blank=True)
    cancellation_reason = models.ForeignKey(
        'booking.BookingCancellationReason',
        on_delete=models.PROTECT,
        related_name='manual_bookings',
        verbose_name=_('Cancellation Reason'),
        null=True,
        blank=True,
    )
    cancellation_reason_text = models.TextField(_('Cancellation Reason Text'), blank=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Manual Booking')
        verbose_name_plural = _('Manual Bookings')
        ordering = ['-start_time', '-id']
        indexes = [
            models.Index(fields=['provider', 'start_time']),
            models.Index(fields=['provider_location', 'start_time']),
            models.Index(fields=['employee', 'start_time']),
            models.Index(fields=['status', 'start_time']),
        ]

    def __str__(self):
        return f'{self.code} {self.pet_name} ({self.start_time})'

    def clean(self):
        if self.end_time <= self.start_time:
            raise ValidationError({'end_time': _('End time must be later than start time.')})

        if self.provider_location_id and self.provider_id and self.provider_location.provider_id != self.provider_id:
            raise ValidationError({'provider_location': _('Location must belong to the same provider.')})

        if self.lead_id and self.provider_id and self.lead.provider_id != self.provider_id:
            raise ValidationError({'lead': _('Lead must belong to the same provider.')})

        if self.breed_id and self.pet_type_id and self.breed.pet_type_id != self.pet_type_id:
            raise ValidationError({'breed': _('Breed must belong to the selected pet type.')})

        if self.employee_id and self.status == BOOKING_STATUS_COMPLETED and self.completed_by_actor == COMPLETED_BY_SYSTEM:
            raise ValidationError({'completed_by_actor': _('System completion must not reference a human user.')})

        if self.status == BOOKING_STATUS_COMPLETED:
            if not self.completed_at:
                raise ValidationError({'completed_at': _('Completed manual bookings must have completed_at.')})
            if not self.completed_by_actor:
                raise ValidationError({'completed_by_actor': _('Completed manual bookings must have completed_by_actor.')})
        elif self.completed_at or self.completed_by_actor or self.completed_by_user_id or self.completion_reason_code:
            raise ValidationError({'status': _('Only completed manual bookings may have completion metadata.')})

        if self.status == BOOKING_STATUS_CANCELLED:
            if not self.cancelled_at:
                raise ValidationError({'cancelled_at': _('Cancelled manual bookings must have cancelled_at.')})
            if not self.cancelled_by:
                raise ValidationError({'cancelled_by': _('Cancelled manual bookings must have cancelled_by.')})
            if not self.cancellation_reason_id:
                raise ValidationError({'cancellation_reason': _('Cancellation reason is required.')})
        elif (
            self.cancelled_at
            or self.cancelled_by
            or self.cancelled_by_user_id
            or self.cancellation_reason_id
            or self.cancellation_reason_text
        ):
            raise ValidationError({'status': _('Only cancelled manual bookings may have cancellation metadata.')})

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        if self.pk:
            self.version += 1
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def protocol_family(self) -> str:
        return self.service.resolve_protocol_family()

    @property
    def requires_protocol(self) -> bool:
        return self.protocol_family != 'none'

    @property
    def is_overdue(self) -> bool:
        return self.status == BOOKING_STATUS_ACTIVE and self.end_time < timezone.now()

    def cancel(self, *, by_user, cancellation_reason, cancellation_reason_text: str = ''):
        """Переводит manual booking в cancelled."""
        self.status = BOOKING_STATUS_CANCELLED
        self.cancelled_at = timezone.now()
        self.cancelled_by = CANCELLED_BY_PROVIDER
        self.cancelled_by_user = by_user
        self.cancellation_reason = cancellation_reason
        self.cancellation_reason_text = cancellation_reason_text.strip()
        self.updated_by = by_user
        self.save()

    def complete(self, *, by_user):
        """Переводит manual booking в completed."""
        self.status = BOOKING_STATUS_COMPLETED
        self.completed_at = timezone.now()
        self.completed_by_actor = COMPLETED_BY_USER
        self.completed_by_user = by_user
        self.completion_reason_code = COMPLETION_REASON_MANUAL
        self.updated_by = by_user
        self.save()

    @classmethod
    def _generate_code(cls) -> str:
        alphabet = string.ascii_uppercase + string.digits
        while True:
            candidate = 'MB' + ''.join(random.choices(alphabet, k=8))
            if not cls.objects.filter(code=candidate).exists():
                return candidate


class ManualVisitProtocol(models.Model):
    """Provider-only протокол визита для manual booking без привязки к Pet."""

    class ProtocolFamily(models.TextChoices):
        NONE = 'none', _('None')
        VETERINARY = 'veterinary', _('Veterinary')

    manual_booking = models.OneToOneField(
        ManualBooking,
        on_delete=models.CASCADE,
        related_name='manual_visit_protocol',
        verbose_name=_('Manual Booking'),
    )
    protocol_family = models.CharField(
        _('Protocol Family'),
        max_length=32,
        choices=ProtocolFamily.choices,
        default=ProtocolFamily.VETERINARY,
    )
    provider_location = models.ForeignKey(
        ProviderLocation,
        on_delete=models.PROTECT,
        related_name='manual_visit_protocols',
        verbose_name=_('Provider Location'),
    )
    service = models.ForeignKey(
        'catalog.Service',
        on_delete=models.PROTECT,
        related_name='manual_visit_protocols',
        verbose_name=_('Service'),
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name='manual_visit_protocols',
        verbose_name=_('Employee'),
        null=True,
        blank=True,
    )
    date = models.DateTimeField(_('Date'))
    next_date = models.DateField(_('Next Date'), null=True, blank=True)
    description = models.TextField(_('Description'), blank=True)
    diagnosis = models.TextField(_('Diagnosis'), blank=True)
    anamnesis = models.TextField(_('Anamnesis'), blank=True)
    results = models.TextField(_('Results'), blank=True)
    recommendations = models.TextField(_('Recommendations'), blank=True)
    notes = models.TextField(_('Notes'), blank=True)
    serial_number = models.CharField(_('Serial Number'), max_length=100, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_manual_visit_protocols',
        verbose_name=_('Created By'),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='updated_manual_visit_protocols',
        verbose_name=_('Updated By'),
        null=True,
        blank=True,
    )
    version = models.PositiveIntegerField(_('Version'), default=1)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Manual Visit Protocol')
        verbose_name_plural = _('Manual Visit Protocols')
        ordering = ['-date', '-id']

    def __str__(self):
        return f'{self.manual_booking.code} protocol'

    def clean(self):
        if self.manual_booking_id:
            if self.provider_location_id != self.manual_booking.provider_location_id:
                raise ValidationError({'provider_location': _('Protocol location must match manual booking location.')})
            if self.service_id != self.manual_booking.service_id:
                raise ValidationError({'service': _('Protocol service must match manual booking service.')})

        if self.protocol_family == self.ProtocolFamily.NONE:
            raise ValidationError({'protocol_family': _('Protocol family must require a protocol.')})

    def save(self, *args, **kwargs):
        if self.pk:
            self.version += 1
        self.full_clean()
        super().save(*args, **kwargs)
