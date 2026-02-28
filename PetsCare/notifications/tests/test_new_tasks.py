from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from unittest.mock import patch, MagicMock
from notifications.tasks import (
    send_debt_reminder_task,
    send_new_review_notification_task,
    send_invite_expired_task,
    send_pet_sitting_notification_task,
    send_payment_failed_notification_task,
    send_refund_notification_task,
    send_system_maintenance_notification_task
)
from notifications.models import Notification
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class DebtReminderTaskTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    @patch('notifications.tasks.NotificationService')
    def test_send_debt_reminder_task_success(self, mock_service):
        """Тест успешной отправки напоминания о задолженности"""
        mock_notification = MagicMock()
        mock_service.return_value.send_notification.return_value = mock_notification
        
        send_debt_reminder_task(self.user.id, 100.0, 'EUR')
        
        mock_service.return_value.send_notification.assert_called_once_with(
            user=self.user,
            notification_type='system',
            title='Payment Reminder',
            message='You have outstanding payments. Please settle your debt to continue using our services.',
            channels=['email', 'push', 'in_app'],
            priority='high',
            data={'debt_amount': 100.0, 'currency': 'EUR'}
        )

    def test_send_debt_reminder_task_user_not_found(self):
        """Тест обработки несуществующего пользователя"""
        with self.assertLogs(logger, level='ERROR'):
            send_debt_reminder_task(99999, 100.0, 'EUR')





class NewReviewNotificationTaskTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    @patch('notifications.tasks.Review')
    @patch('notifications.tasks.NotificationService')
    def test_send_new_review_notification_task(self, mock_service, mock_review):
        """Тест отправки уведомления о новом отзыве"""
        # Мокаем отзыв
        mock_review_instance = MagicMock()
        mock_review_instance.id = 1
        mock_review_instance.provider.owner = self.user
        mock_review_instance.service.name = 'Test Service'
        mock_review_instance.rating = 5
        mock_review_instance.user.get_full_name.return_value = 'Test User'
        mock_review.objects.get.return_value = mock_review_instance
        
        mock_notification = MagicMock()
        mock_service.return_value.send_notification.return_value = mock_notification
        
        send_new_review_notification_task(1)
        
        mock_service.return_value.send_notification.assert_called_once_with(
            user=self.user,
            notification_type='review',
            title='New Review Received',
            message='You have received a new review for your service.',
            channels=['email', 'push', 'in_app'],
            priority='medium',
            data={
                'review_id': 1,
                'rating': 5,
                'service_name': 'Test Service',
                'client_name': 'Test User'
            }
        )


class InviteExpiredTaskTest(TestCase):
    """Тест отправки уведомления об истечении инвайта (invites.Invite)."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    @patch('invites.models.Invite')
    @patch('notifications.tasks.NotificationService')
    def test_send_invite_expired_task(self, mock_service, mock_invite_model):
        """Тест отправки уведомления создателю об истечении инвайта (invites.Invite)."""
        mock_invite_instance = MagicMock()
        mock_invite_instance.id = 1
        mock_invite_instance.created_by = self.user
        mock_invite_instance.created_by_id = self.user.id
        mock_invite_model.objects.select_related.return_value.get.return_value = mock_invite_instance

        mock_notification = MagicMock()
        mock_service.return_value.send_notification.return_value = mock_notification

        send_invite_expired_task(1)

        mock_service.return_value.send_notification.assert_called_once()
        call_kw = mock_service.return_value.send_notification.call_args[1]
        self.assertEqual(call_kw['user'], self.user)
        self.assertEqual(call_kw['notification_type'], 'role_invite')
        self.assertIn('Invitation', call_kw['title'])
        self.assertEqual(call_kw['data'], {'invite_id': 1})


class PetSittingNotificationTaskTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    @patch('notifications.tasks.PetSitting')
    @patch('notifications.tasks.NotificationService')
    def test_send_pet_sitting_notification_task(self, mock_service, mock_sitting):
        """Тест отправки уведомления о передержке"""
        # Мокаем передержку
        mock_sitting_instance = MagicMock()
        mock_sitting_instance.id = 1
        mock_sitting_instance.pet.owner = self.user
        mock_sitting_instance.sitter.get_full_name.return_value = 'Test Sitter'
        mock_sitting_instance.start_date = timezone.now().date()
        mock_sitting_instance.end_date = timezone.now().date()
        mock_sitting.objects.get.return_value = mock_sitting_instance
        
        mock_notification = MagicMock()
        mock_service.return_value.send_notification.return_value = mock_notification
        
        send_pet_sitting_notification_task(1, 'confirmed')
        
        mock_service.return_value.send_notification.assert_called_once()


class PaymentFailedNotificationTaskTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    @patch('notifications.tasks.Payment')
    @patch('notifications.tasks.NotificationService')
    def test_send_payment_failed_notification_task(self, mock_service, mock_payment):
        """Тест отправки уведомления о неудачном платеже"""
        # Мокаем платеж
        mock_payment_instance = MagicMock()
        mock_payment_instance.id = 1
        mock_payment_instance.user = self.user
        mock_payment_instance.amount = 100.0
        mock_payment_instance.currency = 'EUR'
        mock_payment.objects.get.return_value = mock_payment_instance
        
        mock_notification = MagicMock()
        mock_service.return_value.send_notification.return_value = mock_notification
        
        send_payment_failed_notification_task(1, 'Insufficient funds')
        
        mock_service.return_value.send_notification.assert_called_once_with(
            user=self.user,
            notification_type='payment',
            title='Payment Failed',
            message='Your payment could not be processed. Please check your payment method.',
            channels=['email', 'push', 'in_app'],
            priority='high',
            data={
                'payment_id': 1,
                'amount': 100.0,
                'currency': 'EUR',
                'reason': 'Insufficient funds'
            }
        )


class RefundNotificationTaskTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    @patch('notifications.tasks.Refund')
    @patch('notifications.tasks.NotificationService')
    def test_send_refund_notification_task(self, mock_service, mock_refund):
        """Тест отправки уведомления о возврате средств"""
        # Мокаем возврат
        mock_refund_instance = MagicMock()
        mock_refund_instance.id = 1
        mock_refund_instance.payment.user = self.user
        mock_refund_instance.amount = 100.0
        mock_refund_instance.currency = 'EUR'
        mock_refund_instance.payment.id = 1
        mock_refund.objects.get.return_value = mock_refund_instance
        
        mock_notification = MagicMock()
        mock_service.return_value.send_notification.return_value = mock_notification
        
        send_refund_notification_task(1)
        
        mock_service.return_value.send_notification.assert_called_once_with(
            user=self.user,
            notification_type='payment',
            title='Refund Processed',
            message='Your refund has been processed and will be credited to your account.',
            channels=['email', 'push', 'in_app'],
            priority='medium',
            data={
                'refund_id': 1,
                'amount': 100.0,
                'currency': 'EUR',
                'payment_id': 1
            }
        )


class SystemMaintenanceNotificationTaskTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    @patch('notifications.tasks.User')
    @patch('notifications.tasks.NotificationService')
    def test_send_system_maintenance_notification_task(self, mock_service, mock_user):
        """Тест отправки системного уведомления"""
        # Мокаем пользователей
        mock_user.objects.filter.return_value = [self.user]
        
        mock_notification = MagicMock()
        mock_service.return_value.send_notification.return_value = mock_notification
        
        send_system_maintenance_notification_task('System maintenance scheduled', [self.user.id])
        
        mock_service.return_value.send_notification.assert_called_once_with(
            user=self.user,
            notification_type='system',
            title='System Maintenance',
            message='System maintenance scheduled',
            channels=['email', 'push', 'in_app'],
            priority='high',
            data={'maintenance': True}
        ) 