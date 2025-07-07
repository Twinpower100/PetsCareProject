"""
API представления для управления доступом.

Этот модуль содержит представления для:
1. Управления доступом к карточкам питомцев
2. Просмотра логов доступа
"""

from rest_framework import viewsets
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


class AccessLogViewSet(viewsets.ModelViewSet):
    """
    API представление для просмотра логов доступа.
    
    Особенности:
    - Просмотр истории действий
    - Фильтрация по пользователям и действиям
    - Только для чтения
    """
    queryset = AccessLog.objects.all()
    serializer_class = AccessLogSerializer 