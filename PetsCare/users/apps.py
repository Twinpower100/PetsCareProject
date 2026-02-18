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
    
    def ready(self):
        """Подключает сигналы приложения и настраивает админку для SocialApp."""
        # Проверяем, что Django полностью инициализирован
        from django.conf import settings
        if not settings.configured:
            return
        
        # Импортируем сигналы только после полной инициализации
        import users.signals
        
        # Настраиваем админку для SocialApp (только для суперпользователей)
        import users.admin_socialapp  # noqa