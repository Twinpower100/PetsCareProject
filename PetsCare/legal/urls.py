"""
URL configuration for the legal module.

Этот модуль содержит конфигурацию URL для:
1. API юридических документов
2. API для провайдеров (оферты, дополнения)
3. Публичный API (Privacy Policy, Terms of Service)
4. API принятия документов
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views

# ВАЖНО: app_name должен совпадать с именем в кортеже include()
app_name = 'legal'

router = DefaultRouter()
router.register(r'legal/admin-documents', api_views.LegalDocumentViewSet, basename='legal-document')

# ВАЖНО: Порядок URL-паттернов критичен!
# Более специфичные пути должны быть ПЕРЕД менее специфичными

urlpatterns = [
    # API принятия документов - более специфичный путь (с /accept/), должен быть ПЕРВЫМ
    # Это важно, чтобы /legal/documents/1/accept/ не сопоставлялся с /legal/documents/<str:document_type>/
    path('legal/documents/<int:document_id>/accept/', api_views.DocumentAcceptanceAPIView.as_view(), name='document-accept'),
    
    # Публичный API (без авторизации) - обрабатывается ВТОРЫМ
    # ВАЖНО: Этот путь должен быть ПОСЛЕ более специфичных
    path('legal/documents/<str:document_type>/', api_views.PublicDocumentAPIView.as_view(), name='public-document'),
    
    # API для провайдеров
    path('legal/providers/<int:provider_id>/offer/', api_views.ProviderOfferAPIView.as_view(), name='provider-offer'),
    path('legal/providers/<int:provider_id>/regional-addendums/', api_views.ProviderRegionalAddendumsAPIView.as_view(), name='provider-regional-addendums'),
    
    # API конфигурации стран
    path('legal/countries/<str:country_code>/config/', api_views.CountryLegalConfigAPIView.as_view(), name='country-config'),
    
    # API для мастера регистрации провайдера
    path('legal/registration/country/<str:country_code>/offer/', api_views.CountryOfferForRegistrationAPIView.as_view(), name='country-offer-for-registration'),
]

urlpatterns += router.urls
