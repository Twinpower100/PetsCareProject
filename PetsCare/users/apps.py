"""
Configuration for the users application.

Этот модуль содержит настройки приложения users:
1. Автоматическое поле по умолчанию
2. Имя приложения
3. Отображаемое имя
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    """
    Конфигурация приложения users.
    
    Особенности:
    - Управление пользователями
    - Аутентификация
    - Авторизация
    - Профили пользователей
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    verbose_name = _('Users')
