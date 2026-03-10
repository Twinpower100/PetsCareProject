from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
import math
import random
import string
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from catalog.models import Service
from pets.models import Pet
from providers.models import (
    Employee,
    EmployeeLocationRole,
    EmployeeLocationService,
    LocationSchedule,
    Provider,
    ProviderLocation,
    ProviderLocationService,
    Schedule,
)
from users.models import User

from .models import Booking, BookingStatus
from .routing import RoutingService


ACTIVE_BOOKING_STATUS_NAMES = ('active', 'pending_confirmation')


class BookingDomainError(Exception):
    """Структурированная доменная ошибка booking flow."""

    def __init__(
        self,
        code: str,
        message,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(str(message))
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Сериализует ошибку в JSON-совместимый словарь."""
        payload = {
            'code': self.code,
            'message': str(self.message),
        }
        payload.update(self.details)
        return payload


@dataclass(frozen=True)
class BookingPolicy:
    """Конфигурируемые бизнес-правила бронирования."""

    allow_shared_escort_same_location: bool = True
    slot_step_minutes: int = 30
    travel_buffer_percent: int = 5
    travel_extra_buffer_minutes: int = 0

    @classmethod
    def load(cls) -> 'BookingPolicy':
        """Читает политику из Django settings."""
        return cls(
            allow_shared_escort_same_location=getattr(
                settings,
                'BOOKING_ALLOW_SHARED_ESCORT_SAME_LOCATION',
                True,
            ),
            slot_step_minutes=max(
                int(getattr(settings, 'BOOKING_SLOT_STEP_MINUTES', 30)),
                5,
            ),
            travel_buffer_percent=max(
                int(getattr(settings, 'BOOKING_TRAVEL_BUFFER_PERCENT', 5)),
                0,
            ),
            travel_extra_buffer_minutes=max(
                int(getattr(settings, 'BOOKING_TRAVEL_EXTRA_BUFFER_MINUTES', 0)),
                0,
            ),
        )


@dataclass
class BookingDraftValidationResult:
    """Результат единой валидации слота."""

    is_bookable: bool
    start_time: datetime
    end_time: datetime
    occupied_duration_minutes: int
    price: Decimal
    employee: Employee | None = None
    location_service: ProviderLocationService | None = None
    requires_escort_assignment: bool = False
    possible_escort_owner_ids: list[int] = field(default_factory=list)
    conflicting_bookings: list[dict[str, Any]] = field(default_factory=list)
    failure_code: str | None = None
    failure_message: Any = None


class BookingAvailabilityService:
    """Единый источник истины для поиска слотов и проверки доступности."""

    @classmethod
    def validate_booking_request(
        cls,
        *,
        requester: User,
        pet: Pet,
        provider_location: ProviderLocation,
        service: Service,
        start_time: datetime,
        employee: Employee | None = None,
        escort_owner: User | None = None,
        exclude_booking_id: int | None = None,
    ) -> BookingDraftValidationResult:
        """Проверяет возможность создания бронирования по всем доменным правилам."""
        cls._ensure_requester_can_book_pet(requester, pet)

        if start_time <= timezone.now():
            return BookingDraftValidationResult(
                is_bookable=False,
                start_time=start_time,
                end_time=start_time,
                occupied_duration_minutes=0,
                price=Decimal('0.00'),
                failure_code='past_start_time',
                failure_message=_('Booking time must be in the future.'),
            )

        location_service = cls.get_location_service(provider_location, service, pet)
        if location_service is None:
            return BookingDraftValidationResult(
                is_bookable=False,
                start_time=start_time,
                end_time=start_time,
                occupied_duration_minutes=0,
                price=Decimal('0.00'),
                failure_code='service_unavailable',
                failure_message=_('Service is not available for this pet at this location.'),
            )

        occupied_duration_minutes = int(location_service.duration_minutes)
        end_time = start_time + timedelta(minutes=occupied_duration_minutes)
        price = Decimal(location_service.price)

        owner_overlap_bookings = cls._get_owner_overlap_bookings(
            pet=pet,
            start_time=start_time,
            end_time=end_time,
            exclude_booking_id=exclude_booking_id,
        )
        possible_escort_owner_ids = cls.get_possible_escort_owner_ids(
            pet=pet,
            provider_location=provider_location,
            start_time=start_time,
            end_time=end_time,
            exclude_booking_id=exclude_booking_id,
        )
        if not possible_escort_owner_ids:
            return BookingDraftValidationResult(
                is_bookable=False,
                start_time=start_time,
                end_time=end_time,
                occupied_duration_minutes=occupied_duration_minutes,
                price=price,
                location_service=location_service,
                conflicting_bookings=cls.serialize_bookings(owner_overlap_bookings),
                failure_code='escort_unavailable',
                failure_message=_('No pet owner is available to escort this booking.'),
            )

        if escort_owner is not None and escort_owner.id not in possible_escort_owner_ids:
            return BookingDraftValidationResult(
                is_bookable=False,
                start_time=start_time,
                end_time=end_time,
                occupied_duration_minutes=occupied_duration_minutes,
                price=price,
                location_service=location_service,
                conflicting_bookings=cls.serialize_bookings(owner_overlap_bookings),
                possible_escort_owner_ids=possible_escort_owner_ids,
                failure_code='escort_conflict',
                failure_message=_('Selected escort owner is not available for this booking.'),
            )

        requires_escort_assignment = escort_owner is None and requester.id not in possible_escort_owner_ids

        eligible_employees = cls.get_eligible_employees(provider_location, service)
        if employee is not None:
            eligible_employees = [candidate for candidate in eligible_employees if candidate.id == employee.id]
            if not eligible_employees:
                return BookingDraftValidationResult(
                    is_bookable=False,
                    start_time=start_time,
                    end_time=end_time,
                    occupied_duration_minutes=occupied_duration_minutes,
                    price=price,
                    location_service=location_service,
                    possible_escort_owner_ids=possible_escort_owner_ids,
                    conflicting_bookings=cls.serialize_bookings(owner_overlap_bookings),
                    failure_code='employee_service_mismatch',
                    failure_message=_('Employee does not provide this service at the selected location.'),
                )

        if not eligible_employees:
            return BookingDraftValidationResult(
                is_bookable=False,
                start_time=start_time,
                end_time=end_time,
                occupied_duration_minutes=occupied_duration_minutes,
                price=price,
                location_service=location_service,
                possible_escort_owner_ids=possible_escort_owner_ids,
                conflicting_bookings=cls.serialize_bookings(owner_overlap_bookings),
                failure_code='no_eligible_employee',
                failure_message=_('No eligible employee is available for this service.'),
            )

        last_failure_code = 'slot_unavailable'
        last_failure_message = _('Selected slot is not available.')

        for candidate_employee in eligible_employees:
            if cls._is_candidate_bookable(
                pet=pet,
                employee=candidate_employee,
                provider_location=provider_location,
                start_time=start_time,
                end_time=end_time,
                exclude_booking_id=exclude_booking_id,
            ):
                return BookingDraftValidationResult(
                    is_bookable=True,
                    start_time=start_time,
                    end_time=end_time,
                    occupied_duration_minutes=occupied_duration_minutes,
                    price=price,
                    employee=candidate_employee,
                    location_service=location_service,
                    requires_escort_assignment=requires_escort_assignment,
                    possible_escort_owner_ids=possible_escort_owner_ids,
                    conflicting_bookings=cls.serialize_bookings(owner_overlap_bookings),
                )

            if not cls.is_employee_working(candidate_employee, provider_location, start_time, end_time):
                last_failure_code = 'employee_not_working'
                last_failure_message = _('Employee is not working at the selected time.')
            elif cls.has_employee_conflict(candidate_employee, start_time, end_time, exclude_booking_id):
                last_failure_code = 'employee_conflict'
                last_failure_message = _('Employee is already booked for the selected time.')
            else:
                last_failure_code = 'pet_conflict'
                last_failure_message = _('Pet cannot attend the selected time slot.')

        return BookingDraftValidationResult(
            is_bookable=False,
            start_time=start_time,
            end_time=end_time,
            occupied_duration_minutes=occupied_duration_minutes,
            price=price,
            location_service=location_service,
            possible_escort_owner_ids=possible_escort_owner_ids,
            conflicting_bookings=cls.serialize_bookings(owner_overlap_bookings),
            failure_code=last_failure_code,
            failure_message=last_failure_message,
        )

    @classmethod
    def get_available_slots(
        cls,
        *,
        provider_location: ProviderLocation,
        service: Service,
        pet: Pet,
        requester: User,
        date_start: date,
        date_end: date,
    ) -> dict[str, list[dict[str, Any]]]:
        """Возвращает реальные доступные слоты по датам."""
        grouped_slots: dict[str, list[dict[str, Any]]] = {}
        location_service = cls.get_location_service(provider_location, service, pet)
        if location_service is None:
            return grouped_slots

        current_date = date_start
        while current_date <= date_end:
            slots = cls.get_day_slots(
                provider_location=provider_location,
                service=service,
                pet=pet,
                requester=requester,
                target_date=current_date,
                occupied_duration_minutes=int(location_service.duration_minutes),
                price=Decimal(location_service.price),
            )
            grouped_slots[current_date.isoformat()] = slots
            current_date += timedelta(days=1)

        return grouped_slots

    @classmethod
    def get_day_slots(
        cls,
        *,
        provider_location: ProviderLocation,
        service: Service,
        pet: Pet,
        requester: User,
        target_date: date,
        occupied_duration_minutes: int,
        price: Decimal,
    ) -> list[dict[str, Any]]:
        """Генерирует слоты на одну дату по единой логике."""
        policy = BookingPolicy.load()
        slots: list[dict[str, Any]] = []

        location_schedule = cls.get_location_schedule(provider_location, target_date)
        if location_schedule is None:
            return slots

        eligible_employees = cls.get_eligible_employees(provider_location, service)
        current_timezone = timezone.get_current_timezone()

        for employee in eligible_employees:
            employee_schedule = cls.get_employee_schedule(employee, provider_location, target_date)
            if employee_schedule is None:
                continue

            work_start = timezone.make_aware(
                datetime.combine(target_date, max(location_schedule.open_time, employee_schedule.start_time)),
                current_timezone,
            )
            work_end = timezone.make_aware(
                datetime.combine(target_date, min(location_schedule.close_time, employee_schedule.end_time)),
                current_timezone,
            )
            current_time = work_start

            while current_time + timedelta(minutes=occupied_duration_minutes) <= work_end:
                slot_end = current_time + timedelta(minutes=occupied_duration_minutes)

                if current_time <= timezone.now():
                    current_time += timedelta(minutes=policy.slot_step_minutes)
                    continue

                if cls._slot_overlaps_break(current_time, slot_end, employee_schedule):
                    current_time += timedelta(minutes=policy.slot_step_minutes)
                    continue

                validation_result = cls.validate_booking_request(
                    requester=requester,
                    pet=pet,
                    provider_location=provider_location,
                    service=service,
                    start_time=current_time,
                    employee=employee,
                )
                if validation_result.is_bookable:
                    slots.append(
                        {
                            'start_time': current_time.isoformat(),
                            'end_time': slot_end.isoformat(),
                            'employee_id': employee.id,
                            'price': str(price),
                            'occupied_duration_minutes': occupied_duration_minutes,
                            'requires_escort_assignment': validation_result.requires_escort_assignment,
                            'possible_escort_owner_ids': validation_result.possible_escort_owner_ids,
                        }
                    )

                current_time += timedelta(minutes=policy.slot_step_minutes)

        slots.sort(key=lambda item: (item['start_time'], item['employee_id']))
        return slots

    @classmethod
    def location_has_real_availability(
        cls,
        *,
        provider_location: ProviderLocation,
        service: Service,
        pet: Pet,
        requester: User,
        target_date: date,
    ) -> bool:
        """Проверяет, есть ли в локации хотя бы один реальный слот."""
        location_service = cls.get_location_service(provider_location, service, pet)
        if location_service is None:
            return False

        slots = cls.get_day_slots(
            provider_location=provider_location,
            service=service,
            pet=pet,
            requester=requester,
            target_date=target_date,
            occupied_duration_minutes=int(location_service.duration_minutes),
            price=Decimal(location_service.price),
        )
        return bool(slots)

    @classmethod
    def check_slot_availability(
        cls,
        employee: Employee,
        provider: Provider | None,
        start_time: datetime,
        end_time: datetime,
        provider_location: ProviderLocation | None = None,
    ) -> bool:
        """Совместимый интерфейс для старого кода проверки employee slot."""
        if provider_location is None:
            provider_location = cls._infer_provider_location(provider, employee, start_time.date())
        if provider_location is None:
            return False
        return cls._is_candidate_bookable(
            pet=None,
            employee=employee,
            provider_location=provider_location,
            start_time=start_time,
            end_time=end_time,
            exclude_booking_id=None,
        )

    @classmethod
    def get_location_service(
        cls,
        provider_location: ProviderLocation,
        service: Service,
        pet: Pet,
    ) -> ProviderLocationService | None:
        """Находит услугу локации для типа и размера питомца."""
        size_code = pet.get_current_size_category()
        queryset = ProviderLocationService.objects.filter(
            location=provider_location,
            service=service,
            pet_type=pet.pet_type,
            is_active=True,
        )
        if size_code:
            queryset = queryset.filter(size_code=size_code)
        return queryset.select_related('service').first()

    @classmethod
    def get_eligible_employees(
        cls,
        provider_location: ProviderLocation,
        service: Service,
    ) -> list[Employee]:
        """Возвращает сотрудников, реально оказывающих услугу в локации."""
        employee_ids = list(
            EmployeeLocationService.objects.filter(
                provider_location=provider_location,
                service=service,
            ).values_list('employee_id', flat=True)
        )
        if not employee_ids:
            return []

        employees = list(
            Employee.objects.filter(id__in=employee_ids, is_active=True).select_related('user')
        )
        return [
            employee
            for employee in employees
            if cls._is_employee_active_in_location(employee, provider_location)
        ]

    @classmethod
    def get_possible_escort_owner_ids(
        cls,
        *,
        pet: Pet,
        provider_location: ProviderLocation,
        start_time: datetime,
        end_time: datetime,
        exclude_booking_id: int | None,
    ) -> list[int]:
        """Определяет владельцев, которые могут сопровождать питомца."""
        possible_owner_ids: list[int] = []
        for owner in pet.owners.all():
            if cls.is_escort_available(
                owner=owner,
                provider_location=provider_location,
                start_time=start_time,
                end_time=end_time,
                exclude_booking_id=exclude_booking_id,
            ):
                possible_owner_ids.append(owner.id)
        return possible_owner_ids

    @classmethod
    def is_escort_available(
        cls,
        *,
        owner: User,
        provider_location: ProviderLocation,
        start_time: datetime,
        end_time: datetime,
        exclude_booking_id: int | None,
    ) -> bool:
        """Проверяет, может ли конкретный владелец сопровождать питомца."""
        policy = BookingPolicy.load()
        overlapping_bookings = cls.active_bookings().filter(
            escort_owner=owner,
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        if exclude_booking_id is not None:
            overlapping_bookings = overlapping_bookings.exclude(id=exclude_booking_id)

        if not overlapping_bookings.exists():
            return True

        if not policy.allow_shared_escort_same_location:
            return False

        return not overlapping_bookings.exclude(provider_location=provider_location).exists()

    @classmethod
    def active_bookings(cls):
        """Возвращает queryset только с активными бронированиями."""
        return Booking.objects.filter(
            status__name__in=ACTIVE_BOOKING_STATUS_NAMES,
        ).select_related(
            'provider_location__structured_address',
            'escort_owner',
            'pet',
            'employee',
        )

    @classmethod
    def serialize_bookings(cls, bookings) -> list[dict[str, Any]]:
        """Сериализует бронирования для API-ответа."""
        return [
            {
                'id': booking.id,
                'pet_id': booking.pet_id,
                'escort_owner_id': booking.escort_owner_id,
                'provider_location_id': booking.provider_location_id,
                'start_time': booking.start_time.isoformat(),
                'end_time': booking.end_time.isoformat(),
            }
            for booking in bookings
        ]

    @classmethod
    def get_location_schedule(cls, provider_location: ProviderLocation, target_date: date) -> LocationSchedule | None:
        """Возвращает рабочее расписание локации на день."""
        schedule = LocationSchedule.objects.filter(
            provider_location=provider_location,
            weekday=target_date.weekday(),
            is_closed=False,
        ).first()
        if schedule is None or schedule.open_time is None or schedule.close_time is None:
            return None
        return schedule

    @classmethod
    def get_employee_schedule(
        cls,
        employee: Employee,
        provider_location: ProviderLocation,
        target_date: date,
    ) -> Schedule | None:
        """Возвращает рабочее расписание сотрудника в локации на день."""
        schedule = Schedule.objects.filter(
            employee=employee,
            provider_location=provider_location,
            day_of_week=target_date.weekday(),
            is_working=True,
        ).first()
        if schedule is None or schedule.start_time is None or schedule.end_time is None:
            return None
        return schedule

    @classmethod
    def is_employee_working(
        cls,
        employee: Employee,
        provider_location: ProviderLocation,
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """Проверяет рабочее окно сотрудника и локации."""
        if cls.get_location_schedule(provider_location, start_time.date()) is None:
            return False

        schedule = cls.get_employee_schedule(employee, provider_location, start_time.date())
        if schedule is None:
            return False

        start_time_only = start_time.timetz().replace(tzinfo=None)
        end_time_only = end_time.timetz().replace(tzinfo=None)
        if schedule.start_time > start_time_only or schedule.end_time < end_time_only:
            return False

        return not cls._slot_overlaps_break(start_time, end_time, schedule)

    @classmethod
    def has_employee_conflict(
        cls,
        employee: Employee,
        start_time: datetime,
        end_time: datetime,
        exclude_booking_id: int | None,
    ) -> bool:
        """Проверяет пересечения по сотруднику."""
        queryset = cls.active_bookings().filter(
            employee=employee,
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        if exclude_booking_id is not None:
            queryset = queryset.exclude(id=exclude_booking_id)
        return queryset.exists()

    @classmethod
    def has_pet_overlap(
        cls,
        pet: Pet,
        start_time: datetime,
        end_time: datetime,
        exclude_booking_id: int | None,
    ) -> bool:
        """Проверяет временное пересечение бронирований питомца."""
        queryset = cls.active_bookings().filter(
            pet=pet,
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        if exclude_booking_id is not None:
            queryset = queryset.exclude(id=exclude_booking_id)
        return queryset.exists()

    @classmethod
    def ensure_pet_travel_feasible(
        cls,
        *,
        pet: Pet,
        provider_location: ProviderLocation,
        start_time: datetime,
        end_time: datetime,
        exclude_booking_id: int | None,
    ) -> bool:
        """Проверяет feasibility поездки для соседних визитов питомца."""
        previous_booking = cls._get_previous_pet_booking(pet, start_time, exclude_booking_id)
        next_booking = cls._get_next_pet_booking(pet, end_time, exclude_booking_id)

        if previous_booking is not None:
            required_seconds = cls.get_adjusted_travel_seconds(
                previous_booking.provider_location,
                provider_location,
            )
            latest_arrival = previous_booking.end_time + timedelta(seconds=required_seconds)
            if latest_arrival > start_time:
                return False

        if next_booking is not None:
            required_seconds = cls.get_adjusted_travel_seconds(
                provider_location,
                next_booking.provider_location,
            )
            earliest_departure = end_time + timedelta(seconds=required_seconds)
            if earliest_departure > next_booking.start_time:
                return False

        return True

    @classmethod
    def get_adjusted_travel_seconds(cls, source, destination) -> int:
        """Возвращает travel time с бизнес-буфером."""
        base_seconds = RoutingService.get_travel_duration_seconds(source, destination)
        policy = BookingPolicy.load()
        buffered_seconds = math.ceil(base_seconds * (1 + policy.travel_buffer_percent / 100))
        return buffered_seconds + (policy.travel_extra_buffer_minutes * 60)

    @classmethod
    def _ensure_requester_can_book_pet(cls, requester: User, pet: Pet) -> None:
        """Проверяет, что пользователь является владельцем или совладельцем питомца."""
        if not pet.owners.filter(id=requester.id).exists():
            raise BookingDomainError(
                'pet_access_denied',
                _('You do not have access to book services for this pet.'),
                status_code=403,
            )

    @classmethod
    def _is_candidate_bookable(
        cls,
        *,
        pet: Pet | None,
        employee: Employee,
        provider_location: ProviderLocation,
        start_time: datetime,
        end_time: datetime,
        exclude_booking_id: int | None,
    ) -> bool:
        """Проверяет, можно ли использовать слот для конкретного сотрудника."""
        if cls.get_location_schedule(provider_location, start_time.date()) is None:
            return False

        if not cls.is_employee_working(employee, provider_location, start_time, end_time):
            return False

        if cls.has_employee_conflict(employee, start_time, end_time, exclude_booking_id):
            return False

        if pet is None:
            return True

        if cls.has_pet_overlap(pet, start_time, end_time, exclude_booking_id):
            return False

        return cls.ensure_pet_travel_feasible(
            pet=pet,
            provider_location=provider_location,
            start_time=start_time,
            end_time=end_time,
            exclude_booking_id=exclude_booking_id,
        )

    @classmethod
    def _get_owner_overlap_bookings(
        cls,
        *,
        pet: Pet,
        start_time: datetime,
        end_time: datetime,
        exclude_booking_id: int | None,
    ):
        """Возвращает overlapping bookings владельцев питомца."""
        queryset = cls.active_bookings().filter(
            escort_owner_id__in=pet.owners.values_list('id', flat=True),
            start_time__lt=end_time,
            end_time__gt=start_time,
        ).order_by('start_time')
        if exclude_booking_id is not None:
            queryset = queryset.exclude(id=exclude_booking_id)
        return list(queryset)

    @classmethod
    def _get_previous_pet_booking(cls, pet: Pet, start_time: datetime, exclude_booking_id: int | None):
        """Возвращает ближайшее предыдущее активное бронирование питомца."""
        queryset = cls.active_bookings().filter(
            pet=pet,
            end_time__lte=start_time,
        ).order_by('-end_time')
        if exclude_booking_id is not None:
            queryset = queryset.exclude(id=exclude_booking_id)
        return queryset.first()

    @classmethod
    def _get_next_pet_booking(cls, pet: Pet, end_time: datetime, exclude_booking_id: int | None):
        """Возвращает ближайшее следующее активное бронирование питомца."""
        queryset = cls.active_bookings().filter(
            pet=pet,
            start_time__gte=end_time,
        ).order_by('start_time')
        if exclude_booking_id is not None:
            queryset = queryset.exclude(id=exclude_booking_id)
        return queryset.first()

    @classmethod
    def _slot_overlaps_break(cls, start_time: datetime, end_time: datetime, schedule: Schedule) -> bool:
        """Проверяет пересечение слота с employee break."""
        if not schedule.break_start or not schedule.break_end:
            return False
        start_time_only = start_time.timetz().replace(tzinfo=None)
        end_time_only = end_time.timetz().replace(tzinfo=None)
        return start_time_only < schedule.break_end and end_time_only > schedule.break_start

    @classmethod
    def _is_employee_active_in_location(
        cls,
        employee: Employee,
        provider_location: ProviderLocation,
    ) -> bool:
        """Проверяет soft-activation сотрудника в локации без ломки старых данных."""
        roles = EmployeeLocationRole.objects.filter(
            employee=employee,
            provider_location=provider_location,
        )
        return not roles.exists() or roles.filter(is_active=True).exists()

    @classmethod
    def _infer_provider_location(
        cls,
        provider: Provider | None,
        employee: Employee,
        target_date: date,
    ) -> ProviderLocation | None:
        """Пытается подобрать локацию для старых вызовов без явной provider_location."""
        schedules = Schedule.objects.filter(
            employee=employee,
            day_of_week=target_date.weekday(),
            is_working=True,
        ).select_related('provider_location')
        if provider is not None:
            schedules = schedules.filter(provider_location__provider=provider)
        schedule = schedules.first()
        return schedule.provider_location if schedule else None


class BookingTransactionService:
    """Единый сервис создания бронирований под транзакцией."""

    @staticmethod
    @transaction.atomic
    def create_booking(
        user: User,
        pet: Pet,
        provider: Provider | None,
        employee: Employee,
        service: Service,
        start_time: datetime,
        end_time: datetime | None = None,
        price: float | Decimal | None = None,
        notes: str = '',
        provider_location: ProviderLocation | None = None,
        escort_owner: User | None = None,
    ) -> Booking:
        """Создаёт бронирование с повторной проверкой под блокировками."""
        provider_location = BookingTransactionService._resolve_provider_location(
            provider=provider,
            provider_location=provider_location,
            employee=employee,
            target_date=start_time.date(),
        )
        if provider_location is None:
            raise BookingDomainError(
                'provider_location_required',
                _('Provider location is required for booking creation.'),
            )

        provider = provider or provider_location.provider

        pet = Pet.objects.select_for_update().get(pk=pet.pk)
        employee = Employee.objects.select_for_update().get(pk=employee.pk)
        provider_location = ProviderLocation.objects.select_for_update().get(pk=provider_location.pk)

        BookingTransactionService._lock_relevant_bookings(
            pet=pet,
            employee=employee,
            escort_owner=escort_owner or user,
        )

        validation_result = BookingAvailabilityService.validate_booking_request(
            requester=user,
            pet=pet,
            provider_location=provider_location,
            service=service,
            start_time=start_time,
            employee=employee,
            escort_owner=escort_owner,
        )

        if validation_result.requires_escort_assignment:
            raise BookingDomainError(
                'escort_assignment_required',
                _('Escort owner assignment is required for overlapping bookings.'),
                status_code=409,
                details={
                    'requires_escort_assignment': True,
                    'possible_escort_owner_ids': validation_result.possible_escort_owner_ids,
                    'conflicting_bookings': validation_result.conflicting_bookings,
                },
            )

        if not validation_result.is_bookable:
            raise BookingDomainError(
                validation_result.failure_code or 'slot_unavailable',
                validation_result.failure_message or _('Selected slot is not available.'),
                details={
                    'possible_escort_owner_ids': validation_result.possible_escort_owner_ids,
                    'conflicting_bookings': validation_result.conflicting_bookings,
                },
            )

        if escort_owner is None:
            escort_owner = user

        booking_price = Decimal(str(price)) if price is not None else validation_result.price
        booking = Booking.objects.create(
            user=user,
            escort_owner=escort_owner,
            pet=pet,
            provider=provider,
            provider_location=provider_location,
            employee=validation_result.employee or employee,
            service=service,
            status=BookingTransactionService._get_active_status(),
            start_time=validation_result.start_time,
            end_time=validation_result.end_time if end_time is None else validation_result.end_time,
            occupied_duration_minutes=validation_result.occupied_duration_minutes,
            price=booking_price,
            notes=notes,
            code=BookingTransactionService._generate_booking_code(),
        )
        return booking

    @staticmethod
    def _resolve_provider_location(
        *,
        provider: Provider | None,
        provider_location: ProviderLocation | None,
        employee: Employee,
        target_date: date,
    ) -> ProviderLocation | None:
        """Определяет локацию для создания бронирования."""
        if provider_location is not None:
            return provider_location
        return BookingAvailabilityService._infer_provider_location(
            provider=provider,
            employee=employee,
            target_date=target_date,
        )

    @staticmethod
    def _lock_relevant_bookings(*, pet: Pet, employee: Employee, escort_owner: User) -> None:
        """Берёт row locks на потенциально конфликтующие бронирования."""
        list(Booking.objects.select_for_update().filter(
            pet=pet,
            status__name__in=ACTIVE_BOOKING_STATUS_NAMES,
        ))
        list(Booking.objects.select_for_update().filter(
            employee=employee,
            status__name__in=ACTIVE_BOOKING_STATUS_NAMES,
        ))
        list(Booking.objects.select_for_update().filter(
            escort_owner=escort_owner,
            status__name__in=ACTIVE_BOOKING_STATUS_NAMES,
        ))

    @staticmethod
    def _get_active_status() -> BookingStatus:
        """Возвращает активный статус бронирования."""
        status_obj, _ = BookingStatus.objects.get_or_create(name='active')
        return status_obj

    @staticmethod
    def _generate_booking_code() -> str:
        """Генерирует уникальный booking code."""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not Booking.objects.filter(code=code).exists():
                return code

    @staticmethod
    @transaction.atomic
    def update_booking(
        booking_id: int,
        new_start_time: datetime | None = None,
        new_end_time: datetime | None = None,
        new_employee: Employee | None = None,
        new_service: Service | None = None,
        new_price: float | Decimal | None = None,
        new_notes: str | None = None,
        new_escort_owner: User | None = None,
    ) -> Booking:
        """Обновляет бронирование через ту же доменную валидацию, что и create."""
        booking = Booking.objects.select_for_update().select_related(
            'pet',
            'provider',
            'provider_location',
            'employee',
            'service',
            'escort_owner',
            'user',
        ).get(id=booking_id)

        start_time = new_start_time or booking.start_time
        employee = new_employee or booking.employee
        service = new_service or booking.service
        escort_owner = new_escort_owner or booking.escort_owner or booking.user

        BookingTransactionService._lock_relevant_bookings(
            pet=booking.pet,
            employee=employee,
            escort_owner=escort_owner,
        )

        validation_result = BookingAvailabilityService.validate_booking_request(
            requester=booking.user,
            pet=booking.pet,
            provider_location=booking.provider_location,
            service=service,
            start_time=start_time,
            employee=employee,
            escort_owner=escort_owner,
            exclude_booking_id=booking.id,
        )

        if validation_result.requires_escort_assignment:
            raise BookingDomainError(
                'escort_assignment_required',
                _('Escort owner assignment is required for overlapping bookings.'),
                status_code=409,
                details={
                    'requires_escort_assignment': True,
                    'possible_escort_owner_ids': validation_result.possible_escort_owner_ids,
                    'conflicting_bookings': validation_result.conflicting_bookings,
                },
            )

        if not validation_result.is_bookable:
            raise BookingDomainError(
                validation_result.failure_code or 'slot_unavailable',
                validation_result.failure_message or _('Selected slot is not available.'),
                details={
                    'possible_escort_owner_ids': validation_result.possible_escort_owner_ids,
                    'conflicting_bookings': validation_result.conflicting_bookings,
                },
            )

        booking.start_time = validation_result.start_time
        booking.end_time = validation_result.end_time if new_end_time is None else validation_result.end_time
        booking.employee = validation_result.employee or employee
        booking.service = service
        booking.escort_owner = escort_owner
        booking.occupied_duration_minutes = validation_result.occupied_duration_minutes
        if new_price is not None:
            booking.price = Decimal(str(new_price))
        if new_notes is not None:
            booking.notes = new_notes
        booking.save()
        return booking
