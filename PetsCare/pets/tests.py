"""
Тесты для модуля pets.

Этот модуль содержит тесты для:
1. Управления питомцами
2. Медицинских записей
3. Самостоятельного снятия обязанностей совладельца
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.utils import timezone
from .models import Pet, PetType, Breed
from unittest.mock import patch, MagicMock

User = get_user_model()


class CoOwnerRemovalTestCase(APITestCase):
    """
    Тесты для самостоятельного снятия обязанностей совладельца.
    """
    
    def setUp(self):
        """Настройка тестовых данных."""
        # Создаем пользователей
        self.main_owner = User.objects.create_user(
            email='main@example.com',
            password='testpass123',
            first_name='Main',
            last_name='Owner'
        )
        
        self.co_owner = User.objects.create_user(
            email='co@example.com',
            password='testpass123',
            first_name='Co',
            last_name='Owner'
        )
        
        self.other_user = User.objects.create_user(
            email='other@example.com',
            password='testpass123',
            first_name='Other',
            last_name='User'
        )
        
        # Создаем тип питомца и породу
        self.pet_type = PetType.objects.create(
            name='Dog',
            code='dog'
        )
        
        self.breed = Breed.objects.create(
            pet_type=self.pet_type,
            name='Golden Retriever',
            code='golden_retriever'
        )
        
        # Создаем питомца
        self.pet = Pet.objects.create(
            main_owner=self.main_owner,
            name='Buddy',
            pet_type=self.pet_type,
            breed=self.breed
        )
        
        # Добавляем совладельца
        self.pet.owners.add(self.co_owner)
        
        # Настраиваем клиент
        self.client = APIClient()
    
    def test_successful_coowner_removal(self):
        """Тест успешного снятия обязанностей совладельца."""
        # Аутентифицируем совладельца
        self.client.force_authenticate(user=self.co_owner)
        
        # Выполняем запрос
        url = reverse('pets:pet-remove-myself-as-coowner', kwargs={'pk': self.pet.id})
        response = self.client.post(url)
        
        # Проверяем ответ
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        self.assertEqual(response.data['pet_id'], self.pet.id)
        self.assertEqual(response.data['removed_user_id'], self.co_owner.id)
        
        # Проверяем, что совладелец удален из списка владельцев
        self.pet.refresh_from_db()
        self.assertNotIn(self.co_owner, self.pet.owners.all())
    
    def test_main_owner_cannot_remove_themselves(self):
        """Тест что основной владелец не может снять себя как совладельца."""
        # Аутентифицируем основного владельца
        self.client.force_authenticate(user=self.main_owner)
        
        # Выполняем запрос
        url = reverse('pets:pet-remove-myself-as-coowner', kwargs={'pk': self.pet.id})
        response = self.client.post(url)
        
        # Проверяем ответ
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('main owner', response.data['error'].lower())
    
    def test_non_owner_cannot_remove_themselves(self):
        """Тест что пользователь, не являющийся владельцем, не может снять себя."""
        # Аутентифицируем пользователя, не являющегося владельцем
        self.client.force_authenticate(user=self.other_user)
        
        # Выполняем запрос
        url = reverse('pets:pet-remove-myself-as-coowner', kwargs={'pk': self.pet.id})
        response = self.client.post(url)
        
        # Проверяем ответ
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('error', response.data)
        self.assertIn('do not have access', response.data['error'].lower())
    
    @patch('pets.api_views.PetViewSet._has_active_pet_sittings')
    def test_cannot_remove_with_active_pet_sittings(self, mock_has_active):
        """Тест что нельзя снять себя при активных передержках."""
        # Мокаем проверку активных передержек
        mock_has_active.return_value = True
        
        # Аутентифицируем совладельца
        self.client.force_authenticate(user=self.co_owner)
        
        # Выполняем запрос
        url = reverse('pets:pet-remove-myself-as-coowner', kwargs={'pk': self.pet.id})
        response = self.client.post(url)
        
        # Проверяем ответ
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('active pet sittings', response.data['error'].lower())
    
    @patch('pets.api_views.PetViewSet._notify_main_owner')
    def test_main_owner_notification(self, mock_notify):
        """Тест уведомления основного владельца."""
        # Аутентифицируем совладельца
        self.client.force_authenticate(user=self.co_owner)
        
        # Выполняем запрос
        url = reverse('pets:pet-remove-myself-as-coowner', kwargs={'pk': self.pet.id})
        response = self.client.post(url)
        
        # Проверяем что уведомление было вызвано
        mock_notify.assert_called_once_with(self.pet, self.co_owner)
    
    @patch('pets.api_views.PetViewSet._log_coowner_removal')
    def test_audit_logging(self, mock_log):
        """Тест логирования в аудите."""
        # Аутентифицируем совладельца
        self.client.force_authenticate(user=self.co_owner)
        
        # Выполняем запрос
        url = reverse('pets:pet-remove-myself-as-coowner', kwargs={'pk': self.pet.id})
        response = self.client.post(url)
        
        # Проверяем что логирование было вызвано
        mock_log.assert_called_once_with(self.pet, self.co_owner)
    
    def test_transaction_rollback_on_error(self):
        """Тест отката транзакции при ошибке."""
        # Аутентифицируем совладельца
        self.client.force_authenticate(user=self.co_owner)
        
        # Сохраняем исходное состояние
        original_owners_count = self.pet.owners.count()
        
        # Мокаем ошибку в транзакции
        with patch('pets.api_views.PetViewSet._log_coowner_removal', side_effect=Exception('Test error')):
            url = reverse('pets:pet-remove-myself-as-coowner', kwargs={'pk': self.pet.id})
            response = self.client.post(url)
        
        # Проверяем что транзакция откатилась
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.owners.count(), original_owners_count)
        self.assertIn(self.co_owner, self.pet.owners.all())
    
    def test_unauthorized_access(self):
        """Тест доступа без аутентификации."""
        # Не аутентифицируем пользователя
        url = reverse('pets:pet-remove-myself-as-coowner', kwargs={'pk': self.pet.id})
        response = self.client.post(url)
        
        # Проверяем ответ
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_pet_not_found(self):
        """Тест запроса для несуществующего питомца."""
        # Аутентифицируем совладельца
        self.client.force_authenticate(user=self.co_owner)
        
        # Выполняем запрос с несуществующим ID
        url = reverse('pets:pet-remove-myself-as-coowner', kwargs={'pk': 99999})
        response = self.client.post(url)
        
        # Проверяем ответ
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class CoOwnerRemovalIntegrationTestCase(TestCase):
    """
    Интеграционные тесты для снятия обязанностей совладельца.
    """
    
    def setUp(self):
        """Настройка тестовых данных."""
        # Создаем пользователей
        self.main_owner = User.objects.create_user(
            email='main@example.com',
            password='testpass123'
        )
        
        self.co_owner = User.objects.create_user(
            email='co@example.com',
            password='testpass123'
        )
        
        # Создаем питомца
        self.pet_type = PetType.objects.create(name='Dog', code='dog')
        self.pet = Pet.objects.create(
            main_owner=self.main_owner,
            name='Buddy',
            pet_type=self.pet_type
        )
        self.pet.owners.add(self.co_owner)
    
    def test_coowner_removal_affects_pet_access(self):
        """Тест что снятие совладельца влияет на доступы к питомцу."""
        from access.models import PetAccess
        
        # Создаем временный доступ для совладельца
        access = PetAccess.objects.create(
            pet=self.pet,
            granted_to=self.co_owner,
            granted_by=self.main_owner,
            expires_at=timezone.now() + timezone.timedelta(days=7),
            permissions={'read': True, 'book': True}
        )
        
        # Проверяем что доступ существует
        self.assertTrue(PetAccess.objects.filter(id=access.id).exists())
        
        # Симулируем снятие совладельца (удаляем из owners)
        self.pet.owners.remove(self.co_owner)
        
        # Проверяем что временный доступ также удален
        self.assertFalse(PetAccess.objects.filter(id=access.id).exists())
    
    def test_coowner_removal_preserves_main_owner(self):
        """Тест что снятие совладельца не влияет на основного владельца."""
        # Сохраняем основного владельца
        original_main_owner = self.pet.main_owner
        
        # Симулируем снятие совладельца
        self.pet.owners.remove(self.co_owner)
        self.pet.refresh_from_db()
        
        # Проверяем что основной владелец остался
        self.assertEqual(self.pet.main_owner, original_main_owner)
        self.assertIn(self.main_owner, self.pet.owners.all())
