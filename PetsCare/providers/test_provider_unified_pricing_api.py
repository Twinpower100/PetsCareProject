"""Тесты org-level единой матрицы цен организации."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from catalog.models import Service
from geolocation.models import Address
from pets.models import PetType
from providers.models import (
    Employee,
    EmployeeProvider,
    Provider,
    ProviderLocation,
    ProviderLocationService,
    ProviderServicePricing,
)

User = get_user_model()


class ProviderUnifiedPricingAPITests(TestCase):
    """Проверяет unified pricing mode и фильтрацию по pet types филиала."""

    def setUp(self):
        """Создаёт организацию, две локации и минимальный каталог услуг."""
        self.provider = Provider.objects.create(
            name='Unified Pricing Org',
            phone_number='+38267002000',
            email='pricing-org@example.com',
            activation_status='active',
            partnership_status=Provider.PARTNERSHIP_STATUS_ACTIVE,
            is_active=True,
        )
        self.owner_user = User.objects.create_user(
            email='pricing-owner@example.com',
            password='password123',
            username='pricing-owner@example.com',
            phone_number='+38267002001',
        )
        self.owner_user.add_role('provider_admin')
        self.owner_employee = Employee.objects.create(user=self.owner_user)
        EmployeeProvider.objects.create(
            employee=self.owner_employee,
            provider=self.provider,
            role=EmployeeProvider.ROLE_OWNER,
            start_date='2026-03-31',
            is_owner=True,
        )

        self.dog = PetType.objects.create(name='Dog', code='dog')
        self.cat = PetType.objects.create(name='Cat', code='cat')
        self.root_service = Service.objects.create(name='Grooming', code='grooming', level=0, is_client_facing=True)
        self.provider.available_category_levels.add(self.root_service)

        self.address_1 = Address.objects.create(
            country='Montenegro',
            city='Podgorica',
            street='Main street',
            house_number='1',
            formatted_address='Main street 1',
            latitude=42.44,
            longitude=19.26,
            validation_status='valid',
        )
        self.address_2 = Address.objects.create(
            country='Montenegro',
            city='Podgorica',
            street='Second street',
            house_number='2',
            formatted_address='Second street 2',
            latitude=42.45,
            longitude=19.27,
            validation_status='valid',
        )
        self.location_all = ProviderLocation.objects.create(
            provider=self.provider,
            name='All Pets Branch',
            structured_address=self.address_1,
            phone_number='+38267002002',
            email='all@example.com',
            is_active=True,
        )
        self.location_dogs = ProviderLocation.objects.create(
            provider=self.provider,
            name='Dogs Only Branch',
            structured_address=self.address_2,
            phone_number='+38267002003',
            email='dogs@example.com',
            is_active=True,
        )
        self.provider.served_pet_types.set([self.dog, self.cat])
        self.location_all.served_pet_types.set([self.dog, self.cat])
        self.location_dogs.served_pet_types.set([self.dog])

        self.location_all_dog = ProviderLocationService.objects.create(
            location=self.location_all,
            service=self.root_service,
            pet_type=self.dog,
            size_code='S',
            price='20.00',
            duration_minutes=30,
        )
        self.location_all_cat = ProviderLocationService.objects.create(
            location=self.location_all,
            service=self.root_service,
            pet_type=self.cat,
            size_code='S',
            price='21.00',
            duration_minutes=35,
        )
        self.location_dogs_dog = ProviderLocationService.objects.create(
            location=self.location_dogs,
            service=self.root_service,
            pet_type=self.dog,
            size_code='S',
            price='19.00',
            duration_minutes=25,
        )

    def _client(self):
        """Возвращает аутентифицированный API client владельца."""
        client = APIClient()
        client.force_authenticate(self.owner_user)
        return client

    def test_enabling_unified_pricing_bootstraps_org_prices_from_existing_branch_rows(self):
        """При включении unified mode организация подхватывает текущие branch prices как стартовую матрицу."""
        client = self._client()

        response = client.patch(
            f'/api/v1/providers/{self.provider.id}/pricing-settings/',
            {'use_unified_service_pricing': True},
            format='json',
            HTTP_API_VERSION='v1',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.provider.refresh_from_db()
        self.assertTrue(self.provider.use_unified_service_pricing)
        org_rows = [
            (row.pet_type.code, str(row.price), row.duration_minutes)
            for row in ProviderServicePricing.objects.filter(provider=self.provider)
            .select_related('pet_type')
            .order_by('pet_type__code')
        ]
        self.assertEqual(
            org_rows,
            [('cat', '21.00', 35), ('dog', '20.00', 30)],
        )
        self.location_all_dog.refresh_from_db()
        self.location_all_cat.refresh_from_db()
        self.location_dogs_dog.refresh_from_db()
        self.assertEqual(str(self.location_all_dog.price), '20.00')
        self.assertEqual(str(self.location_all_cat.price), '21.00')
        self.assertEqual(str(self.location_dogs_dog.price), '20.00')

    def test_price_matrix_endpoint_returns_configured_items(self):
        """GET price-matrix возвращает сохранённую org-level матрицу по услугам."""
        client = self._client()

        save_prices_response = client.post(
            f'/api/v1/providers/{self.provider.id}/catalog-service/{self.root_service.id}/prices/',
            {
                'prices': [
                    {
                        'pet_type_id': self.dog.id,
                        'base_price': '40.00',
                        'base_duration_minutes': 50,
                        'variants': [{'size_code': 'S', 'price': '40.00', 'duration_minutes': 50}],
                    },
                    {
                        'pet_type_id': self.cat.id,
                        'base_price': '44.00',
                        'base_duration_minutes': 55,
                        'variants': [{'size_code': 'S', 'price': '44.00', 'duration_minutes': 55}],
                    },
                ]
            },
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(save_prices_response.status_code, 200, save_prices_response.content)

        matrix_response = client.get(
            f'/api/v1/providers/{self.provider.id}/price-matrix/',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(matrix_response.status_code, 200, matrix_response.content)
        self.assertEqual(len(matrix_response.data['items']), 1)
        self.assertEqual(matrix_response.data['items'][0]['service_id'], self.root_service.id)
        self.assertEqual(
            sorted(item['pet_type_code'] for item in matrix_response.data['items'][0]['prices']),
            ['cat', 'dog'],
        )
        self.assertEqual(
            sorted(item['code'] for item in matrix_response.data['served_pet_types']),
            ['cat', 'dog'],
        )

    def test_price_matrix_endpoint_uses_organization_pet_type_scope(self):
        """GET price-matrix должен возвращать org-level scope, а не union по филиалам."""
        self.provider.served_pet_types.set([self.dog])

        client = self._client()
        matrix_response = client.get(
            f'/api/v1/providers/{self.provider.id}/price-matrix/',
            HTTP_API_VERSION='v1',
        )

        self.assertEqual(matrix_response.status_code, 200, matrix_response.content)
        self.assertEqual(
            [item['code'] for item in matrix_response.data['served_pet_types']],
            ['dog'],
        )

    def test_provider_served_pet_types_can_be_updated_via_price_matrix_endpoint(self):
        """PATCH price-matrix обновляет org-level served pet types."""
        client = self._client()

        response = client.patch(
            f'/api/v1/providers/{self.provider.id}/price-matrix/',
            {'served_pet_types': [self.dog.id]},
            format='json',
            HTTP_API_VERSION='v1',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.provider.refresh_from_db()
        self.assertEqual(
            list(self.provider.served_pet_types.order_by('code').values_list('code', flat=True)),
            ['dog'],
        )

    def test_org_level_prices_sync_to_branches_and_filter_by_branch_pet_types(self):
        """Org-level цены синхронизируются в филиалы и не создают цены для неподдерживаемых pet types."""
        client = self._client()

        save_prices_response = client.post(
            f'/api/v1/providers/{self.provider.id}/catalog-service/{self.root_service.id}/prices/',
            {
                'prices': [
                    {
                        'pet_type_id': self.dog.id,
                        'base_price': '40.00',
                        'base_duration_minutes': 50,
                        'variants': [{'size_code': 'S', 'price': '40.00', 'duration_minutes': 50}],
                    },
                    {
                        'pet_type_id': self.cat.id,
                        'base_price': '44.00',
                        'base_duration_minutes': 55,
                        'variants': [{'size_code': 'S', 'price': '44.00', 'duration_minutes': 55}],
                    },
                ]
            },
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(save_prices_response.status_code, 200, save_prices_response.content)

        enable_response = client.patch(
            f'/api/v1/providers/{self.provider.id}/pricing-settings/',
            {'use_unified_service_pricing': True},
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(enable_response.status_code, 200, enable_response.content)

        self.provider.refresh_from_db()
        self.assertTrue(self.provider.use_unified_service_pricing)

        all_branch_rows = ProviderLocationService.objects.filter(location=self.location_all, service=self.root_service).order_by('pet_type__code')
        dogs_branch_rows = ProviderLocationService.objects.filter(location=self.location_dogs, service=self.root_service).order_by('pet_type__code')

        self.assertEqual(all_branch_rows.count(), 2)
        self.assertEqual(dogs_branch_rows.count(), 1)
        self.assertEqual(str(all_branch_rows.get(pet_type=self.dog).price), '40.00')
        self.assertEqual(str(all_branch_rows.get(pet_type=self.cat).price), '44.00')
        self.assertEqual(str(dogs_branch_rows.get(pet_type=self.dog).price), '40.00')
        self.assertFalse(dogs_branch_rows.filter(pet_type=self.cat).exists())

        update_prices_response = client.put(
            f'/api/v1/providers/{self.provider.id}/services/{self.root_service.id}/prices/',
            {
                'prices': [
                    {
                        'pet_type_id': self.dog.id,
                        'base_price': '48.00',
                        'base_duration_minutes': 65,
                        'variants': [{'size_code': 'S', 'price': '48.00', 'duration_minutes': 65}],
                    },
                    {
                        'pet_type_id': self.cat.id,
                        'base_price': '52.00',
                        'base_duration_minutes': 70,
                        'variants': [{'size_code': 'S', 'price': '52.00', 'duration_minutes': 70}],
                    },
                ]
            },
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(update_prices_response.status_code, 200, update_prices_response.content)

        self.location_all_dog.refresh_from_db()
        self.location_all_cat.refresh_from_db()
        self.location_dogs_dog.refresh_from_db()

        self.assertEqual(str(self.location_all_dog.price), '48.00')
        self.assertEqual(self.location_all_dog.duration_minutes, 65)
        self.assertEqual(str(self.location_all_cat.price), '52.00')
        self.assertEqual(self.location_all_cat.duration_minutes, 70)
        self.assertEqual(str(self.location_dogs_dog.price), '48.00')
        self.assertEqual(self.location_dogs_dog.duration_minutes, 65)
        self.assertEqual(
            ProviderServicePricing.objects.filter(provider=self.provider, service=self.root_service).count(),
            2,
        )

    def test_disabling_unified_pricing_keeps_latest_organization_prices_in_branch_rows(self):
        """При выключении unified mode филиалы получают последнюю синхронизированную орг-матрицу как базу."""
        client = self._client()

        save_prices_response = client.post(
            f'/api/v1/providers/{self.provider.id}/catalog-service/{self.root_service.id}/prices/',
            {
                'prices': [
                    {
                        'pet_type_id': self.dog.id,
                        'base_price': '40.00',
                        'base_duration_minutes': 50,
                        'variants': [{'size_code': 'S', 'price': '40.00', 'duration_minutes': 50}],
                    },
                    {
                        'pet_type_id': self.cat.id,
                        'base_price': '44.00',
                        'base_duration_minutes': 55,
                        'variants': [{'size_code': 'S', 'price': '44.00', 'duration_minutes': 55}],
                    },
                ]
            },
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(save_prices_response.status_code, 200, save_prices_response.content)

        enable_response = client.patch(
            f'/api/v1/providers/{self.provider.id}/pricing-settings/',
            {'use_unified_service_pricing': True},
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(enable_response.status_code, 200, enable_response.content)

        update_prices_response = client.put(
            f'/api/v1/providers/{self.provider.id}/services/{self.root_service.id}/prices/',
            {
                'prices': [
                    {
                        'pet_type_id': self.dog.id,
                        'base_price': '48.00',
                        'base_duration_minutes': 65,
                        'variants': [{'size_code': 'S', 'price': '48.00', 'duration_minutes': 65}],
                    },
                    {
                        'pet_type_id': self.cat.id,
                        'base_price': '52.00',
                        'base_duration_minutes': 70,
                        'variants': [{'size_code': 'S', 'price': '52.00', 'duration_minutes': 70}],
                    },
                ]
            },
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(update_prices_response.status_code, 200, update_prices_response.content)

        disable_response = client.patch(
            f'/api/v1/providers/{self.provider.id}/pricing-settings/',
            {'use_unified_service_pricing': False},
            format='json',
            HTTP_API_VERSION='v1',
        )
        self.assertEqual(disable_response.status_code, 200, disable_response.content)

        self.provider.refresh_from_db()
        self.location_all_dog.refresh_from_db()
        self.location_all_cat.refresh_from_db()
        self.location_dogs_dog.refresh_from_db()

        self.assertFalse(self.provider.use_unified_service_pricing)
        self.assertEqual(str(self.location_all_dog.price), '48.00')
        self.assertEqual(self.location_all_dog.duration_minutes, 65)
        self.assertEqual(str(self.location_all_cat.price), '52.00')
        self.assertEqual(self.location_all_cat.duration_minutes, 70)
        self.assertEqual(str(self.location_dogs_dog.price), '48.00')
        self.assertEqual(self.location_dogs_dog.duration_minutes, 65)

    def test_org_level_price_rows_can_be_deleted_while_unified_pricing_is_enabled(self):
        """Удаление строк org-level матрицы должно удалять и синхронизированные branch rows."""
        ProviderServicePricing.objects.create(
            provider=self.provider,
            service=self.root_service,
            pet_type=self.dog,
            size_code='S',
            price='40.00',
            duration_minutes=50,
        )
        ProviderServicePricing.objects.create(
            provider=self.provider,
            service=self.root_service,
            pet_type=self.cat,
            size_code='S',
            price='44.00',
            duration_minutes=55,
        )
        self.provider.use_unified_service_pricing = True
        self.provider.save(update_fields=['use_unified_service_pricing', 'updated_at'])

        client = self._client()
        response = client.put(
            f'/api/v1/providers/{self.provider.id}/services/{self.root_service.id}/prices/',
            {
                'prices': [
                    {
                        'pet_type_id': self.dog.id,
                        'base_price': '48.00',
                        'base_duration_minutes': 65,
                        'variants': [{'size_code': 'S', 'price': '48.00', 'duration_minutes': 65}],
                    },
                ]
            },
            format='json',
            HTTP_API_VERSION='v1',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            list(
                ProviderServicePricing.objects.filter(provider=self.provider, service=self.root_service)
                .order_by('pet_type__code')
                .values_list('pet_type__code', flat=True)
            ),
            ['dog'],
        )
        self.assertEqual(
            list(
                ProviderLocationService.objects.filter(location=self.location_all, service=self.root_service)
                .order_by('pet_type__code')
                .values_list('pet_type__code', flat=True)
            ),
            ['dog'],
        )
        self.assertEqual(
            list(
                ProviderLocationService.objects.filter(location=self.location_dogs, service=self.root_service)
                .order_by('pet_type__code')
                .values_list('pet_type__code', flat=True)
            ),
            ['dog'],
        )

    def test_branch_price_mutation_is_blocked_while_unified_pricing_is_enabled(self):
        """После включения unified mode филиал не может менять свою price matrix напрямую."""
        ProviderServicePricing.objects.create(
            provider=self.provider,
            service=self.root_service,
            pet_type=self.dog,
            size_code='S',
            price='40.00',
            duration_minutes=50,
        )
        ProviderServicePricing.objects.create(
            provider=self.provider,
            service=self.root_service,
            pet_type=self.cat,
            size_code='S',
            price='44.00',
            duration_minutes=55,
        )
        self.provider.use_unified_service_pricing = True
        self.provider.save(update_fields=['use_unified_service_pricing', 'updated_at'])

        client = self._client()
        response = client.patch(
            f'/api/v1/provider-location-services/{self.location_all_dog.id}/',
            {'price': '99.00', 'duration_minutes': 99},
            format='json',
            HTTP_API_VERSION='v1',
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.location_all_dog.refresh_from_db()
        self.assertEqual(str(self.location_all_dog.price), '20.00')

    def test_branch_pet_type_scope_must_be_subset_of_organization_scope_in_unified_mode(self):
        """В unified mode филиал не может выбрать pet type вне org-level scope."""
        self.provider.served_pet_types.set([self.dog])
        self.provider.use_unified_service_pricing = True
        self.provider.save(update_fields=['use_unified_service_pricing', 'updated_at'])

        client = self._client()
        response = client.patch(
            f'/api/v1/provider-locations/{self.location_dogs.id}/',
            {'served_pet_types': [self.cat.id]},
            format='json',
            HTTP_API_VERSION='v1',
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.location_dogs.refresh_from_db()
        self.assertEqual(
            list(self.location_dogs.served_pet_types.order_by('code').values_list('code', flat=True)),
            ['dog'],
        )
