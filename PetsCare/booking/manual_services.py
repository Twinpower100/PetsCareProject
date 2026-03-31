"""Сервисы ручного создания бронирований для provider admin приложения."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from catalog.models import Service
from pets.models import Pet, PetOwner, PetType
from providers.models import Employee, EmployeeLocationRole, ProviderLocation, ProviderLocationService
from providers.permission_service import ProviderPermissionService
from users.models import User

from .manual_notes import build_manual_booking_notes
from .models import Booking
from .unified_services import BookingAvailabilityService, BookingDomainError, BookingTransactionService


MANUAL_BOOKING_CONFLICT_CODES = {
    'employee_conflict',
    'pet_conflict',
    'escort_conflict',
    'escort_unavailable',
    'escort_assignment_required',
    'employee_not_working',
    'slot_unavailable',
}

GUEST_PET_TYPE_CODE = 'manual_guest'


@dataclass(frozen=True)
class ManualBookingContext:
    """Контекст, в котором ручное бронирование уходит в доменный сервис."""

    booking_user: User
    booking_pet: Pet
    escort_owner: User
    service_pet_type: PetType | None = None
    service_pet_weight: Decimal | None = None
    ignore_pet_constraints: bool = False
    skip_escort_constraints: bool = False
    notes: str = ''
    is_guest: bool = False


class ManualBookingPermissionService:
    """Проверки доступа к ручному бронированию и emergency override."""

    @classmethod
    def can_create_manual_booking(cls, user: User, provider_location: ProviderLocation) -> bool:
        """Проверяет, может ли пользователь создавать ручные бронирования в локации."""
        return ProviderPermissionService.check_permission(
            user,
            provider_location.provider,
            'bookings.create_manual',
            'create',
            target_location=provider_location,
        )

    @classmethod
    def can_use_emergency_override(cls, user: User, provider_location: ProviderLocation) -> bool:
        """Проверяет, может ли пользователь инициировать emergency override."""
        return ProviderPermissionService.check_permission(
            user,
            provider_location.provider,
            'bookings.create_manual',
            'create',
            target_location=provider_location,
        )


class GuestProfileService:
    """Управляет техническими guest-профилями для anonymous walk-ins."""

    @classmethod
    def ensure_guest_user(cls, provider_location: ProviderLocation) -> User:
        """Создаёт или возвращает технического пользователя для локации."""
        email = f'guest-location-{provider_location.id}@manual-booking.petscare.local'
        user = User.objects.filter(email=email).first()
        if user is not None:
            return user

        return User.objects.create_user(
            email=email,
            password=None,
            first_name='Guest',
            last_name=f'Location {provider_location.id}',
            phone_number=cls._build_guest_phone(provider_location.id),
        )

    @classmethod
    def ensure_guest_pet(cls, provider_location: ProviderLocation, guest_user: User) -> Pet:
        """Создаёт или возвращает технического питомца для локации."""
        pet_name = f'Guest Pet {provider_location.id}'
        pet = Pet.objects.filter(name=pet_name, owners=guest_user, is_active=True).first()
        if pet is not None:
            return pet

        pet_type = cls._ensure_guest_pet_type()
        pet = Pet.objects.create(
            name=pet_name,
            pet_type=pet_type,
            weight=Decimal('1.00'),
            gender='U',
            is_neutered='U',
            description='Technical guest profile for manual walk-in bookings.',
        )
        PetOwner.objects.get_or_create(
            pet=pet,
            user=guest_user,
            defaults={'role': 'main'},
        )
        return pet

    @classmethod
    def ensure_for_location(cls, provider_location: ProviderLocation) -> tuple[User, Pet]:
        """Возвращает технические guest-сущности для локации."""
        guest_user = cls.ensure_guest_user(provider_location)
        guest_pet = cls.ensure_guest_pet(provider_location, guest_user)
        return guest_user, guest_pet

    @staticmethod
    def _build_guest_phone(location_id: int) -> str:
        """Генерирует уникальный технический номер телефона для guest user."""
        return f'+990{location_id:09d}'

    @staticmethod
    def _ensure_guest_pet_type() -> PetType:
        """Создаёт технический тип питомца для guest-профилей."""
        pet_type, _ = PetType.objects.get_or_create(
            code=GUEST_PET_TYPE_CODE,
            defaults={
                'name': 'Manual guest',
                'description': 'Technical pet type for guest walk-in bookings.',
            },
        )
        return pet_type


class ManualBookingService:
    """Оркестрирует ручное создание бронирований и связанные проверки."""

    @classmethod
    def create_manual_booking(cls, *, actor: User, data: dict[str, Any]) -> Booking:
        """Создаёт ручное бронирование от имени provider staff."""
        provider_location = cls._get_provider_location(data['provider_location_id'])
        if not ManualBookingPermissionService.can_create_manual_booking(actor, provider_location):
            raise BookingDomainError(
                'manual_booking_forbidden',
                _('You do not have permission to create manual bookings for this location.'),
                status_code=403,
            )

        employee = cls._get_employee(data['employee_id'], provider_location)
        service = cls._get_service(data['service_id'])
        start_time = data['start_time']
        is_emergency = bool(data.get('is_emergency'))

        if is_emergency:
            if not ManualBookingPermissionService.can_use_emergency_override(actor, provider_location):
                raise BookingDomainError(
                    'emergency_override_forbidden',
                    _('You do not have permission to use emergency override.'),
                    status_code=403,
                )
            cls._validate_emergency_window(start_time)

        context = (
            cls._build_guest_context(provider_location=provider_location, service=service, data=data)
            if data['is_guest']
            else cls._build_registered_context(data=data)
        )

        try:
            return BookingTransactionService.create_booking(
                user=context.booking_user,
                pet=context.booking_pet,
                provider=provider_location.provider,
                employee=employee,
                service=service,
                start_time=start_time,
                notes=context.notes,
                provider_location=provider_location,
                escort_owner=context.escort_owner,
                source=Booking.BookingSource.MANUAL_ENTRY,
                service_pet_type=context.service_pet_type,
                service_pet_weight=context.service_pet_weight,
                ignore_pet_constraints=context.ignore_pet_constraints,
                skip_escort_constraints=context.skip_escort_constraints,
            )
        except BookingDomainError as exc:
            raise cls._augment_domain_error(
                exc=exc,
                provider_location=provider_location,
                service=service,
                employee=employee,
                start_time=start_time,
                context=context,
                is_emergency=is_emergency,
            ) from exc

    @classmethod
    def search_clients(cls, *, actor: User, query: str, provider_location_id: int | None = None) -> list[dict[str, Any]]:
        """Ищет клиентов и их питомцев для ручного бронирования."""
        provider_location = None
        if provider_location_id is not None:
            provider_location = cls._get_provider_location(provider_location_id)
            if not ManualBookingPermissionService.can_create_manual_booking(actor, provider_location):
                raise BookingDomainError(
                    'manual_booking_forbidden',
                    _('You do not have permission to search clients for this location.'),
                    status_code=403,
                )

        raw_query = (query or '').strip()
        queryset = User.objects.filter(pets__is_active=True).distinct().order_by('first_name', 'last_name', 'email')
        if raw_query:
            queryset = queryset.filter(
                Q(first_name__icontains=raw_query)
                | Q(last_name__icontains=raw_query)
                | Q(email__icontains=raw_query)
                | Q(phone_number__icontains=raw_query)
            )

        results: list[dict[str, Any]] = []
        for user in queryset[:10]:
            pets_queryset = Pet.objects.filter(owners=user, is_active=True).select_related('pet_type', 'breed').order_by('name')
            pets_payload = [
                {
                    'id': pet.id,
                    'name': pet.name,
                    'pet_type_name': pet.pet_type.get_localized_name() if pet.pet_type else None,
                    'breed_name': pet.breed.get_localized_name() if pet.breed else None,
                }
                for pet in pets_queryset
            ]
            if not pets_payload:
                continue
            results.append(
                {
                    'id': user.id,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'email': user.email,
                    'phone_number': str(user.phone_number),
                    'pets': pets_payload,
                }
            )
        return results

    @classmethod
    def _build_registered_context(cls, *, data: dict[str, Any]) -> ManualBookingContext:
        """Собирает контекст ручного бронирования для зарегистрированного клиента."""
        booking_user = User.objects.filter(id=data['user_id']).first()
        if booking_user is None:
            raise BookingDomainError(
                'manual_booking_user_not_found',
                _('Selected client was not found.'),
                status_code=404,
            )

        booking_pet = Pet.objects.filter(id=data['pet_id'], is_active=True).first()
        if booking_pet is None:
            raise BookingDomainError(
                'manual_booking_pet_not_found',
                _('Selected pet was not found.'),
                status_code=404,
            )

        if not booking_pet.owners.filter(id=booking_user.id).exists():
            raise BookingDomainError(
                'manual_booking_pet_owner_mismatch',
                _('Selected client does not own the selected pet.'),
                status_code=400,
            )

        escort_owner = booking_user
        escort_owner_id = data.get('escort_owner_id')
        if escort_owner_id is not None:
            escort_owner = booking_pet.owners.filter(id=escort_owner_id).first()
            if escort_owner is None:
                raise BookingDomainError(
                    'escort_owner_invalid',
                    _('Escort owner must be one of the pet owners.'),
                    status_code=400,
                )

        metadata = {
            'is_guest': False,
            'is_emergency': bool(data.get('is_emergency')),
        }

        return ManualBookingContext(
            booking_user=booking_user,
            booking_pet=booking_pet,
            escort_owner=escort_owner,
            notes=build_manual_booking_notes(metadata=metadata, notes=(data.get('notes') or '').strip()),
        )

    @classmethod
    def _build_guest_context(
        cls,
        *,
        provider_location: ProviderLocation,
        service: Service,
        data: dict[str, Any],
    ) -> ManualBookingContext:
        """Собирает контекст ручного бронирования для гостевого сценария."""
        guest_user, guest_pet = GuestProfileService.ensure_for_location(provider_location)
        service_pet_type = cls._resolve_guest_pet_type(provider_location=provider_location, service=service, data=data)
        service_pet_weight = cls._resolve_guest_pet_weight(provider_location=provider_location, service=service, pet_type=service_pet_type, data=data)

        metadata = {
            'is_guest': True,
            'is_emergency': bool(data.get('is_emergency')),
            'guest_client_name': data['guest_client_name'].strip(),
            'guest_client_phone': data['guest_client_phone'].strip(),
            'guest_pet_name': data['guest_pet_name'].strip(),
            'guest_pet_species': (data.get('guest_pet_species') or '').strip() or service_pet_type.get_localized_name(),
            'guest_pet_type_id': service_pet_type.id,
            'guest_pet_weight': str(service_pet_weight) if service_pet_weight is not None else None,
        }
        notes = build_manual_booking_notes(metadata=metadata, notes=(data.get('notes') or '').strip())

        return ManualBookingContext(
            booking_user=guest_user,
            booking_pet=guest_pet,
            escort_owner=guest_user,
            service_pet_type=service_pet_type,
            service_pet_weight=service_pet_weight,
            ignore_pet_constraints=True,
            skip_escort_constraints=True,
            notes=notes,
            is_guest=True,
        )

    @classmethod
    def _resolve_guest_pet_type(
        cls,
        *,
        provider_location: ProviderLocation,
        service: Service,
        data: dict[str, Any],
    ) -> PetType:
        """Определяет тип питомца для расчёта цены/duration guest-бронирования."""
        guest_pet_type_id = data.get('guest_pet_type_id')
        if guest_pet_type_id is not None:
            pet_type = PetType.objects.filter(id=guest_pet_type_id).first()
            if pet_type is None:
                raise BookingDomainError(
                    'guest_pet_type_not_found',
                    _('Selected guest pet type was not found.'),
                    status_code=404,
                )
            return pet_type

        pet_type_ids = list(
            ProviderLocationService.objects.filter(
                location=provider_location,
                service=service,
                is_active=True,
            ).values_list('pet_type_id', flat=True).distinct()
        )
        if len(pet_type_ids) == 1:
            return PetType.objects.get(id=pet_type_ids[0])

        raise BookingDomainError(
            'guest_pet_type_required',
            _('Guest pet type is required for this service.'),
            status_code=400,
        )

    @classmethod
    def _resolve_guest_pet_weight(
        cls,
        *,
        provider_location: ProviderLocation,
        service: Service,
        pet_type: PetType,
        data: dict[str, Any],
    ) -> Decimal | None:
        """Определяет вес питомца для guest pricing, если он действительно нужен."""
        weight = data.get('guest_pet_weight')
        if weight is not None:
            return Decimal(str(weight))

        size_codes = list(
            ProviderLocationService.objects.filter(
                location=provider_location,
                service=service,
                pet_type=pet_type,
                is_active=True,
            ).values_list('size_code', flat=True).distinct()
        )
        if len(size_codes) == 1:
            return None

        raise BookingDomainError(
            'guest_pet_weight_required',
            _('Guest pet weight is required for this service.'),
            status_code=400,
        )

    @classmethod
    def _augment_domain_error(
        cls,
        *,
        exc: BookingDomainError,
        provider_location: ProviderLocation,
        service: Service,
        employee: Employee,
        start_time: datetime,
        context: ManualBookingContext,
        is_emergency: bool,
    ) -> BookingDomainError:
        """Добавляет в конфликтные ошибки альтернативные слоты или конфликтующие бронирования."""
        if exc.code not in MANUAL_BOOKING_CONFLICT_CODES:
            return exc

        details = dict(exc.details)
        details.setdefault('conflicting_bookings', [])
        if is_emergency:
            details['requires_manual_resolution'] = True
            details['can_emergency_override'] = True
            return BookingDomainError(
                'manual_booking_conflict',
                _('Selected slot is occupied and must be manually cleared for an emergency booking.'),
                status_code=409,
                details=details,
            )

        details['alternative_slots'] = cls.find_alternative_slots(
            provider_location=provider_location,
            service=service,
            employee=employee,
            start_time=start_time,
            context=context,
        )
        return BookingDomainError(
            'manual_booking_conflict',
            _('Selected slot is not available.'),
            status_code=409,
            details=details,
        )

    @classmethod
    def find_alternative_slots(
        cls,
        *,
        provider_location: ProviderLocation,
        service: Service,
        employee: Employee,
        start_time: datetime,
        context: ManualBookingContext,
        limit: int = 5,
        days_ahead: int = 10,
    ) -> list[dict[str, Any]]:
        """Подбирает ближайшие реальные альтернативы для того же сотрудника и услуги."""
        location_service = BookingAvailabilityService.get_location_service_for_context(
            provider_location,
            service,
            pet=context.booking_pet,
            pet_type=context.service_pet_type,
            weight=context.service_pet_weight,
        )
        if location_service is None:
            return []

        alternatives: list[dict[str, Any]] = []
        for day_offset in range(days_ahead + 1):
            target_date = start_time.date() + timedelta(days=day_offset)
            candidate_slots = BookingAvailabilityService.get_day_slots(
                provider_location=provider_location,
                service=service,
                target_date=target_date,
                occupied_duration_minutes=int(location_service.duration_minutes),
                price=Decimal(location_service.price),
            )
            for slot in candidate_slots:
                if slot['employee_id'] != employee.id:
                    continue

                candidate_start = datetime.fromisoformat(slot['start_time'])
                if candidate_start <= start_time:
                    continue

                validation_result = BookingAvailabilityService.validate_booking_request(
                    requester=context.booking_user,
                    pet=context.booking_pet,
                    provider_location=provider_location,
                    service=service,
                    start_time=candidate_start,
                    employee=employee,
                    escort_owner=context.escort_owner,
                    service_pet_type=context.service_pet_type,
                    service_pet_weight=context.service_pet_weight,
                    ignore_pet_constraints=context.ignore_pet_constraints,
                    skip_escort_constraints=context.skip_escort_constraints,
                )
                if not validation_result.is_bookable:
                    continue

                alternatives.append(
                    {
                        'start_time': validation_result.start_time.isoformat(),
                        'end_time': validation_result.end_time.isoformat(),
                        'employee_id': employee.id,
                        'price': str(validation_result.price),
                        'occupied_duration_minutes': validation_result.occupied_duration_minutes,
                    }
                )
                if len(alternatives) >= limit:
                    return alternatives
        return alternatives

    @classmethod
    def _validate_emergency_window(cls, start_time: datetime) -> None:
        """Блокирует emergency override вне допустимого окна срочности."""
        window_hours = cls.get_emergency_time_window_hours()
        latest_emergency_start = timezone.now() + timedelta(hours=window_hours)
        if start_time > latest_emergency_start:
            raise BookingDomainError(
                'emergency_window_exceeded',
                _('Emergency override is only available within the configured emergency time window.'),
                status_code=400,
                details={
                    'emergency_time_window_hours': window_hours,
                    'latest_allowed_start_time': latest_emergency_start.isoformat(),
                },
            )

    @staticmethod
    def get_emergency_time_window_hours() -> int:
        """Возвращает размер emergency window в часах из настроек."""
        return max(int(getattr(settings, 'BOOKING_EMERGENCY_TIME_WINDOW_HOURS', 4)), 1)

    @staticmethod
    def _get_provider_location(provider_location_id: int) -> ProviderLocation:
        """Находит активную локацию провайдера."""
        provider_location = ProviderLocation.objects.filter(id=provider_location_id, is_active=True).select_related('provider').first()
        if provider_location is None:
            raise BookingDomainError(
                'manual_booking_location_not_found',
                _('Selected provider location was not found.'),
                status_code=404,
            )
        return provider_location

    @staticmethod
    def _get_employee(employee_id: int, provider_location: ProviderLocation) -> Employee:
        """Находит сотрудника и проверяет его привязку к локации."""
        employee = Employee.objects.filter(id=employee_id, is_active=True).select_related('user').first()
        if employee is None:
            raise BookingDomainError(
                'manual_booking_employee_not_found',
                _('Selected employee was not found.'),
                status_code=404,
            )
        has_location_link = (
            employee.location_roles.filter(provider_location=provider_location, is_active=True).exists()
            or employee.location_services.filter(provider_location=provider_location).exists()
            or employee.locations.filter(id=provider_location.id).exists()
        )
        if not has_location_link:
            raise BookingDomainError(
                'manual_booking_employee_location_mismatch',
                _('Selected employee is not assigned to this location.'),
                status_code=400,
            )
        return employee

    @staticmethod
    def _get_service(service_id: int) -> Service:
        """Находит услугу для ручного бронирования."""
        service = Service.objects.filter(id=service_id).first()
        if service is None:
            raise BookingDomainError(
                'manual_booking_service_not_found',
                _('Selected service was not found.'),
                status_code=404,
            )
        return service
