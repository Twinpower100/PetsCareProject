"""
URL-маршруты для API модуля каталога услуг.

Этот модуль содержит маршруты для:
1. Управления услугами
2. Управления категориями
3. Поиска услуг
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.utils.translation import gettext_lazy as _
from .api_views import (
    ServiceViewSet,
    ServiceCategoryListCreateAPIView,
    ServiceCategoryRetrieveUpdateDestroyAPIView,
    ServiceListCreateAPIView,
    ServiceRetrieveUpdateDestroyAPIView,
    ServiceSearchAPIView
)

# Создаем роутер для API
router = DefaultRouter()
router.register(r'services', ServiceViewSet, basename=_('Service'))

urlpatterns = [
    path('', include(router.urls)),
    # Эндпоинты для категорий услуг
    path('categories/', 
         ServiceCategoryListCreateAPIView.as_view(), 
         name='service-category-list-create'),
    path('categories/<int:pk>/', 
         ServiceCategoryRetrieveUpdateDestroyAPIView.as_view(), 
         name='service-category-retrieve-update-destroy'),

    # Эндпоинты для услуг
    path('services/', 
         ServiceListCreateAPIView.as_view(), 
         name='service-list-create'),
    path('services/<int:pk>/', 
         ServiceRetrieveUpdateDestroyAPIView.as_view(), 
         name='service-retrieve-update-destroy'),
    path('services/search/', 
         ServiceSearchAPIView.as_view(), 
         name='service-search'),
] 