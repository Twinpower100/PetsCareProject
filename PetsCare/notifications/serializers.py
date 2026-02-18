"""
Сериализаторы для API уведомлений.

Этот модуль содержит сериализаторы для:
1. Уведомлений
2. Настроек уведомлений
3. Предпочтений пользователей
4. Шаблонов уведомлений
"""

from rest_framework import serializers
from .models import Notification, Reminder
from pets.serializers import PetSerializer
# ProviderServiceSerializer удален - используйте ProviderLocationServiceSerializer
from django.utils.translation import gettext as _
from .models import (
    NotificationType, NotificationTemplate, NotificationPreference,
    UserNotificationSettings, NotificationRule
)

class NotificationTypeSerializer(serializers.ModelSerializer):
    """
    Сериализатор для типов уведомлений.
    """
    class Meta:
        model = NotificationType
        fields = ['id', 'name', 'code', 'description', 'is_active', 'default_enabled', 'is_required']

class NotificationTemplateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для шаблонов уведомлений.
    """
    class Meta:
        model = NotificationTemplate
        fields = [
            'id', 'name', 'code', 'subject', 'body', 'html_body',
            'channel', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """
    Сериализатор для настроек уведомлений пользователя.
    """
    notification_type_name = serializers.CharField(
        source='notification_type.name',
        read_only=True
    )
    notification_type_code = serializers.CharField(
        source='notification_type.code',
        read_only=True
    )
    
    class Meta:
        model = NotificationPreference
        fields = [
            'id', 'user', 'notification_type', 'notification_type_name',
            'notification_type_code', 'email_enabled', 'push_enabled',
            'in_app_enabled', 'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']

class NotificationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для уведомлений.
    """
    notification_type_display = serializers.CharField(
        source='get_notification_type_display',
        read_only=True
    )
    priority_display = serializers.CharField(
        source='get_priority_display',
        read_only=True
    )
    channel_display = serializers.CharField(
        source='get_channel_display',
        read_only=True
    )
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'user_email', 'pet', 'pet_name', 'notification_type',
            'notification_type_display', 'title', 'message', 'priority',
            'priority_display', 'channel', 'channel_display', 'is_read',
            'created_at', 'scheduled_for', 'sent_at', 'data'
        ]
        read_only_fields = ['user', 'created_at', 'sent_at']

class NotificationListSerializer(serializers.ModelSerializer):
    """
    Упрощенный сериализатор для списка уведомлений.
    """
    notification_type_display = serializers.CharField(
        source='get_notification_type_display',
        read_only=True
    )
    priority_display = serializers.CharField(
        source='get_priority_display',
        read_only=True
    )
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'notification_type_display',
            'title', 'message', 'priority', 'priority_display',
            'is_read', 'created_at', 'pet_name'
        ]
        read_only_fields = ['created_at']

class UserNotificationSettingsSerializer(serializers.ModelSerializer):
    """
    Сериализатор для детальных настроек уведомлений пользователя.
    """
    event_type_display = serializers.CharField(
        source='get_event_type_display',
        read_only=True
    )
    channel_display = serializers.CharField(
        source='get_channel_display',
        read_only=True
    )
    notification_time_display = serializers.CharField(
        source='get_notification_time_display',
        read_only=True
    )
    
    class Meta:
        model = UserNotificationSettings
        fields = [
            'id', 'user', 'event_type', 'event_type_display', 'channel',
            'channel_display', 'notification_time', 'notification_time_display',
            'is_enabled', 'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']
    
    def validate(self, data):
        """
        Валидация данных настроек уведомлений.
        
        Args:
            data: Данные для валидации
            
        Returns:
            dict: Валидированные данные
            
        Raises:
            serializers.ValidationError: Если данные невалидны
        """
        # Проверяем, что настройка не дублируется
        event_type = data.get('event_type')
        channel = data.get('channel')
        notification_time = data.get('notification_time')
        user = self.context['request'].user
        
        if self.instance:
            # При обновлении исключаем текущий объект
            existing = UserNotificationSettings.objects.filter(
                user=user,
                event_type=event_type,
                channel=channel,
                notification_time=notification_time
            ).exclude(pk=self.instance.pk)
        else:
            existing = UserNotificationSettings.objects.filter(
                user=user,
                event_type=event_type,
                channel=channel,
                notification_time=notification_time
            )
        
        if existing.exists():
            raise serializers.ValidationError(
                _('A setting with these parameters already exists')
            )
        
        return data

class ReminderSerializer(serializers.ModelSerializer):
    """
    Сериализатор для напоминаний о процедурах питомцев.
    """
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)
    frequency_display = serializers.CharField(
        source='get_frequency_display',
        read_only=True
    )
    procedure_type_display = serializers.CharField(
        source='get_procedure_type_display',
        read_only=True
    )
    
    class Meta:
        model = Reminder
        fields = [
            'id', 'pet', 'pet_name', 'service', 'service_name', 'title',
            'description', 'procedure_type', 'procedure_type_display',
            'frequency', 'frequency_display', 'interval_days', 'start_date',
            'end_date', 'is_active', 'last_notified', 'next_notification'
        ]
        read_only_fields = ['last_notified', 'next_notification']
    
    def validate(self, data):
        """
        Валидация данных напоминания.
        
        Args:
            data: Данные для валидации
            
        Returns:
            dict: Валидированные данные
            
        Raises:
            serializers.ValidationError: Если данные невалидны
        """
        frequency = data.get('frequency')
        interval_days = data.get('interval_days')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        # Проверяем, что для произвольной частоты указан интервал
        if frequency == 'custom' and not interval_days:
            raise serializers.ValidationError(
                _('Interval days is required for custom frequency')
            )
        
        # Проверяем, что дата окончания не раньше даты начала
        if end_date and start_date and end_date < start_date:
            raise serializers.ValidationError(
                _('End date cannot be earlier than start date')
            )
        
        return data

class NotificationCreateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания уведомлений.
    """
    class Meta:
        model = Notification
        fields = [
            'user', 'pet', 'notification_type', 'title', 'message',
            'priority', 'channel', 'scheduled_for', 'data'
        ]
    
    def validate(self, data):
        """
        Валидация данных уведомления.
        
        Args:
            data: Данные для валидации
            
        Returns:
            dict: Валидированные данные
            
        Raises:
            serializers.ValidationError: Если данные невалидны
        """
        user = data.get('user')
        pet = data.get('pet')
        
        # Проверяем, что питомец принадлежит пользователю
        if pet and pet.owner != user:
            raise serializers.ValidationError(
                _('Pet does not belong to the specified user')
            )
        
        return data

class NotificationBulkCreateSerializer(serializers.Serializer):
    """
    Сериализатор для массового создания уведомлений.
    """
    users = serializers.ListField(
        child=serializers.IntegerField(),
        help_text=_('List of user IDs to send notifications to')
    )
    notification_type = serializers.CharField(
        help_text=_('Type of notification')
    )
    title = serializers.CharField(
        help_text=_('Notification title')
    )
    message = serializers.CharField(
        help_text=_('Notification message')
    )
    priority = serializers.ChoiceField(
        choices=Notification.PRIORITY_CHOICES,
        default='medium',
        help_text=_('Notification priority')
    )
    channels = serializers.ListField(
        child=serializers.ChoiceField(choices=Notification.CHANNEL_CHOICES),
        default=['all'],
        help_text=_('Channels to send notification through')
    )
    data = serializers.DictField(
        required=False,
        help_text=_('Additional data for notification')
    )
    
    def validate_users(self, value):
        """
        Валидация списка пользователей.
        
        Args:
            value: Список ID пользователей
            
        Returns:
            list: Валидированный список
            
        Raises:
            serializers.ValidationError: Если список невалиден
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        if not value:
            raise serializers.ValidationError(_('Users list cannot be empty'))
        
        # Проверяем, что все пользователи существуют
        existing_users = User.objects.filter(id__in=value)
        if len(existing_users) != len(value):
            raise serializers.ValidationError(_('Some users do not exist'))
        
        return value

class NotificationStatisticsSerializer(serializers.Serializer):
    """
    Сериализатор для статистики уведомлений.
    """
    total_count = serializers.IntegerField()
    unread_count = serializers.IntegerField()
    read_count = serializers.IntegerField()
    type_stats = serializers.DictField()
    priority_stats = serializers.DictField()

class NotificationTestSerializer(serializers.Serializer):
    """
    Сериализатор для тестовых уведомлений.
    """
    channels = serializers.ListField(
        child=serializers.ChoiceField(choices=Notification.CHANNEL_CHOICES),
        default=['all'],
        help_text=_('Channels to test notification through')
    )
    priority = serializers.ChoiceField(
        choices=Notification.PRIORITY_CHOICES,
        default='low',
        help_text=_('Test notification priority')
    ) 


class NotificationRuleSerializer(serializers.ModelSerializer):
    """
    Сериализатор для правил уведомлений.
    """
    event_type_display = serializers.CharField(
        source='get_event_type_display',
        read_only=True
    )
    priority_display = serializers.CharField(
        source='get_priority_display',
        read_only=True
    )
    inheritance_display = serializers.CharField(
        source='get_inheritance_display',
        read_only=True
    )
    template_name = serializers.CharField(
        source='template.name',
        read_only=True
    )
    created_by_username = serializers.CharField(
        source='created_by.username',
        read_only=True
    )
    
    class Meta:
        model = NotificationRule
        fields = [
            'id', 'event_type', 'event_type_display', 'condition', 'template',
            'template_name', 'priority', 'priority_display', 'channels',
            'is_active', 'inheritance', 'inheritance_display', 'user',
            'created_by', 'created_by_username', 'created_at', 'updated_at', 'version'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at', 'version']
    
    def validate(self, data):
        """
        Валидация данных правила уведомления.
        
        Args:
            data: Данные для валидации
            
        Returns:
            dict: Валидированные данные
            
        Raises:
            serializers.ValidationError: Если данные невалидны
        """
        # Проверяем, что пользователь указан для пользовательских правил
        inheritance = data.get('inheritance')
        user = data.get('user')
        
        if inheritance == 'user_specific' and not user:
            raise serializers.ValidationError(
                _('User must be specified for user-specific rules')
            )
        
        if inheritance == 'global' and user:
            raise serializers.ValidationError(
                _('User should not be specified for global rules')
            )
        
        # Проверяем, что каналы указаны
        channels = data.get('channels', [])
        if not channels:
            raise serializers.ValidationError(
                _('At least one channel must be specified')
            )
        
        # Проверяем валидность каналов
        valid_channels = ['email', 'push', 'in_app']
        for channel in channels:
            if channel not in valid_channels:
                raise serializers.ValidationError(
                    _('Invalid channel: {}').format(channel)
                )
        
        # Проверяем уникальность правила (для создания)
        if self.instance is None:  # Только для создания новых правил
            from django.db import transaction
            with transaction.atomic():
                existing_rule = NotificationRule.objects.filter(
                    event_type=data.get('event_type'),
                    condition=data.get('condition'),
                    template=data.get('template'),
                    inheritance=data.get('inheritance'),
                    user=data.get('user')
                ).first()
                
                if existing_rule:
                    raise serializers.ValidationError(
                        _('A rule with these exact parameters already exists')
                    )
        
        return data
    
    def validate_condition(self, value):
        """
        Валидация условия правила.
        
        Args:
            value: Условие для валидации
            
        Returns:
            str: Валидированное условие
            
        Raises:
            serializers.ValidationError: Если условие невалидно
        """
        if not value:
            raise serializers.ValidationError(
                _('Condition cannot be empty')
            )
        
        # Здесь можно добавить дополнительную валидацию синтаксиса Python
        # Например, проверку на безопасность выражения
        
        return value


class ReminderSettingsSerializer(serializers.ModelSerializer):
    """
    Сериализатор для настроек напоминаний о бронированиях.
    """
    reminder_intervals_hours = serializers.SerializerMethodField()
    reminder_time_hours = serializers.SerializerMethodField()
    
    class Meta:
        from .models import ReminderSettings
        model = ReminderSettings
        fields = [
            'id', 'user', 'reminder_time_before_booking', 'reminder_time_hours',
            'multiple_reminders', 'reminder_intervals', 'reminder_intervals_hours',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']
    
    def get_reminder_time_hours(self, obj):
        """
        Возвращает время напоминания в часах.
        
        Args:
            obj: Объект настроек напоминаний
            
        Returns:
            float: Время в часах
        """
        return round(obj.reminder_time_before_booking / 60, 2)
    
    def get_reminder_intervals_hours(self, obj):
        """
        Возвращает интервалы напоминаний в часах.
        
        Args:
            obj: Объект настроек напоминаний
            
        Returns:
            list: Список интервалов в часах
        """
        if obj.reminder_intervals:
            return [round(interval / 60, 2) for interval in obj.reminder_intervals]
        return []
    
    def validate_reminder_time_before_booking(self, value):
        """
        Валидирует время напоминания до бронирования.
        
        Args:
            value: Время в минутах
            
        Returns:
            int: Валидное время в минутах
            
        Raises:
            ValidationError: Если время невалидно
        """
        if value < 1:
            raise serializers.ValidationError(_('Reminder time must be at least 1 minute'))
        if value > 10080:  # 1 неделя
            raise serializers.ValidationError(_('Reminder time cannot exceed 1 week'))
        return value
    
    def validate_reminder_intervals(self, value):
        """
        Валидирует интервалы напоминаний.
        
        Args:
            value: Список интервалов в минутах
            
        Returns:
            list: Валидный список интервалов
            
        Raises:
            ValidationError: Если интервалы невалидны
        """
        if not isinstance(value, list):
            raise serializers.ValidationError(_('Reminder intervals must be a list'))
        
        for interval in value:
            if not isinstance(interval, int) or interval < 1:
                raise serializers.ValidationError(_('Each interval must be a positive integer'))
            if interval > 10080:  # 1 неделя
                raise serializers.ValidationError(_('Each interval cannot exceed 1 week'))
        
        # Убираем дубликаты и сортируем
        unique_intervals = sorted(list(set(value)), reverse=True)
        return unique_intervals
    
    def validate(self, data):
        """
        Валидирует данные настроек напоминаний.
        
        Args:
            data: Данные для валидации
            
        Returns:
            dict: Валидные данные
            
        Raises:
            ValidationError: Если данные невалидны
        """
        # Если множественные напоминания отключены, очищаем интервалы
        if not data.get('multiple_reminders', False):
            data['reminder_intervals'] = []
        
        # Если множественные напоминания включены, убеждаемся что есть интервалы
        if data.get('multiple_reminders', False) and not data.get('reminder_intervals'):
            raise serializers.ValidationError(_('Reminder intervals are required when multiple reminders are enabled'))
        
        return data 