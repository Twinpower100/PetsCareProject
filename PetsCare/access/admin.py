"""
Конфигурация административного интерфейса для приложения access.

Этот модуль содержит настройки для:
1. Управления доступом к карточкам питомцев
2. Просмотра логов доступа
"""

from django.contrib import admin
from .models import PetAccess, AccessLog
from custom_admin import custom_admin_site


class PetAccessAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для управления доступом к карточкам питомцев.
    
    Особенности:
    - Фильтрация по статусу и датам
    - Поиск по питомцу и пользователям
    - Защита важных полей от изменения
    """
    list_display = ('pet', 'granted_to', 'granted_by', 'created_at', 'expires_at', 'is_active')
    list_filter = ('is_active', 'created_at', 'expires_at')
    search_fields = ('pet__name', 'granted_to__email', 'granted_by__email')
    readonly_fields = ('token', 'created_at')
    date_hierarchy = 'created_at'


class AccessLogAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для просмотра логов доступа.
    
    Особенности:
    - Фильтрация по действиям и времени
    - Поиск по питомцу и пользователю
    - Защита от изменений
    """
    list_display = ('access', 'user', 'action', 'timestamp')
    list_filter = ('action', 'timestamp')
    search_fields = ('access__pet__name', 'user__email')
    readonly_fields = ('timestamp',)
    date_hierarchy = 'timestamp'


custom_admin_site.register(PetAccess, PetAccessAdmin)
custom_admin_site.register(AccessLog, AccessLogAdmin) 