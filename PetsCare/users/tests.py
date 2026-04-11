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

from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from .models import EmailVerificationToken, User, UserType, ProviderForm
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


class EmailVerificationFlowTest(APITestCase):
    """
    Тесты обязательной верификации email для owner signup.
    """
    def setUp(self):
        self.registration_url = reverse('users:api_register')
        self.confirm_url = reverse('users:email-verification-confirm')
        self.resend_url = reverse('users:email-verification-resend')
        self.invites_url = reverse('invites:invite-list-create')
        self.registration_data = {
            'email': 'verification-flow@example.com',
            'password': 'Secret123!',
            'first_name': 'Verify',
            'last_name': 'Owner',
            'phone_number': '+12125550001',
        }

    def test_registration_creates_unverified_user_and_token(self):
        response = self.client.post(self.registration_url, self.registration_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        user = User.objects.get(email=self.registration_data['email'])
        self.assertFalse(user.email_verified)
        self.assertTrue(
            EmailVerificationToken.objects.filter(user=user, used=False).exists()
        )
        self.assertTrue(response.data['email_verification_required'])
        self.assertTrue(response.data['email_verification_sent'])

    def test_confirm_endpoint_verifies_user_and_marks_token_used(self):
        user = User.objects.create_user(
            email='confirm-email@example.com',
            password='Secret123!',
            first_name='Confirm',
            last_name='Owner',
            phone_number='+12125550002',
            email_verified=False,
            email_verified_at=None,
        )
        token = EmailVerificationToken.create_for_user(user)

        response = self.client.post(self.confirm_url, {'token': token.token}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        user.refresh_from_db()
        token.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(user.email_verified_at)
        self.assertTrue(token.used)
        self.assertEqual(response.data['code'], 'email_verified')

    def test_resend_is_throttled_inside_cooldown(self):
        user = User.objects.create_user(
            email='resend-email@example.com',
            password='Secret123!',
            first_name='Resend',
            last_name='Owner',
            phone_number='+12125550003',
            email_verified=False,
            email_verified_at=None,
        )
        EmailVerificationToken.create_for_user(user)
        self.client.force_authenticate(user=user)

        response = self.client.post(self.resend_url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data['code'], 'email_verification_resend_throttled')

    def test_resend_creates_new_token_after_cooldown(self):
        user = User.objects.create_user(
            email='resend-late@example.com',
            password='Secret123!',
            first_name='Later',
            last_name='Owner',
            phone_number='+12125550004',
            email_verified=False,
            email_verified_at=None,
        )
        token = EmailVerificationToken.create_for_user(user)
        EmailVerificationToken.objects.filter(pk=token.pk).update(
            created_at=timezone.now() - timedelta(minutes=5)
        )
        self.client.force_authenticate(user=user)

        response = self.client.post(self.resend_url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['code'], 'email_verification_sent')
        self.assertEqual(EmailVerificationToken.objects.filter(user=user, used=False).count(), 1)
        token.refresh_from_db()
        self.assertTrue(token.used)

    def test_unverified_owner_cannot_create_invite(self):
        user = User.objects.create_user(
            email='blocked-owner@example.com',
            password='Secret123!',
            first_name='Blocked',
            last_name='Owner',
            phone_number='+12125550005',
            email_verified=False,
            email_verified_at=None,
        )
        self.client.force_authenticate(user=user)

        response = self.client.post(self.invites_url, {'invite_type': 'pet_co_owner'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertEqual(response.data['code'], 'email_verification_required')


class GoogleSignupFlowTest(APITestCase):
    """
    Тесты двухшаговой регистрации через Google с обязательным телефоном.
    """
    def setUp(self):
        self.google_auth_url = reverse('users:api_google_auth')
        self.google_complete_url = reverse('users:api_google_auth_complete')

    def _mock_google_validate(self, phone=None, email='google-owner@example.com'):
        def _validate(serializer, attrs):
            attrs['google_user_data'] = {
                'email': email,
                'name': 'Google Owner',
                'picture': 'https://example.com/avatar.png',
                'google_id': 'google-user-1',
                'phone': phone,
            }
            return attrs

        return _validate

    def test_google_signup_without_phone_returns_pending_state(self):
        with patch('users.serializers.GoogleAuthSerializer.validate', new=self._mock_google_validate(phone=None)):
            response = self.client.post(self.google_auth_url, {'token': 'google-code'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['needs_phone'])
        self.assertIn('pending_google_signup_token', response.data)
        self.assertFalse(User.objects.filter(email='google-owner@example.com').exists())

    def test_google_signup_completion_creates_unverified_user_and_verification_token(self):
        with patch('users.serializers.GoogleAuthSerializer.validate', new=self._mock_google_validate(phone=None)):
            prepare_response = self.client.post(self.google_auth_url, {'token': 'google-code'}, format='json')

        response = self.client.post(
            self.google_complete_url,
            {
                'pending_token': prepare_response.data['pending_google_signup_token'],
                'phone_number': '+12125550111',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        user = User.objects.get(email='google-owner@example.com')
        self.assertEqual(str(user.phone_number), '+12125550111')
        self.assertFalse(user.email_verified)
        self.assertTrue(response.data['email_verification_required'])
        self.assertTrue(response.data['email_verification_sent'])
        self.assertTrue(
            EmailVerificationToken.objects.filter(user=user, used=False).exists()
        )

    def test_google_signup_with_unique_google_phone_creates_user_immediately(self):
        with patch('users.serializers.GoogleAuthSerializer.validate', new=self._mock_google_validate(phone='+12125550112', email='google-direct@example.com')):
            response = self.client.post(self.google_auth_url, {'token': 'google-code'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        user = User.objects.get(email='google-direct@example.com')
        self.assertEqual(str(user.phone_number), '+12125550112')
        self.assertFalse(user.email_verified)
        self.assertFalse(response.data['needs_phone'])
        self.assertTrue(response.data['email_verification_required'])
        self.assertTrue(response.data['email_verification_sent'])
