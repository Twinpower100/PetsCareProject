"""
Административный интерфейс для приложения catalog.

Этот модуль содержит настройки административного интерфейса для:
1. Услуг и категорий услуг
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Service
from custom_admin import custom_admin_site


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для услуг и категорий услуг.
    
    Особенности:
    - Отображение основных полей в списке
    - Поиск по названию и описанию
    - Сортировка по названию
    - Группировка полей в форме
    - Автоматический уровень (level)
    - Исключение самой услуги из parent
    """
    list_display = ['code', 'name', 'parent', 'level', 'is_active', 'is_mandatory', 'is_periodic']
    list_filter = ['level', 'is_active', 'is_mandatory', 'is_periodic']
    search_fields = ['code', 'name', 'description']
    ordering = ['level', 'name']
    readonly_fields = ['level']
    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'code',
                'name',
                'description',
                'parent',
                'icon',
            )
        }),
        (_('Status'), {
            'fields': (
                'is_active',
                'is_mandatory',
                'is_periodic'
            )
        }),
        (_('Periodic Settings'), {
            'fields': (
                'period_days',
                'send_reminders',
                'reminder_days_before'
            ),
            'classes': ('collapse',)
        }),
        (_('Hierarchy'), {
            'fields': (
                'level',
            ),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        """
        Оптимизированный запрос с предзагрузкой родительских категорий.
        """
        return super().get_queryset(request).select_related('parent')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        В выпадающем списке parent не показываем саму услугу (при редактировании).
        """
        if db_field.name == "parent":
            if request.resolver_match and request.resolver_match.kwargs.get('object_id'):
                # Редактирование: исключаем саму услугу
                object_id = request.resolver_match.kwargs['object_id']
                kwargs["queryset"] = Service.objects.exclude(pk=object_id)
            else:
                kwargs["queryset"] = Service.objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


custom_admin_site.register(Service, ServiceAdmin)
