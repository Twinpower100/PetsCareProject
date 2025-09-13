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
    path('api/audit/actions/', api_views.UserActionViewSet.as_view({'get': 'list'}), name='user-actions'),
    path('api/audit/actions/statistics/', api_views.UserActionViewSet.as_view({'get': 'statistics'}), name='user-actions-statistics'),
    path('api/audit/actions/export/', api_views.UserActionViewSet.as_view({'post': 'export'}), name='user-actions-export'),
    path('api/audit/actions/cleanup/', api_views.UserActionViewSet.as_view({'post': 'cleanup'}), name='user-actions-cleanup'),
    path('api/audit/user-activity/<int:user_id>/', api_views.UserActivityView.as_view(), name='user-activity'),
    path('api/audit/security/', api_views.SecurityAuditView.as_view(), name='security-audit'),
    path('api/audit/statistics/', api_views.AuditStatisticsView.as_view(), name='audit-statistics'),
] 