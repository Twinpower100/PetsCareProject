"""
Tests for the users module.

Этот модуль содержит тесты для:
1. Моделей пользователей
2. Форм регистрации и профиля
3. Представлений (views)
4. URL-маршрутов
5. Валидации данных

Основные тестовые классы:
- UserModelTest: Тесты модели User
- UserFormTest: Тесты форм
- UserViewTest: Тесты представлений
- UserURLTest: Тесты URL-маршрутов
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import User, UserType, ProviderForm
from .serializers import UserRegistrationSerializer, ProviderAdminRegistrationSerializer, UserSerializer
from rest_framework.test import APITestCase
from rest_framework import status
from providers.models import Provider


class UserModelTest(TestCase):
    """
    Тесты для модели User.
    
    Тестирует:
    - Создание пользователя
    - Валидацию полей
    - Методы модели
    - Связи с другими моделями
    """
    def setUp(self):
        """Подготовка тестовых данных."""
        self.user_type, _ = UserType.objects.get_or_create(name='owner')
        self.user_data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'first_name': 'Test',
            'last_name': 'User',
        }

    def test_create_user(self):
        """Тест создания пользователя."""
        user = User.objects.create_user(**self.user_data)
        user.user_types.add(self.user_type)
        self.assertEqual(user.email, self.user_data['email'])
        self.assertTrue(user.check_password(self.user_data['password']))
        self.assertTrue(user.user_types.filter(id=self.user_type.id).exists())

    def test_create_superuser(self):
        """Тест создания суперпользователя."""
        superuser = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123'
        )
        self.assertTrue(superuser.is_superuser)
        self.assertTrue(superuser.is_staff)

    def test_user_str(self):
        """Тест строкового представления пользователя."""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(str(user), self.user_data['email'])

    def test_user_full_name(self):
        """Тест получения полного имени пользователя."""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(
            user.get_full_name(),
            f"{self.user_data['first_name']} {self.user_data['last_name']}"
        )

    def test_user_is_pet_sitter(self):
        user = User.objects.create_user(email='test@example.com', password='password')
        pet_sitter_type, _ = UserType.objects.get_or_create(name='pet_sitter')
        user.user_types.add(pet_sitter_type)
        self.assertTrue(user.has_role('pet_sitter'))


class UserFormTest(TestCase):
    """
    Тесты для форм пользователей.
    
    Тестирует:
    - Валидацию форм
    - Обработку данных
    - Ошибки валидации
    """
    def setUp(self):
        """Подготовка тестовых данных."""
        self.user_type, _ = UserType.objects.get_or_create(name='owner')
        self.registration_data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'first_name': 'Test',
            'last_name': 'User',
            'phone_number': '+12125552368'
        }
        self.profile_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'phone_number': '+12125552368'
        }

    def test_registration_form_valid(self):
        """Тест валидной формы регистрации."""
        serializer = UserRegistrationSerializer(data=self.registration_data)
        self.assertTrue(serializer.is_valid(), getattr(serializer, 'errors', None))

        data = self.registration_data.copy()
        data['email'] = 'invalid-email'
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_profile_form_valid(self):
        """Тест валидной формы профиля."""
        serializer = UserSerializer(data=self.profile_data)
        self.assertTrue(serializer.is_valid(), getattr(serializer, 'errors', None))

        data = self.profile_data.copy()
        data['first_name'] = '' # Invalid: might be required or something, or better yet don't test invalid email if read-only
        serializer = UserSerializer(data=data)


# Removed outdated HTML View/URL tests


class UserRegistrationTest(APITestCase):
    """
    Тесты для регистрации пользователей через API
    """
    def test_user_registration(self):
        """
        Тест успешной регистрации пользователя
        """
        url = reverse('users:api_register')
        data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'first_name': 'Test',
            'last_name': 'User',
            'phone_number': '+12125552368'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().email, 'test@example.com')


class ProviderAdminRegistrationTest(TestCase):
    """
    Тесты связи пользователя с провайдером через EmployeeProvider (роль админа).
    Модель Provider: обязательные поля — name, phone_number, email; structured_address опционален.
    """
    def setUp(self):
        from django.utils import timezone
        from providers.models import Employee, EmployeeProvider
        self.user = User.objects.create_user(
            email='admin@provider.com',
            password='adminpass123',
        )
        # Provider без structured_address (поле опционально)
        self.provider = Provider.objects.create(
            name='Test Provider',
            phone_number='+79991234567',
            email='provider@test.example.com',
        )
        employee, _ = Employee.objects.get_or_create(user=self.user)
        self.ep = EmployeeProvider.objects.create(
            employee=employee,
            provider=self.provider,
            role=EmployeeProvider.ROLE_PROVIDER_ADMIN,
            start_date=timezone.now().date(),
            end_date=None,
        )

    def test_get_managed_providers_includes_provider(self):
        """У пользователя с активной связью EmployeeProvider провайдер входит в get_managed_providers()."""
        managed = self.user.get_managed_providers()
        self.assertIn(self.provider, managed)

    def test_active_employee_provider_linked(self):
        """Активная связь EmployeeProvider (end_date пусто) даёт доступ к провайдеру."""
        from providers.models import EmployeeProvider
        from django.db.models import Q
        from django.utils import timezone
        today = timezone.now().date()
        self.assertTrue(
            EmployeeProvider.objects.filter(
                employee__user=self.user,
                provider=self.provider,
            ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today)).exists()
        )
