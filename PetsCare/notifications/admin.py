from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    NotificationType, NotificationTemplate,
    NotificationPreference, Notification, Reminder, UserNotificationSettings, NotificationRule
)
from custom_admin import custom_admin_site


class NotificationTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'default_enabled')
    list_filter = ('is_active', 'default_enabled')
    search_fields = ('name', 'code', 'description')
    fieldsets = (
        (None, {
            'fields': ('name', 'code', 'is_active', 'default_enabled')
        }),
        (_('Description'), {
            'fields': ('description',),
            'classes': ('collapse',)
        })
    )


class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'channel', 'is_active')
    list_filter = ('channel', 'is_active')
    search_fields = ('name', 'code', 'subject', 'body')
    readonly_fields = ('created_at', 'updated_at')


class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_type', 'email_enabled', 'push_enabled')
    list_filter = ('email_enabled', 'push_enabled', 'notification_type')
    search_fields = ('user__username', 'user__email', 'notification_type__name')
    fieldsets = (
        (None, {
            'fields': ('user', 'notification_type')
        }),
        (_('Notification Channels'), {
            'fields': ('email_enabled', 'push_enabled')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')


class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'pet', 'notification_type', 'title', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__username', 'pet__name', 'title', 'message')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


class ReminderAdmin(admin.ModelAdmin):
    list_display = ('pet', 'service', 'title', 'frequency', 'is_active', 'next_notification')
    list_filter = ('frequency', 'is_active')
    search_fields = ('pet__name', 'title', 'description')
    readonly_fields = ('last_notified', 'next_notification')
    date_hierarchy = 'start_date'


class UserNotificationSettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'event_type', 'channel', 'is_enabled')
    list_filter = ('is_enabled', 'event_type', 'channel')
    search_fields = ('user__username', 'user__email', 'event_type')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('user', 'event_type', 'channel')
        }),
        (_('Notification Settings'), {
            'fields': ('notification_time', 'is_enabled')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


class NotificationRuleAdmin(admin.ModelAdmin):
    """
    Админский интерфейс для управления правилами уведомлений.
    """
    list_display = ('event_type', 'template', 'priority', 'inheritance', 'is_active', 'created_by')
    list_filter = ('event_type', 'priority', 'inheritance', 'is_active', 'created_at')
    search_fields = ('event_type', 'template__name', 'condition', 'created_by__username')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('Basic Settings'), {
            'fields': ('event_type', 'template', 'priority', 'is_active')
        }),
        (_('Conditions and Channels'), {
            'fields': ('condition', 'channels'),
            'description': _('Condition is a Python expression evaluated against the event context. '
                           'Available variables: user, booking, service, provider, pet, amount, '
                           'hours_before_start, price_increase_percent')
        }),
        (_('Inheritance'), {
            'fields': ('inheritance', 'user'),
            'description': _('Global rules apply to all users. '
                           'User-specific rules override global ones.')
        }),
        (_('Metadata'), {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def save_model(self, request, obj, form, change):
        """
        Автоматически устанавливает создателя правила при сохранении.
        """
        if not change:  # Только при создании
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        """
        Фильтрует правила в зависимости от прав пользователя.
        """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Обычные администраторы видят только глобальные правила
        return qs.filter(inheritance='global')


custom_admin_site.register(NotificationType, NotificationTypeAdmin)
custom_admin_site.register(NotificationTemplate, NotificationTemplateAdmin)
custom_admin_site.register(NotificationPreference, NotificationPreferenceAdmin)
custom_admin_site.register(Notification, NotificationAdmin)
custom_admin_site.register(Reminder, ReminderAdmin)
custom_admin_site.register(UserNotificationSettings, UserNotificationSettingsAdmin)
custom_admin_site.register(NotificationRule, NotificationRuleAdmin)
