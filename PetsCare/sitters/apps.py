"""
Конфигурация приложения sitters.

Этот модуль содержит настройки приложения sitters:
1. Автоматическое поле по умолчанию
2. Имя приложения
3. Отображаемое имя
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SittersConfig(AppConfig):
    """
    Конфигурация приложения sitters.
    
    Особенности:
    - Управление ситтерами
    - Профили ситтеров
    - Расписание работы
    - Отзывы и рейтинги
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sitters'
    verbose_name = _('Pet Sitters')
    
    def ready(self):
        """Подключает сигналы приложения."""
        import sitters.signals 