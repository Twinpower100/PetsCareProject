"""
URL routes for the providers module.

Этот модуль определяет API эндпоинты для:
1. Управления провайдерами услуг
2. Управления сотрудниками
3. Управления расписаниями
4. Поиска провайдеров по геолокации
5. Расширенного поиска ситтеров

Основные маршруты:
- /api/providers/ - CRUD операции с провайдерами
- /api/employees/ - CRUD операции с сотрудниками
- /api/schedules/ - Управление расписаниями
- /api/search/distance/ - Поиск провайдеров по расстоянию
- /api/search/sitters/advanced/ - Расширенный поиск ситтеров
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views

# Создаем роутер для ViewSets
router = DefaultRouter()
# router.register(r'providers', api_views.ProviderViewSet, basename='provider')  # не существует
# router.register(r'employees', api_views.EmployeeViewSet, basename='employee')  # не существует
# router.register(r'schedules', api_views.ScheduleViewSet, basename='schedule')  # не существует
# router.register(r'provider-services', api_views.ProviderServiceViewSet, basename='provider-service')  # не существует

# URL-паттерны для API
urlpatterns = [
    # Маршруты ViewSets
    path('api/', include(router.urls)),
    
    # Дополнительные API endpoints
    path('api/search/', api_views.ProviderSearchAPIView.as_view(), name='provider-search'),
    path('api/search/distance/', api_views.ProviderSearchByDistanceAPIView.as_view(), name='provider-search-distance'),
    path('api/search/sitters/advanced/', api_views.SitterAdvancedSearchByDistanceAPIView.as_view(), name='sitter-advanced-search'),
    
    # Маршруты для проверки доступности и цен
    path('api/providers/<int:provider_id>/availability/', 
         api_views.check_provider_availability, 
         name='provider-availability'),
    path('api/providers/<int:provider_id>/prices/', 
         api_views.get_provider_prices, 
         name='provider-prices'),
    
    # Маршруты для управления сотрудниками
    path('api/employees/<int:employee_id>/update/', 
         api_views.EmployeeProviderUpdateAPIView.as_view(), 
         name='employee-update'),
    path('api/employees/<int:employee_id>/deactivate/', 
         api_views.EmployeeDeactivateAPIView.as_view(), 
         name='employee-deactivate'),
    
    # Маршруты для заявок на вступление
    path('api/join-requests/', 
         api_views.EmployeeJoinRequestCreateAPIView.as_view(), 
         name='join-request-create'),
    path('api/join-requests/approve/', 
         api_views.EmployeeJoinRequestApproveAPIView.as_view(), 
         name='join-request-approve'),
    path('api/join-requests/confirm/', 
         api_views.EmployeeProviderConfirmAPIView.as_view(), 
         name='join-request-confirm'),
    
    # Маршруты для уведомлений
    path('api/employees/delete-notify/', 
         api_views.EmployeeAccountDeleteNotifyAPIView.as_view(), 
         name='employee-delete-notify'),
    
    # Маршруты для массовых операций
    path('api/work-slots/bulk/', 
         api_views.EmployeeWorkSlotBulkAPIView.as_view(), 
         name='work-slots-bulk'),
    path('api/schedule-patterns/apply/', 
         api_views.SchedulePatternApplyAPIView.as_view(), 
         name='schedule-pattern-apply'),

    # New API endpoints for GAPs #1 and #2
    path('api/providers/<int:provider_id>/available-slots/', api_views.get_provider_available_slots, name='provider-available-slots'),
    path('api/providers/search/map/availability/', api_views.search_providers_map_availability, name='providers-map-availability'),
]

# Добавляем namespace для приложения
app_name = 'providers' 