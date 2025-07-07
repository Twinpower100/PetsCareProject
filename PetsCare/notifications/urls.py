"""
URL маршруты для уведомлений.

Этот модуль содержит URL маршруты для:
1. API уведомлений
2. Настроек уведомлений
3. Административных функций
4. Верификации email
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views
from .api_views import (
    NotificationTypeListCreateAPIView, NotificationTypeRetrieveUpdateDestroyAPIView,
    NotificationTemplateListCreateAPIView, NotificationTemplateRetrieveUpdateDestroyAPIView,
    NotificationPreferenceListCreateAPIView, NotificationPreferenceRetrieveUpdateDestroyAPIView,
    NotificationListCreateAPIView, NotificationRetrieveUpdateDestroyAPIView,
    NotificationMarkAsReadAPIView, ReminderListCreateAPIView,
    ReminderRetrieveUpdateDestroyAPIView, UserNotificationSettingsListCreateAPIView,
    UserNotificationSettingsRetrieveUpdateDestroyAPIView
)

# Создаем роутер для API
router = DefaultRouter()
router.register(r'notifications', api_views.NotificationViewSet, basename='notification')
router.register(r'preferences', api_views.NotificationPreferenceViewSet, basename='notification-preference')
router.register(r'settings', api_views.UserNotificationSettingsViewSet, basename='notification-settings')

app_name = 'notifications'

urlpatterns = [
    # API маршруты
    path('api/', include(router.urls)),
    
    # Дополнительные API endpoints
    path('api/notifications/unread-count/', 
         api_views.NotificationViewSet.as_view({'get': 'unread_count'}),
         name='notification-unread-count'),
    
    path('api/notifications/<int:pk>/mark-as-read/',
         api_views.NotificationViewSet.as_view({'post': 'mark_as_read'}),
         name='notification-mark-as-read'),
    
    path('api/notifications/mark-all-as-read/',
         api_views.NotificationViewSet.as_view({'post': 'mark_all_as_read'}),
         name='notification-mark-all-as-read'),
    
    path('api/notifications/statistics/',
         api_views.NotificationViewSet.as_view({'get': 'statistics'}),
         name='notification-statistics'),
    
    path('api/notifications/test/',
         api_views.NotificationViewSet.as_view({'post': 'test_notification'}),
         name='notification-test'),
    
    path('api/preferences/all/',
         api_views.NotificationPreferenceViewSet.as_view({'get': 'all_preferences'}),
         name='preferences-all'),
    
    path('api/preferences/reset/',
         api_views.NotificationPreferenceViewSet.as_view({'post': 'reset_to_defaults'}),
         name='preferences-reset'),
    
    path('api/settings/bulk-update/',
         api_views.UserNotificationSettingsViewSet.as_view({'post': 'bulk_update'}),
         name='settings-bulk-update'),
    
    path('api/settings/available-options/',
         api_views.UserNotificationSettingsViewSet.as_view({'get': 'available_options'}),
         name='settings-available-options'),
    
    # API endpoints для уведомлений
    path('api/notifications/', api_views.get_notifications, name='api_notifications'),
    path('api/notifications/<int:notification_id>/read/', api_views.mark_notification_as_read, name='api_mark_read'),
    path('api/notifications/read-all/', api_views.mark_all_notifications_as_read, name='api_mark_all_read'),
    path('api/notifications/<int:notification_id>/delete/', api_views.delete_notification, name='api_delete_notification'),
    path('api/notifications/delete-all/', api_views.delete_all_notifications, name='api_delete_all_notifications'),
    path('api/notifications/stats/', api_views.get_notification_stats, name='api_notification_stats'),
    path('api/notifications/preferences/', api_views.update_notification_preferences, name='api_update_preferences'),
    path('api/notifications/templates/', api_views.get_notification_templates, name='api_notification_templates'),
    path('api/notifications/test/', api_views.test_notification, name='api_test_notification'),
    path('api/notifications/history/', api_views.get_notification_history, name='api_notification_history'),
    
    # Webhook для push-уведомлений
    path('api/notifications/push-token/', api_views.update_push_token, name='api_update_push_token'),
    
    # Админские endpoints
    path('api/admin/notifications/', api_views.admin_get_notifications, name='api_admin_notifications'),
    path('api/admin/notifications/send/', api_views.admin_send_notification, name='api_admin_send_notification'),
    path('api/admin/notifications/bulk-send/', api_views.admin_bulk_send_notifications, name='api_admin_bulk_send'),
    path('api/admin/notifications/analytics/', api_views.admin_get_analytics, name='api_admin_analytics'),
] 