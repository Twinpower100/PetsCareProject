"""
URL маршруты для системы аудита.

Этот модуль содержит API endpoints для:
1. Просмотра логов аудита
2. Экспорта логов
3. Аналитики активности пользователей
4. Системных событий
"""

from django.urls import path
from . import api_views

app_name = 'audit'

urlpatterns = [
    # Основные API для аудита
    path('api/audit/logs/', api_views.AuditLogListView.as_view(), name='audit-logs'),
    path('api/audit/logs/export/', api_views.AuditLogExportView.as_view(), name='audit-logs-export'),
    path('api/audit/user-activity/<int:user_id>/', api_views.UserActivityView.as_view(), name='user-activity'),
    path('api/audit/system-events/', api_views.SystemEventsView.as_view(), name='system-events'),
    path('api/audit/statistics/', api_views.AuditStatisticsView.as_view(), name='audit-statistics'),
    
    # Дополнительные endpoints
    path('api/audit/logs/filter/', api_views.AuditLogFilterView.as_view(), name='audit-logs-filter'),
    path('api/audit/logs/search/', api_views.AuditLogSearchView.as_view(), name='audit-logs-search'),
    path('api/audit/logs/cleanup/', api_views.AuditLogCleanupView.as_view(), name='audit-logs-cleanup'),
] 