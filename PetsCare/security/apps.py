from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SecurityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'security'
    verbose_name = _('Security')

    def ready(self):
        """Инициализация приложения"""
        try:
            # Ленивый импорт сигналов - только если БД готова
            from django.db import connection
            if connection.introspection.table_names():
                import security.signals
        except (ImportError, Exception):
            # Если БД еще не готова или есть другие ошибки, пропускаем
            pass
