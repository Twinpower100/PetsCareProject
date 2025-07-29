"""
Админский интерфейс для системных настроек.

Этот модуль содержит админские классы для:
1. Настроек безопасности
2. Глобальных системных настроек
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from django import forms

from .models import SecuritySettings


class SecuritySettingsForm(forms.ModelForm):
    """
    Форма для настроек безопасности с дополнительной валидацией.
    """
    
    class Meta:
        model = SecuritySettings
        fields = '__all__'
    
    def clean(self):
        """Дополнительная валидация настроек безопасности."""
        cleaned_data = super().clean()
        
        # Проверяем, что минимальная длина пароля не меньше 8
        password_min_length = cleaned_data.get('password_min_length')
        if password_min_length and password_min_length < 8:
            raise ValidationError({
                'password_min_length': _('Minimum password length cannot be less than 8 characters')
            })
        
        # Проверяем, что время жизни сессии не меньше 15 минут
        session_timeout = cleaned_data.get('session_timeout_minutes')
        if session_timeout and session_timeout < 15:
            raise ValidationError({
                'session_timeout_minutes': _('Session timeout cannot be less than 15 minutes')
            })
        
        # Проверяем, что время неактивности не больше времени жизни сессии
        inactivity_timeout = cleaned_data.get('session_inactivity_timeout_minutes')
        if session_timeout and inactivity_timeout and inactivity_timeout > session_timeout:
            raise ValidationError({
                'session_inactivity_timeout_minutes': _('Inactivity timeout cannot be greater than session timeout')
            })
        
        # Проверяем IP-адреса в whitelist/blacklist
        ip_whitelist = cleaned_data.get('ip_whitelist', [])
        ip_blacklist = cleaned_data.get('ip_blacklist', [])
        
        if not isinstance(ip_whitelist, list):
            raise ValidationError({
                'ip_whitelist': _('IP whitelist must be a list')
            })
        
        if not isinstance(ip_blacklist, list):
            raise ValidationError({
                'ip_blacklist': _('IP blacklist must be a list')
            })
        
        # Проверяем формат IP-адресов
        import re
        ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
        
        for ip in ip_whitelist:
            if not ip_pattern.match(ip):
                raise ValidationError({
                    'ip_whitelist': _('Invalid IP address format in whitelist: {}').format(ip)
                })
        
        for ip in ip_blacklist:
            if not ip_pattern.match(ip):
                raise ValidationError({
                    'ip_blacklist': _('Invalid IP address format in blacklist: {}').format(ip)
                })
        
        return cleaned_data


@admin.register(SecuritySettings)
class SecuritySettingsAdmin(admin.ModelAdmin):
    """
    Админский интерфейс для настроек безопасности.
    
    Особенности:
    - Группировка полей по категориям
    - Валидация настроек
    - Автоматическое логирование изменений
    - Удобный интерфейс с подсказками
    """
    
    form = SecuritySettingsForm
    
    # Отключаем возможность добавления/удаления (синглтон)
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    # Группировка полей
    fieldsets = (
        (_('Password Policy'), {
            'fields': (
                'password_min_length',
                'password_require_uppercase',
                'password_require_lowercase', 
                'password_require_numbers',
                'password_require_special_chars',
                'password_max_age_days',
                'password_history_count',
            ),
            'description': _('Configure password requirements and policies')
        }),
        
        (_('Session Management'), {
            'fields': (
                'session_timeout_minutes',
                'max_concurrent_sessions',
                'force_logout_on_password_change',
                'session_inactivity_timeout_minutes',
            ),
            'description': _('Configure session timeout and concurrent session limits')
        }),
        
        (_('Rate Limiting'), {
            'fields': (
                'rate_limiting_enabled',
                'login_attempts_per_hour',
                'api_requests_per_minute',
                'brute_force_lockout_minutes',
            ),
            'description': _('Configure rate limiting to prevent brute force attacks')
        }),
        
        (_('IP Restrictions'), {
            'fields': (
                'ip_restrictions_enabled',
                'ip_whitelist',
                'ip_blacklist',
            ),
            'description': _('Configure IP address restrictions (use with caution)')
        }),
        
        (_('Audit & Logging'), {
            'fields': (
                'audit_logging_enabled',
                'audit_log_retention_days',
                'log_sensitive_data',
                'log_failed_login_attempts',
            ),
            'description': _('Configure audit logging and data retention policies')
        }),
        
        (_('Security Headers'), {
            'fields': (
                'require_https',
                'enable_csrf_protection',
                'enable_xss_protection',
                'enable_content_security_policy',
            ),
            'description': _('Configure security headers and HTTPS requirements')
        }),
        
        (_('Metadata'), {
            'fields': (
                'created_at',
                'updated_at',
                'updated_by',
            ),
            'classes': ('collapse',),
            'description': _('System metadata and change tracking')
        }),
    )
    
    # Только для чтения поля
    readonly_fields = ('created_at', 'updated_at')
    
    # Фильтры и поиск (не нужны для синглтона)
    list_display = ('get_settings_summary', 'updated_at', 'updated_by')
    list_filter = ()
    search_fields = ()
    
    # Настройки страницы
    save_on_top = True
    change_form_template = 'admin/security_settings_change_form.html'
    
    def get_settings_summary(self, obj):
        """Возвращает краткое описание настроек для списка."""
        if not obj:
            return _('No settings configured')
        
        summary_parts = []
        
        # Политика паролей
        if obj.password_min_length > 8:
            summary_parts.append(f"Pass: {obj.password_min_length}+ chars")
        
        # Сессии
        if obj.max_concurrent_sessions < 5:
            summary_parts.append(f"Max {obj.max_concurrent_sessions} sessions")
        
        # Rate limiting
        if obj.rate_limiting_enabled:
            summary_parts.append(f"Rate limit: {obj.login_attempts_per_hour}/hour")
        
        # IP ограничения
        if obj.ip_restrictions_enabled:
            summary_parts.append("IP restrictions enabled")
        
        return " | ".join(summary_parts) if summary_parts else _('Default settings')
    
    get_settings_summary.short_description = _('Security Summary')
    
    def save_model(self, request, obj, form, change):
        """Переопределяем сохранение для логирования изменений."""
        if change:
            # Логируем изменения
            from audit.models import AuditLog
            
            AuditLog.objects.create(
                user=request.user,
                action='security_settings_updated',
                resource_type='system',
                resource_id=obj.pk,
                resource_name='Security Settings',
                details={
                    'changed_fields': list(form.changed_data),
                    'old_values': {field: form.initial.get(field) for field in form.changed_data},
                    'new_values': {field: form.cleaned_data.get(field) for field in form.changed_data}
                },
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
        
        # Устанавливаем пользователя, который внес изменения
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        """Возвращаем только одну запись (синглтон)."""
        return SecuritySettings.objects.filter(pk=1)
    
    def changelist_view(self, request, extra_context=None):
        """Перенаправляем на форму редактирования единственной записи."""
        from django.shortcuts import redirect
        from django.urls import reverse
        
        settings = SecuritySettings.get_settings()
        return redirect(reverse('admin:settings_securitysettings_change', args=[settings.pk]))
    
    def response_change(self, request, obj):
        """Кастомное сообщение после сохранения."""
        from django.contrib import messages
        
        messages.success(
            request,
            _('Security settings updated successfully. Changes will take effect immediately.')
        )
        return super().response_change(request, obj)
    
    class Media:
        """Добавляем CSS для улучшения интерфейса."""
        css = {
            'all': ('admin/css/security_settings.css',)
        }
        js = ('admin/js/security_settings.js',) 