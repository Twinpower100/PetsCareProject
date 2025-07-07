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
from .models import User, UserType, ProviderForm, ProviderAdmin
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
        self.user_type = UserType.objects.create(name='owner')
        self.user_data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'first_name': 'Test',
            'last_name': 'User',
            'user_type': self.user_type
        }

    def test_create_user(self):
        """Тест создания пользователя."""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(user.email, self.user_data['email'])
        self.assertTrue(user.check_password(self.user_data['password']))
        self.assertEqual(user.user_type, self.user_type)

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
        user.user_types.add(UserType.objects.get(name='pet_sitter'))
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
        self.user_type = UserType.objects.create(name='owner')
        self.registration_data = {
            'email': 'test@example.com',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'first_name': 'Test',
            'last_name': 'User'
        }
        self.profile_data = {
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'phone': '+1234567890'
        }

    def test_registration_form_valid(self):
        """Тест валидной формы регистрации."""
        serializer = UserRegistrationSerializer(data=self.registration_data)
        self.assertTrue(serializer.is_valid())

    def test_registration_form_invalid(self):
        """Тест невалидной формы регистрации."""
        data = self.registration_data.copy()
        data['password2'] = 'differentpass'
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_profile_form_valid(self):
        """Тест валидной формы профиля."""
        serializer = UserSerializer(data=self.profile_data)
        self.assertTrue(serializer.is_valid())

    def test_profile_form_invalid(self):
        """Тест невалидной формы профиля."""
        data = self.profile_data.copy()
        data['email'] = 'invalid-email'
        serializer = UserSerializer(data=data)
        self.assertFalse(serializer.is_valid())


class UserViewTest(TestCase):
    """
    Тесты для представлений пользователей.
    
    Тестирует:
    - Регистрацию
    - Авторизацию
    - Профиль
    - Выход из системы
    """
    def setUp(self):
        """Подготовка тестовых данных."""
        self.client = Client()
        self.user_type = UserType.objects.create(name='owner')
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
            user_type=self.user_type
        )

    def test_registration_view(self):
        """Тест представления регистрации."""
        response = self.client.get(reverse('users:register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/registration.html')

    def test_login_view(self):
        """Тест представления входа."""
        response = self.client.get(reverse('users:login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')

    def test_profile_view(self):
        """Тест представления профиля."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('users:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/profile.html')

    def test_logout_view(self):
        """Тест представления выхода."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('users:logout'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/logout.html')


class UserURLTest(TestCase):
    """
    Тесты для URL-маршрутов пользователей.
    
    Тестирует:
    - Доступность URL
    - Правильность имен маршрутов
    - Перенаправления
    """
    def setUp(self):
        """Подготовка тестовых данных."""
        self.client = Client()
        self.user_type = UserType.objects.create(name='owner')
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User',
            user_type=self.user_type
        )

    def test_register_url(self):
        """Тест URL регистрации."""
        response = self.client.get('/users/register/')
        self.assertEqual(response.status_code, 200)

    def test_login_url(self):
        """Тест URL входа."""
        response = self.client.get('/users/login/')
        self.assertEqual(response.status_code, 200)

    def test_profile_url(self):
        """Тест URL профиля."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get('/users/profile/')
        self.assertEqual(response.status_code, 200)

    def test_logout_url(self):
        """Тест URL выхода."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get('/users/logout/')
        self.assertEqual(response.status_code, 200)


class UserRegistrationTest(APITestCase):
    """
    Тесты для регистрации пользователей через API
    """
    def test_user_registration(self):
        """
        Тест успешной регистрации пользователя
        """
        url = reverse('api_register')
        data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'first_name': 'Test',
            'last_name': 'User'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().email, 'test@example.com')


class ProviderAdminRegistrationTest(APITestCase):
    """
    Тесты для регистрации администраторов учреждений через API
    """
    def setUp(self):
        """
        Настройка тестовых данных
        """
        self.superuser = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123'
        )
        self.provider = Provider.objects.create(
            name='Test Provider',
            address='Test Address'
        )
        self.client.force_authenticate(user=self.superuser)

    def test_provider_admin_registration(self):
        """
        Тест успешной регистрации администратора учреждения
        """
        url = reverse('provider_admin_register')
        data = {
            'provider_id': self.provider.id,
            'email': 'admin@provider.com',
            'password': 'adminpass123'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='admin@provider.com').exists())
        self.assertTrue(ProviderAdmin.objects.filter(
            user__email='admin@provider.com',
            provider=self.provider
        ).exists())
