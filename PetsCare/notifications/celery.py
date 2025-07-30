from celery import shared_task
from celery.schedules import crontab
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


# Расписание для периодических задач
CELERY_BEAT_SCHEDULE = {
    # Ежедневная очистка старых уведомлений (в 2:00)
    'cleanup-old-notifications': {
        'task': 'notifications.tasks.cleanup_old_notifications_task',
        'schedule': crontab(hour=2, minute=0),
    },
    
    # Ежедневная отправка напоминаний о задолженности (в 9:00)
    'send-debt-reminders': {
        'task': 'notifications.tasks.send_debt_reminders_task',
        'schedule': crontab(hour=9, minute=0),
    },
    

    
    # Ежедневная проверка истечения инвайтов ролей (в 8:00)
    'check-role-invite-expiration': {
        'task': 'notifications.tasks.check_role_invite_expiration_task',
        'schedule': crontab(hour=8, minute=0),
    },
    
    # Ежедневная отправка статистики уведомлений администраторам (в 18:00)
    'send-notification-stats': {
        'task': 'notifications.tasks.send_notification_stats_task',
        'schedule': crontab(hour=18, minute=0),
    },
    
    # Еженедельная очистка неактивных push-токенов (по воскресеньям в 3:00)
    'cleanup-inactive-push-tokens': {
        'task': 'notifications.tasks.cleanup_inactive_push_tokens_task',
        'schedule': crontab(day_of_week=0, hour=3, minute=0),
    },
    
    # Проверка и отправка уведомлений о предстоящих бронированиях каждые 15 минут
    'send-upcoming-booking-reminders': {
        'task': 'notifications.tasks.send_upcoming_booking_reminders_task',
        'schedule': crontab(minute='*/15'),
    },
    

}


# Дополнительные задачи для разработки и тестирования
if settings.DEBUG:
    CELERY_BEAT_SCHEDULE.update({
        # Тестовая отправка уведомлений каждые 5 минут в режиме разработки
        'test-notifications-dev': {
            'task': 'notifications.tasks.send_test_notification_task',
            'schedule': crontab(minute='*/5'),
        },
    })


# Настройки для задач
CELERY_TASK_ROUTES = {
    'notifications.tasks.*': {'queue': 'notifications'},
}

CELERY_TASK_DEFAULT_QUEUE = 'notifications'

# Настройки повторных попыток для задач уведомлений
CELERY_TASK_ANNOTATIONS = {
    'notifications.tasks.send_email_notification_task': {
        'retry_backoff': True,
        'retry_backoff_max': 600,
        'max_retries': 3,
    },
    'notifications.tasks.send_push_notification_task': {
        'retry_backoff': True,
        'retry_backoff_max': 300,
        'max_retries': 2,
    },
    'notifications.tasks.send_in_app_notification_task': {
        'retry_backoff': True,
        'retry_backoff_max': 60,
        'max_retries': 1,
    },
} 