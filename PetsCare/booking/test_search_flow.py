from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.models import Service
from geolocation.models import Address
from pets.models import Pet, PetOwner, PetType, SizeRule
from providers.models import Provider, ProviderLocation, ProviderLocationService


User = get_user_model()


class ProviderSearchFlowAPITestCase(APITestCase):
    def setUp(self):
        self.url = '/api/v1/booking/search/'
        self.user = User.objects.create_user(email='search@example.com', password='testpass123')
        self.client.force_authenticate(self.user)

        self.pet_type = PetType.objects.create(
            code='dog',
            name='Dog',
            name_de='Hund',
        )
        SizeRule.objects.create(
            pet_type=self.pet_type,
            size_code='S',
            min_weight_kg=Decimal('0.00'),
            max_weight_kg=Decimal('10.00'),
        )
        SizeRule.objects.create(
            pet_type=self.pet_type,
            size_code='M',
            min_weight_kg=Decimal('10.01'),
            max_weight_kg=Decimal('25.00'),
        )

        self.pet = Pet.objects.create(
            name='Rex',
            pet_type=self.pet_type,
            weight=Decimal('8.40'),
        )
        PetOwner.objects.create(pet=self.pet, user=self.user, role='main')

        self.grooming = Service.objects.create(
            code='grooming',
            name='Grooming',
            name_de='Pflege',
            level=0,
            hierarchy_order='1',
        )
        self.paw_care = Service.objects.create(
            code='paw_care',
            name='Paw Care',
            name_de='Pfotenpflege',
            parent=self.grooming,
            level=1,
            hierarchy_order='1_1',
        )
        self.vet = Service.objects.create(
            code='vet',
            name='Veterinary',
            name_de='Tierarzt',
            level=0,
            hierarchy_order='2',
        )
        self.checkup = Service.objects.create(
            code='checkup',
            name='Checkup',
            name_de='Untersuchung',
            parent=self.vet,
            level=1,
            hierarchy_order='2_1',
        )

        self.berlin_address = Address.objects.create(
            country='Germany',
            city='Berlin',
            street='Alexanderplatz',
            house_number='1',
            postal_code='10178',
            formatted_address='Alexanderplatz 1, 10178 Berlin, Germany',
            latitude=Decimal('52.5200000'),
            longitude=Decimal('13.4050000'),
            validation_status='valid',
        )
        self.second_berlin_address = Address.objects.create(
            country='Germany',
            city='Berlin',
            street='Sonnenallee',
            house_number='15',
            postal_code='12047',
            formatted_address='Sonnenallee 15, 12047 Berlin, Germany',
            latitude=Decimal('52.4800000'),
            longitude=Decimal('13.4300000'),
            validation_status='valid',
        )

        self.provider = Provider.objects.create(
            name='Berlin Groomers',
            phone_number='+49111111111',
            email='provider@example.com',
            activation_status='active',
            is_active=True,
            show_services=True,
        )
        self.provider.available_category_levels.add(self.grooming, self.vet)

        self.location = ProviderLocation.objects.create(
            provider=self.provider,
            name='Berlin Mitte',
            structured_address=self.berlin_address,
            phone_number='+49222222222',
            email='mitte@example.com',
            is_active=True,
        )
        self.location.served_pet_types.add(self.pet_type)

        ProviderLocationService.objects.create(
            location=self.location,
            service=self.paw_care,
            pet_type=self.pet_type,
            size_code='S',
            price=Decimal('40.00'),
            duration_minutes=45,
            is_active=True,
        )
        ProviderLocationService.objects.create(
            location=self.location,
            service=self.checkup,
            pet_type=self.pet_type,
            size_code='S',
            price=Decimal('65.00'),
            duration_minutes=30,
            is_active=True,
        )

        self.size_mismatch_location = ProviderLocation.objects.create(
            provider=self.provider,
            name='Berlin Neukolln',
            structured_address=self.second_berlin_address,
            phone_number='+49333333333',
            email='neukolln@example.com',
            is_active=True,
        )
        self.size_mismatch_location.served_pet_types.add(self.pet_type)

        ProviderLocationService.objects.create(
            location=self.size_mismatch_location,
            service=self.paw_care,
            pet_type=self.pet_type,
            size_code='M',
            price=Decimal('55.00'),
            duration_minutes=50,
            is_active=True,
        )

    def test_location_query_and_category_filter_return_only_matching_service(self):
        response = self.client.get(
            self.url,
            {
                'pet_id': self.pet.id,
                'location_query': 'Berlin',
                'category_id': self.grooming.id,
            },
            HTTP_ACCEPT_LANGUAGE='de',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.location.id)
        self.assertEqual(response.data[0]['address'], self.berlin_address.formatted_address)
        self.assertEqual(
            [service['id'] for service in response.data[0]['services']],
            [self.paw_care.id],
        )
        self.assertEqual(response.data[0]['services'][0]['name'], 'Pfotenpflege')

    def test_localized_service_query_matches_german_service_name(self):
        response = self.client.get(
            self.url,
            {
                'pet_id': self.pet.id,
                'service_query': 'Pfoten',
                'location_query': 'Berlin',
            },
            HTTP_ACCEPT_LANGUAGE='de',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.location.id)
        self.assertEqual(
            [service['name'] for service in response.data[0]['services']],
            ['Pfotenpflege'],
        )

    def test_cyrillic_location_query_matches_berlin_city(self):
        response = self.client.get(
            self.url,
            {
                'pet_id': self.pet.id,
                'location_query': 'Берлин',
                'service_query': 'Check',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.location.id)
        self.assertEqual(response.data[0]['services'][0]['id'], self.checkup.id)

    def test_structured_location_payload_filters_results_without_raw_query(self):
        response = self.client.get(
            self.url,
            {
                'pet_id': self.pet.id,
                'service_query': 'Check',
                'location_label': 'Berlin, Germany',
                'location_city': 'Berlin',
                'location_country': 'Germany',
                'location_source': 'suggestion',
                'location_place_id': 'test-place-id',
                'location_lat': '52.5200',
                'location_lon': '13.4050',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.location.id)
        self.assertEqual(response.data[0]['address'], self.berlin_address.formatted_address)

    def test_date_filter_falls_back_when_location_has_no_schedule(self):
        response = self.client.get(
            self.url,
            {
                'pet_id': self.pet.id,
                'location_query': 'Berlin',
                'service_query': 'Paw',
                'date': (date.today() + timedelta(days=3)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.location.id)

    def test_size_mismatch_location_is_excluded_from_results(self):
        response = self.client.get(
            self.url,
            {
                'pet_id': self.pet.id,
                'location_query': 'Berlin',
                'service_query': 'Paw',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.location.id)
