"""
Тесты для API поиска по расстоянию.

Тестирует функциональность поиска пользователей, ситтеров и провайдеров
по геолокации с различными фильтрами.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal
from geolocation.models import Address
from providers.models import Provider
from catalog.models import Service, ServiceCategory

User = get_user_model()


class ProviderSearchByDistanceAPITest(APITestCase):
    """
    Тесты для API поиска провайдеров по расстоянию.
    """
    
    def setUp(self):
        """
        Подготавливает тестовые данные.
        """
        # Создаем тестового пользователя
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        
        # Создаем адреса для тестирования
        self.center_address = Address.objects.create(
            country='Russia',
            city='Moscow',
            street='Tverskaya',
            house_number='1',
            latitude=Decimal('55.7558'),
            longitude=Decimal('37.6176'),
            validation_status='valid',
            is_valid=True,
            is_geocoded=True
        )
        
        self.nearby_address = Address.objects.create(
            country='Russia',
            city='Moscow',
            street='Arbat',
            house_number='10',
            latitude=Decimal('55.7494'),
            longitude=Decimal('37.5914'),
            validation_status='valid',
            is_valid=True,
            is_geocoded=True
        )
        
        self.far_address = Address.objects.create(
            country='Russia',
            city='Saint Petersburg',
            street='Nevsky Prospect',
            house_number='1',
            latitude=Decimal('59.9311'),
            longitude=Decimal('30.3609'),
            validation_status='valid',
            is_valid=True,
            is_geocoded=True
        )
        
        # Создаем категорию услуг
        self.category = ServiceCategory.objects.create(
            name='Pet Care',
            description='Pet care services'
        )
        
        # Создаем услугу
        self.service = Service.objects.create(
            name='Dog Walking',
            description='Professional dog walking service',
            category=self.category,
            price=Decimal('500.00')
        )
        
        # Создаем провайдеров
        self.nearby_provider = Provider.objects.create(
            name='Nearby Pet Care',
            description='Pet care near center',
            address=self.nearby_address,
            phone='+7-123-456-7890',
            email='nearby@example.com',
            rating=Decimal('4.5'),
            is_active=True
        )
        
        self.far_provider = Provider.objects.create(
            name='Far Pet Care',
            description='Pet care far from center',
            address=self.far_address,
            phone='+7-987-654-3210',
            email='far@example.com',
            rating=Decimal('4.0'),
            is_active=True
        )
        
        # Создаем услуги провайдеров
        from providers.models import ProviderService
        ProviderService.objects.create(
            provider=self.nearby_provider,
            service=self.service,
            price=Decimal('500.00'),
            is_active=True
        )
        
        ProviderService.objects.create(
            provider=self.far_provider,
            service=self.service,
            price=Decimal('600.00'),
            is_active=True
        )
    
    def test_search_providers_by_distance(self):
        """
        Тестирует поиск провайдеров по расстоянию.
        """
        self.client.force_authenticate(user=self.user)
        
        url = reverse('providers:provider-search-distance')
        params = {
            'latitude': '55.7558',
            'longitude': '37.6176',
            'radius': '5'
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        
        # Проверяем, что найден только ближайший провайдер
        provider_data = response.data[0]
        self.assertEqual(provider_data['name'], 'Nearby Pet Care')
        self.assertIn('distance', provider_data)
        self.assertIsNotNone(provider_data['distance'])
    
    def test_search_providers_with_service_filter(self):
        """
        Тестирует поиск провайдеров с фильтром по услуге.
        """
        self.client.force_authenticate(user=self.user)
        
        url = reverse('providers:provider-search-distance')
        params = {
            'latitude': '55.7558',
            'longitude': '37.6176',
            'radius': '10',
            'service_id': self.service.id
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
    
    def test_search_providers_with_rating_filter(self):
        """
        Тестирует поиск провайдеров с фильтром по рейтингу.
        """
        self.client.force_authenticate(user=self.user)
        
        url = reverse('providers:provider-search-distance')
        params = {
            'latitude': '55.7558',
            'longitude': '37.6176',
            'radius': '10',
            'min_rating': '4.5'
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['rating'], '4.50')
    
    def test_search_providers_invalid_coordinates(self):
        """
        Тестирует поиск с некорректными координатами.
        """
        self.client.force_authenticate(user=self.user)
        
        url = reverse('providers:provider-search-distance')
        params = {
            'latitude': 'invalid',
            'longitude': 'invalid',
            'radius': '5'
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)


class SitterAdvancedSearchByDistanceAPITest(APITestCase):
    """
    Тесты для расширенного API поиска ситтеров по расстоянию.
    """
    
    def setUp(self):
        """
        Подготавливает тестовые данные.
        """
        # Создаем тестового пользователя
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        
        # Создаем ситтеров
        from users.models import UserType
        sitter_type = UserType.objects.create(name='sitter')
        
        self.sitter1 = User.objects.create_user(
            email='sitter1@example.com',
            password='testpass123',
            first_name='Sitter',
            last_name='One',
            rating=Decimal('4.8')
        )
        self.sitter1.user_types.add(sitter_type)
        
        self.sitter2 = User.objects.create_user(
            email='sitter2@example.com',
            password='testpass123',
            first_name='Sitter',
            last_name='Two',
            rating=Decimal('4.2')
        )
        self.sitter2.user_types.add(sitter_type)
        
        # Создаем адреса
        self.center_address = Address.objects.create(
            country='Russia',
            city='Moscow',
            street='Tverskaya',
            house_number='1',
            latitude=Decimal('55.7558'),
            longitude=Decimal('37.6176'),
            validation_status='valid',
            is_valid=True,
            is_geocoded=True
        )
        
        self.nearby_address = Address.objects.create(
            country='Russia',
            city='Moscow',
            street='Arbat',
            house_number='10',
            latitude=Decimal('55.7494'),
            longitude=Decimal('37.5914'),
            validation_status='valid',
            is_valid=True,
            is_geocoded=True
        )
        
        # Привязываем адреса к ситтерам
        self.sitter1.address = self.nearby_address
        self.sitter1.save()
        
        self.sitter2.address = self.center_address
        self.sitter2.save()
    
    def test_advanced_search_sitters_by_distance(self):
        """
        Тестирует расширенный поиск ситтеров по расстоянию.
        """
        self.client.force_authenticate(user=self.user)
        
        url = reverse('providers:sitter-advanced-search')
        params = {
            'latitude': '55.7558',
            'longitude': '37.6176',
            'radius': '5'
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        
        # Проверяем, что результаты отсортированы по расстоянию
        distances = [item['distance'] for item in response.data if item['distance']]
        self.assertEqual(distances, sorted(distances))
    
    def test_advanced_search_sitters_with_rating_filter(self):
        """
        Тестирует поиск ситтеров с фильтром по рейтингу.
        """
        self.client.force_authenticate(user=self.user)
        
        url = reverse('providers:sitter-advanced-search')
        params = {
            'latitude': '55.7558',
            'longitude': '37.6176',
            'radius': '5',
            'min_rating': '4.5'
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['email'], 'sitter1@example.com')
    
    def test_advanced_search_sitters_with_availability_filter(self):
        """
        Тестирует поиск ситтеров с фильтром по доступности.
        """
        self.client.force_authenticate(user=self.user)
        
        url = reverse('providers:sitter-advanced-search')
        params = {
            'latitude': '55.7558',
            'longitude': '37.6176',
            'radius': '5',
            'available': 'true'
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Все ситтеры должны быть доступны (нет активных заявок)
        self.assertEqual(len(response.data), 2)


class DistanceCalculationTest(TestCase):
    """
    Тесты для функций расчета расстояний.
    """
    
    def test_calculate_distance(self):
        """
        Тестирует расчет расстояния между двумя точками.
        """
        from geolocation.utils import calculate_distance
        
        # Москва - Санкт-Петербург (примерно 650 км)
        moscow_lat, moscow_lon = 55.7558, 37.6176
        spb_lat, spb_lon = 59.9311, 30.3609
        
        distance = calculate_distance(moscow_lat, moscow_lon, spb_lat, spb_lon)
        
        self.assertIsNotNone(distance)
        self.assertGreater(distance, 600)  # Должно быть больше 600 км
        self.assertLess(distance, 700)     # И меньше 700 км
    
    def test_is_within_radius(self):
        """
        Тестирует проверку нахождения точки в радиусе.
        """
        from geolocation.utils import is_within_radius
        
        center_lat, center_lon = 55.7558, 37.6176
        nearby_lat, nearby_lon = 55.7494, 37.5914
        far_lat, far_lon = 59.9311, 30.3609
        
        # Близкая точка должна быть в радиусе 5 км
        self.assertTrue(is_within_radius(center_lat, center_lon, nearby_lat, nearby_lon, 5))
        
        # Дальняя точка не должна быть в радиусе 5 км
        self.assertFalse(is_within_radius(center_lat, center_lon, far_lat, far_lon, 5))
    
    def test_validate_coordinates(self):
        """
        Тестирует валидацию координат.
        """
        from geolocation.utils import validate_coordinates
        
        # Корректные координаты
        self.assertTrue(validate_coordinates(55.7558, 37.6176))
        self.assertTrue(validate_coordinates(-90.0, -180.0))
        self.assertTrue(validate_coordinates(90.0, 180.0))
        
        # Некорректные координаты
        self.assertFalse(validate_coordinates(91.0, 37.6176))  # Широта > 90
        self.assertFalse(validate_coordinates(55.7558, 181.0))  # Долгота > 180
        self.assertFalse(validate_coordinates('invalid', 37.6176))  # Не число
        self.assertFalse(validate_coordinates(55.7558, 'invalid'))  # Не число 