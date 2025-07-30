"""
Админский интерфейс для системных настроек.

Этот модуль содержит админские классы для:
1. Настроек безопасности
2. Глобальных системных настроек
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.core.exceptions import ValidationError, PermissionDenied
from django import forms
from django.contrib.auth import get_user_model
import logging

from .models import SecuritySettings, RatingDecaySettings, BlockingScheduleSettings

User = get_user_model()
logger = logging.getLogger(__name__)


class GlobalSettingsAccessMixin:
    """
    Миксин для ограничения доступа к глобальным настройкам только админам проекта.
    
    Проверяет:
    - is_superuser = True (суперпользователь Django)
    - ИЛИ is_staff = True И имеет роль system_admin
    """
    
    def has_module_permission(self, request):
        """Проверяет доступ к модулю."""
        return self._check_global_settings_access(request)
    
    def has_view_permission(self, request, obj=None):
        """Проверяет доступ на просмотр."""
        return self._check_global_settings_access(request)
    
    def has_add_permission(self, request):
        """Проверяет доступ на добавление."""
        return self._check_global_settings_access(request)
    
    def has_change_permission(self, request, obj=None):
        """Проверяет доступ на изменение."""
        return self._check_global_settings_access(request)
    
    def has_delete_permission(self, request, obj=None):
        """Проверяет доступ на удаление."""
        return self._check_global_settings_access(request)
    
    def _check_global_settings_access(self, request):
        """
        Проверяет доступ к глобальным настройкам.
        
        Доступ имеют:
        - Суперпользователи Django (is_superuser=True)
        - Сотрудники с ролью system_admin (is_staff=True + system_admin role)
        """
        if not request.user.is_authenticated:
            self._log_unauthorized_access(request, "Unauthenticated user")
            return False
        
        # Суперпользователи имеют полный доступ
        if request.user.is_superuser:
            return True
        
        # Сотрудники с ролью system_admin имеют доступ
        if request.user.is_staff and request.user.has_role('system_admin'):
            return True
        
        # Логируем попытку несанкционированного доступа
        self._log_unauthorized_access(request, f"User {request.user.email} lacks required permissions")
        return False
    
    def _log_unauthorized_access(self, request, reason):
        """Логирует попытку несанкционированного доступа."""
        logger.warning(
            f"Unauthorized access attempt to global settings: {reason}. "
            f"User: {getattr(request.user, 'email', 'Unknown')}, "
            f"IP: {request.META.get('REMOTE_ADDR', 'Unknown')}, "
            f"Path: {request.path}"
        )
    
    def get_queryset(self, request):
        """Возвращает queryset с проверкой доступа."""
        if not self._check_global_settings_access(request):
            return self.model.objects.none()
        return super().get_queryset(request)


class SettingsAdminSite(admin.AdminSite):
    """
    Кастомный админский сайт для приложения settings.
    
    Скрывает модели от пользователей без соответствующих прав.
    """
    
    def get_app_list(self, request):
        """
        Возвращает список приложений с фильтрацией по правам доступа.
        """
        app_list = super().get_app_list(request)
        
        # Проверяем права доступа к глобальным настройкам
        has_global_settings_access = self._check_global_settings_access(request)
        
        # Фильтруем модели в приложении settings
        for app in app_list:
            if app['app_label'] == 'settings':
                # Оставляем только модели, к которым есть доступ
                filtered_models = []
                for model in app['models']:
                    model_admin = self._registry.get(model['model'])
                    if hasattr(model_admin, '_check_global_settings_access'):
                        if model_admin._check_global_settings_access(request):
                            filtered_models.append(model)
                    else:
                        # Для моделей без специальных проверок оставляем как есть
                        filtered_models.append(model)
                
                app['models'] = filtered_models
        
        return app_list
    
    def _check_global_settings_access(self, request):
        """
        Проверяет доступ к глобальным настройкам.
        """
        if not request.user.is_authenticated:
            return False
        
        # Суперпользователи имеют полный доступ
        if request.user.is_superuser:
            return True
        
        # Сотрудники с ролью system_admin имеют доступ
        if request.user.is_staff and request.user.has_role('system_admin'):
            return True
        
        return False


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
class SecuritySettingsAdmin(GlobalSettingsAccessMixin, admin.ModelAdmin):
    """
    Админский интерфейс для настроек безопасности.
    
    Особенности:
    - Ограниченный доступ только для админов проекта
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


class RatingDecaySettingsForm(forms.ModelForm):
    """
    Форма для настроек затухания рейтингов с дополнительной валидацией.
    """
    
    class Meta:
        model = RatingDecaySettings
        fields = '__all__'
    
    def clean(self):
        """Дополнительная валидация настроек затухания."""
        cleaned_data = super().clean()
        
        # Проверяем, что минимальный вес не больше максимального возраста
        min_weight = cleaned_data.get('min_weight')
        max_age_days = cleaned_data.get('max_age_days')
        half_life_days = cleaned_data.get('half_life_days')
        
        if min_weight and max_age_days and half_life_days:
            # Проверяем логику: max_age должен быть больше half_life
            if max_age_days <= half_life_days:
                raise ValidationError({
                    'max_age_days': _('Maximum age must be greater than half-life period')
                })
            
            # Проверяем, что минимальный вес разумен для максимального возраста
            import math
            expected_min_weight = math.exp(-max_age_days * math.log(2) / half_life_days)
            if min_weight > expected_min_weight:
                raise ValidationError({
                    'min_weight': _('Minimum weight is too high for the given max age and half-life')
                })
        
        return cleaned_data


@admin.register(RatingDecaySettings)
class RatingDecaySettingsAdmin(GlobalSettingsAccessMixin, admin.ModelAdmin):
    """
    Админский интерфейс для настроек затухания рейтингов.
    
    Особенности:
    - Ограниченный доступ только для админов проекта
    - Группировка полей по категориям
    - Валидация настроек
    - Автоматическое управление активностью
    - Удобный интерфейс с подсказками
    """
    
    form = RatingDecaySettingsForm
    
    # Отключаем возможность удаления (синглтон)
    def has_delete_permission(self, request, obj=None):
        return False
    
    # Группировка полей
    fieldsets = (
        (_('Decay Parameters'), {
            'fields': (
                'half_life_days',
                'min_weight',
                'max_age_days',
            ),
            'description': _('Configure exponential decay parameters for review weights')
        }),
        
        (_('Status'), {
            'fields': ('is_active',),
            'description': _('Activate these settings (will deactivate all others)')
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
    
    # Отображение в списке
    list_display = ('get_settings_summary', 'is_active', 'updated_at', 'updated_by')
    list_filter = ('is_active',)
    search_fields = ()
    
    # Настройки страницы
    save_on_top = True
    
    def get_settings_summary(self, obj):
        """Возвращает краткое описание настроек."""
        if obj.is_active:
            status = "🟢 Active"
        else:
            status = "🔴 Inactive"
        
        return format_html(
            '<strong>{}</strong><br>'
            '<small>Half-life: {} days, Min weight: {}, Max age: {} days</small>',
            status,
            obj.half_life_days,
            obj.min_weight,
            obj.max_age_days
        )
    
    get_settings_summary.short_description = _('Settings Summary')
    
    def save_model(self, request, obj, form, change):
        """Сохраняет модель с логированием изменений."""
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        
        # Логируем изменение
        if change:
            from django.contrib import messages
            messages.success(
                request,
                _('Rating decay settings updated successfully. New settings are now active.')
            )
    
    def get_queryset(self, request):
        """Возвращает queryset с сортировкой."""
        return super().get_queryset(request).order_by('-is_active', '-updated_at')
    
    def changelist_view(self, request, extra_context=None):
        """Кастомный вид списка для синглтона."""
        # Перенаправляем на изменение единственной записи
        settings = RatingDecaySettings.objects.first()
        if settings:
            return self.response_change(request, settings)
        else:
            # Создаем настройки по умолчанию
            settings = RatingDecaySettings.objects.create()
            return self.response_change(request, settings)
    
    def response_change(self, request, obj):
        """Кастомный ответ после изменения."""
        from django.contrib import messages
        from django.shortcuts import redirect
        from django.urls import reverse
        
        messages.success(
            request,
            _('Rating decay settings saved successfully.')
        )
        
        return redirect(reverse('admin:settings_ratingdecaysettings_changelist'))
    
    class Media:
        """Добавляем CSS для улучшения интерфейса."""
        css = {
            'all': ('admin/css/rating_decay_settings.css',)
        } 


class BlockingScheduleSettingsForm(forms.ModelForm):
    """Форма для настроек расписания блокировок с валидацией."""
    
    class Meta:
        model = BlockingScheduleSettings
        fields = '__all__'
    
    def clean(self):
        """Валидация формы."""
        cleaned_data = super().clean()
        
        # Проверка совместимости настроек
        frequency = cleaned_data.get('frequency')
        days_of_week = cleaned_data.get('days_of_week', [])
        day_of_month = cleaned_data.get('day_of_month')
        custom_interval_hours = cleaned_data.get('custom_interval_hours')
        
        if frequency == 'weekly' and days_of_week:
            # Проверяем, что дни недели в правильном диапазоне
            invalid_days = [day for day in days_of_week if day not in range(7)]
            if invalid_days:
                raise ValidationError({
                    'days_of_week': _('Days of week must be numbers from 0 to 6 (0=Monday, 6=Sunday)')
                })
        
        if frequency == 'monthly' and not day_of_month:
            raise ValidationError({
                'day_of_month': _('Day of month is required for monthly frequency')
            })
        
        if frequency == 'custom' and not custom_interval_hours:
            raise ValidationError({
                'custom_interval_hours': _('Custom interval is required for custom frequency')
            })
        
        return cleaned_data


@admin.register(BlockingScheduleSettings)
class BlockingScheduleSettingsAdmin(GlobalSettingsAccessMixin, admin.ModelAdmin):
    """
    Админский интерфейс для настроек расписания блокировок.
    
    Особенности:
    - Ограниченный доступ только для админов проекта
    - Группировка полей по категориям
    - Валидация настроек
    - Автоматическое управление активностью
    - Удобный интерфейс с подсказками
    """
    
    form = BlockingScheduleSettingsForm
    
    # Отключаем возможность удаления (синглтон)
    def has_delete_permission(self, request, obj=None):
        return False
    
    # Группировка полей
    fieldsets = (
        (_('Schedule Configuration'), {
            'fields': (
                'frequency',
                'check_time',
                'days_of_week',
                'day_of_month',
                'custom_interval_hours',
            ),
            'description': _('Configure the frequency and timing of blocking checks')
        }),
        
        (_('Additional Options'), {
            'fields': (
                'exclude_weekends',
                'exclude_holidays',
            ),
            'description': _('Configure additional scheduling options')
        }),
        
        (_('Status'), {
            'fields': ('is_active',),
            'description': _('Activate these settings (will deactivate all others)')
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
    
    # Отображение в списке
    list_display = ('get_settings_summary', 'is_active', 'updated_at', 'updated_by')
    list_filter = ('is_active', 'frequency')
    search_fields = ()
    
    # Настройки страницы
    save_on_top = True
    
    def get_settings_summary(self, obj):
        """Возвращает краткое описание настроек для списка."""
        if obj.is_active:
            status = format_html('<span style="color: green;">●</span> Active')
        else:
            status = format_html('<span style="color: red;">●</span> Inactive')
        
        schedule_desc = obj.get_schedule_description()
        
        return format_html(
            '<div><strong>{}</strong><br/>'
            '<small style="color: #666;">{}</small><br/>'
            '<small>{}</small></div>',
            schedule_desc,
            status,
            f"Updated: {obj.updated_at.strftime('%Y-%m-%d %H:%M')}"
        )
    get_settings_summary.short_description = _('Schedule Settings')
    
    def save_model(self, request, obj, form, change):
        """Переопределяем сохранение для логирования изменений."""
        if change:
            # Логируем изменение
            logger.info(
                f"Blocking schedule settings updated by {request.user.email}. "
                f"Changes: {form.changed_data}"
            )
        else:
            # Логируем создание
            logger.info(
                f"Blocking schedule settings created by {request.user.email}"
            )
        
        # Устанавливаем пользователя, внесшего изменения
        obj.updated_by = request.user
        
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        """Возвращает queryset с проверкой доступа."""
        if not self._check_global_settings_access(request):
            return self.model.objects.none()
        return super().get_queryset(request)
    
    def changelist_view(self, request, extra_context=None):
        """Кастомизируем список для синглтона."""
        # Для синглтона показываем только одну запись
        if self.model.objects.exists():
            # Если есть записи, перенаправляем на первую
            first_obj = self.model.objects.first()
            return self.response_change(request, first_obj)
        
        # Если записей нет, показываем форму создания
        return self.add_view(request)
    
    def response_change(self, request, obj):
        """Кастомизируем ответ после изменения."""
        response = super().response_change(request, obj)
        
        # Добавляем сообщение об успешном сохранении
        if '_save' in request.POST:
            self.message_user(
                request,
                _('Blocking schedule settings updated successfully. '
                  'Changes will take effect on the next Celery Beat restart.'),
                level='SUCCESS'
            )
        
        return response
    
    class Media:
        """Добавляем CSS для улучшения интерфейса."""
        css = {
            'all': ('admin/css/blocking_schedule_settings.css',)
        }
        js = ('admin/js/blocking_schedule_settings.js',) 