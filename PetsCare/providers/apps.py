"""
Конфигурация приложения providers.

Этот модуль содержит настройки приложения providers:
1. Автоматическое поле по умолчанию
2. Имя приложения
3. Отображаемое имя
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ProvidersConfig(AppConfig):
    """
    Конфигурация приложения providers.
    
    Особенности:
    - Управление поставщиками услуг
    - Профили организаций
    - Расписание работы
    - Управление услугами
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'providers'
    verbose_name = _('Service Providers')
