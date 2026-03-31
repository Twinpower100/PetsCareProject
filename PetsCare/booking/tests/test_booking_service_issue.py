from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from booking.models import Booking, BookingStatus, BookingCancellationReason, BookingServiceIssue
from booking.serializers import BookingListSerializer, BookingSerializer
from booking.constants import (
    BOOKING_SERVICE_ISSUE_REPORT_WINDOW_DAYS,
    BOOKING_STATUS_ACTIVE, BOOKING_STATUS_CANCELLED, BOOKING_STATUS_COMPLETED,
    CANCELLATION_REASON_CLIENT_REFUSED_ON_SITE, CANCELLATION_REASON_CLIENT_NO_SHOW,
    CANCELLATION_REASON_PROVIDER_UNAVAILABLE, CANCELLED_BY_CLIENT, CANCELLED_BY_PROVIDER,
    ISSUE_TYPE_SERVICE_NOT_PROVIDED, ISSUE_STATUS_OPEN, ISSUE_STATUS_RESOLVED,
    ISSUE_STATUS_REJECTED, RESOLUTION_OUTCOME_PROVIDER_CANCELLED,
    RESOLUTION_OUTCOME_COMPLETED, RESOLVED_BY_SUPPORT
)
from pets.models import Pet, PetType, Breed, PetOwner
from providers.models import Provider, Employee, ProviderLocation, ProviderLocationService, EmployeeProvider
from catalog.models import Service
from geolocation.models import Address

User = get_user_model()

class BookingServiceIssueResolutionTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            email='client@example.com', password='password123', username='client_user', phone_number='+1234567890'
        )
        self.provider_admin = User.objects.create_user(
            email='admin@provider.com', password='password123', username='provider_admin', phone_number='+1234567891'
        )
        self.employee_user = User.objects.create_user(
            email='employee@provider.com', password='password123', username='employee_user', phone_number='+1234567892'
        )
        self.employee_user.add_role('employee')
        self.other_client = User.objects.create_user(
            email='other@example.com', password='password123', username='other_client', phone_number='+1234567893'
        )
        self.system_admin = User.objects.create_user(
            email='support@example.com', password='password123', username='support_user', phone_number='+1234567894'
        )
        self.system_admin.add_role('system_admin')
        
        # Setup provider & employee
        self.provider = Provider.objects.create(name="Pet Care Clinic")
        
        self.provider_admin.add_role('provider_admin')
        self.provider_admin_emp = Employee.objects.create(user=self.provider_admin, is_active=True)
        EmployeeProvider.objects.create(
            employee=self.provider_admin_emp,
            provider=self.provider,
            role=EmployeeProvider.ROLE_PROVIDER_ADMIN,
            is_provider_admin=True,
            start_date=timezone.now().date()
        )
        
        self.employee = Employee.objects.create(user=self.employee_user, is_active=True)
        EmployeeProvider.objects.create(
            employee=self.employee,
            provider=self.provider,
            role=EmployeeProvider.ROLE_SERVICE_WORKER,
            start_date=timezone.now().date()
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
        
        self.location = ProviderLocation.objects.create(
            provider=self.provider, 
            name="Main Branch",
            structured_address=self.address,
            phone_number="+38267000001",
            email="location@example.com",
            is_active=True
        )
        
        # Setup pet
        self.pet_type = PetType.objects.create(name="Dog")
        self.breed = Breed.objects.create(name="Pug", pet_type=self.pet_type)
        self.pet = Pet.objects.create(
            name="Rex", pet_type=self.pet_type, breed=self.breed, weight=8.0
        )
        PetOwner.objects.create(pet=self.pet, user=self.client_user, role='main')

        self.service = Service.objects.create(name="Grooming")
        
        self.provider_service = ProviderLocationService.objects.create(
            location=self.location,
            service=self.service,
            price=100.00,
            duration_minutes=60,
            pet_type=self.pet_type,
            size_code='S'
        )
        
        self.status_active, _ = BookingStatus.objects.get_or_create(name=BOOKING_STATUS_ACTIVE)
        self.status_cancelled, _ = BookingStatus.objects.get_or_create(name=BOOKING_STATUS_CANCELLED)
        self.status_completed, _ = BookingStatus.objects.get_or_create(name=BOOKING_STATUS_COMPLETED)
        
        now = timezone.now()
        
        # Default cancellation reasons
        BookingCancellationReason.objects.get_or_create(code=CANCELLATION_REASON_CLIENT_REFUSED_ON_SITE, defaults={'label': 'Refused', 'scope': CANCELLED_BY_CLIENT})
        BookingCancellationReason.objects.get_or_create(code=CANCELLATION_REASON_CLIENT_NO_SHOW, defaults={'label': 'No show', 'scope': CANCELLED_BY_PROVIDER})
        BookingCancellationReason.objects.get_or_create(code=CANCELLATION_REASON_PROVIDER_UNAVAILABLE, defaults={'label': 'Provider unavailable', 'scope': CANCELLED_BY_PROVIDER})
        
        self.booking = Booking.objects.create(
            user=self.client_user,
            escort_owner=self.client_user,
            pet=self.pet,
            provider=self.provider,
            provider_location=self.location,
            employee=self.employee,
            service=self.service,
            status=self.status_active,
            start_time=now - timedelta(hours=2),
            end_time=now - timedelta(hours=1),
            occupied_duration_minutes=60,
            price=100.00
        )
        
        self.api_client = APIClient()

    def _create_booking(self, *, start_time, end_time, user=None):
        return Booking.objects.create(
            user=user or self.client_user,
            escort_owner=user or self.client_user,
            pet=self.pet,
            provider=self.provider,
            provider_location=self.location,
            employee=self.employee,
            service=self.service,
            status=self.status_active,
            start_time=start_time,
            end_time=end_time,
            occupied_duration_minutes=60,
            price=100.00,
        )

    def _report_issue_url(self, booking_id):
        return f'/api/v1/bookings/{booking_id}/report_service_issue/'

    def _resolve_issue_url(self, booking_id, issue_id):
        return f'/api/v1/bookings/{booking_id}/service-issues/{issue_id}/resolve/'

    def _mark_no_show_url(self, booking_id):
        return f'/api/v1/bookings/{booking_id}/mark_no_show_by_client/'

    def test_client_reports_issue(self):
        """1. Client reports service-not-provided after arrival."""
        self.api_client.force_authenticate(user=self.client_user)
        url = self._report_issue_url(self.booking.id)
        
        data = {
            'issue_type': ISSUE_TYPE_SERVICE_NOT_PROVIDED,
            'client_attendance_snapshot': 'arrived',
            'description': 'Provider was closed'
        }
        response = self.api_client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        self.assertEqual(BookingServiceIssue.objects.count(), 1)
        issue = BookingServiceIssue.objects.first()
        self.assertEqual(issue.booking, self.booking)
        self.assertEqual(issue.status, ISSUE_STATUS_OPEN)
        self.assertEqual(issue.reported_by_user, self.client_user)
        self.assertEqual(issue.client_attendance_snapshot, 'arrived')
        self.assertEqual(issue.description, 'Provider was closed')

    def test_client_cannot_report_issue_for_future_booking(self):
        self.api_client.force_authenticate(user=self.client_user)
        future_booking = self._create_booking(
            start_time=timezone.now() + timedelta(hours=2),
            end_time=timezone.now() + timedelta(hours=3),
        )

        response = self.api_client.post(
            self._report_issue_url(future_booking.id),
            {'issue_type': ISSUE_TYPE_SERVICE_NOT_PROVIDED},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)  # type: ignore[arg-type]

    def test_client_cannot_report_issue_after_grace_window(self):
        self.api_client.force_authenticate(user=self.client_user)
        expired_booking = self._create_booking(
            start_time=timezone.now() - timedelta(days=BOOKING_SERVICE_ISSUE_REPORT_WINDOW_DAYS + 2, hours=1),
            end_time=timezone.now() - timedelta(days=BOOKING_SERVICE_ISSUE_REPORT_WINDOW_DAYS + 2),
        )

        response = self.api_client.post(
            self._report_issue_url(expired_booking.id),
            {'issue_type': ISSUE_TYPE_SERVICE_NOT_PROVIDED},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)  # type: ignore[arg-type]

    def test_reporting_issue_does_not_cancel_booking(self):
        """2. Reporting issue does not create client cancellation."""
        self.api_client.force_authenticate(user=self.client_user)
        url = self._report_issue_url(self.booking.id)
        self.api_client.post(url, {
            'issue_type': ISSUE_TYPE_SERVICE_NOT_PROVIDED,
        })
        
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status.name, BOOKING_STATUS_ACTIVE)
        self.assertIsNone(self.booking.cancelled_at)

    def test_cannot_create_duplicate_open_service_issue(self):
        BookingServiceIssue.objects.create(
            booking=self.booking,
            issue_type=ISSUE_TYPE_SERVICE_NOT_PROVIDED,
            reported_by_user=self.client_user,
        )
        self.api_client.force_authenticate(user=self.client_user)

        response = self.api_client.post(
            self._report_issue_url(self.booking.id),
            {'issue_type': ISSUE_TYPE_SERVICE_NOT_PROVIDED},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)  # type: ignore[arg-type]

    def test_provider_resolves_in_favor_of_client(self):
        """3. Provider resolves issue in favor of client -> booking cancelled by provider with 'arrived'."""
        issue = BookingServiceIssue.objects.create(
            booking=self.booking,
            issue_type=ISSUE_TYPE_SERVICE_NOT_PROVIDED,
            reported_by_user=self.client_user,
            client_attendance_snapshot='arrived'
        )
        
        self.api_client.force_authenticate(user=self.provider_admin)
        url = self._resolve_issue_url(self.booking.id, issue.id)
        
        response = self.api_client.post(url, {
            'resolution_outcome': RESOLUTION_OUTCOME_PROVIDER_CANCELLED,
            'cancellation_reason': CANCELLATION_REASON_PROVIDER_UNAVAILABLE,
            'resolution_note': 'Sorry for the inconvenience'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        issue.refresh_from_db()
        self.assertEqual(issue.status, ISSUE_STATUS_RESOLVED)
        self.assertEqual(issue.resolution_outcome, RESOLUTION_OUTCOME_PROVIDER_CANCELLED)
        
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status.name, BOOKING_STATUS_CANCELLED)
        self.assertEqual(self.booking.cancelled_by, CANCELLED_BY_PROVIDER)
        self.assertEqual(self.booking.client_attendance, 'arrived')
        self.assertEqual(self.booking.cancellation_reason.code, CANCELLATION_REASON_PROVIDER_UNAVAILABLE)

    def test_provider_resolves_issue_as_completed(self):
        """4. Provider resolves issue as service delivered -> booking completed."""
        issue = BookingServiceIssue.objects.create(
            booking=self.booking,
            issue_type=ISSUE_TYPE_SERVICE_NOT_PROVIDED,
            reported_by_user=self.client_user,
            client_attendance_snapshot='unknown'
        )
        
        self.api_client.force_authenticate(user=self.employee_user)
        url = self._resolve_issue_url(self.booking.id, issue.id)
        
        response = self.api_client.post(url, {
            'resolution_outcome': RESOLUTION_OUTCOME_COMPLETED,
            'resolution_note': 'Service was actually rendered'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        issue.refresh_from_db()
        self.assertEqual(issue.status, ISSUE_STATUS_RESOLVED)
        self.assertEqual(issue.resolution_outcome, RESOLUTION_OUTCOME_COMPLETED)
        
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status.name, BOOKING_STATUS_COMPLETED)

    def test_support_can_resolve_issue_for_any_booking(self):
        issue = BookingServiceIssue.objects.create(
            booking=self.booking,
            issue_type=ISSUE_TYPE_SERVICE_NOT_PROVIDED,
            reported_by_user=self.client_user,
            client_attendance_snapshot='arrived'
        )

        self.api_client.force_authenticate(user=self.system_admin)
        response = self.api_client.post(
            self._resolve_issue_url(self.booking.id, issue.id),
            {
                'resolution_outcome': RESOLUTION_OUTCOME_PROVIDER_CANCELLED,
                'cancellation_reason': CANCELLATION_REASON_PROVIDER_UNAVAILABLE,
                'resolution_note': 'Resolved by support',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        issue.refresh_from_db()
        self.assertEqual(issue.resolved_by_actor, RESOLVED_BY_SUPPORT)
        self.assertEqual(issue.status, ISSUE_STATUS_RESOLVED)

    def test_booking_serializers_expose_service_issue_summary(self):
        issue = BookingServiceIssue.objects.create(
            booking=self.booking,
            issue_type=ISSUE_TYPE_SERVICE_NOT_PROVIDED,
            reported_by_user=self.client_user,
            client_attendance_snapshot='arrived',
        )

        detail_payload = BookingSerializer(self.booking).data
        list_payload = BookingListSerializer(self.booking).data

        self.assertTrue(detail_payload['has_open_service_issue'])
        self.assertEqual(detail_payload['latest_service_issue']['id'], issue.id)
        self.assertEqual(list_payload['latest_service_issue']['status'], ISSUE_STATUS_OPEN)
        self.assertTrue(list_payload['has_open_service_issue'])

    def test_client_cannot_report_issue_for_other_booking(self):
        """6. Client cannot report issue for чужой booking."""
        self.api_client.force_authenticate(user=self.other_client)
        url = self._report_issue_url(self.booking.id)
        
        response = self.api_client.post(url, {
            'issue_type': ISSUE_TYPE_SERVICE_NOT_PROVIDED,
        })
        # the list view probably filters by user, so it might be 404
        self.assertTrue(response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    def test_provider_cannot_resolve_issue_for_other_provider(self):
        """7. Provider cannot resolve issue for another provider’s booking."""
        other_provider = Provider.objects.create(
            name="Other Clinic",
            email='other-clinic@example.com',
            phone_number='+38267000002',
        )
        other_admin = User.objects.create_user(
            email='other_admin@prov.com',
            password='pw',
            username='other_adm',
            phone_number='+1234567895',
        )
        other_admin.add_role('provider_admin')
        other_employee = Employee.objects.create(user=other_admin, is_active=True)
        EmployeeProvider.objects.create(
            employee=other_employee,
            provider=other_provider,
            role=EmployeeProvider.ROLE_PROVIDER_ADMIN,
            is_provider_admin=True,
            start_date=timezone.now().date(),
        )
        
        issue = BookingServiceIssue.objects.create(
            booking=self.booking,
            issue_type=ISSUE_TYPE_SERVICE_NOT_PROVIDED,
            reported_by_user=self.client_user
        )
        
        # Test finding url first
        url = self._resolve_issue_url(self.booking.id, issue.id)
        
        self.api_client.force_authenticate(user=other_admin)
        response = self.api_client.post(url, {
            'resolution_outcome': RESOLUTION_OUTCOME_COMPLETED
        })
        self.assertTrue(response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    def test_existing_no_show_flow_produces_provider_cancellation(self):
        """8. Existing no-show flow still produces provider-side cancellation with client_no_show."""
        self.api_client.force_authenticate(user=self.provider_admin)
        url = self._mark_no_show_url(self.booking.id)
        
        response = self.api_client.post(url, {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status.name, BOOKING_STATUS_CANCELLED)
        self.assertEqual(self.booking.cancelled_by, CANCELLED_BY_PROVIDER)
        self.assertEqual(self.booking.client_attendance, 'no_show')
        self.assertEqual(self.booking.cancellation_reason.code, CANCELLATION_REASON_CLIENT_NO_SHOW)
