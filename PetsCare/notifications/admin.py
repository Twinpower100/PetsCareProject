from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    NotificationType, NotificationTemplate,
    NotificationPreference, Notification, Reminder, UserNotificationSettings
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
    list_display = ('user', 'notification_type', 'email_enabled', 'push_enabled')
    list_filter = ('email_enabled', 'push_enabled', 'notification_type')
    search_fields = ('user__username', 'user__email', 'notification_type')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('user', 'notification_type')
        }),
        (_('Notification Channels'), {
            'fields': ('email_enabled', 'push_enabled')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


custom_admin_site.register(NotificationType, NotificationTypeAdmin)
custom_admin_site.register(NotificationTemplate, NotificationTemplateAdmin)
custom_admin_site.register(NotificationPreference, NotificationPreferenceAdmin)
custom_admin_site.register(Notification, NotificationAdmin)
custom_admin_site.register(Reminder, ReminderAdmin)
custom_admin_site.register(UserNotificationSettings, UserNotificationSettingsAdmin)
