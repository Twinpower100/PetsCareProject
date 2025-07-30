from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SecurityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'security'
    verbose_name = _('Security')

    def ready(self):
        """Инициализация приложения"""
        try:
            # Импортировать сигналы
            import security.signals
        except ImportError:
            pass
