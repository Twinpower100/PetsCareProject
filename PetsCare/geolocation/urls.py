"""
URL-маршруты для модуля геолокации.

Содержит маршруты для:
1. CRUD операций с адресами
2. Валидации адресов
3. Автодополнения
4. Геокодирования
5. Кэширования
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views, api_views

# Создаем роутер для ViewSets
router = DefaultRouter()
router.register(r'addresses', views.AddressViewSet, basename='address')
router.register(r'validations', views.AddressValidationViewSet, basename='address-validation')
router.register(r'cache', views.AddressCacheViewSet, basename='address-cache')

# URL-паттерны для API
urlpatterns = [
    # Маршруты ViewSets
    path('api/', include(router.urls)),
    
    # Дополнительные API endpoints
    path('api/autocomplete/', views.AddressAutocompleteView.as_view(), name='address-autocomplete'),
    path('api/geocode/', views.AddressGeocodeView.as_view(), name='address-geocode'),
    path('api/reverse-geocode/', views.AddressReverseGeocodeView.as_view(), name='address-reverse-geocode'),
    path('api/validate-bulk/', views.AddressValidationBulkView.as_view(), name='address-validate-bulk'),

    # API для геолокации пользователя
    path('api/user-location/', api_views.get_user_location, name='get_user_location'),
    path('api/device-location/', api_views.save_device_location, name='save_device_location'),
    path('api/map-location/', api_views.save_map_location, name='save_map_location'),
    path('api/location-info/', api_views.get_location_info, name='get_location_info'),
    path('api/clear-location/', api_views.clear_user_location, name='clear_user_location'),
    
    # API для проверки требований к адресу
    path('api/check-address-requirement/', api_views.check_address_requirement, name='check_address_requirement'),
    path('api/validate-location-for-role/', api_views.validate_location_for_role, name='validate_location_for_role'),
]

# Добавляем namespace для приложения
app_name = 'geolocation' 