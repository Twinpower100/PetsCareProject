"""
Тесты для модуля каталога услуг.

Этот модуль содержит тесты для:
1. Моделей категорий и услуг
2. Представлений каталога
3. Административного интерфейса
4. Валидации данных

Основные тестовые классы:
- ServiceCategoryTest: Тесты модели ServiceCategory
- ServiceTest: Тесты модели Service
- CatalogViewTest: Тесты представлений
"""

from django.test import TestCase, Client
from unittest import skip
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from .models import Service


class ServiceCategoryTest(TestCase):
    """
    Тесты для модели ServiceCategory.
    
    Тестирует:
    - Создание категории
    - Валидацию полей
    - Методы модели
    - Строковое представление
    """
    def setUp(self):
        """Подготовка тестовых данных."""
        self.category_data = {
            'code': 'test_category',
            'name': 'Test Category',
            'description': 'Test Description',
            'level': 0,
            'is_active': True
        }

    def test_create_category(self):
        """Тест создания категории."""
        category = Service.objects.create(**self.category_data)
        self.assertEqual(category.name, self.category_data['name'])
        self.assertEqual(category.description, self.category_data['description'])
        self.assertEqual(category.level, 0)

    def test_category_str(self):
        """Тест строкового представления категории."""
        category = Service.objects.create(**self.category_data)
        self.assertEqual(str(category), self.category_data['name'])


class ServiceTest(TestCase):
    """
    Тесты для модели Service.
    
    Тестирует:
    - Создание услуги
    - Валидацию полей
    - Методы модели
    - Строковое представление
    - Связи с категорией
    """
    def setUp(self):
        """Подготовка тестовых данных."""
        self.category = Service.objects.create(
            code='test_category_parent',
            name='Test Category',
            description='Test Description',
            level=0,
            is_active=True
        )
        self.service_data = {
            'parent': self.category,
            'code': 'test_service',
            'name': 'Test Service',
            'description': 'Test Description',
            'level': 1,
            'is_active': True
        }

    def test_create_service(self):
        """Тест создания услуги."""
        service = Service.objects.create(**self.service_data)
        self.assertEqual(service.name, self.service_data['name'])
        self.assertEqual(service.parent, self.category)
        self.assertEqual(service.level, 1)
        self.assertTrue(service.is_active)

    def test_service_str(self):
        """Тест строкового представления услуги."""
        service = Service.objects.create(**self.service_data)
        self.assertEqual(str(service), self.service_data['name'])


@skip("Deprecated HTML catalog views removed")
class CatalogViewTest(TestCase):
    """
    Тесты для представлений каталога.
    
    Тестирует:
    - Список категорий
    - Список услуг
    - Детальную информацию об услуге
    - Поиск услуг
    """
    def setUp(self):
        """Подготовка тестовых данных."""
        self.client = Client()
        self.category = Service.objects.create(
            code='test_category_root',
            name='Test Category',
            description='Test Description',
            level=0,
            is_active=True
        )
        self.service = Service.objects.create(
            parent=self.category,
            code='test_service_child',
            name='Test Service',
            description='Test Description',
            level=1,
            is_active=True
        )

    def test_category_list_view(self):
        """Тест представления списка категорий."""
        response = self.client.get(reverse('catalog:category_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'catalog/category_list.html')
        self.assertContains(response, self.category.name)

    def test_service_list_view(self):
        """Тест представления списка услуг."""
        response = self.client.get(reverse('catalog:service_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'catalog/service_list.html')
        self.assertContains(response, self.service.name)

    def test_service_detail_view(self):
        """Тест представления детальной информации об услуге."""
        response = self.client.get(reverse('catalog:service_detail', args=[self.service.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'catalog/service_detail.html')
        self.assertContains(response, self.service.name)

    def test_service_search_view(self):
        """Тест представления поиска услуг."""
        response = self.client.get(reverse('catalog:service_search'), {'q': 'Test'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'catalog/service_search.html')
        self.assertContains(response, self.service.name)
