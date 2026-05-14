"""
Конфигурация приложения системных настроек.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SystemSettingsConfig(AppConfig):
    """
    Конфигурация приложения системных настроек.
    """
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'system_settings'
    verbose_name = _('System Settings')
    
    def ready(self):
        """
        Инициализация приложения при запуске.
        """
        # Импортируем сигналы
        try:
            import system_settings.signals
        except ImportError:
            pass 
