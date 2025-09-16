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
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_active')
    list_filter = ('user_types', 'is_active')
    search_fields = ('email', 'first_name', 'last_name', 'username', 'user_types__name')
    ordering = ('email',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'phone_number')}),
        (_('Permissions'), {'fields': ('user_types', 'is_active', 'is_staff', 'is_superuser')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'user_types'),
        }),
    )

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
            'description': _('List of permissions for this role. Use the format: app.action_model (e.g., users.add_user)')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
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
