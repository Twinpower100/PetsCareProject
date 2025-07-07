"""
Конфигурация приложения access.

Этот модуль содержит настройки приложения access:
1. Автоматическое поле по умолчанию
2. Имя приложения
3. Отображаемое имя
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccessConfig(AppConfig):
    """
    Конфигурация приложения access.
    
    Особенности:
    - Управление правами доступа
    - Разграничение ролей
    - Контроль доступа к данным
    - Аудит действий
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'access'
    verbose_name = _('Access Control') 