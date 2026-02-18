"""
API представления для управления доступом.

Этот модуль содержит представления для:
1. Управления доступом к карточкам питомцев
2. Просмотра логов доступа
"""

from rest_framework import viewsets, permissions
from django.db.models import Q
from .models import PetAccess, AccessLog
from .serializers import PetAccessSerializer, AccessLogSerializer


class PetAccessViewSet(viewsets.ModelViewSet):
    """
    API представление для управления доступом к карточкам питомцев.
    
    Особенности:
    - CRUD операции с доступами
    - Автоматическая валидация
    - Проверка прав доступа
    """
    queryset = PetAccess.objects.all()
    serializer_class = PetAccessSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return PetAccess.objects.none()
        user = self.request.user
        return PetAccess.objects.filter(
            Q(granted_to=user) |
            Q(granted_by=user) |
            Q(pet__owners=user)
        ).distinct()


class AccessLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API представление для просмотра логов доступа.
    
    Особенности:
    - Просмотр истории действий
    - Фильтрация по пользователям и действиям
    - Только для чтения
    """
    queryset = AccessLog.objects.all()
    serializer_class = AccessLogSerializer 
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return AccessLog.objects.none()
        user = self.request.user
        return AccessLog.objects.filter(
            Q(user=user) |
            Q(access__granted_to=user) |
            Q(access__granted_by=user)
        ).distinct()