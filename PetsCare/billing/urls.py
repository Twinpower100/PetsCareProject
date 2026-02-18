"""
URL configuration for the billing module.

Этот модуль содержит конфигурацию URL для:
1. API платежей
2. API счетов
3. API возвратов
4. API типов контрактов
5. API блокировок учреждений
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views

# Создаем роутер для API
router = DefaultRouter()
# ContractTypeViewSet и ContractViewSet удалены - используется LegalDocument и DocumentAcceptance
router.register(r'payments', api_views.PaymentViewSet)
router.register(r'invoices', api_views.InvoiceViewSet)
router.register(r'refunds', api_views.RefundViewSet)

urlpatterns = [
    path('', include(router.urls)),
    
    # API для блокировок учреждений
    path('blocking-rules/', api_views.BlockingRuleListCreateAPIView.as_view(), name='blocking-rules-list'),
    path('blocking-rules/<int:pk>/', api_views.BlockingRuleRetrieveUpdateDestroyAPIView.as_view(), name='blocking-rules-detail'),
    
    path('provider-blockings/', api_views.ProviderBlockingListAPIView.as_view(), name='provider-blockings-list'),
    path('provider-blockings/<int:pk>/', api_views.ProviderBlockingRetrieveAPIView.as_view(), name='provider-blockings-detail'),
    path('provider-blockings/<int:blocking_id>/resolve/', api_views.ProviderBlockingResolveAPIView.as_view(), name='provider-blockings-resolve'),
    
    path('providers/<int:provider_id>/blocking-status/', api_views.ProviderBlockingStatusAPIView.as_view(), name='provider-blocking-status'),
    path('providers/<int:provider_id>/blocking-history/', api_views.ProviderBlockingHistoryAPIView.as_view(), name='provider-blocking-history'),
    
    path('blocking-notifications/', api_views.BlockingNotificationListAPIView.as_view(), name='blocking-notifications-list'),
    path('blocking-notifications/<int:notification_id>/retry/', api_views.BlockingNotificationRetryAPIView.as_view(), name='blocking-notifications-retry'),
    
    # API для получения списка валют
    path('currencies/', api_views.CurrencyListAPIView.as_view(), name='currencies-list'),
    
    # API для workflow согласования контрактов удалено - используется PublicOffer и ProviderOfferAcceptance
] 