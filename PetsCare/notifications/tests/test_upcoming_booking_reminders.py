from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from booking.constants import CANCELLED_BY_PROVIDER
from booking.models import BookingCancellationReason
from booking.test_booking_flow_logic import BookingFlowBaseMixin
from notifications.api_views import ReminderSettingsViewSet
from notifications.models import Notification, NotificationPreference, NotificationType, ReminderSettings
from notifications.tasks import send_upcoming_booking_reminders_task


class UpcomingBookingReminderTaskTests(BookingFlowBaseMixin, TestCase):
    """
    Тесты MVP-потока upcoming booking reminder.
    """

    def setUp(self):
        super().setUp()
        BookingCancellationReason.ensure_default_reasons()
        self.provider_unavailable = BookingCancellationReason.objects.get(code='provider_unavailable')

    def _create_due_booking(self):
        """
        Создает активное бронирование, попадающее в default reminder window.
        """
        return self._create_booking(
            pet=self.pet_one,
            location=self.location_a,
            employee=self.employee_a,
            start_time=timezone.now() + timedelta(hours=2),
        )

    @patch('notifications.services.send_mail', return_value=1)
    def test_active_booking_receives_one_upcoming_reminder(self, mocked_send_mail):
        """
        Для active booking reminder создается и отправляется ровно один раз.
        """
        booking = self._create_due_booking()

        result = send_upcoming_booking_reminders_task()

        notification = Notification.objects.get(
            user=booking.user,
            notification_type='reminder',
            data__booking_id=booking.id,
            data__reminder_type='upcoming_booking',
        )
        self.assertEqual(result['sent_count'], 1)
        self.assertEqual(notification.channel, 'email')
        self.assertIsNotNone(notification.sent_at)
        mocked_send_mail.assert_called_once()

    @patch('notifications.services.send_mail', return_value=1)
    def test_cancelled_booking_does_not_receive_upcoming_reminder(self, mocked_send_mail):
        """
        Отмененное бронирование не получает upcoming reminder.
        """
        booking = self._create_due_booking()
        booking.cancel_booking(
            cancelled_by=CANCELLED_BY_PROVIDER,
            cancelled_by_user=self.employee_a.user,
            cancellation_reason=self.provider_unavailable,
        )

        result = send_upcoming_booking_reminders_task()

        self.assertEqual(result['sent_count'], 0)
        self.assertFalse(
            Notification.objects.filter(
                user=booking.user,
                notification_type='reminder',
                data__booking_id=booking.id,
                data__reminder_type='upcoming_booking',
            ).exists()
        )
        mocked_send_mail.assert_not_called()

    @patch('notifications.services.send_mail', return_value=1)
    def test_task_does_not_duplicate_upcoming_reminder(self, mocked_send_mail):
        """
        Повторный запуск task не создает duplicate reminder.
        """
        booking = self._create_due_booking()

        send_upcoming_booking_reminders_task()
        second_result = send_upcoming_booking_reminders_task()

        self.assertEqual(second_result['sent_count'], 0)
        self.assertEqual(
            Notification.objects.filter(
                user=booking.user,
                notification_type='reminder',
                data__booking_id=booking.id,
                data__reminder_type='upcoming_booking',
            ).count(),
            1,
        )
        mocked_send_mail.assert_called_once()

    @patch('notifications.services.send_mail', return_value=1)
    def test_completed_booking_does_not_receive_upcoming_reminder(self, mocked_send_mail):
        """
        Завершенное бронирование не получает upcoming reminder.
        """
        booking = self._create_due_booking()
        booking.start_time = timezone.now() - timedelta(hours=2)
        booking.end_time = timezone.now() - timedelta(hours=1)
        booking.save(update_fields=['start_time', 'end_time', 'updated_at'])
        booking.complete_booking(self.employee_a.user)

        result = send_upcoming_booking_reminders_task()

        self.assertEqual(result['sent_count'], 0)
        self.assertFalse(
            Notification.objects.filter(
                user=booking.user,
                notification_type='reminder',
                data__booking_id=booking.id,
                data__reminder_type='upcoming_booking',
            ).exists()
        )
        mocked_send_mail.assert_not_called()

    @patch('notifications.services.send_mail', return_value=1)
    def test_email_disabled_prevents_upcoming_reminder(self, mocked_send_mail):
        """
        Если email reminder выключен в preference, письмо не отправляется.
        """
        booking = self._create_due_booking()
        reminder_type, _ = NotificationType.objects.update_or_create(
            code='reminder',
            defaults={
                'name': 'Reminder',
                'name_en': 'Reminder',
                'description': 'Generic reminder notifications',
                'description_en': 'Generic reminder notifications',
                'is_active': True,
                'default_enabled': True,
                'is_required': False,
            },
        )
        NotificationPreference.objects.create(
            user=self.owner,
            notification_type=reminder_type,
            email_enabled=False,
            push_enabled=True,
            in_app_enabled=True,
        )

        result = send_upcoming_booking_reminders_task()

        self.assertEqual(result['sent_count'], 0)
        self.assertFalse(
            Notification.objects.filter(
                user=booking.user,
                notification_type='reminder',
                data__booking_id=booking.id,
                data__reminder_type='upcoming_booking',
            ).exists()
        )
        mocked_send_mail.assert_not_called()


class ReminderSettingsViewSetTests(BookingFlowBaseMixin, APITestCase):
    """
    Тесты API настроек reminder.
    """

    def setUp(self):
        super().setUp()
        self.factory = APIRequestFactory()

    def test_current_action_works_without_notification_settings(self):
        """
        Endpoint current не падает, даже если NOTIFICATION_SETTINGS отсутствует в settings.
        """
        view = ReminderSettingsViewSet.as_view({'get': 'current'})
        request = self.factory.get('/api/v1/notifications/reminder-settings/current/')
        force_authenticate(request, user=self.owner)

        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['reminder_time_before_booking'], 120)
        self.assertTrue(ReminderSettings.objects.filter(user=self.owner).exists())


class UpcomingBookingReminderSetupCommandTests(BookingFlowBaseMixin, TestCase):
    """
    Тесты data setup для reminder MVP.
    """

    def test_setup_command_is_idempotent(self):
        """
        Команда setup не плодит дубли NotificationType и ReminderSettings.
        """
        self._create_booking(
            pet=self.pet_one,
            location=self.location_a,
            employee=self.employee_a,
            start_time=timezone.now() + timedelta(hours=2),
        )

        call_command('setup_upcoming_booking_reminders')
        call_command('setup_upcoming_booking_reminders')

        self.assertEqual(NotificationType.objects.filter(code='reminder').count(), 1)
        self.assertEqual(ReminderSettings.objects.filter(user=self.owner).count(), 1)
