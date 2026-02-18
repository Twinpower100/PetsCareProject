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
from datetime import timedelta

from .models import Address, AddressValidation, AddressCache
from .services import AddressValidationService, GoogleMapsService
from .signals import auto_validate_address
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
            'house_number': '123',
            'street': 'Test Street',
            'city': 'Test City',
            'region': 'Test Region',
            'country': 'Test Country',
            'postal_code': '12345'
        }
    
    def test_create_address(self):
        """Test creating an address."""
        address = Address.objects.create(**self.address_data)
        
        self.assertEqual(address.house_number, '123')
        self.assertEqual(address.street, 'Test Street')
        self.assertEqual(address.city, 'Test City')
        self.assertEqual(address.country, 'Test Country')
        self.assertFalse(address.is_validated)
        self.assertEqual(address.validation_status, 'pending')
    
    def test_address_str_representation(self):
        """Test string representation of an address."""
        address = Address.objects.create(**self.address_data)
        
        expected_str = f"{self.address_data['street']}, {self.address_data['house_number']}, {self.address_data['city']}"
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
            house_number='123',
            street='Test Street',
            city='Test City',
            country='Test Country'
        )
    
    def test_create_validation(self):
        """Test creating a validation record."""
        validation = AddressValidation.objects.create(
            address=self.address,
            is_valid=True,
            confidence_score=Decimal('0.90')
        )
        
        self.assertEqual(validation.address, self.address)
        self.assertTrue(validation.is_valid)
        self.assertEqual(validation.confidence_score, Decimal('0.90'))
    
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
        from django.utils import timezone
        cache_entry = AddressCache.objects.create(
            cache_key='test_hash_123',
            address_data={'formatted_address': '123 Test Street, Test City'},
            expires_at=timezone.now() + timedelta(days=1)
        )
        
        self.assertEqual(cache_entry.cache_key, 'test_hash_123')
        self.assertEqual(cache_entry.address_data['formatted_address'], '123 Test Street, Test City')
    
    def test_cache_str_representation(self):
        """Test string representation of a cache."""
        from django.utils import timezone
        cache_entry = AddressCache.objects.create(
            cache_key='test_hash_123',
            address_data={'formatted_address': 'Test Address'},
            expires_at=timezone.now() + timedelta(days=1)
        )
        
        expected_str = f"Cache: test_hash_123 (expires: {cache_entry.expires_at})"
        self.assertEqual(str(cache_entry), expected_str)


class AddressFormTest(TestCase):
    """
    Tests for the AddressForm.
    """
    
    def setUp(self):
        """Setting up test data."""
        self.form_data = {
            'house_number': '123',
            'street': 'Test Street',
            'city': 'Test City',
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
        self.assertIn('At least one address component', str(form.errors))
    
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
            'house_number': '123',
            'street': 'Test Street',
            'city': 'Test City',
            'country': 'Test Country'
        }
        self.address = Address.objects.create(**self.address_data)
    
    def test_serializer_fields(self):
        """Test serializer fields."""
        serializer = AddressSerializer(self.address)
        data = serializer.data
        
        self.assertIn('id', data)
        self.assertIn('house_number', data)
        self.assertIn('street', data)
        self.assertIn('city', data)
        self.assertIn('country', data)
        self.assertIn('is_valid', data)
        self.assertIn('is_geocoded', data)
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
            house_number='123',
            street='Test Street',
            city='Test City',
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
            'house_number': '456',
            'street': 'New Street',
            'city': 'New City',
            'country': 'New Country'
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_retrieve_address(self):
        """Test getting a specific address."""
        url = reverse('geolocation:address-detail', args=[self.address.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['house_number'], '123')
    
    def test_update_address(self):
        """Test updating an address."""
        url = reverse('geolocation:address-detail', args=[self.address.id])
        data = {
            'house_number': '789',
            'street': 'Updated Street',
            'city': 'Updated City',
            'country': 'Updated Country'
        }
        
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['house_number'], '789')
    
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
            house_number='123',
            street='Test Street',
            city='Test City',
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
        
        self.assertTrue(result)
        self.assertEqual(self.address.formatted_address, '123 Test Street, Test City, Test Country')
        self.assertEqual(self.address.latitude, Decimal('55.7558'))
        self.assertEqual(self.address.longitude, Decimal('37.6176'))
    
    @patch('geolocation.services.GoogleMapsService')
    def test_validate_address_failure(self, mock_google_maps):
        """Test unsuccessful address validation."""
        # Mock Google Maps API response
        mock_service = MagicMock()
        mock_service.geocode_address.return_value = None
        mock_google_maps.return_value = mock_service
        
        result = self.service.validate_address(self.address)
        
        self.assertFalse(result)
        self.assertIsNone(self.address.formatted_address)
        self.assertIsNone(self.address.latitude)
        self.assertIsNone(self.address.longitude)


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
            'house_number': '123',
            'street': 'Test Street',
            'city': 'Test City',
            'country': 'Test Country'
        }
    
    @patch('geolocation.signals.AddressValidationService')
    def test_auto_validate_address_signal(self, mock_service):
        """Test automatic address validation through signal."""
        # Mock validation service
        mock_service_instance = MagicMock()
        mock_service_instance.validate_address.return_value = True
        mock_service.return_value = mock_service_instance
        
        address = Address.objects.create(**self.address_data)
        auto_validate_address(Address, address, created=True)
        
        mock_service_instance.validate_address.assert_called_once_with(address)

"""
Тесты для геолокационных функций с PostGIS.
"""

from django.test import TestCase
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.db import connection
from decimal import Decimal
import math

from .models import Address, Location, LocationHistory, UserLocation
from .utils import (
    filter_by_distance,
    create_distance_annotation,
    optimize_geospatial_query,
    batch_distance_calculation,
    validate_coordinates,
    format_distance
)


class PostGISFunctionsTestCase(TestCase):
    """Тесты для PostGIS функций геолокации."""

    def setUp(self):
        """Создание тестовых данных."""
        # Создаем тестовые адреса с координатами
        self.moscow_center = Address.objects.create(
            street="Красная площадь",
            city="Москва",
            country="Россия",
            point=Point(37.6173, 55.7558, srid=4326)  # Москва, Красная площадь
        )
        
        self.spb_center = Address.objects.create(
            street="Дворцовая площадь",
            city="Санкт-Петербург", 
            country="Россия",
            point=Point(30.3141, 59.9386, srid=4326)  # СПб, Дворцовая площадь
        )
        
        self.kazan_center = Address.objects.create(
            street="Баумана",
            city="Казань",
            country="Россия", 
            point=Point(49.1221, 55.7887, srid=4326)  # Казань, ул. Баумана
        )

    def test_filter_by_distance(self):
        """Тест фильтрации по расстоянию с PostGIS."""
        # Центр поиска - Москва
        center_lat, center_lon = 55.7558, 37.6173
        
        # Фильтруем адреса в радиусе 1000 км от Москвы
        results = filter_by_distance(
            Address.objects.all(),
            center_lat,
            center_lon,
            1000,
            'point'
        )
        
        # Должны найти все 3 адреса
        self.assertEqual(len(results), 3)
        
        # Проверяем, что результаты отсортированы по расстоянию
        distances = [distance for _, distance in results]
        self.assertEqual(distances, sorted(distances))
        
        # Москва должна быть первой (расстояние 0)
        self.assertEqual(results[0][0].city, "Москва")
        self.assertAlmostEqual(results[0][1], 0, places=1)

    def test_create_distance_annotation(self):
        """Тест создания аннотации расстояния."""
        center_lat, center_lon = 55.7558, 37.6173
        
        # Создаем аннотацию расстояния
        queryset = create_distance_annotation(
            Address.objects.all(),
            center_lat,
            center_lon,
            'point'
        )
        
        # Проверяем, что у каждого объекта есть поле distance
        for obj in queryset:
            self.assertTrue(hasattr(obj, 'distance'))
            self.assertIsNotNone(obj.distance)

    def test_optimize_geospatial_query(self):
        """Тест оптимизации геопространственных запросов."""
        center_lat, center_lon = 55.7558, 37.6173
        
        # Оптимизируем запрос
        queryset = optimize_geospatial_query(
            Address.objects.all(),
            center_lat,
            center_lon,
            1000,
            'point'
        )
        
        # Проверяем, что запрос выполняется без ошибок
        results = list(queryset)
        self.assertGreater(len(results), 0)
        
        # Проверяем, что у каждого объекта есть distance
        for obj in results:
            self.assertTrue(hasattr(obj, 'distance'))

    def test_batch_distance_calculation(self):
        """Тест батчевого расчета расстояний."""
        center_lat, center_lon = 55.7558, 37.6173
        
        # Выполняем батчевый расчет
        results = batch_distance_calculation(
            Address.objects.all(),
            center_lat,
            center_lon,
            batch_size=2
        )
        
        # Проверяем результаты
        self.assertEqual(len(results), 3)
        
        # Проверяем, что расстояния корректны
        for obj, distance in results:
            self.assertIsInstance(distance, (int, float))
            self.assertGreaterEqual(distance, 0)

    def test_validate_coordinates(self):
        """Тест валидации координат."""
        # Валидные координаты
        self.assertTrue(validate_coordinates(55.7558, 37.6173))
        self.assertTrue(validate_coordinates(-90, -180))
        self.assertTrue(validate_coordinates(90, 180))
        
        # Невалидные координаты
        self.assertFalse(validate_coordinates(91, 37.6173))  # Широта > 90
        self.assertFalse(validate_coordinates(55.7558, 181))  # Долгота > 180
        self.assertFalse(validate_coordinates(-91, 37.6173))  # Широта < -90
        self.assertFalse(validate_coordinates(55.7558, -181))  # Долгота < -180
        
        # Нечисловые значения
        self.assertFalse(validate_coordinates("abc", 37.6173))
        self.assertFalse(validate_coordinates(55.7558, "def"))

    def test_format_distance(self):
        """Тест форматирования расстояния."""
        # Меньше 1 км
        self.assertEqual(format_distance(0.5), "500 m")
        self.assertEqual(format_distance(0.1), "100 m")
        
        # Меньше 10 км
        self.assertEqual(format_distance(1.5), "1.5 km")
        self.assertEqual(format_distance(5.7), "5.7 km")
        
        # Больше 10 км
        self.assertEqual(format_distance(15), "15 km")
        self.assertEqual(format_distance(100.3), "100 km")

    def test_distance_calculation_accuracy(self):
        """Тест точности расчета расстояний."""
        # Расстояние между Москвой и СПб (примерно 650 км)
        moscow_point = Point(37.6173, 55.7558, srid=4326)
        spb_point = Point(30.3141, 59.9386, srid=4326)
        
        # Используем PostGIS для расчета
        distance_meters = moscow_point.distance(spb_point) * 111320  # Приблизительно
        distance_km = distance_meters / 1000
        
        # Проверяем, что расстояние в разумных пределах (600-700 км)
        self.assertGreater(distance_km, 600)
        self.assertLess(distance_km, 700)

    def test_spatial_index_usage(self):
        """Тест использования пространственных индексов."""
        # Проверяем, что в базе данных есть пространственные индексы
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'geolocation_address' 
                AND indexname LIKE '%gist%'
            """)
            indexes = cursor.fetchall()
            
            # Должен быть хотя бы один GiST индекс
            self.assertGreater(len(indexes), 0)

    def test_fallback_functionality(self):
        """Тест fallback функциональности при ошибках PostGIS."""
        # Создаем объект без point поля
        address_without_point = Address.objects.create(
            street="Тестовая улица",
            city="Тестовый город",
            country="Тестовая страна"
            # point не указан
        )
        
        # Функция должна работать без ошибок
        center_lat, center_lon = 55.7558, 37.6173
        results = filter_by_distance(
            Address.objects.all(),
            center_lat,
            center_lon,
            1000,
            'point'
        )
        
        # Проверяем, что функция не падает
        self.assertIsInstance(results, list)

    def test_large_dataset_performance(self):
        """Тест производительности на большом наборе данных."""
        # Создаем дополнительные тестовые данные
        for i in range(100):
            lat = 55.7558 + (i * 0.01)  # Смещаем на 0.01 градуса
            lon = 37.6173 + (i * 0.01)
            Address.objects.create(
                street=f"Улица {i}",
                city=f"Город {i}",
                country="Россия",
                point=Point(lon, lat, srid=4326)
            )
        
        # Тестируем производительность
        center_lat, center_lon = 55.7558, 37.6173
        
        import time
        start_time = time.time()
        
        results = filter_by_distance(
            Address.objects.all(),
            center_lat,
            center_lon,
            100,
            'point'
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Проверяем, что запрос выполняется быстро (менее 1 секунды)
        self.assertLess(execution_time, 1.0)
        
        # Проверяем, что результаты корректны
        self.assertGreater(len(results), 0)
        
        # Проверяем сортировку по расстоянию
        distances = [distance for _, distance in results]
        self.assertEqual(distances, sorted(distances))


class AddressModelTestCase(TestCase):
    """Тесты для модели Address с PostGIS."""

    def test_point_field_creation(self):
        """Тест создания PointField."""
        address = Address.objects.create(
            street="Тестовая улица",
            city="Тестовый город",
            country="Тестовая страна",
            point=Point(37.6173, 55.7558, srid=4326)
        )
        
        self.assertIsNotNone(address.point)
        self.assertEqual(address.point.srid, 4326)
        self.assertEqual(address.point.coords, (37.6173, 55.7558))

    def test_distance_calculation(self):
        """Тест расчета расстояния между адресами."""
        address1 = Address.objects.create(
            street="Адрес 1",
            city="Город 1",
            country="Страна 1",
            point=Point(37.6173, 55.7558, srid=4326)
        )
        
        address2 = Address.objects.create(
            street="Адрес 2", 
            city="Город 2",
            country="Страна 2",
            point=Point(30.3141, 59.9386, srid=4326)
        )
        
        # Расстояние должно быть положительным
        distance = address1.point.distance(address2.point)
        self.assertGreater(distance, 0)

    def test_spatial_query(self):
        """Тест пространственного запроса."""
        # Создаем адреса в разных точках
        Address.objects.create(
            street="Центр",
            city="Город",
            country="Страна",
            point=Point(37.6173, 55.7558, srid=4326)
        )
        
        Address.objects.create(
            street="Близко",
            city="Город", 
            country="Страна",
            point=Point(37.6273, 55.7558, srid=4326)  # 1 км восточнее
        )
        
        Address.objects.create(
            street="Далеко",
            city="Город",
            country="Страна", 
            point=Point(30.3141, 59.9386, srid=4326)  # Другой город
        )
        
        # Ищем адреса в радиусе 2 км от центра
        center_point = Point(37.6173, 55.7558, srid=4326)
        nearby_addresses = Address.objects.filter(
            point__distance_lte=(center_point, 2000)  # 2 км в метрах
        ).annotate(
            distance=Distance('point', center_point)
        ).order_by('distance')
        
        # Должны найти 2 адреса (центр и близко)
        self.assertEqual(nearby_addresses.count(), 2)
        
        # Первый должен быть центр (расстояние 0)
        self.assertEqual(nearby_addresses[0].street, "Центр")
        self.assertAlmostEqual(nearby_addresses[0].distance.m, 0, places=1) 