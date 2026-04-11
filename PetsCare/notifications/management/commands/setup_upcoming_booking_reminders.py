"""
Команда подготовки MVP-данных для reminder о предстоящих бронированиях.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from booking.constants import BOOKING_STATUS_ACTIVE
from booking.models import Booking
from notifications.models import NotificationType, ReminderSettings
from notifications.upcoming_booking_reminders import get_upcoming_booking_reminder_defaults


class Command(BaseCommand):
    """
    Идемпотентно подготавливает минимальные notification-данные для upcoming reminders.
    """

    help = 'Create minimal data required for upcoming booking reminder MVP'

    @transaction.atomic
    def handle(self, *args, **options):
        """
        Выполняет подготовку notification data для reminder MVP.
        """
        notification_type, created_notification_type = NotificationType.objects.update_or_create(
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

        defaults = get_upcoming_booking_reminder_defaults()
        owner_user_ids = list(
            Booking.objects.filter(
                status__name=BOOKING_STATUS_ACTIVE,
                start_time__gt=timezone.now(),
            )
            .values_list('user_id', flat=True)
            .distinct()
        )

        created_settings_count = 0
        for user_id in owner_user_ids:
            _, created = ReminderSettings.objects.get_or_create(
                user_id=user_id,
                defaults=defaults,
            )
            if created:
                created_settings_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                'Upcoming booking reminder MVP data is ready: '
                f'notification_type_id={notification_type.id}, '
                f'notification_type_created={created_notification_type}, '
                f'users_with_future_active_bookings={len(owner_user_ids)}, '
                f'reminder_settings_created={created_settings_count}'
            )
        )
