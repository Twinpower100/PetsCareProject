"""
MVP-сервис для email-напоминаний о предстоящих бронированиях.

Этот модуль собирает в одном месте:
1. безопасные значения по умолчанию для ReminderSettings;
2. логику отбора будущих active-бронирований;
3. идемпотентную отправку email reminder без full-blown rule engine.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from booking.constants import BOOKING_STATUS_ACTIVE
from booking.models import Booking
from notifications.models import Notification, NotificationPreference, ReminderSettings
from notifications.services import NotificationService

logger = logging.getLogger(__name__)

DEFAULT_REMINDER_TIME_MINUTES = 120
DEFAULT_MULTIPLE_REMINDERS = False
DEFAULT_REMINDER_WINDOW_MINUTES = 15
MAX_REMINDER_LOOKAHEAD_MINUTES = 7 * 24 * 60


def get_upcoming_booking_reminder_defaults() -> dict[str, Any]:
    """
    Возвращает безопасные дефолты reminder settings.

    Логика не зависит от наличия settings.NOTIFICATION_SETTINGS и умеет
    работать даже если этот объект отсутствует в settings.py.
    """
    raw_settings = getattr(settings, 'NOTIFICATION_SETTINGS', None) or {}

    reminder_time_before_booking = int(
        raw_settings.get('DEFAULT_REMINDER_TIME_MINUTES', DEFAULT_REMINDER_TIME_MINUTES)
    )
    multiple_reminders = bool(
        raw_settings.get('MULTIPLE_REMINDERS_ENABLED', DEFAULT_MULTIPLE_REMINDERS)
    )
    configured_intervals = raw_settings.get('DEFAULT_REMINDER_INTERVALS', [])

    reminder_intervals = _normalize_reminder_intervals(
        configured_intervals,
        primary_interval=reminder_time_before_booking,
        multiple_reminders=multiple_reminders,
    )

    return {
        'reminder_time_before_booking': reminder_time_before_booking,
        'multiple_reminders': multiple_reminders,
        'reminder_intervals': reminder_intervals,
        'is_active': True,
    }


def get_or_create_upcoming_booking_reminder_settings(user) -> ReminderSettings:
    """
    Возвращает настройки reminder для пользователя или создает их по дефолту.
    """
    defaults = get_upcoming_booking_reminder_defaults()
    reminder_settings, _ = ReminderSettings.objects.get_or_create(
        user=user,
        defaults=defaults,
    )
    return reminder_settings


class UpcomingBookingReminderService:
    """
    MVP-сервис отправки email reminder по будущим active-бронированиям.
    """

    reminder_window = timedelta(minutes=DEFAULT_REMINDER_WINDOW_MINUTES)
    max_lookahead = timedelta(minutes=MAX_REMINDER_LOOKAHEAD_MINUTES)

    def send_due_reminders(self, reference_time=None) -> dict[str, int]:
        """
        Обходит кандидатов и отправляет все due reminder на момент запуска.
        """
        reference_time = reference_time or timezone.now()
        booking_ids = list(
            Booking.objects.filter(
                start_time__gt=reference_time,
                start_time__lte=reference_time + self.max_lookahead,
                status__name=BOOKING_STATUS_ACTIVE,
            ).values_list('id', flat=True)
        )

        processed_count = 0
        sent_count = 0

        for booking_id in booking_ids:
            processed_count += 1
            sent_count += self.send_due_reminders_for_booking(
                booking_id=booking_id,
                reference_time=reference_time,
            )

        return {
            'processed_count': processed_count,
            'sent_count': sent_count,
        }

    def send_due_reminders_for_booking(self, booking_id: int, reference_time=None) -> int:
        """
        Отправляет все due reminder для одного бронирования.
        """
        reference_time = reference_time or timezone.now()
        notification_ids_to_deliver: list[int] = []

        with transaction.atomic():
            booking = (
                Booking.objects.select_for_update()
                .select_related('status', 'user', 'pet', 'service')
                .filter(id=booking_id)
                .first()
            )

            if booking is None:
                logger.info("Booking %s was not found for upcoming reminder", booking_id)
                return 0

            if booking.status.name != BOOKING_STATUS_ACTIVE:
                logger.info(
                    "Booking %s is no longer active, skipping upcoming reminder",
                    booking_id,
                )
                return 0

            if booking.start_time <= reference_time:
                logger.info(
                    "Booking %s has already started, skipping upcoming reminder",
                    booking_id,
                )
                return 0

            reminder_settings = self._get_or_create_locked_reminder_settings(booking.user)
            if not reminder_settings.is_active:
                logger.info(
                    "Upcoming booking reminders are disabled for user %s",
                    booking.user_id,
                )
                return 0

            if not self._is_email_channel_enabled(booking.user):
                logger.info(
                    "Reminder email channel is disabled for user %s",
                    booking.user_id,
                )
                return 0

            due_offsets = self._get_due_offsets(
                reminder_settings=reminder_settings,
                booking_start_time=booking.start_time,
                reference_time=reference_time,
            )
            if not due_offsets:
                return 0

            for offset_minutes in due_offsets:
                reminder_time = booking.start_time - timedelta(minutes=offset_minutes)
                notification = self._get_existing_notification(
                    booking=booking,
                    offset_minutes=offset_minutes,
                )

                if notification is None:
                    notification = Notification.objects.create(
                        user=booking.user,
                        pet=booking.pet,
                        notification_type='reminder',
                        title=_('Upcoming Booking Reminder'),
                        message=self._build_message(
                            booking=booking,
                            reference_time=reference_time,
                        ),
                        priority='medium',
                        channel='email',
                        scheduled_for=reminder_time,
                        data={
                            'booking_id': booking.id,
                            'service_name': booking.service.name,
                            'provider_name': getattr(booking.provider, 'name', ''),
                            'provider_location_name': getattr(booking.provider_location, 'name', ''),
                            'start_time': booking.start_time.isoformat(),
                            'reminder_type': 'upcoming_booking',
                            'reminder_offset_minutes': offset_minutes,
                            'reminder_due_at': reminder_time.isoformat(),
                        },
                    )

                if notification.sent_at is None:
                    notification_ids_to_deliver.append(notification.id)

        for notification_id in notification_ids_to_deliver:
            self._deliver_notification(notification_id)

        return len(notification_ids_to_deliver)

    def get_next_reminder_time_for_booking(self, booking_id: int):
        """
        Возвращает следующее planned reminder time для совместимости старых entry points.
        """
        booking = (
            Booking.objects.select_related('status', 'user')
            .filter(id=booking_id, status__name=BOOKING_STATUS_ACTIVE)
            .first()
        )
        if booking is None:
            return None

        reminder_settings = get_or_create_upcoming_booking_reminder_settings(booking.user)
        return reminder_settings.get_next_reminder_time(booking.start_time)

    def _get_or_create_locked_reminder_settings(self, user) -> ReminderSettings:
        """
        Получает settings с блокировкой строки для защиты от гонки.
        """
        reminder_settings = ReminderSettings.objects.select_for_update().filter(user=user).first()
        if reminder_settings is not None:
            return reminder_settings

        defaults = get_upcoming_booking_reminder_defaults()
        try:
            return ReminderSettings.objects.create(user=user, **defaults)
        except IntegrityError:
            return ReminderSettings.objects.select_for_update().get(user=user)

    def _get_due_offsets(
        self,
        *,
        reminder_settings: ReminderSettings,
        booking_start_time,
        reference_time,
    ) -> list[int]:
        """
        Вычисляет интервалы, которые попали в текущее reminder window.
        """
        due_offsets: list[int] = []

        for offset_minutes in reminder_settings.get_reminder_intervals():
            reminder_time = booking_start_time - timedelta(minutes=offset_minutes)
            if reminder_time <= reference_time <= reminder_time + self.reminder_window:
                due_offsets.append(offset_minutes)

        return sorted(due_offsets, reverse=True)

    def _get_existing_notification(self, *, booking: Booking, offset_minutes: int):
        """
        Ищет уже созданное reminder-уведомление для этого booking и интервала.
        """
        return Notification.objects.filter(
            user=booking.user,
            notification_type='reminder',
            data__booking_id=booking.id,
            data__reminder_type='upcoming_booking',
            data__reminder_offset_minutes=offset_minutes,
        ).order_by('-created_at').first()

    def _is_email_channel_enabled(self, user) -> bool:
        """
        Проверяет, разрешен ли email-канал для reminder.

        Для MVP действует простое правило:
        - если отдельной preference нет, email reminder считаем включенным;
        - если preference есть и email выключен, reminder не отправляем.
        """
        preference = (
            NotificationPreference.objects.filter(
                user=user,
                notification_type__code='reminder',
            )
            .order_by('-updated_at', '-id')
            .first()
        )
        if preference is None:
            return True
        return preference.email_enabled

    def _deliver_notification(self, notification_id: int) -> None:
        """
        Отправляет уже созданное уведомление по email, если оно еще не отправлено.
        """
        notification = Notification.objects.select_related('user').filter(id=notification_id).first()
        if notification is None or notification.sent_at is not None:
            return

        NotificationService()._send_notification(notification, ['email'])

    def _build_message(self, *, booking: Booking, reference_time) -> str:
        """
        Формирует текст email reminder.
        """
        provider_name = (
            getattr(booking.provider_location, 'name', None)
            or getattr(booking.provider, 'name', None)
            or _('your provider')
        )
        return _(
            'Your booking for %(service)s at %(provider)s starts in %(time)s.'
        ) % {
            'service': booking.service.name,
            'provider': provider_name,
            'time': self._format_time_until_booking(
                booking_start_time=booking.start_time,
                reference_time=reference_time,
            ),
        }

    def _format_time_until_booking(self, *, booking_start_time, reference_time) -> str:
        """
        Возвращает человекочитаемый интервал до начала бронирования.
        """
        total_minutes = max(
            int((booking_start_time - reference_time).total_seconds() // 60),
            0,
        )

        if total_minutes >= 24 * 60:
            day_count = max(total_minutes // (24 * 60), 1)
            return ngettext(
                '%(count)d day',
                '%(count)d days',
                day_count,
            ) % {'count': day_count}

        if total_minutes >= 60:
            hour_count = max(total_minutes // 60, 1)
            return ngettext(
                '%(count)d hour',
                '%(count)d hours',
                hour_count,
            ) % {'count': hour_count}

        minute_count = max(total_minutes, 1)
        return ngettext(
            '%(count)d minute',
            '%(count)d minutes',
            minute_count,
        ) % {'count': minute_count}


def _normalize_reminder_intervals(
    configured_intervals,
    *,
    primary_interval: int,
    multiple_reminders: bool,
) -> list[int]:
    """
    Нормализует reminder intervals из settings.
    """
    if not multiple_reminders:
        return []

    normalized: list[int] = []
    for raw_value in configured_intervals or []:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        if value > 0:
            normalized.append(value)

    if primary_interval > 0:
        normalized.append(primary_interval)

    return sorted(set(normalized), reverse=True)
