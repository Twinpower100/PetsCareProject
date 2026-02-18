"""
Административный интерфейс для приложения catalog.

Этот модуль содержит настройки административного интерфейса для:
1. Услуг и категорий услуг
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db import transaction
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
    list_display = ['get_tree_name', 'get_full_path', 'code', 'parent', 'level', 'hierarchy_order', 'is_active', 'is_client_facing', 'is_mandatory', 'is_periodic', 'requires_license', 'get_allowed_pet_types']
    list_filter = ['level', 'is_active', 'is_client_facing', 'is_mandatory', 'is_periodic', 'requires_license', 'allowed_pet_types']
    search_fields = ['code', 'name', 'name_en', 'name_ru', 'name_me', 'name_de', 'description', 'description_en', 'description_ru', 'description_me', 'description_de']
    ordering = ['hierarchy_order', 'name']
    readonly_fields = ['level', 'hierarchy_order', 'version']
    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'code',
                'name',
                'name_en',
                'name_ru',
                'name_me',
                'name_de',
                'description',
                'description_en',
                'description_ru',
                'description_me',
                'description_de',
                'parent',
                'icon',
            )
        }),
        (_('Status'), {
            'fields': (
                'is_active',
                'is_client_facing',
                'is_mandatory',
                'is_periodic',
                'requires_license'
            ),
            'description': _('is_client_facing: if unchecked, this is a technical/internal service (e.g. cleaning) not bookable by clients.')
        }),
        (_('Pet Types'), {
            'fields': (
                'allowed_pet_types',
            ),
            'description': _('Select pet types this service is available for. Leave empty to make it available for all types.')
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
                'hierarchy_order',
                'version',
            ),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        """
        Оптимизированный запрос с предзагрузкой родительских категорий.
        Сортировка происходит автоматически по полю hierarchy_order.
        """
        return super().get_queryset(request).select_related('parent').prefetch_related('allowed_pet_types')
    
    @transaction.atomic
    def save_model(self, request, obj, form, change):
        """
        Переопределение сохранения модели с транзакционной защитой.
        """
        from django.core.exceptions import ValidationError
        
        try:
            # Блокируем запись для редактирования
            if change and obj.pk:
                try:
                    current = Service.objects.select_for_update().get(pk=obj.pk)
                    if current.version != obj.version:
                        raise ValidationError(_('Record was modified by another user. Please refresh and try again.'))
                except Service.DoesNotExist:
                    raise ValidationError(_('Record was deleted by another user.'))
            
            super().save_model(request, obj, form, change)
        except ValidationError as e:
            # Показываем ошибку пользователю
            from django.contrib import messages
            messages.error(request, str(e))
            return
    
    def get_tree_name(self, obj):
        """
        Отображает название услуги с отступами для древовидной структуры.
        """
        # Создаем отступы в зависимости от уровня
        indent = "&nbsp;&nbsp;&nbsp;&nbsp;" * obj.level
        
        # Добавляем иконку в зависимости от уровня
        if obj.level == 0:
            icon = "📁"  # Папка для корневых категорий
        elif obj.children.exists():
            icon = "📂"  # Папка для подкатегорий
        else:
            icon = "📄"  # Файл для услуг
        
        # Создаем ссылку на редактирование
        url = reverse('admin:catalog_service_change', args=[obj.pk])
        
        # Форматируем название с отступами и иконкой
        tree_name = f"{indent}{icon} {obj.name}"
        
        # Добавляем CSS класс для стилизации
        css_class = f"level-{obj.level}"
        
        # Определяем стили в зависимости от уровня
        if obj.level == 0:
            style = "text-decoration: none; font-weight: bold; color: #2c3e50; font-family: monospace;"
        elif obj.level == 1:
            style = "text-decoration: none; color: #34495e; font-family: monospace;"
        elif obj.level == 2:
            style = "text-decoration: none; color: #7f8c8d; font-family: monospace;"
        else:
            style = "text-decoration: none; color: #bdc3c7; font-family: monospace;"
        
        return format_html(
            '<a href="{}" class="{}" style="{}">{}</a>',
            url,
            css_class,
            style,
            mark_safe(tree_name)
        )
    get_tree_name.short_description = _('Name (Tree)')
    get_tree_name.admin_order_field = 'name'
    
    def get_full_path(self, obj):
        """
        Отображает полный путь к услуге в иерархии.
        """
        return obj.get_full_path()
    get_full_path.short_description = _('Full Path')
    get_full_path.admin_order_field = 'name'
    
    def get_allowed_pet_types(self, obj):
        """
        Отображает разрешенные типы животных для услуги.
        """
        if not obj.allowed_pet_types.exists():
            return _("All types")
        return ", ".join([pet_type.name for pet_type in obj.allowed_pet_types.all()])
    get_allowed_pet_types.short_description = _('Allowed Pet Types')
    
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
