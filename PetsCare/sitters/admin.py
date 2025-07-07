"""
Административный интерфейс для модуля передержки питомцев.
"""

from django.contrib import admin
from .models import SitterProfile
from custom_admin import custom_admin_site


class SitterProfileAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для профиля передержки.
    
    Особенности:
    - Отображение основных полей
    - Фильтрация по статусу
    - Поиск по пользователю
    """
    list_display = [
        'user',
        'is_verified',
        'experience_years',
        'max_pets',
        'compensation_type',
        'created_at'
    ]
    list_filter = [
        'is_verified',
        'compensation_type',
        'created_at'
    ]
    search_fields = [
        'user__email',
        'user__first_name',
        'user__last_name',
        'description'
    ]
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['user']

custom_admin_site.register(SitterProfile, SitterProfileAdmin) 