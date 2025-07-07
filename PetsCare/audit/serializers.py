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
from .models import AuditLog, UserActivity, SystemEvent


class AuditLogSerializer(serializers.ModelSerializer):
    """
    Serializer для логов аудита.
    """
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_full_name = serializers.SerializerMethodField()
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    resource_type_display = serializers.CharField(source='get_resource_type_display', read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'user_email', 'user_full_name', 'action', 'action_display',
            'resource_type', 'resource_type_display', 'resource_id', 'resource_name',
            'ip_address', 'user_agent', 'details', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_user_full_name(self, obj):
        """Получает полное имя пользователя."""
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email
        return "Anonymous"


class UserActivitySerializer(serializers.ModelSerializer):
    """
    Serializer для активности пользователей.
    """
    class Meta:
        model = UserActivity
        fields = [
            'id', 'user', 'activity_type', 'description', 'ip_address',
            'user_agent', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class SystemEventSerializer(serializers.ModelSerializer):
    """
    Serializer для системных событий.
    """
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)

    class Meta:
        model = SystemEvent
        fields = [
            'id', 'event_type', 'event_type_display', 'severity', 'severity_display',
            'description', 'details', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


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