"""
URL-маршруты для API модуля передержки питомцев.

Этот модуль содержит маршруты для:
1. Управления профилями передержки
2. Поиска передержек
3. Получения профиля текущего пользователя
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import SitterProfileViewSet, PetSittingAdViewSet, PetSittingResponseViewSet, ReviewViewSet, PetSittingViewSet
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

router = DefaultRouter()
router.register(r'profiles', SitterProfileViewSet, basename='sitter-profile')
router.register(r'ads', PetSittingAdViewSet, basename='pet-sitting-ad')
router.register(r'responses', PetSittingResponseViewSet, basename='pet-sitting-response')
router.register(r'pet-sitting', PetSittingViewSet, basename='pet-sitting')
router.register(r'reviews', ReviewViewSet, basename='review')

schema_view = get_schema_view(
    openapi.Info(
        title="PetCare API",
        default_version='v1',
        description="API documentation for PetCare",
    ),
    public=True,
)

urlpatterns = [
    path('', include(router.urls)),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
] 