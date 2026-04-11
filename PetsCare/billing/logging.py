"""
Система логирования для операций блокировки учреждений.

Этот модуль содержит функции для логирования:
1. Создания блокировок
2. Снятия блокировок
3. Изменения региональных политик блокировок
4. Отправки уведомлений
"""

import logging

from django.utils.translation import gettext as _
from django.contrib.admin.models import LogEntry, CHANGE, ADDITION
from django.contrib.contenttypes.models import ContentType
from .models import RegionalBlockingPolicy, ProviderBlocking, BlockingNotification

# Создаем логгер для операций блокировки
blocking_logger = logging.getLogger('billing.blocking')


def log_blocking_created(blocking, created_by=None):
    """
    Логирует создание новой блокировки.

    Args:
        blocking: Объект ProviderBlocking
        created_by: Пользователь, создавший блокировку (если не автоматически)
    """
    message = (
        f"Blocking facility {blocking.provider.name} created. "
        f"Debt: {blocking.debt_amount} {blocking.currency.code}, "
        f"Overdue: {blocking.overdue_days} days"
    )

    # Логируем в файл
    blocking_logger.info(message)

    # Логируем в админку Django
    content_type = ContentType.objects.get_for_model(ProviderBlocking)
    LogEntry.objects.log_action(
        user_id=created_by.id if created_by else None,  # type: ignore[arg-type]
        content_type_id=content_type.id,
        object_id=blocking.id,
        object_repr=f"Blocking {blocking.provider.name}",
        action_flag=ADDITION,
        change_message=message
    )


def log_blocking_resolved(blocking, resolved_by, notes=''):
    """
    Логирует снятие блокировки.

    Args:
        blocking: Объект ProviderBlocking
        resolved_by: Пользователь, снявший блокировку
        notes: Примечания к снятию блокировки
    """
    message = (
        f"Provider blocking {blocking.provider.name} resolved. "
        f"Resolved by: {resolved_by.get_full_name() if resolved_by else 'System'}"
    )
    if notes:
        message += f", Notes: {notes}"

    # Логируем в файл
    blocking_logger.info(message)

    # Логируем в админку Django
    content_type = ContentType.objects.get_for_model(ProviderBlocking)
    LogEntry.objects.log_action(
        user_id=resolved_by.id if resolved_by else None,  # type: ignore[arg-type]
        content_type_id=content_type.id,
        object_id=blocking.id,
        object_repr=f"Blocking {blocking.provider.name}",
        action_flag=CHANGE,
        change_message=message
    )


def log_regional_blocking_policy_created(policy, created_by):
    """Логирует создание региональной политики блокировок."""
    message = (
        f'Regional blocking policy "{policy.region_code}" created. '
        f"Tolerance: {policy.tolerance_amount} {policy.currency.code}, "
        f"L2 from {policy.overdue_days_l2_from} d, L3 from {policy.overdue_days_l3_from} d"
    )

    blocking_logger.info(message)

    content_type = ContentType.objects.get_for_model(RegionalBlockingPolicy)
    LogEntry.objects.log_action(
        user_id=created_by.id,
        content_type_id=content_type.id,
        object_id=policy.id,
        object_repr=f"Policy {policy.region_code}",
        action_flag=ADDITION,
        change_message=message
    )


def log_regional_blocking_policy_updated(policy, updated_by, changes):
    """Логирует изменение региональной политики блокировок."""
    changes_text = ', '.join([f'{k}: {v}' for k, v in changes.items()])
    message = f'Regional blocking policy "{policy.region_code}" changed. Changes: {changes_text}'

    blocking_logger.info(message)

    content_type = ContentType.objects.get_for_model(RegionalBlockingPolicy)
    LogEntry.objects.log_action(
        user_id=updated_by.id,
        content_type_id=content_type.id,
        object_id=policy.id,
        object_repr=f"Policy {policy.region_code}",
        action_flag=CHANGE,
        change_message=message
    )


# Обратная совместимость имён
log_blocking_rule_created = log_regional_blocking_policy_created
log_blocking_rule_updated = log_regional_blocking_policy_updated


def log_notification_sent(notification):
    """
    Логирует отправку уведомления о блокировке.

    Args:
        notification: Объект BlockingNotification
    """
    message = (
        f"Notification sent. Facility: {notification.provider_blocking.provider.name}, "
        f"Type: {notification.get_notification_type_display()}, "
        f"Recipient: {notification.recipient_email or notification.recipient_phone}"
    )

    # Логируем в файл
    blocking_logger.info(message)


def log_notification_failed(notification, error_message):
    """
    Логирует неудачную отправку уведомления.

    Args:
        notification: Объект BlockingNotification
        error_message: Сообщение об ошибке
    """
    message = _(  # Мультиязычное сообщение для логирования
        'Notification sending failed. Facility: %(provider)s, Error: %(error)s'
    ) % {
        'provider': notification.provider_blocking.provider.name,
        'error': error_message
    }

    # Логируем в файл
    blocking_logger.error(message)


def log_automatic_check_started():
    """
    Логирует начало автоматической проверки блокировок.
    """
    message = _('Started automatic provider blocking check')
    blocking_logger.info(message)


def log_automatic_check_completed(blocked_count, resolved_count):
    """
    Логирует завершение автоматической проверки блокировок.

    Args:
        blocked_count: Количество заблокированных учреждений
        resolved_count: Количество разблокированных учреждений
    """
    message = _('Automatic provider blocking check completed. Blocked: %(blocked)d, Resolved: %(resolved)d') % {
        'blocked': blocked_count,
        'resolved': resolved_count
    }
    blocking_logger.info(message)
