"""
Система логирования для операций блокировки учреждений.

Этот модуль содержит функции для логирования:
1. Создания блокировок
2. Снятия блокировок
3. Изменения правил блокировки
4. Отправки уведомлений
"""

import logging
from django.utils import timezone
from django.utils.translation import gettext as _
from django.contrib.admin.models import LogEntry, CHANGE, ADDITION, DELETION
from django.contrib.contenttypes.models import ContentType
from .models import BlockingRule, ProviderBlocking, BlockingNotification

# Создаем логгер для операций блокировки
blocking_logger = logging.getLogger('billing.blocking')


def log_blocking_created(blocking, created_by=None):
    """
    Логирует создание новой блокировки.
    
    Args:
        blocking: Объект ProviderBlocking
        created_by: Пользователь, создавший блокировку (если не автоматически)
    """
    message = _(  # Мультиязычное сообщение для логирования
        'Blocking facility %(provider)s created. Debt: %(debt)s %(currency)s, Overdue: %(days)s days'
    ) % {
        'provider': blocking.provider.name,
        'debt': blocking.debt_amount,
        'currency': blocking.currency.code,
        'days': blocking.overdue_days,
    }
    
    # Логируем в файл
    blocking_logger.info(message)
    
    # Логируем в админку Django
    content_type = ContentType.objects.get_for_model(ProviderBlocking)
    LogEntry.objects.log_action(
        user_id=created_by.id if created_by else None,
        content_type_id=content_type.id,
        object_id=blocking.id,
        object_repr=_('Blocking %(provider)s') % {'provider': blocking.provider.name},
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
    message = _('Provider blocking %(provider)s resolved. Resolved by: %(user)s') % {
        'provider': blocking.provider.name,
        'user': resolved_by.get_full_name() if resolved_by else 'System'
    }
    if notes:
        message += _(', Notes: %(notes)s') % {'notes': notes}
    
    # Логируем в файл
    blocking_logger.info(message)
    
    # Логируем в админку Django
    content_type = ContentType.objects.get_for_model(ProviderBlocking)
    LogEntry.objects.log_action(
        user_id=resolved_by.id,
        content_type_id=content_type.id,
        object_id=blocking.id,
        object_repr=_('Blocking %(provider)s') % {'provider': blocking.provider.name},
        action_flag=CHANGE,
        change_message=message
    )


def log_blocking_rule_created(rule, created_by):
    """
    Логирует создание нового правила блокировки.
    
    Args:
        rule: Объект BlockingRule
        created_by: Пользователь, создавший правило
    """
    message = _(  # Мультиязычное сообщение для логирования
        'Blocking rule "%(name)s" created. Debt threshold: %(debt)s, Overdue threshold: %(days)s days'
    ) % {
        'name': rule.name,
        'debt': rule.debt_amount_threshold,
        'days': rule.overdue_days_threshold,
    }
    
    # Логируем в файл
    blocking_logger.info(message)
    
    # Логируем в админку Django
    content_type = ContentType.objects.get_for_model(BlockingRule)
    LogEntry.objects.log_action(
        user_id=created_by.id,
        content_type_id=content_type.id,
        object_id=rule.id,
        object_repr=_('Rule %(name)s') % {'name': rule.name},
        action_flag=ADDITION,
        change_message=message
    )


def log_blocking_rule_updated(rule, updated_by, changes):
    """
    Логирует изменение правила блокировки.
    
    Args:
        rule: Объект BlockingRule
        updated_by: Пользователь, изменивший правило
        changes: Словарь с изменениями
    """
    changes_text = ', '.join([f'{k}: {v}' for k, v in changes.items()])
    message = _('Blocking rule "%(name)s" changed. Changes: %(changes)s') % {
        'name': rule.name,
        'changes': changes_text
    }
    
    # Логируем в файл
    blocking_logger.info(message)
    
    # Логируем в админку Django
    content_type = ContentType.objects.get_for_model(BlockingRule)
    LogEntry.objects.log_action(
        user_id=updated_by.id,
        content_type_id=content_type.id,
        object_id=rule.id,
        object_repr=_('Rule %(name)s') % {'name': rule.name},
        action_flag=CHANGE,
        change_message=message
    )


def log_notification_sent(notification):
    """
    Логирует отправку уведомления о блокировке.
    
    Args:
        notification: Объект BlockingNotification
    """
    message = _(  # Мультиязычное сообщение для логирования
        'Notification sent. Facility: %(provider)s, Type: %(type)s, Recipient: %(recipient)s'
    ) % {
        'provider': notification.provider_blocking.provider.name,
        'type': notification.get_notification_type_display(),
        'recipient': notification.recipient_email or notification.recipient_phone
    }
    
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


def log_mass_rule_applied(rule, applied_to_count, applied_to_type):
    """
    Логирует применение массового правила.
    
    Args:
        rule: Объект BlockingRule
        applied_to_count: Количество применений
        applied_to_type: Тип применения (регионы, типы услуг)
    """
    message = _('Mass rule "%(name)s" applied to %(count)d %(type)s') % {
        'name': rule.name,
        'count': applied_to_count,
        'type': 'providers' if applied_to_count != 1 else 'provider'
    }
    blocking_logger.info(message) 