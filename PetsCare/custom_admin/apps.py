from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class CustomAdminConfig(AppConfig):
    """
    Конфигурация приложения для кастомного админа.
    Используется для регистрации приложения в проекте.
    """
    name = 'custom_admin'
    verbose_name = _('Custom Admin')

    def ready(self):
        """
        Регистрирует стандартные модели админки после загрузки всех приложений.
        """
        from .admin import register_admin_models
        register_admin_models() 