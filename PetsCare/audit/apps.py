from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'audit'
    verbose_name = _('Audit and Logging')
    
    def ready(self):
        """Инициализация приложения при запуске"""
        import audit.signals
