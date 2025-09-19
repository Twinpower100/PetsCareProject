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
    # Audit endpoints
    path('audit/actions/', api_views.UserActionViewSet.as_view(), name='user-actions'),
    path('audit/actions/statistics/', api_views.UserActionStatisticsView.as_view(), name='user-actions-statistics'),
    path('audit/actions/export/', api_views.UserActionExportView.as_view(), name='user-actions-export'),
    path('audit/actions/cleanup/', api_views.UserActionCleanupView.as_view(), name='user-actions-cleanup'),
    path('audit/activity/<int:user_id>/', api_views.UserActivityView.as_view(), name='user-activity'),
    path('audit/security/', api_views.SecurityAuditView.as_view(), name='security-audit'),
    path('audit/statistics/', api_views.AuditStatisticsView.as_view(), name='audit-statistics'),
] 