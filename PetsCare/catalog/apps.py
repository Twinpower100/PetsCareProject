"""
Конфигурация приложения catalog.

Этот модуль содержит настройки приложения catalog:
1. Автоматическое поле по умолчанию
2. Имя приложения
3. Отображаемое имя
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CatalogConfig(AppConfig):
    """
    Конфигурация приложения catalog.
    
    Особенности:
    - Каталог услуг
    - Категории услуг
    - Поиск и фильтрация
    - Управление ценами
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'catalog'
    verbose_name = _('Service Catalog')
