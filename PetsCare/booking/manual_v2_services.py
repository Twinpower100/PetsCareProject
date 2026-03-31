"""Сервисы для Manual Booking V2."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Any, cast

import phonenumbers
from PIL import Image, ImageDraw, ImageFont
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponse
from django.template import Context, Template
from django.utils import timezone, translation
from django.utils.html import escape
from django.utils.translation import gettext as _

from booking.constants import (
    ACTIVE_BOOKING_STATUS_NAMES,
    BOOKING_STATUS_ACTIVE,
    CANCELLED_BY_PROVIDER,
    CANCELLATION_REASON_PROVIDER_EMERGENCY_PREEMPTION,
)
from booking.manual_v2_models import ManualBooking, ManualVisitProtocol, ProviderClientLead
from booking.models import Booking, BookingAutoCompleteSettings, BookingCancellationReason
from booking.unified_services import BookingAvailabilityService, BookingDomainError, BookingPolicy
from catalog.models import Service
from pets.models import Breed, PetType, SizeRule
from providers.models import Employee, EmployeeLocationRole, Provider, ProviderLocation, ProviderLocationService
from users.models import User


DEFAULT_EMERGENCY_WINDOW_HOURS = 4
MANUAL_ALTERNATIVE_SLOT_LIMIT = 8
MANUAL_ALTERNATIVE_DAY_SPAN = 3


class ManualBookingSettingsService:
    """Доступ к глобальным настройкам manual booking."""

    @classmethod
    def get_emergency_window_hours(cls) -> int:
        settings = BookingAutoCompleteSettings.get_settings()
        return max(int(settings.manual_booking_emergency_window_hours or DEFAULT_EMERGENCY_WINDOW_HOURS), 1)

    @classmethod
    def is_inside_emergency_window(cls, start_time: datetime | None, *, now: datetime | None = None) -> bool:
        if start_time is None:
            return False
        current_time = now or timezone.now()
        return current_time <= start_time <= current_time + timedelta(hours=cls.get_emergency_window_hours())


@dataclass(frozen=True)
class ManualResolvedContext:
    """Нормализованный контекст ручной записи перед созданием."""

    provider: Provider
    provider_location: ProviderLocation
    employee: Employee
    service: Service
    pet_type: PetType
    breed: Breed
    size_code: str
    lead: ProviderClientLead
    owner_first_name: str
    owner_last_name: str
    owner_phone_number: str
    owner_email: str
    pet_name: str
    notes: str
    is_emergency: bool
    start_time: datetime
    end_time: datetime
    occupied_duration_minutes: int
    price: Decimal


class ManualBookingAccessService:
    """Проверки доступа staff к provider-owned manual flow."""

    @classmethod
    def ensure_provider_staff(cls, actor: User, provider: Provider) -> None:
        """Проверяет, что пользователь может работать с manual flow провайдера."""
        if actor.is_superuser or actor.is_system_admin():
            return

        if actor.get_managed_providers().filter(id=provider.id).exists():
            return

        employee = getattr(actor, 'employee_profile', None)
        if employee is None or not employee.is_active:
            raise BookingDomainError(
                'manual_booking_forbidden',
                _('You do not have permission to manage manual bookings for this provider.'),
                status_code=403,
            )

        has_location_role = EmployeeLocationRole.objects.filter(
            employee=employee,
            provider_location__provider=provider,
            is_active=True,
            end_date__isnull=True,
        ).exists()
        if has_location_role:
            return

        raise BookingDomainError(
            'manual_booking_forbidden',
            _('You do not have permission to manage manual bookings for this provider.'),
            status_code=403,
        )

    @classmethod
    def get_accessible_locations(cls, actor: User, provider: Provider) -> list[ProviderLocation]:
        """Возвращает доступные staff-локации для manual flow."""
        cls.ensure_provider_staff(actor, provider)
        queryset = ProviderLocation.objects.filter(provider=provider, is_active=True)

        if actor.is_superuser or actor.is_system_admin() or actor.get_managed_providers().filter(id=provider.id).exists():
            return list(queryset.order_by('name'))

        employee = actor.employee_profile
        location_ids = EmployeeLocationRole.objects.filter(
            employee=employee,
            provider_location__provider=provider,
            is_active=True,
            end_date__isnull=True,
        ).values_list('provider_location_id', flat=True)
        return list(queryset.filter(id__in=location_ids).order_by('name'))

    @classmethod
    def resolve_location(
        cls,
        *,
        actor: User,
        provider: Provider,
        requested_location_id: int | None,
    ) -> tuple[ProviderLocation, bool, list[ProviderLocation]]:
        """Разрешает локацию и сообщает, была ли она auto-locked."""
        locations = cls.get_accessible_locations(actor, provider)
        if not locations:
            raise BookingDomainError(
                'manual_booking_no_locations',
                _('No active provider locations are available for manual booking.'),
                status_code=400,
            )

        if len(locations) == 1:
            return locations[0], True, locations

        if requested_location_id is None:
            raise BookingDomainError(
                'manual_booking_location_required',
                _('Location is required for manual booking.'),
                status_code=400,
            )

        for location in locations:
            if location.id == requested_location_id:
                return location, False, locations

        raise BookingDomainError(
            'manual_booking_location_forbidden',
            _('You do not have access to the selected location.'),
            status_code=403,
        )


class ManualBookingOptionsService:
    """Собирает варианты и префиллы для manual booking формы."""

    @classmethod
    def get_options(
        cls,
        *,
        actor: User,
        provider_id: int,
        location_id: int | None = None,
        pet_type_id: int | None = None,
        size_code: str | None = None,
        service_id: int | None = None,
        start_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Возвращает unified options payload для manual dialog."""
        provider = Provider.objects.filter(id=provider_id, is_active=True).first()
        if provider is None:
            raise BookingDomainError('manual_booking_provider_not_found', _('Provider not found.'), status_code=404)

        accessible_locations = ManualBookingAccessService.get_accessible_locations(actor, provider)
        resolved_location = None
        is_location_locked = False
        if location_id is not None or len(accessible_locations) == 1:
            resolved_location, is_location_locked, accessible_locations = ManualBookingAccessService.resolve_location(
                actor=actor,
                provider=provider,
                requested_location_id=location_id,
            )

        pet_types = cls._get_pet_types(resolved_location, accessible_locations)
        selected_pet_type = cls._resolve_selected_pet_type(pet_types, pet_type_id)
        breeds = cls._get_breeds(selected_pet_type)
        size_codes = cls._get_size_codes(selected_pet_type)
        services = cls._get_services(resolved_location, selected_pet_type, size_code)
        selected_service = cls._resolve_selected_service(services, service_id)
        specialists = cls._get_specialists(resolved_location, selected_service, start_time)
        auto_employee_id = specialists[0]['id'] if len(specialists) == 1 else None
        emergency_window_hours = ManualBookingSettingsService.get_emergency_window_hours()
        emergency_allowed = bool(
            selected_service
            and selected_service['emergency_capable']
            and ManualBookingSettingsService.is_inside_emergency_window(start_time)
        )

        return {
            'locations': [cls._serialize_location(location) for location in accessible_locations],
            'resolved_location_id': resolved_location.id if resolved_location else None,
            'location_locked': is_location_locked,
            'pet_types': pet_types,
            'breeds': breeds,
            'size_codes': size_codes,
            'services': services,
            'specialists': specialists,
            'auto_prefill': {
                'location_id': resolved_location.id if is_location_locked and resolved_location else None,
                'employee_id': auto_employee_id,
            },
            'service_capabilities': {
                'emergency_capable': selected_service['emergency_capable'] if selected_service else False,
                'protocol_family': selected_service['protocol_family'] if selected_service else 'none',
            },
            'emergency': {
                'window_hours': emergency_window_hours,
                'allowed': emergency_allowed,
            },
        }

    @staticmethod
    def _serialize_location(location: ProviderLocation) -> dict[str, Any]:
        return {
            'id': location.id,
            'name': location.name,
            'full_address': location.get_full_address(),
            'served_pet_types': list(location.served_pet_types.values_list('id', flat=True)),
            'served_pet_types_details': [
                {'id': pet_type.id, 'code': pet_type.code, 'name': pet_type.get_localized_name()}
                for pet_type in location.served_pet_types.all().order_by('name')
            ],
        }

    @staticmethod
    def _get_pet_types(
        selected_location: ProviderLocation | None,
        accessible_locations: list[ProviderLocation],
    ) -> list[dict[str, Any]]:
        if selected_location is not None:
            queryset = selected_location.served_pet_types.all().order_by('name')
        else:
            location_ids = [location.id for location in accessible_locations]
            queryset = PetType.objects.filter(provider_locations_served__id__in=location_ids).distinct().order_by('name')

        return [{'id': pet_type.id, 'code': pet_type.code, 'name': pet_type.get_localized_name()} for pet_type in queryset]

    @staticmethod
    def _resolve_selected_pet_type(pet_types: list[dict[str, Any]], pet_type_id: int | None) -> PetType | None:
        if pet_type_id is None:
            return None
        allowed_ids = {item['id'] for item in pet_types}
        if pet_type_id not in allowed_ids:
            return None
        return PetType.objects.filter(id=pet_type_id).first()

    @staticmethod
    def _resolve_selected_service(
        services: list[dict[str, Any]],
        service_id: int | None,
    ) -> dict[str, Any] | None:
        if service_id is None:
            return None
        for service in services:
            if service['id'] == service_id:
                return service
        return None

    @staticmethod
    def _get_breeds(selected_pet_type: PetType | None) -> list[dict[str, Any]]:
        if selected_pet_type is None:
            return []
        return [
            {'id': breed.id, 'code': breed.code, 'name': breed.get_localized_name()}
            for breed in Breed.objects.filter(pet_type=selected_pet_type).order_by('name')
        ]

    @staticmethod
    def _get_size_codes(selected_pet_type: PetType | None) -> list[dict[str, Any]]:
        if selected_pet_type is None:
            return []
        return [
            {
                'code': rule.size_code,
                'label': rule.size_code,
                'min_weight_kg': str(rule.min_weight_kg),
                'max_weight_kg': str(rule.max_weight_kg),
            }
            for rule in SizeRule.objects.filter(pet_type=selected_pet_type).order_by('min_weight_kg')
        ]

    @staticmethod
    def _get_services(
        selected_location: ProviderLocation | None,
        selected_pet_type: PetType | None,
        size_code: str | None,
    ) -> list[dict[str, Any]]:
        if selected_location is None or selected_pet_type is None or not size_code:
            return []

        queryset = ProviderLocationService.objects.filter(
            location=selected_location,
            pet_type=selected_pet_type,
            size_code=size_code,
            is_active=True,
            service__is_active=True,
            service__is_client_facing=True,
        ).select_related('service').order_by('service__hierarchy_order', 'service__name')

        results = []
        seen: set[int] = set()
        for location_service in queryset:
            service = location_service.service
            if service.id in seen or service.children.exists():
                continue
            seen.add(service.id)
            results.append(
                {
                    'id': service.id,
                    'name': service.get_localized_name(),
                    'code': service.code,
                    'is_client_facing': service.is_client_facing,
                    'emergency_capable': service.resolve_emergency_capable(),
                    'protocol_family': service.resolve_protocol_family(),
                    'price': str(location_service.price),
                    'duration_minutes': int(location_service.duration_minutes),
                }
            )
        return results

    @staticmethod
    def _get_specialists(
        selected_location: ProviderLocation | None,
        selected_service: dict[str, Any] | None,
        start_time: datetime | None,
    ) -> list[dict[str, Any]]:
        if selected_location is None or selected_service is None:
            return []

        service = Service.objects.filter(id=selected_service['id']).first()
        if service is None:
            return []

        employees = BookingAvailabilityService.get_eligible_employees(selected_location, service)
        results = []
        for employee in employees:
            is_available = True
            if start_time is not None:
                end_time = start_time + timedelta(minutes=int(selected_service['duration_minutes']))
                is_available = ManualBookingSchedulingService.employee_can_take_slot(
                    employee=employee,
                    provider_location=selected_location,
                    start_time=start_time,
                    end_time=end_time,
                )
            results.append(
                {
                    'id': employee.id,
                    'name': employee.user.get_full_name() or employee.user.email,
                    'is_available_for_requested_time': is_available,
                }
            )
        return results


class ManualBookingSchedulingService:
    """Расчёт доступности и конфликтов для Manual Booking V2."""

    @classmethod
    def get_location_service(
        cls,
        *,
        provider_location: ProviderLocation,
        service: Service,
        pet_type: PetType,
        size_code: str,
    ) -> ProviderLocationService:
        """Находит price/duration запись по location + service + pet_type + size_code."""
        location_service = ProviderLocationService.objects.filter(
            location=provider_location,
            service=service,
            pet_type=pet_type,
            size_code=size_code,
            is_active=True,
        ).select_related('service').first()
        if location_service is None:
            raise BookingDomainError(
                'manual_booking_service_unavailable',
                _('Service is not available for the selected pet type and size at this location.'),
                status_code=400,
            )
        return location_service

    @classmethod
    def get_conflicting_items(
        cls,
        *,
        employee: Employee,
        start_time: datetime,
        end_time: datetime,
        exclude_manual_booking_id: int | None = None,
        exclude_booking_id: int | None = None,
        lock: bool = False,
    ) -> list[dict[str, Any]]:
        """Возвращает пересекающиеся operational items по сотруднику."""
        booking_queryset = Booking.objects.filter(
            status__name__in=ACTIVE_BOOKING_STATUS_NAMES,
            employee=employee,
            start_time__lt=end_time,
            end_time__gt=start_time,
        ).select_related('user', 'pet', 'provider_location', 'service', 'employee__user')
        manual_queryset = ManualBooking.objects.filter(
            status=BOOKING_STATUS_ACTIVE,
            employee=employee,
            start_time__lt=end_time,
            end_time__gt=start_time,
        ).select_related('lead', 'provider_location', 'service', 'employee__user')

        if exclude_booking_id is not None:
            booking_queryset = booking_queryset.exclude(id=exclude_booking_id)
        if exclude_manual_booking_id is not None:
            manual_queryset = manual_queryset.exclude(id=exclude_manual_booking_id)
        if lock:
            booking_queryset = booking_queryset.select_for_update(of=('self',))
            manual_queryset = manual_queryset.select_for_update(of=('self',))

        results: list[dict[str, Any]] = []
        for booking in booking_queryset:
            results.append(
                {
                    'kind': 'booking',
                    'id': booking.id,
                    'code': booking.code,
                    'start_time': booking.start_time,
                    'end_time': booking.end_time,
                    'owner_name': booking.user.get_full_name() or booking.user.email,
                    'pet_name': booking.pet.name,
                    'service_name': booking.service.get_localized_name(),
                    'location_name': booking.provider_location.name if booking.provider_location else '',
                    'email': booking.user.email,
                }
            )
        for booking in manual_queryset:
            results.append(
                {
                    'kind': 'manual',
                    'id': booking.id,
                    'code': booking.code,
                    'start_time': booking.start_time,
                    'end_time': booking.end_time,
                    'owner_name': f'{booking.owner_first_name} {booking.owner_last_name}'.strip(),
                    'pet_name': booking.pet_name,
                    'service_name': booking.service.get_localized_name(),
                    'location_name': booking.provider_location.name,
                    'email': booking.owner_email,
                }
            )
        results.sort(key=lambda item: item['start_time'])
        return results

    @classmethod
    def employee_can_take_slot(
        cls,
        *,
        employee: Employee,
        provider_location: ProviderLocation,
        start_time: datetime,
        end_time: datetime,
        exclude_manual_booking_id: int | None = None,
        exclude_booking_id: int | None = None,
    ) -> bool:
        """Проверяет рабочее окно и отсутствие конфликтов."""
        if not BookingAvailabilityService.is_employee_working(employee, provider_location, start_time, end_time):
            return False
        conflicts = cls.get_conflicting_items(
            employee=employee,
            start_time=start_time,
            end_time=end_time,
            exclude_manual_booking_id=exclude_manual_booking_id,
            exclude_booking_id=exclude_booking_id,
        )
        return len(conflicts) == 0

    @classmethod
    def resolve_employee(
        cls,
        *,
        provider_location: ProviderLocation,
        service: Service,
        start_time: datetime,
        occupied_duration_minutes: int,
        requested_employee_id: int | None,
        exclude_manual_booking_id: int | None = None,
    ) -> Employee:
        """Разрешает специалиста с учётом optional-create контракта."""
        eligible_employees = BookingAvailabilityService.get_eligible_employees(provider_location, service)
        if not eligible_employees:
            raise BookingDomainError(
                'manual_booking_no_specialists',
                _('No specialists can perform the selected service in this location.'),
                status_code=400,
            )

        end_time = start_time + timedelta(minutes=occupied_duration_minutes)
        if requested_employee_id is not None:
            for employee in eligible_employees:
                if employee.id == requested_employee_id:
                    return employee
            raise BookingDomainError(
                'manual_booking_specialist_invalid',
                _('Selected specialist cannot perform the requested service in this location.'),
                status_code=400,
            )

        immediately_available = [
            employee
            for employee in eligible_employees
            if cls.employee_can_take_slot(
                employee=employee,
                provider_location=provider_location,
                start_time=start_time,
                end_time=end_time,
                exclude_manual_booking_id=exclude_manual_booking_id,
            )
        ]
        if immediately_available:
            return immediately_available[0]
        return eligible_employees[0]

    @classmethod
    def build_alternative_slots(
        cls,
        *,
        provider_location: ProviderLocation,
        service: Service,
        occupied_duration_minutes: int,
        requested_start_time: datetime,
    ) -> list[dict[str, Any]]:
        """Генерирует ближайшие альтернативные слоты для manual booking."""
        alternatives: list[dict[str, Any]] = []
        policy = BookingPolicy.load()
        eligible_employees = BookingAvailabilityService.get_eligible_employees(provider_location, service)
        if not eligible_employees:
            return alternatives

        current_date = requested_start_time.date()
        end_date = current_date + timedelta(days=MANUAL_ALTERNATIVE_DAY_SPAN)
        current_timezone = timezone.get_current_timezone()

        while current_date <= end_date and len(alternatives) < MANUAL_ALTERNATIVE_SLOT_LIMIT:
            location_schedule = BookingAvailabilityService.get_location_schedule(provider_location, current_date)
            if location_schedule is None:
                current_date += timedelta(days=1)
                continue

            for employee in eligible_employees:
                employee_schedule = BookingAvailabilityService.get_employee_schedule(employee, provider_location, current_date)
                if employee_schedule is None:
                    continue
                if (
                    location_schedule.open_time is None
                    or location_schedule.close_time is None
                    or employee_schedule.start_time is None
                    or employee_schedule.end_time is None
                ):
                    continue

                work_start = timezone.make_aware(
                    datetime.combine(current_date, max(location_schedule.open_time, employee_schedule.start_time)),
                    current_timezone,
                )
                work_end = timezone.make_aware(
                    datetime.combine(current_date, min(location_schedule.close_time, employee_schedule.end_time)),
                    current_timezone,
                )
                current_time = max(work_start, requested_start_time)
                while current_time + timedelta(minutes=occupied_duration_minutes) <= work_end:
                    slot_end = current_time + timedelta(minutes=occupied_duration_minutes)
                    if current_time > timezone.now() and cls.employee_can_take_slot(
                        employee=employee,
                        provider_location=provider_location,
                        start_time=current_time,
                        end_time=slot_end,
                    ):
                        alternatives.append(
                            {
                                'start_time': current_time.isoformat(),
                                'end_time': slot_end.isoformat(),
                                'employee_id': employee.id,
                                'employee_name': employee.user.get_full_name() or employee.user.email,
                            }
                        )
                        if len(alternatives) >= MANUAL_ALTERNATIVE_SLOT_LIMIT:
                            return alternatives
                    current_time += timedelta(minutes=policy.slot_step_minutes)
            current_date += timedelta(days=1)

        return alternatives


class ManualBookingServiceV2:
    """Основной application service для Manual Booking V2."""

    @classmethod
    @transaction.atomic
    def create_manual_booking(cls, *, actor: User, payload: dict[str, Any]) -> ManualBooking:
        """Создаёт provider-owned manual booking."""
        context = cls._resolve_context(actor=actor, payload=payload)
        return cls._create_from_context(actor=actor, context=context)

    @classmethod
    @transaction.atomic
    def update_manual_booking(cls, *, actor: User, manual_booking: ManualBooking, payload: dict[str, Any]) -> ManualBooking:
        """Обновляет редактируемые поля manual booking."""
        ManualBookingAccessService.ensure_provider_staff(actor, manual_booking.provider)
        locked_booking = ManualBooking.objects.select_for_update().select_related(
            'provider',
            'provider_location',
            'lead',
            'service',
            'pet_type',
            'breed',
            'employee__user',
        ).get(id=manual_booking.id)
        if locked_booking.status != BOOKING_STATUS_ACTIVE:
            raise BookingDomainError(
                'manual_booking_not_editable',
                _('Only active manual bookings can be edited.'),
                status_code=400,
            )

        mutable_payload = {
            'provider_id': locked_booking.provider_id,
            'provider_location_id': payload.get('provider_location_id', locked_booking.provider_location_id),
            'employee_id': payload.get('employee_id', locked_booking.employee_id),
            'service_id': payload.get('service_id', locked_booking.service_id),
            'pet_type_id': payload.get('pet_type_id', locked_booking.pet_type_id),
            'breed_id': payload.get('breed_id', locked_booking.breed_id),
            'size_code': payload.get('size_code', locked_booking.size_code),
            'owner_first_name': payload.get('owner_first_name', locked_booking.owner_first_name),
            'owner_last_name': payload.get('owner_last_name', locked_booking.owner_last_name),
            'owner_phone_number': payload.get('owner_phone_number', str(locked_booking.owner_phone_number)),
            'owner_email': payload.get('owner_email', locked_booking.owner_email),
            'pet_name': payload.get('pet_name', locked_booking.pet_name),
            'notes': payload.get('notes', locked_booking.notes),
            'is_emergency': payload.get('is_emergency', locked_booking.is_emergency),
            'start_time': payload.get('start_time', locked_booking.start_time),
        }
        context = cls._resolve_context(
            actor=actor,
            payload=mutable_payload,
            existing_manual_booking=locked_booking,
        )

        locked_booking.provider_location = context.provider_location
        locked_booking.employee = context.employee
        locked_booking.service = context.service
        locked_booking.pet_type = context.pet_type
        locked_booking.breed = context.breed
        locked_booking.size_code = context.size_code
        locked_booking.lead = context.lead
        locked_booking.owner_first_name = context.owner_first_name
        locked_booking.owner_last_name = context.owner_last_name
        locked_booking.owner_phone_number = context.owner_phone_number
        locked_booking.owner_email = context.owner_email
        locked_booking.pet_name = context.pet_name
        locked_booking.notes = context.notes
        locked_booking.is_emergency = context.is_emergency
        locked_booking.start_time = context.start_time
        locked_booking.end_time = context.end_time
        locked_booking.occupied_duration_minutes = context.occupied_duration_minutes
        locked_booking.price = context.price
        locked_booking.updated_by = actor
        locked_booking.save()
        return locked_booking

    @classmethod
    @transaction.atomic
    def cancel_manual_booking(
        cls,
        *,
        actor: User,
        manual_booking: ManualBooking,
        cancellation_reason: BookingCancellationReason,
        cancellation_reason_text: str = '',
    ) -> ManualBooking:
        """Отменяет manual booking без abuse checks."""
        ManualBookingAccessService.ensure_provider_staff(actor, manual_booking.provider)
        locked_booking = ManualBooking.objects.select_for_update().get(id=manual_booking.id)
        if locked_booking.status != BOOKING_STATUS_ACTIVE:
            raise BookingDomainError(
                'manual_booking_cannot_cancel',
                _('Only active manual bookings can be cancelled.'),
                status_code=400,
            )
        locked_booking.cancel(
            by_user=actor,
            cancellation_reason=cancellation_reason,
            cancellation_reason_text=cancellation_reason_text,
        )
        return locked_booking

    @classmethod
    @transaction.atomic
    def complete_manual_booking(cls, *, actor: User, manual_booking: ManualBooking) -> ManualBooking:
        """Завершает manual booking."""
        ManualBookingAccessService.ensure_provider_staff(actor, manual_booking.provider)
        locked_booking = ManualBooking.objects.select_for_update().get(id=manual_booking.id)
        if locked_booking.status != BOOKING_STATUS_ACTIVE:
            raise BookingDomainError(
                'manual_booking_cannot_complete',
                _('Only active manual bookings can be completed.'),
                status_code=400,
            )
        if timezone.now() < locked_booking.start_time:
            raise BookingDomainError(
                'manual_booking_future_completion',
                _('Manual booking cannot be completed before start time.'),
                status_code=400,
            )
        locked_booking.complete(by_user=actor)
        return locked_booking

    @classmethod
    @transaction.atomic
    def upsert_protocol(
        cls,
        *,
        actor: User,
        manual_booking: ManualBooking,
        payload: dict[str, Any],
    ) -> ManualVisitProtocol:
        """Создаёт или обновляет provider-only протокол manual booking."""
        ManualBookingAccessService.ensure_provider_staff(actor, manual_booking.provider)
        if not manual_booking.requires_protocol:
            raise BookingDomainError(
                'manual_booking_protocol_unavailable',
                _('This service does not require a visit protocol.'),
                status_code=400,
            )

        locked_booking = ManualBooking.objects.select_for_update().select_related('service', 'provider_location').get(id=manual_booking.id)
        protocol = getattr(locked_booking, 'manual_visit_protocol', None)
        if protocol is None:
            protocol = ManualVisitProtocol(
                manual_booking=locked_booking,
                protocol_family=locked_booking.protocol_family,
                provider_location=locked_booking.provider_location,
                service=locked_booking.service,
                employee=locked_booking.employee,
                date=locked_booking.start_time,
                created_by=actor,
                updated_by=actor,
            )
        else:
            protocol = ManualVisitProtocol.objects.select_for_update().get(id=protocol.id)
            protocol.updated_by = actor
            protocol.employee = locked_booking.employee

        for field in ('description', 'diagnosis', 'anamnesis', 'results', 'recommendations', 'notes', 'serial_number'):
            if field in payload:
                setattr(protocol, field, (payload.get(field) or '').strip())
        if 'next_date' in payload:
            protocol.next_date = payload.get('next_date') or None
        protocol.save()
        return protocol

    @classmethod
    @transaction.atomic
    def resolve_emergency_conflict(
        cls,
        *,
        actor: User,
        payload: dict[str, Any],
    ) -> ManualBooking:
        """Разрешает emergency-конфликт и создаёт manual booking."""
        resolution_action = payload.get('resolution_action')
        if resolution_action == 'abort':
            raise BookingDomainError('manual_booking_emergency_aborted', _('Emergency booking was aborted.'), status_code=400)

        conflict_kind = payload.get('conflict_kind')
        conflict_id = payload.get('conflict_id')
        if conflict_kind not in {'booking', 'manual'} or not conflict_id:
            raise BookingDomainError(
                'manual_booking_resolution_target_required',
                _('Conflict target is required for emergency resolution.'),
                status_code=400,
            )

        creation_payload = dict(payload)
        creation_payload.pop('resolution_action', None)
        creation_payload.pop('conflict_kind', None)
        creation_payload.pop('conflict_id', None)
        move_start_time = creation_payload.pop('move_start_time', None)

        context = cls._resolve_context(actor=actor, payload=creation_payload)
        if not context.is_emergency:
            raise BookingDomainError(
                'manual_booking_resolution_requires_emergency',
                _('Conflict resolution is available only for emergency manual bookings.'),
                status_code=400,
            )

        if resolution_action == 'cancel_conflict':
            cls.cancel_conflicting_item(actor=actor, kind=conflict_kind, item_id=int(conflict_id))
        elif resolution_action == 'move_conflict':
            if not move_start_time:
                raise BookingDomainError(
                    'manual_booking_move_start_time_required',
                    _('New start time is required when moving a conflicting booking.'),
                    status_code=400,
                )
            cls.move_conflicting_item(
                actor=actor,
                kind=conflict_kind,
                item_id=int(conflict_id),
                new_start_time=move_start_time,
            )
        else:
            raise BookingDomainError(
                'manual_booking_resolution_action_invalid',
                _('Unsupported emergency conflict resolution action.'),
                status_code=400,
            )

        return cls._create_from_context(actor=actor, context=context)

    @classmethod
    def _resolve_context(
        cls,
        *,
        actor: User,
        payload: dict[str, Any],
        existing_manual_booking: ManualBooking | None = None,
    ) -> ManualResolvedContext:
        """Проверяет payload и собирает нормализованный контекст создания."""
        provider = Provider.objects.filter(id=payload['provider_id'], is_active=True).first()
        if provider is None:
            raise BookingDomainError('manual_booking_provider_not_found', _('Provider not found.'), status_code=404)

        provider_location, _resolved_provider, _accessible_locations = ManualBookingAccessService.resolve_location(
            actor=actor,
            provider=provider,
            requested_location_id=payload.get('provider_location_id'),
        )

        start_time = payload.get('start_time')
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        if start_time is None or not isinstance(start_time, datetime):
            raise BookingDomainError('manual_booking_start_time_required', _('Start time is required.'), status_code=400)
        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time, timezone.get_current_timezone())
        if start_time <= timezone.now():
            raise BookingDomainError('manual_booking_past_start_time', _('Manual booking time must be in the future.'), status_code=400)

        service = Service.objects.filter(id=payload['service_id'], is_active=True).first()
        if service is None:
            raise BookingDomainError('manual_booking_service_not_found', _('Service not found.'), status_code=404)
        if service.children.exists():
            raise BookingDomainError('manual_booking_service_not_leaf', _('Manual booking supports only leaf services.'), status_code=400)
        if not service.is_client_facing:
            raise BookingDomainError('manual_booking_service_not_client_facing', _('Technical services cannot be used for manual booking.'), status_code=400)

        pet_type = PetType.objects.filter(id=payload['pet_type_id']).first()
        if pet_type is None:
            raise BookingDomainError('manual_booking_pet_type_not_found', _('Pet type not found.'), status_code=404)
        if not provider_location.served_pet_types.filter(id=pet_type.id).exists():
            raise BookingDomainError(
                'manual_booking_pet_type_forbidden',
                _('Selected location does not serve this pet type.'),
                status_code=400,
            )

        breed = Breed.objects.filter(id=payload['breed_id'], pet_type=pet_type).first()
        if breed is None:
            raise BookingDomainError('manual_booking_breed_not_found', _('Breed not found for the selected pet type.'), status_code=404)

        size_code = (payload.get('size_code') or '').strip()
        if not size_code:
            raise BookingDomainError('manual_booking_size_code_required', _('Size code is required.'), status_code=400)

        location_service = ManualBookingSchedulingService.get_location_service(
            provider_location=provider_location,
            service=service,
            pet_type=pet_type,
            size_code=size_code,
        )
        occupied_duration_minutes = int(location_service.duration_minutes)
        price = Decimal(location_service.price)
        end_time = start_time + timedelta(minutes=occupied_duration_minutes)

        is_emergency = bool(payload.get('is_emergency'))
        if is_emergency:
            if not service.resolve_emergency_capable():
                raise BookingDomainError(
                    'manual_booking_emergency_not_supported',
                    _('The selected service does not support emergency booking.'),
                    status_code=400,
                )
            if not ManualBookingSettingsService.is_inside_emergency_window(start_time):
                raise BookingDomainError(
                    'emergency_window_exceeded',
                    _('Emergency manual booking is allowed only inside the emergency time window.'),
                    status_code=400,
                )

        employee = ManualBookingSchedulingService.resolve_employee(
            provider_location=provider_location,
            service=service,
            start_time=start_time,
            occupied_duration_minutes=occupied_duration_minutes,
            requested_employee_id=payload.get('employee_id'),
            exclude_manual_booking_id=existing_manual_booking.id if existing_manual_booking else None,
        )

        owner_first_name = (payload.get('owner_first_name') or '').strip()
        owner_last_name = (payload.get('owner_last_name') or '').strip()
        pet_name = (payload.get('pet_name') or '').strip()
        owner_phone_number = cls._normalize_phone(str(payload.get('owner_phone_number') or ''))
        owner_email = (payload.get('owner_email') or '').strip().lower()
        if not owner_first_name or not owner_last_name or not pet_name:
            raise BookingDomainError(
                'manual_booking_snapshot_required',
                _('Owner name and pet name are required.'),
                status_code=400,
            )

        lead = cls._get_or_create_lead(
            provider=provider,
            provider_location=provider_location,
            owner_first_name=owner_first_name,
            owner_last_name=owner_last_name,
            owner_phone_number=owner_phone_number,
            owner_email=owner_email,
        )

        return ManualResolvedContext(
            provider=provider,
            provider_location=provider_location,
            employee=employee,
            service=service,
            pet_type=pet_type,
            breed=breed,
            size_code=size_code,
            lead=lead,
            owner_first_name=owner_first_name,
            owner_last_name=owner_last_name,
            owner_phone_number=owner_phone_number,
            owner_email=owner_email,
            pet_name=pet_name,
            notes=(payload.get('notes') or '').strip(),
            is_emergency=is_emergency,
            start_time=start_time,
            end_time=end_time,
            occupied_duration_minutes=occupied_duration_minutes,
            price=price,
        )

    @classmethod
    def _create_from_context(cls, *, actor: User, context: ManualResolvedContext) -> ManualBooking:
        """Переиспользуемая ветка финального создания manual booking."""
        locked_employees = list(
            Employee.objects.select_for_update().filter(
                id__in=[employee.id for employee in BookingAvailabilityService.get_eligible_employees(context.provider_location, context.service)],
            )
        )
        if context.employee.id not in {employee.id for employee in locked_employees}:
            raise BookingDomainError(
                'manual_booking_specialist_invalid',
                _('Selected specialist is no longer available for this service.'),
                status_code=409,
            )

        conflicts = ManualBookingSchedulingService.get_conflicting_items(
            employee=context.employee,
            start_time=context.start_time,
            end_time=context.end_time,
            lock=True,
        )
        if conflicts:
            alternatives = ManualBookingSchedulingService.build_alternative_slots(
                provider_location=context.provider_location,
                service=context.service,
                occupied_duration_minutes=context.occupied_duration_minutes,
                requested_start_time=context.start_time,
            )
            raise BookingDomainError(
                'manual_booking_emergency_conflict' if context.is_emergency else 'manual_booking_conflict',
                _('The requested slot is unavailable.'),
                status_code=409,
                details={
                    'alternative_slots': cls._serialize_alternative_slots(alternatives),
                    'conflicting_bookings': cls._serialize_conflicts(conflicts),
                    'requires_resolution': context.is_emergency,
                },
            )

        return ManualBooking.objects.create(
            provider=context.provider,
            provider_location=context.provider_location,
            lead=context.lead,
            employee=context.employee,
            service=context.service,
            pet_type=context.pet_type,
            breed=context.breed,
            size_code=context.size_code,
            owner_first_name=context.owner_first_name,
            owner_last_name=context.owner_last_name,
            owner_phone_number=context.owner_phone_number,
            owner_email=context.owner_email,
            pet_name=context.pet_name,
            notes=context.notes,
            is_emergency=context.is_emergency,
            start_time=context.start_time,
            end_time=context.end_time,
            occupied_duration_minutes=context.occupied_duration_minutes,
            price=context.price,
            created_by=actor,
            updated_by=actor,
        )

    @classmethod
    def _get_or_create_lead(
        cls,
        *,
        provider: Provider,
        provider_location: ProviderLocation,
        owner_first_name: str,
        owner_last_name: str,
        owner_phone_number: str,
        owner_email: str,
    ) -> ProviderClientLead:
        """Создаёт или обновляет provider-owned lead по уникальному телефону."""
        lead = ProviderClientLead.objects.select_for_update().filter(
            provider=provider,
            normalized_phone_number=owner_phone_number,
        ).first()
        if lead is None:
            return ProviderClientLead.objects.create(
                provider=provider,
                provider_location=provider_location,
                first_name=owner_first_name,
                last_name=owner_last_name,
                phone_number=owner_phone_number,
                normalized_phone_number=owner_phone_number,
                email=owner_email,
            )

        lead.provider_location = provider_location
        lead.first_name = owner_first_name
        lead.last_name = owner_last_name
        lead.phone_number = owner_phone_number
        lead.email = owner_email
        lead.save()
        return lead

    @staticmethod
    def _normalize_phone(value: str) -> str:
        """Нормализует телефон в E.164 для identity key."""
        try:
            parsed = phonenumbers.parse(value, None)
        except phonenumbers.NumberParseException as exc:
            raise BookingDomainError(
                'manual_booking_phone_invalid',
                _('Owner phone number is invalid.'),
                status_code=400,
            ) from exc
        if not phonenumbers.is_possible_number(parsed) or not phonenumbers.is_valid_number(parsed):
            raise BookingDomainError(
                'manual_booking_phone_invalid',
                _('Owner phone number is invalid.'),
                status_code=400,
            )
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    @staticmethod
    def _serialize_alternative_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                'start_time': slot['start_time'],
                'end_time': slot['end_time'],
                'employee_id': slot['employee_id'],
                'employee_name': slot['employee_name'],
            }
            for slot in slots
        ]

    @staticmethod
    def _serialize_conflicts(conflicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                'kind': conflict['kind'],
                'id': conflict['id'],
                'code': conflict['code'],
                'start_time': conflict['start_time'].isoformat(),
                'end_time': conflict['end_time'].isoformat(),
                'owner_name': conflict['owner_name'],
                'pet_name': conflict['pet_name'],
                'service_name': conflict['service_name'],
                'location_name': conflict['location_name'],
                'email': conflict['email'],
            }
            for conflict in conflicts
        ]

    @classmethod
    def cancel_conflicting_item(cls, *, actor: User, kind: str, item_id: int) -> None:
        """Отменяет конфликтующий operational item по emergency preemption."""
        cancellation_reason = BookingCancellationReason.objects.filter(
            code=CANCELLATION_REASON_PROVIDER_EMERGENCY_PREEMPTION,
            is_active=True,
        ).first()
        if cancellation_reason is None:
            raise BookingDomainError(
                'manual_booking_emergency_reason_missing',
                _('Emergency preemption cancellation reason is not configured.'),
                status_code=500,
            )

        if kind == 'booking':
            booking = Booking.objects.select_for_update().select_related('user', 'provider_location').get(id=item_id)
            booking.cancel_booking(
                cancelled_by=CANCELLED_BY_PROVIDER,
                cancelled_by_user=actor,
                cancellation_reason=cancellation_reason,
                cancellation_reason_text='',
            )
            cls._send_platform_preemption_email(booking)
            return

        booking = ManualBooking.objects.select_for_update().get(id=item_id)
        booking.cancel(
            by_user=actor,
            cancellation_reason=cancellation_reason,
            cancellation_reason_text='',
        )

    @classmethod
    def move_conflicting_item(
        cls,
        *,
        actor: User,
        kind: str,
        item_id: int,
        new_start_time: str | datetime,
    ) -> None:
        """Переносит конфликтующую запись на новый слот."""
        if isinstance(new_start_time, str):
            new_start_time = datetime.fromisoformat(new_start_time.replace('Z', '+00:00'))
        if timezone.is_naive(new_start_time):
            new_start_time = timezone.make_aware(new_start_time, timezone.get_current_timezone())

        if kind == 'booking':
            booking = Booking.objects.select_for_update().select_related(
                'provider_location',
                'service',
                'pet',
                'employee',
                'user',
                'escort_owner',
            ).get(id=item_id)
            validation = BookingAvailabilityService.validate_booking_request(
                requester=cast(User, booking.user),
                pet=booking.pet,
                provider_location=cast(ProviderLocation, booking.provider_location),
                service=booking.service,
                start_time=new_start_time,
                employee=booking.employee,
                escort_owner=cast(User | None, booking.escort_owner),
                exclude_booking_id=booking.id,
            )
            if not validation.is_bookable:
                raise BookingDomainError(
                    'manual_booking_conflict_move_unavailable',
                    _('Conflicting booking cannot be moved to the selected slot.'),
                    status_code=409,
                    details={
                        'failure_code': validation.failure_code,
                        'conflicting_bookings': validation.conflicting_bookings,
                    },
                )
            booking.start_time = validation.start_time
            booking.end_time = validation.end_time
            booking.occupied_duration_minutes = validation.occupied_duration_minutes
            booking.employee = validation.employee or booking.employee
            booking.save()
            cls._send_platform_move_email(booking)
            return

        manual_booking = ManualBooking.objects.select_for_update().select_related(
            'provider',
            'provider_location',
            'service',
            'pet_type',
            'breed',
            'lead',
        ).get(id=item_id)
        payload = {
            'provider_id': manual_booking.provider_id,
            'provider_location_id': manual_booking.provider_location_id,
            'employee_id': manual_booking.employee_id,
            'service_id': manual_booking.service_id,
            'pet_type_id': manual_booking.pet_type_id,
            'breed_id': manual_booking.breed_id,
            'size_code': manual_booking.size_code,
            'owner_first_name': manual_booking.owner_first_name,
            'owner_last_name': manual_booking.owner_last_name,
            'owner_phone_number': str(manual_booking.owner_phone_number),
            'owner_email': manual_booking.owner_email,
            'pet_name': manual_booking.pet_name,
            'notes': manual_booking.notes,
            'is_emergency': manual_booking.is_emergency,
            'start_time': new_start_time,
        }
        context = cls._resolve_context(actor=actor, payload=payload, existing_manual_booking=manual_booking)
        manual_booking.provider_location = context.provider_location
        manual_booking.employee = context.employee
        manual_booking.service = context.service
        manual_booking.pet_type = context.pet_type
        manual_booking.breed = context.breed
        manual_booking.size_code = context.size_code
        manual_booking.start_time = context.start_time
        manual_booking.end_time = context.end_time
        manual_booking.occupied_duration_minutes = context.occupied_duration_minutes
        manual_booking.price = context.price
        manual_booking.updated_by = actor
        manual_booking.save()

    @staticmethod
    def _send_platform_preemption_email(booking: Booking) -> None:
        """Отправляет email владельцу platform booking при emergency preemption."""
        if not booking.user.email:
            return
        send_mail(
            subject=str(_('Your booking was cancelled due to an emergency case')),
            message=str(
                _('Your booking %(code)s at %(location)s was cancelled because the provider had to free the slot for an emergency case.')
            ) % {
                'code': booking.code,
                'location': booking.provider_location.name if booking.provider_location else '',
            },
            from_email=None,
            recipient_list=[booking.user.email],
            fail_silently=True,
        )

    @staticmethod
    def _send_platform_move_email(booking: Booking) -> None:
        """Отправляет email владельцу platform booking при emergency move."""
        if not booking.user.email:
            return
        send_mail(
            subject=str(_('Your booking was moved due to an emergency case')),
            message=str(
                _('Your booking %(code)s was moved to %(start_time)s because the provider had to resolve an emergency case.')
            ) % {
                'code': booking.code,
                'start_time': timezone.localtime(booking.start_time).strftime('%Y-%m-%d %H:%M'),
            },
            from_email=None,
            recipient_list=[booking.user.email],
            fail_silently=True,
        )


class ProtocolDocumentService:
    """Генерация локализованных print/PDF документов для протокола визита."""

    PRINT_TEMPLATE = Template(
        """
        <html>
          <head>
            <meta charset="utf-8" />
            <title>{{ document.title }}</title>
            <style>
              body { font-family: Arial, sans-serif; margin: 24px; color: #111827; }
              h1, h2 { margin: 0 0 8px; }
              h2 { margin-top: 24px; }
              .subtitle { margin: 6px 0 18px; color: #4b5563; }
              .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
              .card { border: 1px solid #d1d5db; border-radius: 12px; padding: 12px; break-inside: avoid; }
              .label { font-size: 12px; text-transform: uppercase; color: #6b7280; margin-bottom: 4px; }
              .value { font-size: 14px; white-space: pre-wrap; }
            </style>
          </head>
          <body>
            <h1>{{ document.title }}</h1>
            <p class="subtitle">{{ document.subtitle }}</p>
            <div class="grid">
              {% for item in document.summary %}
                <div class="card">
                  <div class="label">{{ item.label }}</div>
                  <div class="value">{{ item.value }}</div>
                </div>
              {% endfor %}
            </div>
            <h2>{{ document.protocol_title }}</h2>
            {% if document.fields %}
              {% for field in document.fields %}
                <div class="card" style="margin-bottom: 12px;">
                  <div class="label">{{ field.label }}</div>
                  <div class="value">{{ field.value }}</div>
                </div>
              {% endfor %}
            {% else %}
              <div class="card">
                <div class="value">{{ document.empty_protocol_message }}</div>
              </div>
            {% endif %}
            <script>
              window.addEventListener("load", function () {
                setTimeout(function () {
                  window.focus();
                  window.print();
                }, 150);
              });
            </script>
          </body>
        </html>
        """
    )
    FONT_CANDIDATES = (
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    DOCUMENT_LABELS = {
        'en': {
            'booking_code': 'Booking code',
            'date': 'Date',
            'owner': 'Owner',
            'phone': 'Phone',
            'pet': 'Pet',
            'pet_descriptor': 'Pet type / breed / size',
            'location': 'Location',
            'specialist': 'Specialist',
            'protocol': 'Visit protocol',
            'empty_protocol': 'The protocol is empty.',
            'description': 'Description',
            'anamnesis': 'Anamnesis',
            'diagnosis': 'Diagnosis',
            'results': 'Results',
            'recommendations': 'Recommendations',
            'notes': 'Notes',
            'serial_number': 'Serial number',
            'next_date': 'Next date',
        },
        'ru': {
            'booking_code': 'Код записи',
            'date': 'Дата',
            'owner': 'Владелец',
            'phone': 'Телефон',
            'pet': 'Питомец',
            'pet_descriptor': 'Тип / порода / размер',
            'location': 'Филиал',
            'specialist': 'Специалист',
            'protocol': 'Протокол визита',
            'empty_protocol': 'Протокол пока пуст.',
            'description': 'Описание',
            'anamnesis': 'Анамнез',
            'diagnosis': 'Диагноз',
            'results': 'Результаты',
            'recommendations': 'Рекомендации',
            'notes': 'Заметки',
            'serial_number': 'Серийный номер',
            'next_date': 'Следующая дата',
        },
        'de': {
            'booking_code': 'Buchungscode',
            'date': 'Datum',
            'owner': 'Besitzer',
            'phone': 'Telefon',
            'pet': 'Tier',
            'pet_descriptor': 'Tierart / Rasse / Größe',
            'location': 'Filiale',
            'specialist': 'Fachkraft',
            'protocol': 'Besuchsprotokoll',
            'empty_protocol': 'Das Protokoll ist noch leer.',
            'description': 'Beschreibung',
            'anamnesis': 'Anamnese',
            'diagnosis': 'Diagnose',
            'results': 'Ergebnisse',
            'recommendations': 'Empfehlungen',
            'notes': 'Notizen',
            'serial_number': 'Seriennummer',
            'next_date': 'Nächstes Datum',
        },
        'me': {
            'booking_code': 'Kod rezervacije',
            'date': 'Datum',
            'owner': 'Vlasnik',
            'phone': 'Telefon',
            'pet': 'Ljubimac',
            'pet_descriptor': 'Tip / rasa / veličina',
            'location': 'Filijala',
            'specialist': 'Specijalista',
            'protocol': 'Protokol posjete',
            'empty_protocol': 'Protokol je za sada prazan.',
            'description': 'Opis',
            'anamnesis': 'Anamneza',
            'diagnosis': 'Dijagnoza',
            'results': 'Rezultati',
            'recommendations': 'Preporuke',
            'notes': 'Bilješke',
            'serial_number': 'Serijski broj',
            'next_date': 'Sljedeći datum',
        },
    }

    @classmethod
    def render_manual_print_response(cls, protocol: ManualVisitProtocol) -> HttpResponse:
        return cls._render_print_response(cls._build_manual_document(protocol))

    @classmethod
    def render_manual_pdf_response(cls, protocol: ManualVisitProtocol) -> HttpResponse:
        manual_booking = protocol.manual_booking
        return cls._render_pdf_response(
            document=cls._build_manual_document(protocol),
            filename=f'{manual_booking.code}.pdf',
        )

    @classmethod
    def render_booking_print_response(cls, booking: Booking) -> HttpResponse:
        return cls._render_print_response(cls._build_booking_document(booking))

    @classmethod
    def render_booking_pdf_response(cls, booking: Booking) -> HttpResponse:
        return cls._render_pdf_response(
            document=cls._build_booking_document(booking),
            filename=f'{booking.code}.pdf',
        )

    @classmethod
    def _render_print_response(cls, document: dict[str, Any]) -> HttpResponse:
        html = cls.PRINT_TEMPLATE.render(Context({'document': document}))
        return HttpResponse(html, content_type='text/html; charset=utf-8')

    @classmethod
    def _render_pdf_response(cls, *, document: dict[str, Any], filename: str) -> HttpResponse:
        pdf_bytes = cls._build_unicode_pdf(cls._build_pdf_lines(document))
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @classmethod
    def _build_manual_document(cls, protocol: ManualVisitProtocol) -> dict[str, Any]:
        booking = protocol.manual_booking
        return cls._build_document(
            code=booking.code,
            service_name=booking.service.get_localized_name(),
            start_time=booking.start_time,
            owner_name=f'{booking.owner_first_name} {booking.owner_last_name}'.strip(),
            owner_phone=str(booking.owner_phone_number),
            pet_name=booking.pet_name,
            pet_type_name=booking.pet_type.get_localized_name(),
            breed_name=booking.breed.get_localized_name(),
            size_code=booking.size_code,
            location_name=booking.provider_location.name,
            employee_name=booking.employee.user.get_full_name() if booking.employee else '',
            protocol_fields=cls._extract_protocol_fields(
                description=protocol.description,
                anamnesis=protocol.anamnesis,
                diagnosis=protocol.diagnosis,
                results=protocol.results,
                recommendations=protocol.recommendations,
                notes=protocol.notes,
                serial_number=protocol.serial_number,
                next_date=protocol.next_date,
            ),
        )

    @classmethod
    def _build_booking_document(cls, booking: Booking) -> dict[str, Any]:
        visit_record = booking.visit_record
        if visit_record is None:
            raise BookingDomainError(
                'visit_record_document_unavailable',
                _('Visit protocol is not available for this booking.'),
                status_code=400,
            )

        escort = booking.escort_owner or booking.user
        return cls._build_document(
            code=booking.code,
            service_name=booking.service.get_localized_name() if booking.service else booking.code,
            start_time=booking.start_time,
            owner_name=escort.get_full_name() or escort.email,
            owner_phone=escort.phone_number or booking.user.phone_number or '',
            pet_name=booking.pet.name,
            pet_type_name=booking.pet.pet_type.get_localized_name() if booking.pet.pet_type_id else '',
            breed_name=booking.pet.breed.get_localized_name() if booking.pet.breed_id else '',
            size_code='',
            location_name=booking.provider_location.name if booking.provider_location_id else '',
            employee_name=booking.employee.user.get_full_name() if booking.employee_id else '',
            protocol_fields=cls._extract_protocol_fields(
                description=visit_record.description,
                anamnesis=visit_record.anamnesis,
                diagnosis=visit_record.diagnosis,
                results=visit_record.results,
                recommendations=visit_record.recommendations,
                notes=visit_record.notes,
                serial_number=visit_record.serial_number,
                next_date=visit_record.next_date,
            ),
        )

    @classmethod
    def _build_document(
        cls,
        *,
        code: str,
        service_name: str,
        start_time: datetime,
        owner_name: str,
        owner_phone: str,
        pet_name: str,
        pet_type_name: str,
        breed_name: str,
        size_code: str,
        location_name: str,
        employee_name: str,
        protocol_fields: list[dict[str, str]],
    ) -> dict[str, Any]:
        labels = cls._get_document_labels()
        pet_descriptor_parts = [part for part in [pet_type_name, breed_name, size_code] if part]
        summary = [
            {'label': labels['booking_code'], 'value': code},
            {'label': labels['date'], 'value': cls._format_datetime(start_time)},
            {'label': labels['owner'], 'value': owner_name},
            {'label': labels['phone'], 'value': owner_phone},
            {'label': labels['pet'], 'value': pet_name},
        ]
        if pet_descriptor_parts:
            summary.append(
                {
                    'label': labels['pet_descriptor'],
                    'value': ' / '.join(pet_descriptor_parts),
                }
            )
        if location_name:
            summary.append({'label': labels['location'], 'value': location_name})
        if employee_name:
            summary.append({'label': labels['specialist'], 'value': employee_name})

        return {
            'title': service_name,
            'subtitle': escape(labels['protocol']),
            'protocol_title': labels['protocol'],
            'empty_protocol_message': labels['empty_protocol'],
            'summary': summary,
            'fields': protocol_fields,
        }

    @classmethod
    def _extract_protocol_fields(
        cls,
        *,
        description: str | None,
        anamnesis: str | None,
        diagnosis: str | None,
        results: str | None,
        recommendations: str | None,
        notes: str | None,
        serial_number: str | None,
        next_date,
    ) -> list[dict[str, str]]:
        labels = cls._get_document_labels()
        fields = [
            (labels['description'], description),
            (labels['anamnesis'], anamnesis),
            (labels['diagnosis'], diagnosis),
            (labels['results'], results),
            (labels['recommendations'], recommendations),
            (labels['notes'], notes),
            (labels['serial_number'], serial_number),
            (labels['next_date'], cls._format_date(next_date) if next_date else ''),
        ]
        return [
            {'label': label, 'value': value.strip()}
            for label, value in fields
            if isinstance(value, str) and value.strip()
        ]

    @classmethod
    def _build_pdf_lines(cls, document: dict[str, Any]) -> list[str]:
        lines = [document['title'], document['protocol_title'], '']
        for item in document['summary']:
            lines.append(f"{item['label']}: {item['value']}")
        lines.append('')
        if document['fields']:
            for field in document['fields']:
                lines.append(f"{field['label']}: {field['value']}")
        else:
            lines.append(document['empty_protocol_message'])
        return lines

    @classmethod
    def _build_unicode_pdf(cls, lines: list[str]) -> bytes:
        page_width, page_height = 1240, 1754
        margin = 90
        line_spacing = 18
        title_font = cls._load_font(32)
        body_font = cls._load_font(22)
        pages: list[Image.Image] = []

        image = Image.new('RGB', (page_width, page_height), 'white')
        draw = ImageDraw.Draw(image)
        y = margin

        def flush_page() -> None:
            nonlocal image, draw, y
            pages.append(image)
            image = Image.new('RGB', (page_width, page_height), 'white')
            draw = ImageDraw.Draw(image)
            y = margin

        for index, raw_line in enumerate(lines):
            font = title_font if index == 0 else body_font
            wrapped_lines = cls._wrap_text(draw, raw_line, font, page_width - margin * 2)
            if not wrapped_lines:
                wrapped_lines = ['']
            for wrapped_line in wrapped_lines:
                bbox = draw.textbbox((0, 0), wrapped_line or ' ', font=font)
                line_height = max((bbox[3] - bbox[1]) + line_spacing, 28)
                if y + line_height > page_height - margin:
                    flush_page()
                draw.text((margin, y), wrapped_line, font=font, fill='#111827')
                y += line_height
            y += 6

        if not pages or image.getbbox() is not None:
            pages.append(image)

        buffer = BytesIO()
        rgb_pages = [page.convert('RGB') for page in pages]
        rgb_pages[0].save(
            buffer,
            format='PDF',
            save_all=True,
            append_images=rgb_pages[1:],
            resolution=150.0,
        )
        return buffer.getvalue()

    @classmethod
    def _wrap_text(
        cls,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        if not text:
            return ['']
        words = text.split()
        if not words:
            return ['']

        lines: list[str] = []
        current_line = words[0]
        for word in words[1:]:
            candidate = f'{current_line} {word}'
            if draw.textlength(candidate, font=font) <= max_width:
                current_line = candidate
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)
        return lines

    @classmethod
    def _load_font(cls, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for font_path in cls.FONT_CANDIDATES:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size=size)
        return ImageFont.load_default()

    @classmethod
    def _get_document_labels(cls) -> dict[str, str]:
        language = (translation.get_language() or 'en').lower()
        if language.startswith('ru'):
            return cls.DOCUMENT_LABELS['ru']
        if language.startswith('de'):
            return cls.DOCUMENT_LABELS['de']
        if language.startswith('me') or language.startswith('sr') or language.startswith('bs'):
            return cls.DOCUMENT_LABELS['me']
        return cls.DOCUMENT_LABELS['en']

    @staticmethod
    def _format_datetime(value: datetime) -> str:
        return timezone.localtime(value).strftime('%d.%m.%Y %H:%M')

    @staticmethod
    def _format_date(value) -> str:
        return value.strftime('%d.%m.%Y')


class ManualBookingDocumentService:
    """Совместимость со старым manual-only API поверх общего document service."""

    @classmethod
    def render_print_response(cls, protocol: ManualVisitProtocol) -> HttpResponse:
        return ProtocolDocumentService.render_manual_print_response(protocol)

    @classmethod
    def render_pdf_response(cls, protocol: ManualVisitProtocol) -> HttpResponse:
        return ProtocolDocumentService.render_manual_pdf_response(protocol)
