"""
Настройка админки для SocialApp (django-allauth).

Ограничивает доступ к SocialApp внутренним администраторам.
"""
from django.contrib import admin
from allauth.socialaccount.models import SocialApp, SocialAccount, SocialToken
from django.utils.translation import gettext_lazy as _


def _is_internal_admin(user):
    if getattr(user, 'is_superuser', False):
        return True
    has_role = getattr(user, 'has_role', None)
    return callable(has_role) and any(
        has_role(role)
        for role in ('system_admin', 'billing_manager')
    )


class SocialAppAdmin(admin.ModelAdmin):
    """
    Админка для SocialApp с ограничением доступа только для суперпользователей.
    
    SocialApp - это настройки OAuth приложений для входа через социальные сети (Google, Facebook и т.д.).
    Каждый SocialApp содержит Client ID и Secret для конкретного OAuth сервиса (например, Google).
    """
    list_display = ('name', 'oauth_provider', 'client_id_short', 'get_sites')
    list_filter = ('provider',)
    search_fields = ('name', 'client_id')
    readonly_fields = ()
    filter_horizontal = ('sites',)
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'provider', 'client_id', 'secret', 'key'),
            'description': _('OAuth application settings for social login (Google, Facebook, etc.)')
        }),
        (_('Sites'), {
            'fields': ('sites',),
            'description': _('Select sites where this OAuth app should be available')
        }),
    )
    
    def oauth_provider(self, obj):
        """Показывает OAuth провайдера (Google, Facebook и т.д.)."""
        return obj.provider
    oauth_provider.short_description = _('OAuth Service')
    oauth_provider.admin_order_field = 'provider'
    
    def get_form(self, request, obj=None, **kwargs):
        """Переопределяем форму, чтобы изменить label поля 'provider'."""
        form = super().get_form(request, obj, **kwargs)
        # Переименовываем "Провайдер" на "OAuth сервис", чтобы не путать с провайдерами услуг
        if 'provider' in form.base_fields:
            form.base_fields['provider'].label = _('OAuth Service')
            form.base_fields['provider'].help_text = _('OAuth service provider (Google, Facebook, etc.)')
        return form
    
    def client_id_short(self, obj):
        """Показывает сокращенный Client ID для списка."""
        if obj.client_id:
            return f"{obj.client_id[:30]}..." if len(obj.client_id) > 30 else obj.client_id
        return '-'
    client_id_short.short_description = _('Client ID')
    
    def get_sites(self, obj):
        """Показывает список связанных Sites."""
        sites = obj.sites.all()
        if sites:
            return ', '.join([site.domain for site in sites])
        return _('No sites')
    get_sites.short_description = _('Sites')
    
    def has_module_permission(self, request):
        return _is_internal_admin(request.user)
    
    def has_view_permission(self, request, obj=None):
        return _is_internal_admin(request.user)
    
    def has_add_permission(self, request):
        return _is_internal_admin(request.user)
    
    def has_change_permission(self, request, obj=None):
        return _is_internal_admin(request.user)
    
    def has_delete_permission(self, request, obj=None):
        return _is_internal_admin(request.user)


class SocialTokenAdmin(admin.ModelAdmin):
    """
    Админка для SocialToken с ограничением доступа только для суперпользователей.
    """
    list_display = ('app', 'account', 'token_short', 'expires_at')
    list_filter = ('app', 'expires_at')
    search_fields = ('account__user__email', 'token')
    readonly_fields = ()
    
    def token_short(self, obj):
        """Показывает сокращенный токен для списка."""
        if obj.token:
            return f"{obj.token[:20]}..." if len(obj.token) > 20 else obj.token
        return '-'
    token_short.short_description = _('Token')
    
    def has_module_permission(self, request):
        """Только суперпользователь может видеть SocialToken."""
        return request.user.is_superuser
    
    def has_view_permission(self, request, obj=None):
        """Только суперпользователь может просматривать SocialToken."""
        return request.user.is_superuser
    
    def has_add_permission(self, request):
        """Только суперпользователь может создавать SocialToken."""
        return request.user.is_superuser
    
    def has_change_permission(self, request, obj=None):
        """Только суперпользователь может изменять SocialToken."""
        return request.user.is_superuser
    
    def has_delete_permission(self, request, obj=None):
        """Только суперпользователь может удалять SocialToken."""
        return request.user.is_superuser


# Отменяем регистрацию allauth в стандартной админке
# Это нужно, так как allauth уже зарегистрировал эти модели
try:
    admin.site.unregister(SocialApp)
    admin.site.unregister(SocialAccount)
    admin.site.unregister(SocialToken)
except admin.sites.NotRegistered:
    # Модели еще не зарегистрированы - это нормально
    pass

# Регистрируем в кастомной админке (custom_admin_site)
# Это нужно, так как проект использует custom_admin_site вместо стандартного admin.site
from custom_admin import custom_admin_site

# Отменяем регистрацию в custom_admin_site, если они там уже зарегистрированы
try:
    custom_admin_site.unregister(SocialApp)
    custom_admin_site.unregister(SocialAccount)
    custom_admin_site.unregister(SocialToken)
except admin.sites.NotRegistered:
    # Модели еще не зарегистрированы - это нормально
    pass

# Регистрируем наш кастомный админ с доступом для внутренних администраторов.
# В кастомной админке, которая используется в проекте
custom_admin_site.register(SocialApp, SocialAppAdmin)
# SocialAccount не регистрируем: фронтовый Google auth не пишет в эту таблицу.
# SocialToken не регистрируем: он содержит OAuth-токены.
# custom_admin_site.register(SocialToken, SocialTokenAdmin)

# Скрываем отдельный раздел Sites из админки.
# django.contrib.sites остается в проекте, потому что allauth хранит связи
# OAuth-приложений с Site, но публичные домены теперь управляются брендингом.
from django.contrib.sites.models import Site

# Отменяем регистрацию в стандартной админке, если она есть
try:
    admin.site.unregister(Site)
except admin.sites.NotRegistered:
    pass

# Регистрируем в custom_admin_site
try:
    custom_admin_site.unregister(Site)
except admin.sites.NotRegistered:
    pass

