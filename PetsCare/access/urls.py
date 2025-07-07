"""
Конфигурация URL для приложения access.

Этот модуль содержит маршруты для:
1. API доступа к карточкам питомцев
2. API логов доступа
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import PetAccessViewSet, AccessLogViewSet

# Создаем роутер для API
router = DefaultRouter()
router.register(r'accesses', PetAccessViewSet)
router.register(r'logs', AccessLogViewSet)

# Определяем маршруты
urlpatterns = [
    path('', include(router.urls)),
] 