"""
Administrative interface for the users module.

Этот модуль содержит настройки административного интерфейса для:
1. Управления пользователями
2. Настройки отображения и фильтрации
3. Кастомизации действий администратора

Основные классы:
- UserAdmin: Административный интерфейс для модели User
- CustomAdminSite: Кастомный сайт администрирования с разграничением прав
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, UserType, ProviderForm, ProviderAdmin
from custom_admin import custom_admin_site

class CustomUserAdmin(UserAdmin):
    """
    Кастомная админка для модели User.
    """
    list_display = ('username', 'email', 'first_name', 'last_name', 'phone_number', 'is_active')
    list_filter = ('user_types', 'is_active')
    search_fields = ('email', 'first_name', 'last_name', 'username', 'phone_number', 'user_types__name')
    ordering = ('email',)
    
    fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'phone_number')}),
        (_('Permissions'), {'fields': ('user_types', 'is_active', 'is_staff', 'is_superuser')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'first_name', 'last_name', 'phone_number', 'password1', 'password2', 'user_types'),
        }),
    )
    
    actions = ['safe_delete_user', 'clear_user_roles']
    
    def get_actions(self, request):
        """
        Убираем стандартное действие удаления, оставляем только наше кастомное.
        """
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
    
    def safe_delete_user(self, request, queryset):
        """
        Безопасное удаление пользователей с предварительной очисткой связей.
        """
        deleted_count = 0
        for user in queryset:
            try:
                # Очищаем все роли пользователя
                user.user_types.clear()
                # Удаляем пользователя
                user.delete()
                deleted_count += 1
            except Exception as e:
                self.message_user(request, _('Error deleting user %(username)s: %(error)s') % {'username': user.username, 'error': str(e)}, level='ERROR')
        
        if deleted_count > 0:
            self.message_user(request, _('Successfully deleted %(count)d users.') % {'count': deleted_count}, level='SUCCESS')
    
    safe_delete_user.short_description = _("Safely delete selected users")
    
    def clear_user_roles(self, request, queryset):
        """
        Очистить все роли у выбранных пользователей.
        """
        cleared_count = 0
        for user in queryset:
            user.user_types.clear()
            cleared_count += 1
        
        self.message_user(request, _('Roles cleared for %(count)d users.') % {'count': cleared_count}, level='SUCCESS')
    
    clear_user_roles.short_description = _("Clear roles for selected users")
    
    def delete_model(self, request, obj):
        """
        Кастомное удаление отдельного пользователя с очисткой связей.
        """
        try:
            # Очищаем все роли пользователя
            obj.user_types.clear()
            # Удаляем пользователя
            obj.delete()
            self.message_user(request, _('User %(username)s successfully deleted.') % {'username': obj.username}, level='SUCCESS')
        except Exception as e:
            self.message_user(request, _('Error deleting user %(username)s: %(error)s') % {'username': obj.username, 'error': str(e)}, level='ERROR')

    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к модулю пользователей.
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            user.is_system_admin() or
            user.is_billing_manager()
        )

class UserTypeAdmin(admin.ModelAdmin):
    """
    Админка для типов пользователей.
    """
    list_display = ('name', 'description', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'description', 'is_active')
        }),
        (_('Permissions'), {
            'fields': ('permissions',),
            'description': _('Select permissions for this role. You can choose from predefined sets or add custom permissions.')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Кастомизация полей формы"""
        if db_field.name == 'permissions':
            # Получаем все доступные разрешения
            from .permissions import PERMISSION_DESCRIPTIONS, ROLE_PERMISSION_SETS
            
            # Создаем выборы для предопределенных наборов
            choices = []
            
            # Добавляем предопределенные наборы
            for role_key, role_data in ROLE_PERMISSION_SETS.items():
                choices.append((
                    f"SET:{role_key}",
                    f"{role_data['name']} - {role_data['description']}"
                ))
            
            # Добавляем отдельные разрешения
            for perm, desc in PERMISSION_DESCRIPTIONS.items():
                choices.append((perm, f"{perm} - {desc}"))
            
            # Создаем поле с выбором
            from django import forms
            field = forms.MultipleChoiceField(
                choices=choices,
                widget=admin.widgets.FilteredSelectMultiple(
                    verbose_name=_('Permissions'),
                    is_stacked=False
                ),
                required=False
            )
            return field
            
        return super().formfield_for_dbfield(db_field, request, **kwargs)
    
    def get_permissions_display(self, obj):
        """Показывает разрешения с описаниями."""
        if not obj.permissions:
            return _('No permissions')
        
        from .permissions import get_permission_description
        descriptions = [get_permission_description(perm) for perm in obj.permissions[:5]]
        if len(obj.permissions) > 5:
            descriptions.append(f'... and {len(obj.permissions) - 5} more')
        return ', '.join(descriptions)
    get_permissions_display.short_description = _('Permissions')
    
    def save_model(self, request, obj, form, change):
        """Обработка сохранения модели"""
        # Обработка предопределенных наборов теперь в модели.clean()
        super().save_model(request, obj, form, change)
    
    class Media:
        js = ('admin/js/user_type_admin.js',)

    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к типам пользователей.
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return user.is_superuser or user.is_system_admin()

class ProviderFormAdmin(admin.ModelAdmin):
    """
    Админка для форм учреждений.
    """
    list_display = ('provider_name', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('provider_name', 'provider_address')
    readonly_fields = ('created_at', 'updated_at', 'approved_at')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'provider_name',
                'provider_address',
                'provider_phone',
            )
        }),
        (_('Documents'), {
            'fields': (
                'documents',
            ),
            'description': _('Documents are required only if the institution provides services that require licensing or certification')
        }),
        (_('Status'), {
            'fields': (
                'status',
                'created_at',
                'updated_at',
                'approved_at'
            )
        }),
    )
    
    def has_documents(self, obj):
        """Показывает, есть ли документы у учреждения."""
        return bool(obj.documents)
    has_documents.boolean = True
    has_documents.short_description = _('Has Documents')

    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к формам учреждений.
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            user.is_system_admin() or
            user.is_billing_manager()
        )

class ProviderAdministratorAdmin(admin.ModelAdmin):
    """
    Админка для администраторов учреждений.
    """
    list_display = ('user', 'provider', 'is_active', 'created_at')
    list_filter = ('provider', 'is_active')
    search_fields = ('user__email', 'provider__name')
    readonly_fields = ('created_at', 'updated_at')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if (request.user.is_authenticated and 
            hasattr(request.user, 'has_role') and 
            request.user.has_role('provider_admin')):
            return qs.filter(provider__in=request.user.get_managed_providers())
        return qs

    def has_add_permission(self, request):
        if not request.user.is_authenticated:
            return False
        return hasattr(request.user, 'has_role') and request.user.has_role('system_admin')

    def has_change_permission(self, request, obj=None):
        if not request.user.is_authenticated:
            return False
        if not obj:
            return True
        if hasattr(request.user, 'has_role') and request.user.has_role('provider_admin'):
            return obj.provider in request.user.get_managed_providers()
        return hasattr(request.user, 'has_role') and request.user.has_role('system_admin')

    def has_delete_permission(self, request, obj=None):
        if not request.user.is_authenticated:
            return False
        return hasattr(request.user, 'has_role') and request.user.has_role('system_admin')

    def has_module_permission(self, request):
        if not request.user.is_authenticated:
            return False
        return (hasattr(request.user, 'has_role') and 
                (request.user.has_role('system_admin') or request.user.has_role('provider_admin')))

custom_admin_site.register(User, CustomUserAdmin)
custom_admin_site.register(UserType, UserTypeAdmin)
custom_admin_site.register(ProviderForm, ProviderFormAdmin)
custom_admin_site.register(ProviderAdmin, ProviderAdministratorAdmin)
