from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from booking.models import Booking, BookingStatus
from catalog.models import Service
from geolocation.models import Address
from pets.models import Pet, PetOwner, PetType, SizeRule
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


User = get_user_model()


class BookingFlowBaseMixin:
    """Общая тестовая фикстура для booking flow."""

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(
            email='owner@example.com',
            password='testpass123',
            phone_number='+100000001',
        )
        self.coowner = User.objects.create_user(
            email='coowner@example.com',
            password='testpass123',
            phone_number='+100000002',
        )
        self.other_user = User.objects.create_user(
            email='other@example.com',
            password='testpass123',
            phone_number='+100000003',
        )
        if hasattr(self, 'client') and hasattr(self.client, 'force_authenticate'):
            self.client.force_authenticate(self.owner)

        self.target_date = timezone.localdate() + timedelta(days=5)
        self.active_status, _ = BookingStatus.objects.get_or_create(name='active')

        self.pet_type = PetType.objects.create(code='dog', name='Dog')
        SizeRule.objects.create(
            pet_type=self.pet_type,
            size_code='S',
            min_weight_kg=Decimal('0.00'),
            max_weight_kg=Decimal('10.00'),
        )

        self.service = Service.objects.create(
            code='grooming',
            name='Grooming',
            level=0,
            hierarchy_order='1',
        )

        self.provider = Provider.objects.create(
            name='Provider',
            phone_number='+111111111',
            email='provider@example.com',
            activation_status='active',
            is_active=True,
            show_services=True,
        )
        self.provider.available_category_levels.add(self.service)

        self.location_a = self._create_location('Alpha', 'alpha@example.com', Decimal('42.0000000'), Decimal('19.0000000'))
        self.location_b = self._create_location('Beta', 'beta@example.com', Decimal('42.0100000'), Decimal('19.0100000'))
        self.location_c = self._create_location('Gamma', 'gamma@example.com', Decimal('42.0200000'), Decimal('19.0200000'))

        self.pet_one = self._create_pet('Rex')
        self.pet_two = self._create_pet('Luna')

        self.location_service_a = self._create_location_service(self.location_a, duration_minutes=60)
        self.location_service_b = self._create_location_service(self.location_b, duration_minutes=60)
        self.location_service_c = self._create_location_service(self.location_c, duration_minutes=60)

        self.employee_a = self._create_employee('employee-a@example.com', self.location_a, has_service=True)
        self.employee_a_second = self._create_employee('employee-a-second@example.com', self.location_a, has_service=True)
        self.employee_b = self._create_employee('employee-b@example.com', self.location_b, has_service=True)
        self.employee_without_service = self._create_employee('employee-c@example.com', self.location_a, has_service=False)

        self.search_url = '/api/v1/booking/search/'
        self.slots_url = f'/api/v1/booking/locations/{self.location_a.id}/slots/'
        self.create_url = '/api/v1/booking/appointments/'
        self.validate_url = '/api/v1/booking/appointments/validate/'

    def _create_location(self, name, email, latitude, longitude):
        address = Address.objects.create(
            country='Montenegro',
            city='Podgorica',
            street=f'{name} street',
            house_number='1',
            formatted_address=f'{name} street 1',
            latitude=latitude,
            longitude=longitude,
            validation_status='valid',
        )
        location = ProviderLocation.objects.create(
            provider=self.provider,
            name=name,
            structured_address=address,
            phone_number=f'+38267000{Address.objects.count():04d}',
            email=email,
            is_active=True,
        )
        location.served_pet_types.add(self.pet_type)
        return location

    def _create_pet(self, name):
        pet = Pet.objects.create(
            name=name,
            pet_type=self.pet_type,
            weight=Decimal('8.00'),
        )
        PetOwner.objects.create(pet=pet, user=self.owner, role='main')
        PetOwner.objects.create(pet=pet, user=self.coowner, role='coowner')
        return pet

    def _create_location_service(self, location, duration_minutes):
        return ProviderLocationService.objects.create(
            location=location,
            service=self.service,
            pet_type=self.pet_type,
            size_code='S',
            price=Decimal('35.00'),
            duration_minutes=duration_minutes,
            tech_break_minutes=30,
            is_active=True,
        )

    def _create_employee(self, email, location, has_service):
        employee = Employee.objects.create(
            user=User.objects.create_user(
                email=email,
                password='testpass123',
                phone_number=f'+2000{User.objects.count():05d}',
            ),
            is_active=True,
        )
        EmployeeLocationRole.objects.create(
            employee=employee,
            provider_location=location,
            role='service_worker',
            is_active=True,
        )
        if has_service:
            EmployeeLocationService.objects.create(
                employee=employee,
                provider_location=location,
                service=self.service,
            )

        LocationSchedule.objects.update_or_create(
            provider_location=location,
            weekday=self.target_date.weekday(),
            defaults={
                'open_time': time(9, 0),
                'close_time': time(18, 0),
                'is_closed': False,
            },
        )
        Schedule.objects.create(
            employee=employee,
            provider_location=location,
            day_of_week=self.target_date.weekday(),
            start_time=time(9, 0),
            end_time=time(18, 0),
            is_working=True,
        )
        return employee

    def _dt(self, hour, minute=0):
        value = datetime.combine(self.target_date, time(hour, minute))
        return timezone.make_aware(value, timezone.get_current_timezone())

    def _create_booking(self, *, pet, location, employee, start_time, escort_owner=None):
        end_time = start_time + timedelta(minutes=60)
        return Booking.objects.create(
            user=self.owner,
            escort_owner=escort_owner or self.owner,
            pet=pet,
            provider=self.provider,
            provider_location=location,
            employee=employee,
            service=self.service,
            status=self.active_status,
            start_time=start_time,
            end_time=end_time,
            occupied_duration_minutes=60,
            price=Decimal('35.00'),
        )


class BookingFlowLogicAPITests(BookingFlowBaseMixin, APITestCase):
    """API-тесты новой booking логики."""

    def test_booking_defaults_escort_owner_to_creator(self):
        response = self.client.post(
            self.create_url,
            {
                'provider_location_id': self.location_a.id,
                'service_id': self.service.id,
                'pet_id': self.pet_one.id,
                'start_time': self._dt(10, 0).isoformat(),
                'employee_id': self.employee_a.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        booking = Booking.objects.get(id=response.data['booking_id'])
        self.assertEqual(booking.escort_owner_id, self.owner.id)
        self.assertEqual(booking.occupied_duration_minutes, 60)

    def test_booking_is_rejected_if_escort_owner_is_not_pet_owner(self):
        response = self.client.post(
            self.create_url,
            {
                'provider_location_id': self.location_a.id,
                'service_id': self.service.id,
                'pet_id': self.pet_one.id,
                'start_time': self._dt(11, 0).isoformat(),
                'employee_id': self.employee_a.id,
                'escort_owner_id': self.other_user.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Escort owner', response.data['error'])

    def test_same_pet_cannot_be_double_booked_at_overlapping_times(self):
        self._create_booking(
            pet=self.pet_one,
            location=self.location_a,
            employee=self.employee_a,
            start_time=self._dt(10, 0),
        )

        response = self.client.post(
            self.create_url,
            {
                'provider_location_id': self.location_b.id,
                'service_id': self.service.id,
                'pet_id': self.pet_one.id,
                'start_time': self._dt(10, 30).isoformat(),
                'employee_id': self.employee_b.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'pet_conflict')

    @patch('booking.unified_services.RoutingService.get_travel_duration_seconds', return_value=7200)
    def test_same_pet_cannot_be_booked_in_routing_impossible_consecutive_bookings(self, _mock_routing):
        self._create_booking(
            pet=self.pet_one,
            location=self.location_a,
            employee=self.employee_a,
            start_time=self._dt(9, 0),
        )

        response = self.client.post(
            self.create_url,
            {
                'provider_location_id': self.location_b.id,
                'service_id': self.service.id,
                'pet_id': self.pet_one.id,
                'start_time': self._dt(10, 5).isoformat(),
                'employee_id': self.employee_b.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'pet_conflict')

    def test_same_escort_owner_can_accompany_multiple_pets_simultaneously_by_default(self):
        self._create_booking(
            pet=self.pet_one,
            location=self.location_a,
            employee=self.employee_a,
            start_time=self._dt(13, 0),
        )

        response = self.client.post(
            self.create_url,
            {
                'provider_location_id': self.location_a.id,
                'service_id': self.service.id,
                'pet_id': self.pet_two.id,
                'start_time': self._dt(13, 0).isoformat(),
                'employee_id': self.employee_a_second.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        booking = Booking.objects.get(id=response.data['booking_id'])
        self.assertEqual(booking.escort_owner_id, self.owner.id)

    def test_slot_generation_excludes_employees_who_do_not_provide_service_in_location(self):
        response = self.client.get(
            self.slots_url,
            {
                'service_id': self.service.id,
                'pet_id': self.pet_one.id,
                'date_start': self.target_date.isoformat(),
                'date_end': self.target_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        employee_ids = {slot['employee_id'] for slot in response.data['slots_by_date'][self.target_date.isoformat()]}
        self.assertIn(self.employee_a.id, employee_ids)
        self.assertIn(self.employee_a_second.id, employee_ids)
        self.assertNotIn(self.employee_without_service.id, employee_ids)

    def test_slot_generation_excludes_non_working_schedule_windows(self):
        response = self.client.get(
            self.slots_url,
            {
                'service_id': self.service.id,
                'pet_id': self.pet_one.id,
                'date_start': self.target_date.isoformat(),
                'date_end': self.target_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slot_hours = {
            datetime.fromisoformat(slot['start_time']).hour
            for slot in response.data['slots_by_date'][self.target_date.isoformat()]
        }
        self.assertTrue(all(9 <= hour <= 17 for hour in slot_hours))
        self.assertNotIn(8, slot_hours)

    def test_date_filtered_search_returns_only_locations_with_real_slots(self):
        response = self.client.get(
            self.search_url,
            {
                'pet_id': self.pet_one.id,
                'service_query': 'Groom',
                'date': self.target_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        location_ids = {item['id'] for item in response.data}
        self.assertIn(self.location_a.id, location_ids)
        self.assertIn(self.location_b.id, location_ids)
        self.assertNotIn(self.location_c.id, location_ids)

    def test_booking_creation_endpoint_and_slot_endpoint_use_same_availability_rules(self):
        self._create_booking(
            pet=self.pet_one,
            location=self.location_a,
            employee=self.employee_a,
            start_time=self._dt(9, 0),
        )

        slots_response = self.client.get(
            self.slots_url,
            {
                'service_id': self.service.id,
                'pet_id': self.pet_two.id,
                'date_start': self.target_date.isoformat(),
                'date_end': self.target_date.isoformat(),
            },
        )
        self.assertEqual(slots_response.status_code, status.HTTP_200_OK)
        first_slot = slots_response.data['slots_by_date'][self.target_date.isoformat()][0]

        create_response = self.client.post(
            self.create_url,
            {
                'provider_location_id': self.location_a.id,
                'service_id': self.service.id,
                'pet_id': self.pet_two.id,
                'start_time': first_slot['start_time'],
                'employee_id': first_slot['employee_id'],
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

    def test_booking_draft_validation_requires_escort_assignment_only_when_default_escort_is_unavailable(self):
        self._create_booking(
            pet=self.pet_one,
            location=self.location_b,
            employee=self.employee_b,
            start_time=self._dt(15, 0),
        )

        response = self.client.post(
            self.validate_url,
            {
                'provider_location_id': self.location_a.id,
                'service_id': self.service.id,
                'pet_id': self.pet_two.id,
                'start_time': self._dt(15, 0).isoformat(),
                'employee_id': self.employee_a.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_bookable'])
        self.assertTrue(response.data['requires_escort_assignment'])
        self.assertIn(self.coowner.id, response.data['possible_escort_owner_ids'])
        self.assertNotIn(self.owner.id, response.data['possible_escort_owner_ids'])


class HistoricalBookingSnapshotTests(BookingFlowBaseMixin, TestCase):
    """Тесты snapshot-полей на модели Booking."""

    def test_historical_booking_keeps_occupied_duration_snapshot_after_live_duration_change(self):
        booking = self._create_booking(
            pet=self.pet_one,
            location=self.location_a,
            employee=self.employee_a,
            start_time=self._dt(9, 0),
        )

        self.location_service_a.duration_minutes = 180
        self.location_service_a.save(update_fields=['duration_minutes'])

        booking.refresh_from_db()
        self.assertEqual(booking.occupied_duration_minutes, 60)
        self.assertEqual(booking.end_time, self._dt(10, 0))
