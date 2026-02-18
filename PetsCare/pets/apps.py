"""
Конфигурация приложения pets.

Этот модуль содержит настройки приложения pets:
1. Автоматическое поле по умолчанию
2. Имя приложения
3. Отображаемое имя
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PetsConfig(AppConfig):
    """
    Конфигурация приложения pets.
    
    Особенности:
    - Управление питомцами
    - Медицинские карты
    - История обслуживания
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pets'
    verbose_name = _('Pets')
    
    def ready(self):
        """Подключает сигналы приложения."""
        # Проверяем, что Django полностью инициализирован
        from django.conf import settings
        if not settings.configured:
            return
            
        import pets.signals