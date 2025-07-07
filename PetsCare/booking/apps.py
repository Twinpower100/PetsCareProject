"""
Configuration for the booking application.

Этот модуль содержит настройки приложения booking:
1. Автоматическое поле по умолчанию
2. Имя приложения
3. Отображаемое имя
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BookingConfig(AppConfig):
    """
    Конфигурация приложения booking.
    
    Особенности:
    - Управление бронированиями
    - Расписание услуг
    - Подтверждение записей
    - Уведомления
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'booking'
    verbose_name = _('Booking')
