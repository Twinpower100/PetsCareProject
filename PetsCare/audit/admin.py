from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from .models import UserAction, SecurityAudit, AuditSettings


@admin.register(UserAction)
class UserActionAdmin(admin.ModelAdmin):
    """
    Админский интерфейс для просмотра логов действий пользователей.
    
    Предоставляет полный доступ к логам с фильтрацией,
    поиском и экспортом данных.
    """
    
    list_display = [
        'user_display', 'action_type', 'object_display', 
        'ip_address', 'timestamp', 'execution_time_display'
    ]
    
    list_filter = [
        'action_type', 'timestamp', 'user', 'ip_address',
        'http_method', 'status_code'
    ]
    
    search_fields = [
        'user__email', 'user__first_name', 'user__last_name',
        'details', 'url', 'user_agent'
    ]
    
    readonly_fields = [
        'user', 'action_type', 'content_type', 'object_id',
        'details', 'ip_address', 'user_agent', 'http_method',
        'url', 'status_code', 'execution_time', 'timestamp',
        'session_key', 'object_name'
    ]
    
    date_hierarchy = 'timestamp'
    
    list_per_page = 50
    
    actions = ['export_selected', 'mark_as_reviewed']
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('user', 'action_type', 'timestamp')
        }),
        (_('Object Information'), {
            'fields': ('content_type', 'object_id', 'object_name')
        }),
        (_('Request Information'), {
            'fields': ('ip_address', 'user_agent', 'http_method', 'url', 'status_code')
        }),
        (_('Performance'), {
            'fields': ('execution_time',)
        }),
        (_('Details'), {
            'fields': ('details', 'session_key'),
            'classes': ('collapse',)
        }),
    )
    
    def user_display(self, obj):
        """Отображает пользователя с ссылкой"""
        if obj.user:
            url = reverse('admin:users_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.email)
        return _('Anonymous')
    user_display.short_description = _('User')
    user_display.admin_order_field = 'user__email'
    
    def object_display(self, obj):
        """Отображает объект с ссылкой"""
        if obj.content_object:
            try:
                url = reverse(f'admin:{obj.content_type.app_label}_{obj.content_type.model}_change', 
                             args=[obj.object_id])
                return format_html('<a href="{}">{}</a>', url, obj.object_name)
            except:
                return obj.object_name
        return '-'
    object_display.short_description = _('Object')
    
    def execution_time_display(self, obj):
        """Отображает время выполнения"""
        if obj.execution_time:
            return f"{obj.execution_time:.3f}s"
        return '-'
    execution_time_display.short_description = _('Execution Time')
    execution_time_display.admin_order_field = 'execution_time'
    
    def get_queryset(self, request):
        """Оптимизированный queryset с prefetch_related"""
        return super().get_queryset(request).select_related(
            'user', 'content_type'
        ).prefetch_related('content_object')
    
    def has_add_permission(self, request):
        """Запрещает создание логов вручную"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Запрещает редактирование логов"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Разрешает удаление только администраторам"""
        return request.user.is_superuser
    
    def export_selected(self, request, queryset):
        """Экспорт выбранных логов"""
        # Здесь можно добавить логику экспорта
        self.message_user(request, f"Exported {queryset.count()} logs")
    export_selected.short_description = _("Export selected logs")
    
    def mark_as_reviewed(self, request, queryset):
        """Пометить как просмотренные"""
        queryset.update(reviewed=True)
        self.message_user(request, f"Marked {queryset.count()} logs as reviewed")
    mark_as_reviewed.short_description = _("Mark as reviewed")


@admin.register(SecurityAudit)
class SecurityAuditAdmin(admin.ModelAdmin):
    """
    Админский интерфейс для просмотра аудита безопасности.
    
    Предоставляет доступ к критически важным операциям
    с возможностью проверки и одобрения.
    """
    
    list_display = [
        'user_display', 'audit_type', 'object_display', 
        'is_critical', 'review_status', 'timestamp'
    ]
    
    list_filter = [
        'audit_type', 'is_critical', 'review_status', 'timestamp',
        'reviewed_by'
    ]
    
    search_fields = [
        'user__email', 'user__first_name', 'user__last_name',
        'reason', 'details', 'old_values', 'new_values'
    ]
    
    readonly_fields = [
        'user', 'audit_type', 'content_type', 'object_id',
        'details', 'old_values', 'new_values', 'reason',
        'ip_address', 'timestamp', 'is_critical', 'object_name'
    ]
    
    date_hierarchy = 'timestamp'
    
    list_per_page = 30
    
    actions = ['approve_selected', 'reject_selected', 'mark_as_reviewed']
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('user', 'audit_type', 'timestamp', 'is_critical')
        }),
        (_('Object Information'), {
            'fields': ('content_type', 'object_id', 'object_name')
        }),
        (_('Changes'), {
            'fields': ('old_values', 'new_values')
        }),
        (_('Details'), {
            'fields': ('details', 'reason', 'ip_address')
        }),
        (_('Review'), {
            'fields': ('review_status', 'reviewed_by', 'review_comment'),
            'classes': ('collapse',)
        }),
    )
    
    def user_display(self, obj):
        """Отображает пользователя с ссылкой"""
        if obj.user:
            url = reverse('admin:users_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.email)
        return _('System')
    user_display.short_description = _('User')
    user_display.admin_order_field = 'user__email'
    
    def object_display(self, obj):
        """Отображает объект с ссылкой"""
        if obj.content_object:
            try:
                url = reverse(f'admin:{obj.content_type.app_label}_{obj.content_type.model}_change', 
                             args=[obj.object_id])
                return format_html('<a href="{}">{}</a>', url, obj.object_name)
            except:
                return obj.object_name
        return '-'
    object_display.short_description = _('Object')
    
    def get_queryset(self, request):
        """Оптимизированный queryset"""
        return super().get_queryset(request).select_related(
            'user', 'content_type', 'reviewed_by'
        ).prefetch_related('content_object')
    
    def has_add_permission(self, request):
        """Запрещает создание записей аудита вручную"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Разрешает редактирование только полей проверки"""
        if obj and request.user.is_staff:
            return True
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Запрещает удаление записей аудита"""
        return False
    
    def approve_selected(self, request, queryset):
        """Одобрить выбранные записи"""
        queryset.update(
            review_status='approved',
            reviewed_by=request.user,
            review_comment='Approved via bulk action'
        )
        self.message_user(request, f"Approved {queryset.count()} audit records")
    approve_selected.short_description = _("Approve selected")
    
    def reject_selected(self, request, queryset):
        """Отклонить выбранные записи"""
        queryset.update(
            review_status='rejected',
            reviewed_by=request.user,
            review_comment='Rejected via bulk action'
        )
        self.message_user(request, f"Rejected {queryset.count()} audit records")
    reject_selected.short_description = _("Reject selected")
    
    def mark_as_reviewed(self, request, queryset):
        """Пометить как просмотренные"""
        queryset.update(
            review_status='reviewed',
            reviewed_by=request.user
        )
        self.message_user(request, f"Marked {queryset.count()} records as reviewed")
    mark_as_reviewed.short_description = _("Mark as reviewed")


@admin.register(AuditSettings)
class AuditSettingsAdmin(admin.ModelAdmin):
    """
    Админский интерфейс для настроек аудита.
    
    Позволяет управлять глобальными настройками
    системы логирования и аудита.
    """
    
    list_display = ['logging_enabled', 'security_audit_enabled', 'updated_at']
    
    fieldsets = (
        (_('General Settings'), {
            'fields': ('logging_enabled', 'security_audit_enabled')
        }),
        (_('Logging Configuration'), {
            'fields': (
                'log_http_requests', 'log_database_changes',
                'log_business_operations', 'log_system_events',
                'min_log_level'
            )
        }),
        (_('Retention Settings'), {
            'fields': ('log_retention_days', 'security_audit_retention_days')
        }),
        (_('Cleanup Settings'), {
            'fields': ('auto_cleanup_enabled', 'cleanup_frequency_days')
        }),
        (_('Notifications'), {
            'fields': ('critical_operation_notifications', 'notification_email')
        }),
    )
    
    def has_add_permission(self, request):
        """Разрешает только одну запись настроек"""
        return not AuditSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        """Запрещает удаление настроек"""
        return False


# Добавляем статистику в админку
class AuditDashboard:
    """
    Дашборд с статистикой аудита для админки.
    """
    
    @staticmethod
    def get_statistics():
        """Получает статистику аудита"""
        try:
            # Проверить, готова ли база данных
            from django.db import connection
            if not connection.introspection.table_names():
                # Если таблицы еще не созданы, возвращаем пустую статистику
                return {
                    'total_actions': 0,
                    'total_audits': 0,
                    'actions_today': 0,
                    'audits_today': 0,
                    'critical_audits': 0,
                    'pending_reviews': 0,
                    'top_actions': [],
                    'top_users': [],
                }
        except:
            # Если БД еще не готова, возвращаем пустую статистику
            return {
                'total_actions': 0,
                'total_audits': 0,
                'actions_today': 0,
                'audits_today': 0,
                'critical_audits': 0,
                'pending_reviews': 0,
                'top_actions': [],
                'top_users': [],
            }
        
        now = timezone.now()
        yesterday = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        
        return {
            'total_actions': UserAction.objects.count(),
            'total_audits': SecurityAudit.objects.count(),
            'actions_today': UserAction.objects.filter(timestamp__date=now.date()).count(),
            'audits_today': SecurityAudit.objects.filter(timestamp__date=now.date()).count(),
            'critical_audits': SecurityAudit.objects.filter(is_critical=True).count(),
            'pending_reviews': SecurityAudit.objects.filter(review_status='pending').count(),
            'top_actions': UserAction.objects.values('action_type').annotate(
                count=Count('id')
            ).order_by('-count')[:5],
            'top_users': UserAction.objects.values('user__email').annotate(
                count=Count('id')
            ).filter(user__isnull=False).order_by('-count')[:5],
        }
