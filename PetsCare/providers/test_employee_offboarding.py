from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from providers.models import Provider, ProviderLocation, Employee, EmployeeProvider, EmployeeLocationRole, ProviderService, EmployeeLocationService
from catalog.models import Service
from booking.models import Booking, BookingStatus
from django.contrib.gis.geos import Point
from geolocation.models import Address
from pets.models import Pet, PetType

User = get_user_model()

class EmployeeOffboardingAPITest(APITestCase):
    def setUp(self):
        # Create Provider Admin
        self.provider_admin = User.objects.create_user(
            email='admin@vet.ru', password='password123', first_name='Admin', phone_number='+10000000000'
        )
        
        self.provider = Provider.objects.create(
            name="Vet Clinic", 
            email="contact@vet.ru", 
            phone_number="+71234567890",
            is_active=True,
            activation_status='active'
        )
        
        # Link admin to provider to give management permissions
        self.admin_emp = Employee.objects.create(user=self.provider_admin, is_active=True)
        EmployeeProvider.objects.create(
            employee=self.admin_emp, 
            provider=self.provider, 
            role=EmployeeProvider.ROLE_OWNER,
            is_owner=True,
            start_date=timezone.now().date()
        )

        # Create Address
        self.address = Address.objects.create(
            street="Main St, 1",
            city="Moscow",
            country="Russia",
            point=Point(37.6173, 55.7558, srid=4326)
        )
        
        # Create Location
        self.location = ProviderLocation.objects.create(
            provider=self.provider, 
            name="Main Branch", 
            is_active=True,
            structured_address=self.address,
            phone_number="+79998887766",
            email="location@vet.ru"
        )
        
        # Create Employee 1 (To be deactivated)
        self.emp1_user = User.objects.create_user(
            email='emp1@vet.ru', password='password123', first_name='John', last_name='Doe', phone_number='+10000000001'
        )
        self.emp1 = Employee.objects.create(user=self.emp1_user, is_active=True)
        EmployeeProvider.objects.create(
            employee=self.emp1, 
            provider=self.provider, 
            start_date=timezone.now().date()
        )
        self.emp1_loc_role = EmployeeLocationRole.objects.create(
            employee=self.emp1, provider_location=self.location, is_active=True
        )
        self.emp1.locations.add(self.location)
        
        # Create Employee 2 (Target for reassignment)
        self.emp2_user = User.objects.create_user(
            email='emp2@vet.ru', password='password123', first_name='Jane', last_name='Doe', phone_number='+10000000002'
        )
        self.emp2 = Employee.objects.create(user=self.emp2_user, is_active=True)
        EmployeeProvider.objects.create(
            employee=self.emp2, 
            provider=self.provider, 
            start_date=timezone.now().date()
        )
        self.emp2_loc_role = EmployeeLocationRole.objects.create(
            employee=self.emp2, provider_location=self.location, is_active=True
        )
        self.emp2.locations.add(self.location)

        # Basic Service
        self.service = Service.objects.create(name="Consultation", code="consult", level=0)
        self.provider_service = ProviderService.objects.create(
            provider=self.provider, service=self.service, price=1000, base_price=1000, duration_minutes=30
        )
        
        # Add services to employees
        EmployeeLocationService.objects.create(employee=self.emp1, provider_location=self.location, service=self.service)
        EmployeeLocationService.objects.create(employee=self.emp2, provider_location=self.location, service=self.service)
        
        # Booking Statuses
        self.status_active, _ = BookingStatus.objects.get_or_create(name='active', defaults={'name_en': 'Active'})
        self.status_cancelled, _ = BookingStatus.objects.get_or_create(name='cancelled', defaults={'name_en': 'Cancelled'})
        
        # Create Client User and Pet
        self.client_user = User.objects.create_user(
            email='client@vet.ru', password='password123', first_name='Client', phone_number='+10000000003'
        )
        self.pet_type, _ = PetType.objects.get_or_create(name="Cat", code="cat")
        self.pet = Pet.objects.create(
            main_owner=self.client_user,
            name="Fluffy",
            pet_type=self.pet_type,
            birth_date=timezone.now().date(),
            weight=4.5
        )
        
        self.client.force_authenticate(user=self.provider_admin)
        
        # URL names with providers: namespace
        self.deactivate_url = reverse('providers:location-staff-deactivate', kwargs={'location_pk': self.location.id, 'employee_id': self.emp1.id})
        self.reactivate_url = reverse('providers:location-staff-reactivate', kwargs={'location_pk': self.location.id, 'employee_id': self.emp1.id})

    def test_deactivate_staff_no_bookings(self):
        response = self.client.patch(self.deactivate_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.emp1_loc_role.refresh_from_db()
        self.assertFalse(self.emp1_loc_role.is_active)
        self.assertIsNotNone(self.emp1_loc_role.end_date)
        
    def test_deactivate_staff_with_future_bookings_returns_409(self):
        # Create a future booking for emp1
        future_date = timezone.now() + timedelta(days=2)
        booking = Booking.objects.create(
            user=self.client_user,
            pet=self.pet,
            price=1000,
            code="BKR1",
            provider_location=self.location,
            employee=self.emp1,
            service=self.service,
            start_time=future_date,
            end_time=future_date + timedelta(minutes=30),
            status=self.status_active
        )
        
        response = self.client.patch(self.deactivate_url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['conflict_type'], 'future_bookings')
        self.assertEqual(len(response.data['bookings']), 1)
        
        self.emp1_loc_role.refresh_from_db()
        self.assertTrue(self.emp1_loc_role.is_active)  # Still active
        
    def test_deactivate_staff_cancel_resolution(self):
        future_date = timezone.now() + timedelta(days=2)
        booking = Booking.objects.create(
            user=self.client_user,
            pet=self.pet,
            price=1000,
            code="BKR2",
            provider_location=self.location,
            employee=self.emp1,
            service=self.service,
            start_time=future_date,
            end_time=future_date + timedelta(minutes=30),
            status=self.status_active
        )
        
        response = self.client.patch(self.deactivate_url, data={
            'resolution_action': 'cancel',
            'cancellation_reason': 'Employee left'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.emp1_loc_role.refresh_from_db()
        self.assertFalse(self.emp1_loc_role.is_active)
        
        booking.refresh_from_db()
        self.assertEqual(booking.status, self.status_cancelled)
        self.assertEqual(booking.cancelled_by, 'provider')
        
    def test_deactivate_staff_reassign_resolution(self):
        future_date = timezone.now() + timedelta(days=2)
        booking = Booking.objects.create(
            user=self.client_user,
            pet=self.pet,
            price=1000,
            code="BKR3",
            provider_location=self.location,
            employee=self.emp1,
            service=self.service,
            start_time=future_date,
            end_time=future_date + timedelta(minutes=30),
            status=self.status_active
        )
        
        response = self.client.patch(self.deactivate_url, data={
            'resolution_action': 'reassign',
            'target_employee_id': self.emp2.id
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.emp1_loc_role.refresh_from_db()
        self.assertFalse(self.emp1_loc_role.is_active)
        
        booking.refresh_from_db()
        self.assertEqual(booking.employee, self.emp2)
        self.assertEqual(booking.status, self.status_active)
        
    def test_reactivate_staff(self):
        self.emp1_loc_role.is_active = False
        self.emp1_loc_role.end_date = timezone.now()
        self.emp1_loc_role.save()
        
        response = self.client.patch(self.reactivate_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.emp1_loc_role.refresh_from_db()
        self.assertTrue(self.emp1_loc_role.is_active)
        self.assertIsNone(self.emp1_loc_role.end_date)
