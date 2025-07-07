"""
Конфигурация приложения геолокации.

Этот модуль содержит настройки приложения geolocation:
1. Автоматическое поле по умолчанию
2. Имя приложения
3. Отображаемое имя
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class GeolocationConfig(AppConfig):
    """
    Конфигурация приложения геолокации.
    
    Особенности:
    - Регистрация сигналов
    - Настройка переводов
    - Инициализация сервисов
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'geolocation'
    verbose_name = _('Geolocation')
    
    def ready(self):
        """
        Инициализация приложения при запуске.
        
        Регистрирует сигналы и выполняет другие операции инициализации.
        """
        # Импортируем сигналы для их регистрации
        import geolocation.signals
        
        # Здесь можно добавить другие операции инициализации
        # например, создание периодических задач, инициализация кэша и т.д. 