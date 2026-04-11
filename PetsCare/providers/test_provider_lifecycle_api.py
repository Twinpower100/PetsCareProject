"""Тесты lifecycle API организаций и филиалов."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from geolocation.models import Address
from providers.models import (
    Employee,
    EmployeeLocationRole,
    EmployeeProvider,
    Provider,
    ProviderLifecycleSettings,
    ProviderLocation,
    Schedule,
)
from providers.permission_service import ProviderPermissionService
from providers.serializers import ProviderLocationListSerializer

User = get_user_model()


class ProviderLifecycleAPITests(TestCase):
    """Проверяет lifecycle-операции и post-termination доступ."""

    def setUp(self):
        """Создаёт минимальный набор данных для lifecycle-сценариев."""
        self.today = timezone.localdate()
        ProviderLifecycleSettings.get_solo()

        self.provider = Provider.objects.create(
            name='PetCare Lifecycle Org',
            phone_number='+38267001000',
            email='org@example.com',
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
        self.location = ProviderLocation.objects.create(
            provider=self.provider,
            name='Main Branch',
            structured_address=self.address,
            phone_number='+38267001001',
            email='branch@example.com',
        )

        self.owner_user = self._create_user('owner@example.com', '+38267001010')
        self.owner_employee = Employee.objects.create(user=self.owner_user)
        EmployeeProvider.objects.create(
            employee=self.owner_employee,
            provider=self.provider,
            role=EmployeeProvider.ROLE_OWNER,
            start_date=self.today,
            is_owner=True,
        )

        self.provider_admin_user = self._create_user('admin@example.com', '+38267001011')
        self.provider_admin_employee = Employee.objects.create(user=self.provider_admin_user)
        self.provider_admin_link = EmployeeProvider.objects.create(
            employee=self.provider_admin_employee,
            provider=self.provider,
            role=EmployeeProvider.ROLE_PROVIDER_ADMIN,
            start_date=self.today,
            is_provider_admin=True,
        )

        self.branch_manager_user = self._create_user('branch-manager@example.com', '+38267001012')
        self.branch_manager_employee = Employee.objects.create(user=self.branch_manager_user)
        EmployeeProvider.objects.create(
            employee=self.branch_manager_employee,
            provider=self.provider,
            role=EmployeeProvider.ROLE_WORKER,
            start_date=self.today,
        )
        self.branch_manager_role = EmployeeLocationRole.objects.create(
            employee=self.branch_manager_employee,
            provider_location=self.location,
            role=EmployeeLocationRole.ROLE_BRANCH_MANAGER,
            is_active=True,
        )
        self.location.manager = self.branch_manager_user
        self.location.save(update_fields=['manager'])

    def _create_user(self, email: str, phone_number: str):
        """Создаёт пользователя для provider lifecycle тестов."""
        user = User.objects.create_user(
            email=email,
            password='password123',
            username=email,
            phone_number=phone_number,
        )
        user.add_role('provider_admin')
        return user

    def _auth_client(self, user):
        """Возвращает аутентифицированный API client."""
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _response_items(self, response):
        """Нормализует list-ответ DRF."""
        data = response.json()
        if isinstance(data, list):
            return data
        return data.get('results', [])

    def test_owner_keeps_read_only_access_during_post_termination_window(self):
        """После termination owner остаётся в read-only окне и видит организацию в кабинете."""
        client = self._auth_client(self.owner_user)

        response = client.post(
            f'/api/v1/providers/{self.provider.id}/partnership/terminate/',
            {
                'effective_date': self.today.isoformat(),
                'reason': 'Contract completed',
            },
            format='json',
            HTTP_API_VERSION='v1',
        )

        self.assertEqual(response.status_code, 200, response.content)

        self.provider.refresh_from_db()
        self.location.refresh_from_db()
        self.provider_admin_link.refresh_from_db()
        self.branch_manager_role.refresh_from_db()

        self.assertEqual(self.provider.partnership_status, Provider.PARTNERSHIP_STATUS_TERMINATED)
        self.assertFalse(self.provider.is_active)
        self.assertTrue(self.provider.has_post_termination_owner_access())
        self.assertIsNotNone(self.provider.post_termination_access_until)

        self.assertEqual(self.location.lifecycle_status, ProviderLocation.LIFECYCLE_STATUS_DEACTIVATED)
        self.assertFalse(self.location.is_active)

        self.assertEqual(self.provider_admin_link.end_date, self.today)
        self.assertFalse(self.provider_admin_link.is_provider_admin)
        self.assertFalse(self.branch_manager_role.is_active)
        self.assertEqual(self.branch_manager_role.end_date.date(), self.today)

        fresh_owner = User.objects.get(pk=self.owner_user.pk)
        fresh_client = self._auth_client(fresh_owner)

        permissions_response = fresh_client.get(
            f'/api/v1/providers/{self.provider.id}/my-permissions/',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(permissions_response.status_code, 200, permissions_response.content)
        permissions_data = permissions_response.json()
        self.assertEqual(permissions_data['roles'], ['owner'])
        self.assertTrue(permissions_data['permissions']['dashboard']['can_read'])
        self.assertNotIn('org.deactivation', permissions_data['permissions'])
        self.assertFalse(
            ProviderPermissionService.check_permission(
                fresh_owner,
                Provider.objects.get(pk=self.provider.pk),
                'org.deactivation',
                'delete',
            )
        )

        providers_response = fresh_client.get('/api/v1/providers/?brief=1', HTTP_API_VERSION='v1')
        self.assertEqual(providers_response.status_code, 200, providers_response.content)
        provider_ids = {item['id'] for item in self._response_items(providers_response)}
        self.assertIn(self.provider.id, provider_ids)

    def test_owner_loses_access_after_post_termination_window_expires(self):
        """После истечения owner read-only окна доступ к terminated организации пропадает."""
        self.provider.partnership_status = Provider.PARTNERSHIP_STATUS_TERMINATED
        self.provider.is_active = False
        self.provider.post_termination_access_until = timezone.now() - timedelta(days=1)
        self.provider.save(update_fields=['partnership_status', 'is_active', 'post_termination_access_until', 'updated_at'])

        owner = User.objects.get(pk=self.owner_user.pk)
        provider = Provider.objects.get(pk=self.provider.pk)

        self.assertEqual(
            ProviderPermissionService.get_user_roles_for_provider(owner, provider),
            [],
        )

        client = self._auth_client(owner)
        providers_response = client.get('/api/v1/providers/?brief=1', HTTP_API_VERSION='v1')
        self.assertEqual(providers_response.status_code, 200, providers_response.content)
        provider_ids = {item['id'] for item in self._response_items(providers_response)}
        self.assertNotIn(self.provider.id, provider_ids)

    def test_branch_manager_can_see_closed_branch_and_reactivate_it(self):
        """Branch manager не теряет видимость временно закрытого филиала и может его реактивировать."""
        client = self._auth_client(self.branch_manager_user)
        reopen_date = (self.today + timedelta(days=10)).isoformat()

        close_response = client.post(
            f'/api/v1/providers/{self.provider.id}/locations/{self.location.id}/temporary-close/',
            {
                'effective_date': self.today.isoformat(),
                'resume_date': reopen_date,
                'reason': 'Renovation',
            },
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(close_response.status_code, 200, close_response.content)

        self.location.refresh_from_db()
        self.assertEqual(self.location.lifecycle_status, ProviderLocation.LIFECYCLE_STATUS_TEMPORARILY_CLOSED)
        self.assertFalse(self.location.is_active)

        list_response = client.get(
            f'/api/v1/provider-locations/?provider={self.provider.id}',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(list_response.status_code, 200, list_response.content)
        location_ids = {item['id'] for item in self._response_items(list_response)}
        self.assertIn(self.location.id, location_ids)

        detail_response = client.get(
            f'/api/v1/provider-locations/{self.location.id}/',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(detail_response.status_code, 200, detail_response.content)

        reactivate_response = client.post(
            f'/api/v1/providers/{self.provider.id}/locations/{self.location.id}/reactivate/',
            {
                'effective_date': self.today.isoformat(),
                'reason': 'Renovation completed',
            },
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(reactivate_response.status_code, 200, reactivate_response.content)

        self.location.refresh_from_db()
        self.assertEqual(self.location.lifecycle_status, ProviderLocation.LIFECYCLE_STATUS_ACTIVE)
        self.assertTrue(self.location.is_active)

    def test_pause_requires_resume_date(self):
        """Временная пауза организации и филиала требует дату возобновления."""
        owner_client = self._auth_client(self.owner_user)
        branch_client = self._auth_client(self.branch_manager_user)

        org_response = owner_client.post(
            f'/api/v1/providers/{self.provider.id}/partnership/pause/',
            {
                'effective_date': self.today.isoformat(),
                'reason': 'Renovation',
            },
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(org_response.status_code, 400, org_response.content)
        self.assertIn('resume_date', org_response.json())

        branch_response = branch_client.post(
            f'/api/v1/providers/{self.provider.id}/locations/{self.location.id}/temporary-close/',
            {
                'effective_date': self.today.isoformat(),
                'reason': 'Renovation',
            },
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(branch_response.status_code, 400, branch_response.content)
        self.assertIn('resume_date', branch_response.json())

    def test_reactivation_restores_provider_links_and_selected_branch_roles(self):
        """После termination/reactivate восстанавливаются org links и роли выбранного филиала."""
        owner_client = self._auth_client(self.owner_user)

        terminate_response = owner_client.post(
            f'/api/v1/providers/{self.provider.id}/partnership/terminate/',
            {
                'effective_date': self.today.isoformat(),
                'reason': 'Contract completed',
            },
            format='json',
            HTTP_API_VERSION='v1',
            )
        self.assertEqual(terminate_response.status_code, 200, terminate_response.content)

        reactivate_provider_response = owner_client.post(
            f'/api/v1/providers/{self.provider.id}/partnership/reactivate/',
            {
                'effective_date': self.today.isoformat(),
                'reason': 'Contract renewed',
            },
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(reactivate_provider_response.status_code, 200, reactivate_provider_response.content)

        self.provider_admin_link.refresh_from_db()
        self.assertIsNone(self.provider_admin_link.end_date)
        self.assertTrue(self.provider_admin_link.is_provider_admin)

        bulk_response = owner_client.post(
            f'/api/v1/providers/{self.provider.id}/locations/reactivate-bulk/',
            {
                'location_ids': [self.location.id],
                'effective_date': self.today.isoformat(),
                'reason': 'Restore branch',
                'restore_staffing': True,
            },
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(bulk_response.status_code, 200, bulk_response.content)

        self.location.refresh_from_db()
        self.branch_manager_role.refresh_from_db()
        self.assertEqual(self.location.lifecycle_status, ProviderLocation.LIFECYCLE_STATUS_ACTIVE)
        self.assertTrue(self.location.is_active)
        self.assertTrue(self.branch_manager_role.is_active)
        self.assertIsNone(self.branch_manager_role.end_date)

    def test_branch_manager_without_schedule_does_not_break_staff_schedule_indicator(self):
        """Семафор staff schedule не должен требовать расписание от branch manager без смен."""
        worker_user = self._create_user('worker@example.com', '+38267001013')
        worker_employee = Employee.objects.create(user=worker_user)
        EmployeeProvider.objects.create(
            employee=worker_employee,
            provider=self.provider,
            role=EmployeeProvider.ROLE_WORKER,
            start_date=self.today,
        )
        EmployeeLocationRole.objects.create(
            employee=worker_employee,
            provider_location=self.location,
            role=EmployeeLocationRole.ROLE_WORKER,
            is_active=True,
        )
        Schedule.objects.create(
            employee=worker_employee,
            provider_location=self.location,
            day_of_week=1,
            start_time='09:00',
            end_time='17:00',
            is_working=True,
        )

        data = ProviderLocationListSerializer(self.location).data
        self.assertTrue(data['staff_schedule_filled'])
