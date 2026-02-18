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
from . import offer_api_views

# Создаем роутер для ViewSets
router = DefaultRouter()
# router.register(r'providers', api_views.ProviderListCreateAPIView, basename='provider')  # APIView, не ViewSet
# router.register(r'employees', api_views.EmployeeListCreateAPIView, basename='employee')  # APIView, не ViewSet
# router.register(r'schedules', api_views.ScheduleListCreateAPIView, basename='schedule')  # APIView, не ViewSet
# ProviderService API удален - используйте ProviderLocationService API

# URL-паттерны для API согласно ФД
urlpatterns = [
    # Маршруты ViewSets
    path('', include(router.urls)),
    
    # CRUD endpoints согласно ФД
    path('providers/', api_views.ProviderListCreateAPIView.as_view(), name='provider-list-create'),
    path('providers/<int:pk>/', api_views.ProviderRetrieveUpdateDestroyAPIView.as_view(), name='provider-detail'),
    path('employees/', api_views.EmployeeListCreateAPIView.as_view(), name='employee-list-create'),
    path('employees/<int:pk>/', api_views.EmployeeRetrieveUpdateDestroyAPIView.as_view(), name='employee-detail'),
    path('schedules/', api_views.ScheduleListCreateAPIView.as_view(), name='schedule-list-create'),
    path('schedules/<int:pk>/', api_views.ScheduleRetrieveUpdateDestroyAPIView.as_view(), name='schedule-detail'),
    # Поиск согласно ФД
    path('search/', api_views.ProviderSearchAPIView.as_view(), name='provider-search'),
    
    # Управление сотрудниками согласно ФД
    path('employees/<int:employee_id>/update/', api_views.EmployeeProviderUpdateAPIView.as_view(), name='employee-update'),
    path('employees/<int:employee_id>/deactivate/', api_views.EmployeeDeactivateAPIView.as_view(), name='employee-deactivate'),
    
    # Заявки на вступление согласно ФД
    path('join-requests/', api_views.EmployeeJoinRequestCreateAPIView.as_view(), name='join-request-create'),
    path('join-requests/approve/', api_views.EmployeeJoinRequestApproveAPIView.as_view(), name='join-request-approve'),
    path('join-requests/confirm/', api_views.EmployeeProviderConfirmAPIView.as_view(), name='join-request-confirm'),
    
    # Дополнительные функции провайдеров
    path('providers/<int:provider_id>/admins/', api_views.ProviderAdminListAPIView.as_view(), name='provider-admin-list'),
    path('providers/<int:provider_id>/admins/invite/', api_views.ProviderAdminInviteAPIView.as_view(), name='provider-admin-invite'),
    path('providers/<int:provider_id>/admins/assign-self/', api_views.ProviderAdminAssignSelfAPIView.as_view(), name='provider-admin-assign-self'),
    path('provider-owner-manager-invite/accept/', api_views.AcceptProviderOwnerManagerInviteAPIView.as_view(), name='provider-owner-manager-invite-accept'),
    path('providers/<int:provider_id>/availability/', api_views.check_provider_availability, name='check-provider-availability'),
    path('providers/<int:provider_id>/available-catalog-services/', api_views.ProviderAvailableCatalogServicesAPIView.as_view(), name='provider-available-catalog-services'),
    path('providers/<int:provider_id>/prices/', api_views.get_provider_prices, name='get-provider-prices'),
    path('providers/<int:provider_id>/slots/', api_views.get_provider_available_slots, name='get-provider-available-slots'),
    path('providers/search/map/', api_views.search_providers_map_availability, name='search-providers-map-availability'),
    
    # API для локаций провайдера
    path('provider-locations/', api_views.ProviderLocationListCreateAPIView.as_view(), name='provider-location-list-create'),
    path('provider-locations/<int:pk>/', api_views.ProviderLocationRetrieveUpdateDestroyAPIView.as_view(), name='provider-location-detail'),
    # Руководитель филиала: установка по email (свой email — сразу, чужой — инвайт с кодом), снятие, принятие инвайта
    path('provider-locations/<int:pk>/set-manager/', api_views.SetLocationManagerAPIView.as_view(), name='location-set-manager'),
    path('provider-locations/<int:pk>/manager/', api_views.RemoveLocationManagerAPIView.as_view(), name='location-remove-manager'),
    path('location-manager-invite/accept/', api_views.AcceptLocationManagerInviteAPIView.as_view(), name='location-manager-invite-accept'),
    # Персонал филиала: инвайты и список
    path('provider-locations/<int:pk>/invite-staff/', api_views.InviteLocationStaffAPIView.as_view(), name='location-invite-staff'),
    path('provider-locations/<int:pk>/staff/', api_views.LocationStaffListAPIView.as_view(), name='location-staff-list'),
    path('provider-locations/<int:pk>/staff-invites/<int:invite_id>/', api_views.LocationStaffInviteDestroyAPIView.as_view(), name='location-staff-invite-destroy'),
    path('provider-locations/<int:location_pk>/staff/<int:employee_id>/services/', api_views.LocationStaffServicesAPIView.as_view(), name='location-staff-services'),
    path('provider-locations/<int:location_pk>/staff/<int:employee_id>/services/add-by-category/', api_views.LocationStaffServicesAddByCategoryAPIView.as_view(), name='location-staff-services-add-by-category'),
    path('provider-locations/<int:location_pk>/staff/<int:employee_id>/schedules/', api_views.LocationStaffSchedulePatternAPIView.as_view(), name='location-staff-schedule-pattern'),
    path('location-staff-invite/accept/', api_views.AcceptLocationStaffInviteAPIView.as_view(), name='location-staff-invite-accept'),
    # Расписание работы локации (дни, время открытия/закрытия)
    path('provider-locations/<int:location_pk>/schedules/', api_views.LocationScheduleListCreateAPIView.as_view(), name='location-schedule-list-create'),
    path('provider-locations/<int:location_pk>/schedules/<int:pk>/', api_views.LocationScheduleRetrieveUpdateDestroyAPIView.as_view(), name='location-schedule-detail'),
    # Смены в праздничные дни
    path('provider-locations/<int:location_pk>/holiday-shifts/', api_views.HolidayShiftListCreateAPIView.as_view(), name='holiday-shift-list-create'),
    path('provider-locations/<int:location_pk>/holiday-shifts/<int:pk>/', api_views.HolidayShiftRetrieveUpdateDestroyAPIView.as_view(), name='holiday-shift-detail'),
    
    # API для услуг локаций провайдера
    path('provider-location-services/', api_views.ProviderLocationServiceListCreateAPIView.as_view(), name='provider-location-service-list-create'),
    path('provider-location-services/<int:pk>/', api_views.ProviderLocationServiceRetrieveUpdateDestroyAPIView.as_view(), name='provider-location-service-detail'),
    # Матрица цен по типу животного и размеру (прайс)
    path('provider-locations/<int:pk>/price-matrix/', api_views.LocationPriceMatrixAPIView.as_view(), name='location-price-matrix'),
    path('provider-locations/<int:location_pk>/services/<int:location_service_id>/prices/', api_views.LocationServicePricesUpdateAPIView.as_view(), name='location-service-prices-update'),
    
    # API для публичной оферты
    path('providers/<int:provider_id>/offer/', offer_api_views.ProviderOfferAPIView.as_view(), name='provider-offer'),
    path('providers/<int:provider_id>/accept-offer/', offer_api_views.ProviderAcceptOfferAPIView.as_view(), name='provider-accept-offer'),
    path('providers/<int:provider_id>/verify-vat/', offer_api_views.ProviderVerifyVATAPIView.as_view(), name='provider-verify-vat'),

    # Подсказки/правила для реквизитов (шаг 3 регистрации провайдера)
    path('requisites/rules/', api_views.RequisitesValidationRulesAPIView.as_view(), name='requisites-validation-rules'),
]

# Добавляем namespace для приложения
app_name = 'providers' 