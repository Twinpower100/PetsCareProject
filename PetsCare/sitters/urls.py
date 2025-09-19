"""
URL-маршруты для API модуля передержки питомцев.

Этот модуль содержит маршруты для:
1. Управления профилями передержки
2. Поиска передержек
3. Получения профиля текущего пользователя
4. Фильтрации питомцев при создании объявления о передержке
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import SitterProfileViewSet, PetSittingAdViewSet, PetSittingResponseViewSet, SitterReviewViewSet, PetSittingViewSet, ConversationViewSet, PetFilterForSittingAPIView

router = DefaultRouter()
router.register(r'profiles', SitterProfileViewSet, basename='sitter-profile')
router.register(r'ads', PetSittingAdViewSet, basename='pet-sitting-ad')
router.register(r'responses', PetSittingResponseViewSet, basename='pet-sitting-response')
router.register(r'pet-sitting', PetSittingViewSet, basename='pet-sitting')
router.register(r'reviews', SitterReviewViewSet, basename='sitter-review')
router.register(r'conversations', ConversationViewSet, basename='conversation')

urlpatterns = [
    path('', include(router.urls)),
    path('pets/filter/', PetFilterForSittingAPIView.as_view(), name='pet-filter-for-sitting'),
] 