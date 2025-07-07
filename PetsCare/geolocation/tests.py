"""
Тесты для модуля геолокации.

Содержит тесты для:
1. Моделей адресов
2. Сервисов валидации
3. API endpoints
4. Форм и сериализаторов
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch, MagicMock
from decimal import Decimal

from .models import Address, AddressValidation, AddressCache
from .services import AddressValidationService, GoogleMapsService
from .forms import AddressForm
from .serializers import AddressSerializer

User = get_user_model()


class AddressModelTest(TestCase):
    """
    Tests for the Address model.
    """
    
    def setUp(self):
        """Setting up test data."""
        self.address_data = {
            'street_number': '123',
            'route': 'Test Street',
            'locality': 'Test City',
            'administrative_area_level_1': 'Test Region',
            'country': 'Test Country',
            'postal_code': '12345'
        }
    
    def test_create_address(self):
        """Test creating an address."""
        address = Address.objects.create(**self.address_data)
        
        self.assertEqual(address.street_number, '123')
        self.assertEqual(address.route, 'Test Street')
        self.assertEqual(address.locality, 'Test City')
        self.assertEqual(address.country, 'Test Country')
        self.assertFalse(address.is_validated)
        self.assertEqual(address.validation_status, 'pending')
    
    def test_address_str_representation(self):
        """Test string representation of an address."""
        address = Address.objects.create(**self.address_data)
        
        expected_str = f"{self.address_data['street_number']} {self.address_data['route']}, {self.address_data['locality']}"
        self.assertEqual(str(address), expected_str)
    
    def test_address_with_coordinates(self):
        """Test address with coordinates."""
        address = Address.objects.create(
            **self.address_data,
            latitude=Decimal('55.7558'),
            longitude=Decimal('37.6176'),
            is_validated=True,
            validation_status='valid'
        )
        
        self.assertEqual(address.latitude, Decimal('55.7558'))
        self.assertEqual(address.longitude, Decimal('37.6176'))
        self.assertTrue(address.is_validated)
        self.assertEqual(address.validation_status, 'valid')


class AddressValidationModelTest(TestCase):
    """
    Tests for the AddressValidation model.
    """
    
    def setUp(self):
        """Setting up test data."""
        self.address = Address.objects.create(
            street_number='123',
            route='Test Street',
            locality='Test City',
            country='Test Country'
        )
    
    def test_create_validation(self):
        """Test creating a validation record."""
        validation = AddressValidation.objects.create(
            address=self.address,
            is_valid=True,
            formatted_address='123 Test Street, Test City, Test Country',
            latitude=Decimal('55.7558'),
            longitude=Decimal('37.6176'),
            confidence_score=0.9
        )
        
        self.assertEqual(validation.address, self.address)
        self.assertTrue(validation.is_valid)
        self.assertEqual(validation.confidence_score, 0.9)
    
    def test_validation_str_representation(self):
        """Test string representation of a validation."""
        validation = AddressValidation.objects.create(
            address=self.address,
            is_valid=True
        )
        
        expected_str = f"Validation for {self.address} - Valid"
        self.assertEqual(str(validation), expected_str)


class AddressCacheModelTest(TestCase):
    """
    Tests for the AddressCache model.
    """
    
    def test_create_cache_entry(self):
        """Test creating a cache entry."""
        cache_entry = AddressCache.objects.create(
            query_hash='test_hash_123',
            query_text='Test Address',
            formatted_address='123 Test Street, Test City',
            latitude=Decimal('55.7558'),
            longitude=Decimal('37.6176')
        )
        
        self.assertEqual(cache_entry.query_hash, 'test_hash_123')
        self.assertEqual(cache_entry.query_text, 'Test Address')
        self.assertEqual(cache_entry.latitude, Decimal('55.7558'))
    
    def test_cache_str_representation(self):
        """Test string representation of a cache."""
        cache_entry = AddressCache.objects.create(
            query_hash='test_hash_123',
            query_text='Test Address'
        )
        
        expected_str = f"Cache: test_hash_123 - Test Address"
        self.assertEqual(str(cache_entry), expected_str)


class AddressFormTest(TestCase):
    """
    Tests for the AddressForm.
    """
    
    def setUp(self):
        """Setting up test data."""
        self.form_data = {
            'street_number': '123',
            'route': 'Test Street',
            'locality': 'Test City',
            'country': 'Test Country',
            'auto_validate': True
        }
    
    def test_valid_form(self):
        """Test a valid form."""
        form = AddressForm(data=self.form_data)
        self.assertTrue(form.is_valid())
    
    def test_invalid_form_missing_fields(self):
        """Test an invalid form with missing fields."""
        form = AddressForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('You must specify at least one component of the address', str(form.errors))
    
    def test_form_with_full_address(self):
        """Test form with a full address."""
        form_data = {
            'full_address': '123 Test Street, Test City, Test Country',
            'auto_validate': True
        }
        form = AddressForm(data=form_data)
        self.assertTrue(form.is_valid())


class AddressSerializerTest(APITestCase):
    """
    Tests for the AddressSerializer.
    """
    
    def setUp(self):
        """Setting up test data."""
        self.address_data = {
            'street_number': '123',
            'route': 'Test Street',
            'locality': 'Test City',
            'country': 'Test Country'
        }
        self.address = Address.objects.create(**self.address_data)
    
    def test_serializer_fields(self):
        """Test serializer fields."""
        serializer = AddressSerializer(self.address)
        data = serializer.data
        
        self.assertIn('id', data)
        self.assertIn('street_number', data)
        self.assertIn('route', data)
        self.assertIn('locality', data)
        self.assertIn('country', data)
        self.assertIn('is_validated', data)
        self.assertIn('validation_status', data)
    
    def test_serializer_validation(self):
        """Test serializer validation."""
        serializer = AddressSerializer(data=self.address_data)
        self.assertTrue(serializer.is_valid())
    
    def test_serializer_invalid_data(self):
        """Test invalid data in the serializer."""
        serializer = AddressSerializer(data={})
        self.assertFalse(serializer.is_valid())


class AddressAPIViewTest(APITestCase):
    """
    Tests for Address API views.
    """
    
    def setUp(self):
        """Setting up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        self.address = Address.objects.create(
            street_number='123',
            route='Test Street',
            locality='Test City',
            country='Test Country'
        )
    
    def test_list_addresses(self):
        """Test getting a list of addresses."""
        url = reverse('geolocation:address-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
    
    def test_create_address(self):
        """Test creating an address through API."""
        url = reverse('geolocation:address-list')
        data = {
            'street_number': '456',
            'route': 'New Street',
            'locality': 'New City',
            'country': 'New Country'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_retrieve_address(self):
        """Test getting a specific address."""
        url = reverse('geolocation:address-detail', args=[self.address.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['street_number'], '123')
    
    def test_update_address(self):
        """Test updating an address."""
        url = reverse('geolocation:address-detail', args=[self.address.id])
        data = {
            'street_number': '789',
            'route': 'Updated Street',
            'locality': 'Updated City',
            'country': 'Updated Country'
        }
        
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['street_number'], '789')
    
    def test_delete_address(self):
        """Test deleting an address."""
        url = reverse('geolocation:address-detail', args=[self.address.id])
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Address.objects.filter(id=self.address.id).exists())


class AddressValidationServiceTest(TestCase):
    """
    Tests for the address validation service.
    """
    
    def setUp(self):
        """Setting up test data."""
        self.address = Address.objects.create(
            street_number='123',
            route='Test Street',
            locality='Test City',
            country='Test Country'
        )
        self.service = AddressValidationService()
    
    @patch('geolocation.services.GoogleMapsService')
    def test_validate_address_success(self, mock_google_maps):
        """Test successful address validation."""
        # Mock Google Maps API response
        mock_response = {
            'formatted_address': '123 Test Street, Test City, Test Country',
            'geometry': {
                'location': {
                    'lat': 55.7558,
                    'lng': 37.6176
                }
            },
            'place_id': 'test_place_id'
        }
        
        mock_service = MagicMock()
        mock_service.geocode_address.return_value = mock_response
        mock_google_maps.return_value = mock_service
        
        result = self.service.validate_address(self.address)
        
        self.assertTrue(result.is_valid)
        self.assertEqual(result.formatted_address, '123 Test Street, Test City, Test Country')
        self.assertEqual(result.latitude, Decimal('55.7558'))
        self.assertEqual(result.longitude, Decimal('37.6176'))
    
    @patch('geolocation.services.GoogleMapsService')
    def test_validate_address_failure(self, mock_google_maps):
        """Test unsuccessful address validation."""
        # Mock Google Maps API response
        mock_service = MagicMock()
        mock_service.geocode_address.return_value = None
        mock_google_maps.return_value = mock_service
        
        result = self.service.validate_address(self.address)
        
        self.assertFalse(result.is_valid)
        self.assertIsNone(result.formatted_address)
        self.assertIsNone(result.latitude)
        self.assertIsNone(result.longitude)


class GoogleMapsServiceTest(TestCase):
    """
    Tests for the Google Maps service.
    """
    
    def setUp(self):
        """Setting up test data."""
        self.service = GoogleMapsService()
    
    @patch('geolocation.services.googlemaps.Client')
    def test_geocode_address_success(self, mock_client):
        """Test successful geocoding of an address."""
        # Mock Google Maps API response
        mock_response = [{
            'formatted_address': '123 Test Street, Test City, Test Country',
            'geometry': {
                'location': {
                    'lat': 55.7558,
                    'lng': 37.6176
                }
            },
            'place_id': 'test_place_id'
        }]
        
        mock_gmaps = MagicMock()
        mock_gmaps.geocode.return_value = mock_response
        mock_client.return_value = mock_gmaps
        
        result = self.service.geocode_address('Test Address')
        
        self.assertIsNotNone(result)
        self.assertEqual(result['formatted_address'], '123 Test Street, Test City, Test Country')
        self.assertEqual(result['geometry']['location']['lat'], 55.7558)
    
    @patch('geolocation.services.googlemaps.Client')
    def test_geocode_address_failure(self, mock_client):
        """Test unsuccessful geocoding of an address."""
        # Mock Google Maps API response
        mock_gmaps = MagicMock()
        mock_gmaps.geocode.return_value = []
        mock_client.return_value = mock_gmaps
        
        result = self.service.geocode_address('Invalid Address')
        
        self.assertIsNone(result)
    
    @patch('geolocation.services.googlemaps.Client')
    def test_get_place_autocomplete(self, mock_client):
        """Test place autocomplete."""
        # Mock Google Maps API response
        mock_response = {
            'predictions': [
                {
                    'description': 'Test Address 1',
                    'place_id': 'place_id_1'
                },
                {
                    'description': 'Test Address 2',
                    'place_id': 'place_id_2'
                }
            ]
        }
        
        mock_gmaps = MagicMock()
        mock_gmaps.places_autocomplete.return_value = mock_response
        mock_client.return_value = mock_gmaps
        
        result = self.service.get_place_autocomplete('Test')
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['description'], 'Test Address 1')


class AddressSignalsTest(TestCase):
    """
    Tests for address signals.
    """
    
    def setUp(self):
        """Setting up test data."""
        self.address_data = {
            'street_number': '123',
            'route': 'Test Street',
            'locality': 'Test City',
            'country': 'Test Country'
        }
    
    @patch('geolocation.signals.AddressValidationService')
    def test_auto_validate_address_signal(self, mock_service):
        """Test automatic address validation through signal."""
        # Mock validation service
        mock_validation_result = MagicMock()
        mock_validation_result.is_valid = True
        mock_validation_result.formatted_address = '123 Test Street, Test City, Test Country'
        mock_validation_result.latitude = Decimal('55.7558')
        mock_validation_result.longitude = Decimal('37.6176')
        
        mock_service_instance = MagicMock()
        mock_service_instance.validate_address.return_value = mock_validation_result
        mock_service.return_value = mock_service_instance
        
        # Create address (signal should be triggered)
        address = Address.objects.create(**self.address_data)
        
        # Check if validation service was called
        mock_service_instance.validate_address.assert_called_once_with(address)
        
        # Refresh address from database
        address.refresh_from_db()
        
        # Check if address was validated
        self.assertTrue(address.is_validated)
        self.assertEqual(address.validation_status, 'valid')
        self.assertEqual(address.formatted_address, '123 Test Street, Test City, Test Country') 