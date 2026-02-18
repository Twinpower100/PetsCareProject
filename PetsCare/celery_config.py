"""
Конфигурация Celery для проекта PetsCare.

Этот модуль содержит настройки Celery для:
1. Асинхронных задач
2. Периодических задач
3. Мониторинга задач
"""

from __future__ import absolute_import, unicode_literals
import os
import logging
from celery import Celery
from django.conf import settings
from celery.schedules import crontab

logger = logging.getLogger(__name__)

# Установка переменной окружения для настроек проекта
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PetsCare.settings')

app = Celery('PetsCare')

# Загрузка настроек из Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Автоматическое обнаружение и регистрация задач из приложений
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# Настройка периодических задач
app.conf.beat_schedule = {
    'update-currency-rates': {
        'task': 'billing.tasks.update_currency_rates',
        'schedule': crontab(hour=0, minute=0),  # Ежедневно в полночь
    },
    'activate-pending-offers': {
        'task': 'billing.tasks.activate_pending_offers',
        'schedule': crontab(hour=0, minute=0),  # Ежедневно в полночь (проверка оферт с effective_date = сегодня)
    },
}

@app.task(bind=True)
def debug_task(self):
    """Тестовая задача для проверки работы Celery"""
    logger.info(f'Request: {self.request!r}') 