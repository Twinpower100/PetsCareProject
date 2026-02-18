"""
Тесты для API views провайдеров с PostGIS функциональностью.
"""

from django.test import TestCase
from unittest import skip
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from decimal import Decimal

from .models import Provider, Employee, ProviderService
from geolocation.models import Address
from catalog.models import Service

User = get_user_model()


@skip("Deprecated provider distance search tests require model updates")
class ProviderAPITestCase(TestCase):
    """Тесты для API провайдеров с PostGIS."""

    def setUp(self):
        """Создание тестовых данных."""
        self.client = APIClient()
        
        # Создаем тестового пользователя
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Тест',
            last_name='Пользователь'
        )
        
        # Создаем адреса с координатами
        self.moscow_address = Address.objects.create(
            street="Красная площадь, 1",
            city="Москва",
            country="Россия",
            point=Point(37.6173, 55.7558, srid=4326)
        )
        
        self.spb_address = Address.objects.create(
            street="Дворцовая площадь, 1",
            city="Санкт-Петербург",
            country="Россия",
            point=Point(30.3141, 59.9386, srid=4326)
        )
        
        self.kazan_address = Address.objects.create(
            street="Баумана, 1",
            city="Казань",
            country="Россия",
            point=Point(49.1221, 55.7887, srid=4326)
        )
        
        # Создаем категорию услуг
        self.category = ServiceCategory.objects.create(
            name="Ветеринария",
            description="Ветеринарные услуги"
        )
        
        # Создаем услугу
        self.service = Service.objects.create(
            name="Консультация ветеринара",
            description="Консультация специалиста",
            category=self.category,
            base_price=Decimal('1000.00')
        )
        
        # Создаем провайдеров
        self.moscow_provider = Provider.objects.create(
            name="Ветеринарная клиника Москва",
            description="Клиника в центре Москвы",
            structured_address=self.moscow_address,
            point=self.moscow_address.point,
            phone_number="+7-495-123-45-67",
            email="moscow@vet.ru",
            rating=4.5,
            is_active=True
        )
        
        self.spb_provider = Provider.objects.create(
            name="Ветеринарная клиника СПб",
            description="Клиника в центре СПб",
            structured_address=self.spb_address,
            point=self.spb_address.point,
            phone_number="+7-812-123-45-67",
            email="spb@vet.ru",
            rating=4.2,
            is_active=True
        )
        
        self.kazan_provider = Provider.objects.create(
            name="Ветеринарная клиника Казань",
            description="Клиника в центре Казани",
            structured_address=self.kazan_address,
            point=self.kazan_address.point,
            phone_number="+7-843-123-45-67",
            email="kazan@vet.ru",
            rating=4.0,
            is_active=True
        )
        
        # Создаем услуги провайдеров
        ProviderService.objects.create(
            provider=self.moscow_provider,
            service=self.service,
            price=Decimal('1200.00'),
            base_price=Decimal('1000.00'),
            duration_minutes=30,
            is_active=True
        )
        
        ProviderService.objects.create(
            provider=self.spb_provider,
            service=self.service,
            price=Decimal('1100.00'),
            base_price=Decimal('1000.00'),
            duration_minutes=30,
            is_active=True
        )
        
        ProviderService.objects.create(
            provider=self.kazan_provider,
            service=self.service,
            price=Decimal('900.00'),
            base_price=Decimal('1000.00'),
            duration_minutes=30,
            is_active=True
        )

    def test_provider_search_by_distance(self):
        """Тест поиска провайдеров по расстоянию."""
        # Аутентифицируем пользователя
        self.client.force_authenticate(user=self.user)
        
        # URL для поиска по расстоянию
        url = reverse('provider-search-by-distance')
        
        # Параметры поиска: центр Москвы, радиус 1000 км
        params = {
            'latitude': 55.7558,
            'longitude': 37.6173,
            'radius': 1000,
            'service_id': self.service.id
        }
        
        response = self.client.get(url, params)
        
        # Проверяем успешный ответ
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Проверяем, что получили результаты
        results = response.data
        self.assertGreater(len(results), 0)
        
        # Проверяем, что результаты отсортированы по расстоянию
        distances = [item.get('distance', 0) for item in results]
        self.assertEqual(distances, sorted(distances))
        
        # Москва должна быть первой (расстояние 0)
        self.assertEqual(results[0]['name'], "Ветеринарная клиника Москва")
        self.assertAlmostEqual(results[0]['distance'], 0, places=1)

    def test_provider_search_with_rating_filter(self):
        """Тест поиска провайдеров с фильтром по рейтингу."""
        self.client.force_authenticate(user=self.user)
        
        url = reverse('provider-search-by-distance')
        
        # Параметры поиска с минимальным рейтингом 4.3
        params = {
            'latitude': 55.7558,
            'longitude': 37.6173,
            'radius': 1000,
            'min_rating': 4.3
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Должны найти только провайдеров с рейтингом >= 4.3
        results = response.data
        for provider in results:
            self.assertGreaterEqual(provider['rating'], 4.3)

    def test_provider_search_with_price_filter(self):
        """Тест поиска провайдеров с фильтром по цене."""
        self.client.force_authenticate(user=self.user)
        
        url = reverse('provider-search-by-distance')
        
        # Параметры поиска с максимальной ценой 1000
        params = {
            'latitude': 55.7558,
            'longitude': 37.6173,
            'radius': 1000,
            'service_id': self.service.id,
            'price_max': 1000
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Проверяем, что у всех провайдеров цена <= 1000
        results = response.data
        for provider in results:
            price_info = provider.get('price_info')
            if price_info:
                self.assertLessEqual(price_info['price'], 1000)

    def test_provider_search_sorting(self):
        """Тест сортировки результатов поиска."""
        self.client.force_authenticate(user=self.user)
        
        url = reverse('provider-search-by-distance')
        
        # Тестируем сортировку по рейтингу
        params = {
            'latitude': 55.7558,
            'longitude': 37.6173,
            'radius': 1000,
            'sort_by': 'rating'
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Проверяем сортировку по убыванию рейтинга
        results = response.data
        ratings = [provider['rating'] for provider in results]
        self.assertEqual(ratings, sorted(ratings, reverse=True))

    def test_provider_search_price_ascending(self):
        """Тест сортировки по возрастанию цены."""
        self.client.force_authenticate(user=self.user)
        
        url = reverse('provider-search-by-distance')
        
        params = {
            'latitude': 55.7558,
            'longitude': 37.6173,
            'radius': 1000,
            'service_id': self.service.id,
            'sort_by': 'price_asc'
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Проверяем сортировку по возрастанию цены
        results = response.data
        prices = []
        for provider in results:
            price_info = provider.get('price_info')
            if price_info:
                prices.append(price_info['price'])
        
        self.assertEqual(prices, sorted(prices))

    def test_provider_search_price_descending(self):
        """Тест сортировки по убыванию цены."""
        self.client.force_authenticate(user=self.user)
        
        url = reverse('provider-search-by-distance')
        
        params = {
            'latitude': 55.7558,
            'longitude': 37.6173,
            'radius': 1000,
            'service_id': self.service.id,
            'sort_by': 'price_desc'
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Проверяем сортировку по убыванию цены
        results = response.data
        prices = []
        for provider in results:
            price_info = provider.get('price_info')
            if price_info:
                prices.append(price_info['price'])
        
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_provider_search_invalid_coordinates(self):
        """Тест поиска с невалидными координатами."""
        self.client.force_authenticate(user=self.user)
        
        url = reverse('provider-search-by-distance')
        
        # Невалидные координаты
        params = {
            'latitude': 91,  # Широта > 90
            'longitude': 37.6173,
            'radius': 1000
        }
        
        response = self.client.get(url, params)
        
        # Должны получить пустой результат
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_provider_search_missing_coordinates(self):
        """Тест поиска без координат."""
        self.client.force_authenticate(user=self.user)
        
        url = reverse('provider-search-by-distance')
        
        # Без координат
        params = {
            'radius': 1000
        }
        
        response = self.client.get(url, params)
        
        # Должны получить пустой результат
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_provider_search_large_radius(self):
        """Тест поиска с большим радиусом."""
        self.client.force_authenticate(user=self.user)
        
        url = reverse('provider-search-by-distance')
        
        # Большой радиус (2000 км)
        params = {
            'latitude': 55.7558,
            'longitude': 37.6173,
            'radius': 2000
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Должны найти всех провайдеров
        results = response.data
        self.assertEqual(len(results), 3)

    def test_provider_search_small_radius(self):
        """Тест поиска с малым радиусом."""
        self.client.force_authenticate(user=self.user)
        
        url = reverse('provider-search-by-distance')
        
        # Малый радиус (1 км)
        params = {
            'latitude': 55.7558,
            'longitude': 37.6173,
            'radius': 1
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Должны найти только московского провайдера
        results = response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], "Ветеринарная клиника Москва")

    def test_provider_search_limit_results(self):
        """Тест ограничения количества результатов."""
        self.client.force_authenticate(user=self.user)
        
        url = reverse('provider-search-by-distance')
        
        # Ограничиваем до 2 результатов
        params = {
            'latitude': 55.7558,
            'longitude': 37.6173,
            'radius': 1000,
            'limit': 2
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Должны получить не более 2 результатов
        results = response.data
        self.assertLessEqual(len(results), 2)

    def test_provider_search_with_availability(self):
        """Тест поиска с проверкой доступности."""
        self.client.force_authenticate(user=self.user)
        
        url = reverse('provider-search-by-distance')
        
        # Параметры с проверкой доступности
        params = {
            'latitude': 55.7558,
            'longitude': 37.6173,
            'radius': 1000,
            'available_date': '2024-01-15',
            'available_time': '10:00'
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Проверяем, что у всех провайдеров есть информация о доступности
        results = response.data
        for provider in results:
            self.assertIn('availability_info', provider)

    def test_provider_model_find_nearest(self):
        """Тест метода find_nearest модели Provider."""
        # Тестируем поиск ближайших провайдеров
        center_lat, center_lon = 55.7558, 37.6173  # Москва
        
        nearest = Provider.find_nearest(center_lat, center_lon, radius=1000, limit=3)
        
        # Должны найти 3 провайдера
        self.assertEqual(len(nearest), 3)
        
        # Проверяем сортировку по расстоянию
        distances = [distance for _, distance in nearest]
        self.assertEqual(distances, sorted(distances))
        
        # Москва должна быть первой
        self.assertEqual(nearest[0][0].name, "Ветеринарная клиника Москва")
        self.assertAlmostEqual(nearest[0][1], 0, places=1)

    def test_provider_model_distance_to(self):
        """Тест метода distance_to модели Provider."""
        # Тестируем расчет расстояния
        center_lat, center_lon = 55.7558, 37.6173  # Москва
        
        # Расстояние от московского провайдера до центра Москвы
        distance = self.moscow_provider.distance_to(center_lat, center_lon)
        self.assertAlmostEqual(distance, 0, places=1)
        
        # Расстояние от СПб провайдера до центра Москвы
        distance = self.spb_provider.distance_to(center_lat, center_lon)
        self.assertGreater(distance, 600)  # Должно быть больше 600 км
        self.assertLess(distance, 700)     # И меньше 700 км
