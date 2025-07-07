"""
Инициализация приложения кастомного админа.
Указывает Django использовать CustomAdminConfig как конфигурацию приложения.
"""
from .admin import custom_admin_site

__all__ = ['custom_admin_site']

default_app_config = 'custom_admin.apps.CustomAdminConfig' 