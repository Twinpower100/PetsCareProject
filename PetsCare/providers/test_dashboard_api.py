"""Тесты API operational dashboard провайдера."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from booking.constants import (
    BOOKING_STATUS_ACTIVE,
    BOOKING_STATUS_CANCELLED,
    BOOKING_STATUS_COMPLETED,
    CANCELLATION_REASON_CLIENT_NO_SHOW,
    CANCELLATION_REASON_PROVIDER_EMERGENCY_PREEMPTION,
    CANCELLED_BY_PROVIDER,
    COMPLETED_BY_USER,
    COMPLETION_REASON_MANUAL,
    ISSUE_STATUS_OPEN,
)
from booking.manual_notes import build_manual_booking_notes
from booking.models import Booking, BookingCancellationReason, BookingServiceIssue, BookingStatus
from catalog.models import Service
from geolocation.models import Address
from notifications.models import Notification
from providers.models import Employee, EmployeeLocationRole, EmployeeProvider, Provider, ProviderLocation, Schedule

User = get_user_model()


class ProviderDashboardAPITests(TestCase):
    """Проверяет расчёты и RBAC provider dashboard."""

    def setUp(self):
        """Подготавливает общие тестовые данные."""
        self.client = APIClient()
        self.now = timezone.localtime(timezone.now()).replace(hour=12, minute=0, second=0, microsecond=0)
        self.today = self.now.date()
        self.weekday = self.now.weekday()

        self.status_active, _ = BookingStatus.objects.get_or_create(name=BOOKING_STATUS_ACTIVE)
        self.status_completed, _ = BookingStatus.objects.get_or_create(name=BOOKING_STATUS_COMPLETED)
        self.status_cancelled, _ = BookingStatus.objects.get_or_create(name=BOOKING_STATUS_CANCELLED)
        self.reason_no_show, _ = BookingCancellationReason.objects.get_or_create(
            code=CANCELLATION_REASON_CLIENT_NO_SHOW,
            defaults={'label': 'No show', 'scope': CANCELLED_BY_PROVIDER},
        )
        self.reason_emergency, _ = BookingCancellationReason.objects.get_or_create(
            code=CANCELLATION_REASON_PROVIDER_EMERGENCY_PREEMPTION,
            defaults={'label': 'Emergency preemption', 'scope': CANCELLED_BY_PROVIDER},
        )

        self.provider = Provider.objects.create(
            name='PetCare Clinic',
            phone_number='+38267000100',
            email='clinic@example.com',
            activation_status='active',
            is_active=True,
        )

        self.address = Address.objects.create(
            country='Montenegro',
            city='Podgorica',
            street='Main street',
            house_number='1',
            formatted_address='Main street 1',
            latitude=42.44,
            longitude=19.26,
            validation_status='valid',
        )

        self.location_one = ProviderLocation.objects.create(
            provider=self.provider,
            name='Central Branch',
            structured_address=self.address,
            phone_number='+38267000101',
            email='central@example.com',
            is_active=True,
        )
        self.location_two = ProviderLocation.objects.create(
            provider=self.provider,
            name='North Branch',
            structured_address=self.address,
            phone_number='+38267000102',
            email='north@example.com',
            is_active=True,
        )

        self.provider_admin_user = self._create_user('admin@example.com', '+38267000110')
        self.provider_admin_user.add_role('provider_admin')
        self.provider_admin_employee = self._link_employee(
            user=self.provider_admin_user,
            provider_role=EmployeeProvider.ROLE_PROVIDER_ADMIN,
            is_provider_admin=True,
        )

        self.branch_manager_user = self._create_user('branch@example.com', '+38267000111')
        self.branch_manager_user.add_role('branch_manager')
        self.branch_manager_employee = self._link_employee(
            user=self.branch_manager_user,
            provider_role=EmployeeProvider.ROLE_SERVICE_WORKER,
        )
        EmployeeLocationRole.objects.create(
            employee=self.branch_manager_employee,
            provider_location=self.location_one,
            role=EmployeeLocationRole.ROLE_LOCATION_MANAGER,
            is_active=True,
        )
        self.location_one.manager = self.branch_manager_user
        self.location_one.save(update_fields=['manager'])

        self.worker_user = self._create_user('worker@example.com', '+38267000112')
        self.worker_user.add_role('employee')
        self.worker_employee = self._link_employee(
            user=self.worker_user,
            provider_role=EmployeeProvider.ROLE_SERVICE_WORKER,
        )
        EmployeeLocationRole.objects.create(
            employee=self.worker_employee,
            provider_location=self.location_one,
            role=EmployeeLocationRole.ROLE_SERVICE_WORKER,
            is_active=True,
        )

        self.worker_two_user = self._create_user('worker-two@example.com', '+38267000113')
        self.worker_two_user.add_role('employee')
        self.worker_two_employee = self._link_employee(
            user=self.worker_two_user,
            provider_role=EmployeeProvider.ROLE_SERVICE_WORKER,
        )
        EmployeeLocationRole.objects.create(
            employee=self.worker_two_employee,
            provider_location=self.location_two,
            role=EmployeeLocationRole.ROLE_SERVICE_WORKER,
            is_active=True,
        )

        self._create_schedule(self.branch_manager_employee, self.location_one)
        self._create_schedule(self.worker_employee, self.location_one)
        self._create_schedule(self.worker_two_employee, self.location_two)

        self.service = Service.objects.create(name='Consultation')

        self.active_booking = self._create_booking(
            employee=self.worker_employee,
            provider_location=self.location_one,
            status=self.status_active,
            start_time=self.now - timedelta(minutes=30),
            end_time=self.now + timedelta(minutes=30),
            price=Decimal('100.00'),
        )
        self.completed_today = self._create_booking(
            employee=self.branch_manager_employee,
            provider_location=self.location_one,
            status=self.status_completed,
            start_time=self.now - timedelta(hours=2),
            end_time=self.now - timedelta(hours=1, minutes=30),
            price=Decimal('80.00'),
            completed_at=self.now - timedelta(hours=1),
        )
        self.future_location_two = self._create_booking(
            employee=self.worker_two_employee,
            provider_location=self.location_two,
            status=self.status_active,
            start_time=self.now + timedelta(hours=2),
            end_time=self.now + timedelta(hours=3),
            price=Decimal('50.00'),
        )
        self.manual_emergency = self._create_booking(
            employee=self.worker_employee,
            provider_location=self.location_one,
            status=self.status_active,
            start_time=self.now + timedelta(hours=4),
            end_time=self.now + timedelta(hours=5),
            price=Decimal('70.00'),
            source=Booking.BookingSource.MANUAL_ENTRY,
            notes=build_manual_booking_notes(
                metadata={'is_guest': False, 'is_emergency': True},
                notes='Emergency walk-in',
            ),
        )
        self.cancelled_no_show = self._create_booking(
            employee=self.worker_employee,
            provider_location=self.location_one,
            status=self.status_cancelled,
            start_time=self.now + timedelta(hours=6),
            end_time=self.now + timedelta(hours=7),
            price=Decimal('40.00'),
            cancelled_at=self.now - timedelta(minutes=10),
            cancellation_reason=self.reason_no_show,
            client_attendance='no_show',
        )
        self.displaced_booking = self._create_booking(
            employee=self.branch_manager_employee,
            provider_location=self.location_one,
            status=self.status_cancelled,
            start_time=self.now + timedelta(hours=8),
            end_time=self.now + timedelta(hours=9),
            price=Decimal('60.00'),
            cancelled_at=self.now - timedelta(minutes=5),
            cancellation_reason=self.reason_emergency,
            client_attendance='arrived',
        )
        self.completed_month_other_branch = self._create_booking(
            employee=self.worker_two_employee,
            provider_location=self.location_two,
            status=self.status_completed,
            start_time=self.now - timedelta(days=2),
            end_time=self.now - timedelta(days=2, minutes=-30),
            price=Decimal('200.00'),
            completed_at=self.now - timedelta(days=2),
        )

        BookingServiceIssue.objects.create(
            booking=self.active_booking,
            issue_type='service_not_provided',
            status=ISSUE_STATUS_OPEN,
            reported_by_user=self.provider_admin_user,
        )

        Notification.objects.create(
            user=self.provider_admin_user,
            notification_type='system',
            title='System alert',
            message='Queue processing is delayed.',
            priority='high',
            channel='in_app',
        )

    def _create_user(self, email: str, phone: str):
        """Создаёт пользователя для тестов."""
        return User.objects.create_user(
            email=email,
            password='password123',
            username=email,
            phone_number=phone,
        )

    def _link_employee(self, *, user, provider_role: str, is_provider_admin: bool = False) -> Employee:
        """Создаёт сотрудника и активную связь с провайдером."""
        employee = Employee.objects.create(user=user, is_active=True)
        EmployeeProvider.objects.create(
            employee=employee,
            provider=self.provider,
            role=provider_role,
            is_provider_admin=is_provider_admin,
            start_date=self.today,
        )
        return employee

    def _create_schedule(self, employee: Employee, location: ProviderLocation) -> None:
        """Создаёт активное расписание на текущий день недели."""
        start_dt = self.now - timedelta(hours=1)
        if start_dt.date() != self.today:
            start_dt = self.now.replace(hour=0, minute=0, second=0, microsecond=0)

        end_dt = self.now + timedelta(hours=8)
        if end_dt.date() != self.today or end_dt <= start_dt:
            end_dt = self.now.replace(hour=23, minute=59, second=0, microsecond=0)

        if end_dt <= start_dt:
            start_dt = self.now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = self.now.replace(hour=23, minute=59, second=0, microsecond=0)

        Schedule.objects.create(
            employee=employee,
            provider_location=location,
            day_of_week=self.weekday,
            start_time=start_dt.time().replace(microsecond=0),
            end_time=end_dt.time().replace(microsecond=0),
            is_working=True,
        )

    def _create_booking(
        self,
        *,
        employee: Employee,
        provider_location: ProviderLocation,
        status: BookingStatus,
        start_time,
        end_time,
        price: Decimal,
        source: str = Booking.BookingSource.BOOKING_SERVICE,
        notes: str = '',
        completed_at=None,
        cancelled_at=None,
        cancellation_reason=None,
        client_attendance='unknown',
    ) -> Booking:
        """Создаёт бронирование для dashboard тестов."""
        booking = Booking.objects.create(
            user=self.provider_admin_user,
            escort_owner=self.provider_admin_user,
            pet=self._get_or_create_pet(),
            provider=self.provider,
            provider_location=provider_location,
            employee=employee,
            service=self.service,
            status=status,
            start_time=start_time,
            end_time=end_time,
            occupied_duration_minutes=60,
            price=price,
            source=source,
            notes=notes,
            completed_at=completed_at,
            completed_by_actor=COMPLETED_BY_USER if status.name == BOOKING_STATUS_COMPLETED else '',
            completed_by_user=self.provider_admin_user if status.name == BOOKING_STATUS_COMPLETED else None,
            completion_reason_code=COMPLETION_REASON_MANUAL if status.name == BOOKING_STATUS_COMPLETED else '',
            cancelled_by=CANCELLED_BY_PROVIDER if status.name == BOOKING_STATUS_CANCELLED else '',
            cancelled_by_user=self.provider_admin_user if status.name == BOOKING_STATUS_CANCELLED else None,
            cancelled_at=cancelled_at,
            cancellation_reason=cancellation_reason,
            client_attendance=client_attendance,
        )
        return booking

    def _get_dashboard_response(self, user):
        """Выполняет запрос к dashboard с фиксированным текущим временем."""
        self.client.force_authenticate(user=user)
        with patch('providers.dashboard_services.timezone.now', return_value=self.now):
            return self.client.get(f'/api/v1/provider/dashboard/?provider_id={self.provider.id}&alerts_minutes=60')

    def _get_or_create_pet(self):
        """Возвращает технического питомца для тестовых бронирований."""
        from pets.models import Pet, PetOwner, PetType

        pet_type, _ = PetType.objects.get_or_create(name='Dog')
        pet, _ = Pet.objects.get_or_create(
            name='Rex',
            pet_type=pet_type,
            defaults={'weight': Decimal('10.00')},
        )
        PetOwner.objects.get_or_create(pet=pet, user=self.provider_admin_user, defaults={'role': 'main'})
        return pet

    def test_provider_admin_receives_provider_financials(self):
        """Provider admin видит агрегаты и финансы по всем филиалам провайдера."""
        response = self._get_dashboard_response(self.provider_admin_user)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['scope']['scope_type'], 'provider')
        self.assertTrue(response.data['scope']['can_view_financials'])
        self.assertEqual(response.data['appointments']['completed'], 1)
        self.assertEqual(response.data['appointments']['total'], 4)
        self.assertTrue(response.data['appointments']['has_overload'])
        self.assertEqual(response.data['staff']['total'], 3)
        self.assertEqual(response.data['staff']['busy'], 1)
        self.assertEqual(response.data['staff']['available'], 2)
        self.assertEqual(response.data['financials']['expected_revenue_today'], '340.00')
        self.assertEqual(response.data['financials']['month_actual_revenue'], '280.00')
        self.assertEqual(response.data['incidents'][0]['count'], 1)
        self.assertEqual(response.data['incidents'][1]['count'], 1)
        self.assertEqual(response.data['incidents'][2]['count'], 1)
        self.assertIn('system', [item['event_type'] for item in response.data['system_alerts']])

    def test_branch_manager_receives_location_financials_only(self):
        """Branch manager получает только данные своего филиала."""
        response = self._get_dashboard_response(self.branch_manager_user)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['scope']['scope_type'], 'location')
        self.assertEqual(response.data['scope']['location_ids'], [self.location_one.id])
        self.assertTrue(response.data['scope']['can_view_financials'])
        self.assertEqual(response.data['appointments']['completed'], 1)
        self.assertEqual(response.data['appointments']['total'], 3)
        self.assertEqual(response.data['financials']['expected_revenue_today'], '290.00')
        self.assertEqual(response.data['financials']['month_actual_revenue'], '80.00')
        self.assertEqual(response.data['staff']['total'], 2)
        self.assertEqual(response.data['staff']['busy'], 1)

    def test_line_staff_does_not_receive_financials(self):
        """Линейный сотрудник получает operational data без финансовых полей."""
        response = self._get_dashboard_response(self.worker_user)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['scope']['scope_type'], 'location')
        self.assertFalse(response.data['scope']['can_view_financials'])
        self.assertNotIn('financials', response.data)
        self.assertEqual(response.data['appointments']['completed'], 1)
        self.assertEqual(response.data['appointments']['total'], 3)

    def test_provider_brief_list_returns_only_accessible_organizations(self):
        """brief-list не должен падать на select_related и должен фильтровать чужие организации."""
        foreign_provider = Provider.objects.create(
            name='Foreign Clinic',
            phone_number='+38267000999',
            email='foreign@example.com',
            activation_status='active',
            is_active=True,
            structured_address=self.address,
        )

        self.client.force_authenticate(self.provider_admin_user)
        response = self.client.get(
            reverse('providers:provider-list-create'),
            {'brief': 1},
        )

        self.assertEqual(response.status_code, 200)
        provider_ids = [item['id'] for item in response.data['results']]  # type: ignore[index]
        self.assertIn(self.provider.id, provider_ids)
        self.assertNotIn(foreign_provider.id, provider_ids)
