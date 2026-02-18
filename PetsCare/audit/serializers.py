"""
Serializers для API аудита.

Этот модуль содержит сериализаторы для:
1. Логов аудита
2. Активности пользователей
3. Системных событий
4. Статистики аудита
"""

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import UserAction, SecurityAudit, AuditSettings


class UserActionSerializer(serializers.ModelSerializer):
    """
    Serializer для действий пользователей.
    """
    ip_address = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    class Meta:
        model = UserAction
        fields = [
            'id', 'user', 'action_type', 'content_type', 'object_id', 'details', 
            'ip_address', 'user_agent', 'http_method', 'url', 'status_code', 
            'execution_time', 'timestamp', 'session_key'
        ]
        read_only_fields = ['id', 'timestamp']


class SecurityAuditSerializer(serializers.ModelSerializer):
    """
    Serializer для аудита безопасности.
    """
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_full_name = serializers.SerializerMethodField()
    audit_type_display = serializers.CharField(source='get_audit_type_display', read_only=True)
    review_status_display = serializers.CharField(source='get_review_status_display', read_only=True)
    object_name = serializers.CharField(source='object_name', read_only=True)
    reviewed_by_email = serializers.CharField(source='reviewed_by.email', read_only=True)
    ip_address = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = SecurityAudit
        fields = [
            'id', 'user', 'user_email', 'user_full_name', 'audit_type', 'audit_type_display',
            'content_type', 'object_id', 'object_name', 'details', 'old_values', 'new_values',
            'reason', 'ip_address', 'timestamp', 'is_critical', 'review_status', 
            'review_status_display', 'reviewed_by', 'reviewed_by_email', 'review_comment'
        ]
        read_only_fields = ['id', 'timestamp']

    def get_user_full_name(self, obj):
        """Получает полное имя пользователя."""
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email
        return "Anonymous"


class AuditSettingsSerializer(serializers.ModelSerializer):
    """
    Serializer для настроек аудита.
    """
    class Meta:
        model = AuditSettings
        fields = [
            'id', 'logging_enabled', 'security_audit_enabled', 'log_retention_days',
            'security_audit_retention_days', 'log_http_requests', 'log_database_changes',
            'log_business_operations', 'log_system_events', 'min_log_level',
            'auto_cleanup_enabled', 'cleanup_frequency_days', 
            'critical_operation_notifications', 'notification_email', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at']


class AuditStatisticsSerializer(serializers.Serializer):
    """
    Serializer для статистики аудита.
    """
    total_logs = serializers.IntegerField()
    today_logs = serializers.IntegerField()
    action_stats = serializers.ListField()
    user_stats = serializers.ListField()
    resource_stats = serializers.ListField()


class AuditLogFilterSerializer(serializers.Serializer):
    """
    Serializer для фильтрации логов аудита.
    """
    user_id = serializers.IntegerField(required=False)
    action = serializers.CharField(required=False)
    resource_type = serializers.CharField(required=False)
    resource_id = serializers.IntegerField(required=False)
    created_after = serializers.DateTimeField(required=False)
    created_before = serializers.DateTimeField(required=False)
    ip_address = serializers.CharField(required=False)
    user_agent = serializers.CharField(required=False)


class AuditLogExportSerializer(serializers.Serializer):
    """
    Serializer для экспорта логов аудита.
    """
    format = serializers.ChoiceField(choices=['csv', 'json'], default='csv')
    filters = AuditLogFilterSerializer(required=False)
    limit = serializers.IntegerField(min_value=1, max_value=10000, default=1000)


class AuditLogCleanupSerializer(serializers.Serializer):
    """
    Serializer для очистки логов аудита.
    """
    days = serializers.IntegerField(min_value=1, max_value=365, default=90)
    confirm = serializers.BooleanField(default=False)

    def validate(self, data):
        """Проверяет подтверждение очистки."""
        if not data.get('confirm'):
            raise serializers.ValidationError(_("Please confirm the cleanup operation"))
        return data 