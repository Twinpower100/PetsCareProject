"""
Конфигурация приложения ratings.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RatingsConfig(AppConfig):
    """
    Конфигурация приложения системы рейтингов и жалоб.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ratings'
    verbose_name = _('Ratings and Complaints')
    
    def ready(self):
        """
        Инициализация приложения при запуске.
        """
        # Проверяем, что Django полностью инициализирован
        from django.conf import settings
        if not settings.configured:
            return
            
        import ratings.signals 