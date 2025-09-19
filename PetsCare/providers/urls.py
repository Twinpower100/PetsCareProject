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
# router.register(r'providers', api_views.ProviderListCreateAPIView, basename='provider')  # APIView, не ViewSet
# router.register(r'employees', api_views.EmployeeListCreateAPIView, basename='employee')  # APIView, не ViewSet
# router.register(r'schedules', api_views.ScheduleListCreateAPIView, basename='schedule')  # APIView, не ViewSet
# router.register(r'provider-services', api_views.ProviderServiceListCreateAPIView, basename='provider-service')  # APIView, не ViewSet

# URL-паттерны для API согласно ФД
urlpatterns = [
    # Маршруты ViewSets
    path('api/', include(router.urls)),
    
    # CRUD endpoints согласно ФД
    path('api/providers/', api_views.ProviderListCreateAPIView.as_view(), name='provider-list-create'),
    path('api/providers/<int:pk>/', api_views.ProviderRetrieveUpdateDestroyAPIView.as_view(), name='provider-detail'),
    path('api/employees/', api_views.EmployeeListCreateAPIView.as_view(), name='employee-list-create'),
    path('api/employees/<int:pk>/', api_views.EmployeeRetrieveUpdateDestroyAPIView.as_view(), name='employee-detail'),
    path('api/schedules/', api_views.ScheduleListCreateAPIView.as_view(), name='schedule-list-create'),
    path('api/schedules/<int:pk>/', api_views.ScheduleRetrieveUpdateDestroyAPIView.as_view(), name='schedule-detail'),
    path('api/provider-services/', api_views.ProviderServiceListCreateAPIView.as_view(), name='provider-service-list-create'),
    path('api/provider-services/<int:pk>/', api_views.ProviderServiceRetrieveUpdateDestroyAPIView.as_view(), name='provider-service-detail'),
    
    # Поиск согласно ФД
    path('api/search/', api_views.ProviderSearchAPIView.as_view(), name='provider-search'),
    
    # Управление сотрудниками согласно ФД
    path('api/employees/<int:employee_id>/update/', api_views.EmployeeProviderUpdateAPIView.as_view(), name='employee-update'),
    path('api/employees/<int:employee_id>/deactivate/', api_views.EmployeeDeactivateAPIView.as_view(), name='employee-deactivate'),
    
    # Заявки на вступление согласно ФД
    path('api/join-requests/', api_views.EmployeeJoinRequestCreateAPIView.as_view(), name='join-request-create'),
    path('api/join-requests/approve/', api_views.EmployeeJoinRequestApproveAPIView.as_view(), name='join-request-approve'),
    path('api/join-requests/confirm/', api_views.EmployeeProviderConfirmAPIView.as_view(), name='join-request-confirm'),
    
    # Дополнительные функции провайдеров
    path('api/providers/<int:provider_id>/availability/', api_views.check_provider_availability, name='check-provider-availability'),
    path('api/providers/<int:provider_id>/prices/', api_views.get_provider_prices, name='get-provider-prices'),
    path('api/providers/<int:provider_id>/slots/', api_views.get_provider_available_slots, name='get-provider-available-slots'),
    path('api/providers/search/map/', api_views.search_providers_map_availability, name='search-providers-map-availability'),
]

# Добавляем namespace для приложения
app_name = 'providers' 