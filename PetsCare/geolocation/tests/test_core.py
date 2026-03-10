"""
Актуальные smoke и regression-тесты для geolocation.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from geolocation.forms import AddressForm
from geolocation.models import Address, AddressCache, AddressValidation, UserLocation
from geolocation.serializers import AddressSerializer
from geolocation.services import AddressValidationService, DeviceLocationService, GoogleMapsService
from geolocation.utils import (
    batch_distance_calculation,
    filter_by_distance,
    format_distance,
    validate_coordinates,
)

User = get_user_model()


def _make_geocode_result():
    return {
        'formatted_address': '123 Test Street, Test City, Test Country',
        'location_type': 'ROOFTOP',
        'coordinates': {
            'latitude': Decimal('55.7558000'),
            'longitude': Decimal('37.6176000'),
        },
        'address_components': {
            'city': 'Test City',
            'country': 'Test Country',
            'street': 'Test Street',
            'house_number': '123',
        },
        'place_id': 'test_place_id',
        'types': ['street_address'],
    }


class AddressModelTestCase(TestCase):
    def test_save_builds_point_from_lat_lon(self):
        address = Address.objects.create(
            street='Test Street',
            house_number='123',
            city='Test City',
            country='Test Country',
            latitude=Decimal('55.7558000'),
            longitude=Decimal('37.6176000'),
        )

        self.assertIsNotNone(address.point)
        self.assertEqual(address.point.coords, (37.6176, 55.7558))
        self.assertTrue(address.is_geocoded)

    def test_save_preserves_explicit_point(self):
        address = Address.objects.create(
            street='Test Street',
            city='Test City',
            country='Test Country',
            point=Point(37.6173, 55.7558, srid=4326),
        )

        self.assertIsNotNone(address.point)
        self.assertEqual(address.latitude, Decimal('55.7558'))
        self.assertEqual(address.longitude, Decimal('37.6173'))
        self.assertTrue(address.is_geocoded)


class AddressFormTestCase(TestCase):
    @patch('geolocation.forms.AddressValidationService')
    def test_full_address_uses_geocoding_without_unsaved_model_error(self, service_cls):
        service = service_cls.return_value
        service.google_service.geocode_address.return_value = _make_geocode_result()

        form = AddressForm(data={
            'full_address': '123 Test Street, Test City, Test Country',
            'auto_validate': True,
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['validation_status'], 'valid')
        self.assertEqual(form.cleaned_data['formatted_address'], '123 Test Street, Test City, Test Country')


class AddressSerializerTestCase(TestCase):
    @patch('geolocation.serializers.AddressValidationService')
    def test_create_validates_and_keeps_valid_address(self, service_cls):
        service = service_cls.return_value
        service.validate_address.side_effect = lambda address: (
            setattr(address, 'validation_status', 'valid'),
            setattr(address, 'formatted_address', '123 Test Street, Test City, Test Country'),
            setattr(address, 'latitude', Decimal('55.7558000')),
            setattr(address, 'longitude', Decimal('37.6176000')),
            address.save(),
            True,
        )[-1]

        serializer = AddressSerializer(data={
            'house_number': '123',
            'street': 'Test Street',
            'city': 'Test City',
            'country': 'Test Country',
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        address = serializer.save()
        self.assertEqual(address.validation_status, 'valid')
        self.assertEqual(address.formatted_address, '123 Test Street, Test City, Test Country')


class AddressAPIViewTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='geo_api_user',
            email='geo-api@example.com',
            phone_number='+10000000001',
            password='testpass123',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.address = Address.objects.create(
            house_number='123',
            street='Test Street',
            city='Test City',
            country='Test Country',
        )

    @patch('geolocation.serializers.AddressValidationService')
    def test_address_crud(self, service_cls):
        service = service_cls.return_value

        def mark_valid(address):
            address.validation_status = 'valid'
            address.formatted_address = address.get_full_address()
            address.latitude = Decimal('55.7558000')
            address.longitude = Decimal('37.6176000')
            address.save()
            return True

        service.validate_address.side_effect = mark_valid

        list_response = self.client.get(reverse('geolocation:address-list'))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)

        create_response = self.client.post(reverse('geolocation:address-list'), {
            'house_number': '456',
            'street': 'New Street',
            'city': 'New City',
            'country': 'New Country',
        }, format='json')
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        detail_url = reverse('geolocation:address-detail', args=[self.address.id])
        retrieve_response = self.client.get(detail_url)
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)

        update_response = self.client.put(detail_url, {
            'house_number': '789',
            'street': 'Updated Street',
            'city': 'Updated City',
            'country': 'Updated Country',
        }, format='json')
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.address.refresh_from_db()
        self.assertEqual(self.address.house_number, '789')

        delete_response = self.client.delete(detail_url)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)


@override_settings(GOOGLE_MAPS_API_KEY='test-key')
class AddressValidationServiceTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.address = Address.objects.create(
            house_number='123',
            street='Test Street',
            city='Test City',
            country='Test Country',
        )

    @patch('geolocation.services.GoogleMapsService.geocode_address')
    def test_validate_address_success(self, geocode_mock):
        geocode_mock.return_value = _make_geocode_result()
        service = AddressValidationService()

        result = service.validate_address(self.address)

        self.assertTrue(result)
        self.address.refresh_from_db()
        self.assertEqual(self.address.validation_status, 'valid')
        self.assertEqual(self.address.formatted_address, '123 Test Street, Test City, Test Country')
        self.assertEqual(AddressValidation.objects.filter(address=self.address, is_valid=True).count(), 1)
        self.assertEqual(AddressCache.objects.count(), 1)

    @patch('geolocation.services.GoogleMapsService.geocode_address')
    def test_validate_address_failure(self, geocode_mock):
        geocode_mock.return_value = None
        service = AddressValidationService()

        result = service.validate_address(self.address)

        self.assertFalse(result)
        self.address.refresh_from_db()
        self.assertEqual(self.address.validation_status, 'invalid')


@override_settings(GOOGLE_MAPS_API_KEY='test-key')
class GoogleMapsServiceTestCase(TestCase):
    @patch('geolocation.services.requests.get')
    def test_geocode_address_success(self, get_mock):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.url = 'https://maps.googleapis.com/fake'
        response.json.return_value = {
            'status': 'OK',
            'results': [{
                'formatted_address': '123 Test Street, Test City, Test Country',
                'geometry': {
                    'location': {'lat': 55.7558, 'lng': 37.6176},
                    'location_type': 'ROOFTOP',
                },
                'address_components': [],
                'place_id': 'test_place_id',
                'types': ['street_address'],
            }],
        }
        get_mock.return_value = response

        result = GoogleMapsService().geocode_address('Test Address')

        self.assertEqual(result['formatted_address'], '123 Test Street, Test City, Test Country')
        self.assertEqual(result['coordinates']['latitude'], Decimal('55.7558'))

    @patch('geolocation.services.requests.get')
    def test_autocomplete_returns_predictions(self, get_mock):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            'status': 'OK',
            'predictions': [
                {'description': 'Test Address 1', 'place_id': 'place_1', 'types': ['address']},
                {'description': 'Test Address 2', 'place_id': 'place_2', 'types': ['address']},
            ],
        }
        get_mock.return_value = response

        result = GoogleMapsService().autocomplete_address('Test')

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['description'], 'Test Address 1')


class GeolocationUtilsTestCase(TestCase):
    def setUp(self):
        self.moscow = Address.objects.create(
            street='Moscow',
            city='Moscow',
            country='Russia',
            point=Point(37.6173, 55.7558, srid=4326),
        )
        self.spb = Address.objects.create(
            street='SPB',
            city='Saint Petersburg',
            country='Russia',
            point=Point(30.3141, 59.9386, srid=4326),
        )

    def test_filter_by_distance_returns_sorted_results(self):
        results = filter_by_distance(Address.objects.all(), 55.7558, 37.6173, 1000, 'point')

        self.assertGreaterEqual(len(results), 2)
        self.assertEqual(results[0][0].id, self.moscow.id)
        self.assertLessEqual(results[0][1], results[1][1])

    def test_batch_distance_calculation_returns_non_negative_distances(self):
        results = batch_distance_calculation(Address.objects.all(), 55.7558, 37.6173, batch_size=1)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(distance >= 0 for _, distance in results))

    def test_coordinate_helpers(self):
        self.assertTrue(validate_coordinates(55.7558, 37.6173))
        self.assertFalse(validate_coordinates(120, 37.6173))
        self.assertEqual(format_distance(0.5), '500 m')
        self.assertEqual(format_distance(1.5), '1.5 km')


class DeviceLocationServiceTestCase(TestCase):
    def test_save_device_location_persists_point(self):
        user = User.objects.create_user(
            username='geo_device_user',
            email='geo-device@example.com',
            phone_number='+10000000002',
            password='testpass123',
        )

        service = DeviceLocationService()
        service.save_device_location(user, 55.7558, 37.6173, accuracy=15, source='device')

        location = UserLocation.objects.get(user=user)
        self.assertEqual(location.point.coords, (37.6173, 55.7558))
        self.assertEqual(location.source, 'device')
