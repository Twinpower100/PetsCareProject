"""
URL маршруты для аналитики.

Этот модуль содержит URL маршруты для:
1. Аналитики роста пользователей
2. Производительности учреждений
3. Трендов выручки
4. Поведенческой аналитики
"""

from django.urls import path
from . import api_views

app_name = 'analytics'

urlpatterns = [
    # Аналитика
    path('api/analytics/user-growth/', api_views.UserGrowthAnalyticsAPIView.as_view(), name='user-growth'),
    path('api/analytics/provider-performance/', api_views.ProviderPerformanceAnalyticsAPIView.as_view(), name='provider-performance'),
    path('api/analytics/revenue-trends/', api_views.RevenueTrendsAnalyticsAPIView.as_view(), name='revenue-trends'),
    path('api/analytics/behavioral/', api_views.BehavioralAnalyticsAPIView.as_view(), name='behavioral'),
] 