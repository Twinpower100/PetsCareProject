"""
URL маршруты для системных настроек.

Этот модуль содержит URL маршруты для:
1. Управления системными настройками
2. Управления функциями системы
3. Проверки здоровья системы
"""

from django.urls import path
from . import api_views

app_name = 'settings'

urlpatterns = [
    path('branding/', api_views.PublicBrandingAPIView.as_view(), name='public-branding'),
    path('support-requests/', api_views.PublicSupportRequestCreateAPIView.as_view(), name='support-request-create'),
    # Системные настройки
    path('system/', api_views.SystemSettingsAPIView.as_view(), name='system-settings'),
    path('features/', api_views.FeatureSettingsAPIView.as_view(), name='feature-settings'),
    path('health/', api_views.SystemHealthAPIView.as_view(), name='system-health'),
] 
