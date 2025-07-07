"""
URL-маршруты для системы рейтингов и жалоб.

Этот модуль содержит:
1. URL-маршруты для API рейтингов
2. URL-маршруты для API отзывов
3. URL-маршруты для API жалоб
4. URL-маршруты для подозрительной активности
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views

# Создаем роутер для API
router = DefaultRouter()
router.register(r'ratings', api_views.RatingViewSet)
router.register(r'reviews', api_views.ReviewViewSet)
router.register(r'complaints', api_views.ComplaintViewSet)
router.register(r'complaint-responses', api_views.ComplaintResponseViewSet)
router.register(r'suspicious-activities', api_views.SuspiciousActivityViewSet)

app_name = 'ratings'

urlpatterns = [
    # API маршруты
    path('api/', include(router.urls)),
] 