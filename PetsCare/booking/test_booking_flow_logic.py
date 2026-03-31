"""
Базовый mixin для тестов бронирований.

Предоставляет общую настройку: owner, pet_one, employee_a, location_a,
service, pet_type, provider, _create_booking, _dt.
"""

from datetime import datetime, time, timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone

from booking.constants import BOOKING_STATUS_ACTIVE
from booking.models import Booking, BookingStatus
from catalog.models import Service
from geolocation.models import Address
from pets.models import Breed, Pet, PetOwner, PetType
from providers.models import Employee, EmployeeProvider, Provider, ProviderLocation
from providers.models import (
    EmployeeLocationRole,
    EmployeeLocationService,
    LocationSchedule,
    ProviderLocationService,
    Schedule,
)

User = get_user_model()


class BookingFlowBaseMixin:
    """Mixin с общей настройкой для тестов бронирований."""

    def setUp(self):
        super().setUp()
        self._setup_booking_flow()

    def _setup_booking_flow(self):
        """Создаёт owner, pet, employee, location, service, provider."""
        self.owner = User.objects.create_user(
            email='owner@example.com',
            password='password123',
            username='owner_user',
            phone_number='+38267000001',
        )
        self.provider = Provider.objects.create(name='Test Pet Clinic', is_active=True)
        self.employee_a = Employee.objects.create(
            user=User.objects.create_user(
                email='employee@example.com',
                password='password123',
                username='employee_user',
                phone_number='+38267000002',
            ),
            is_active=True,
        )
        EmployeeProvider.objects.create(
            employee=self.employee_a,
            provider=self.provider,
            role=EmployeeProvider.ROLE_SERVICE_WORKER,
            start_date=timezone.now().date(),
        )
        self.address = Address.objects.create(
            country='Montenegro',
            city='Podgorica',
            street='Main street',
            house_number='1',
            formatted_address='Main street 1',
            latitude=42.0,
            longitude=19.0,
            validation_status='valid',
        )
        self.location_a = ProviderLocation.objects.create(
            provider=self.provider,
            name='Main Branch',
            structured_address=self.address,
            phone_number='+38267000001',
            email='location@example.com',
            is_active=True,
        )
        self.pet_type = PetType.objects.create(name='Dog')
        self.location_a.served_pet_types.add(self.pet_type)
        self.breed = Breed.objects.create(name='Pug', pet_type=self.pet_type)
        self.pet_one = Pet.objects.create(
            name='Rex',
            pet_type=self.pet_type,
            breed=self.breed,
            weight=8.0,
        )
        PetOwner.objects.create(pet=self.pet_one, user=self.owner, role='main')
        self.service = Service.objects.create(
            code='grooming',
            name='Grooming',
            parent=None,
            level=0,
            is_client_facing=True,
        )
        EmployeeLocationRole.objects.create(
            employee=self.employee_a,
            provider_location=self.location_a,
            role=EmployeeLocationRole.ROLE_SERVICE_WORKER,
            is_active=True,
        )
        ProviderLocationService.objects.create(
            location=self.location_a,
            service=self.service,
            price=100.00,
            duration_minutes=60,
            pet_type=self.pet_type,
            size_code='S',
        )
        EmployeeLocationService.objects.create(
            employee=self.employee_a,
            provider_location=self.location_a,
            service=self.service,
        )
        for weekday in range(7):
            LocationSchedule.objects.create(
                provider_location=self.location_a,
                weekday=weekday,
                open_time=time(hour=0, minute=0),
                close_time=time(hour=23, minute=59),
                is_closed=False,
            )
            Schedule.objects.create(
                employee=self.employee_a,
                provider_location=self.location_a,
                day_of_week=weekday,
                start_time=time(hour=0, minute=0),
                end_time=time(hour=23, minute=59),
                is_working=True,
            )
        self.status_active, _ = BookingStatus.objects.get_or_create(name=BOOKING_STATUS_ACTIVE)

    def _dt(self, hour: int, minute: int):
        """Возвращает datetime на сегодня с указанным временем."""
        today = timezone.now().date()
        return timezone.make_aware(datetime.combine(today, time(hour=hour, minute=minute)))

    def _create_booking(
        self,
        *,
        pet,
        location,
        employee,
        start_time,
        **kwargs,
    ):
        """Создаёт бронирование."""
        end_time = kwargs.pop('end_time', start_time + timedelta(hours=1))
        provider = location.provider
        return Booking.objects.create(
            user=self.owner,
            escort_owner=self.owner,
            pet=pet,
            provider=provider,
            provider_location=location,
            employee=employee,
            service=self.service,
            status=self.status_active,
            start_time=start_time,
            end_time=end_time,
            occupied_duration_minutes=60,
            price=100.00,
            **kwargs,
        )
