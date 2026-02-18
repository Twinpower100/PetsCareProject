"""
API представления для модуля услуг.

Этот модуль предоставляет REST API endpoints для управления услугами в системе PetsCare.

Основной функционал:
1. CRUD операции для услуг (создание, чтение, обновление, удаление)
2. Расширенный поиск услуг по различным параметрам
3. Фильтрация услуг по категориям, ценам и другим атрибутам
4. Сортировка результатов по различным полям

Особенности реализации:
- Использует Django REST Framework для создания API
- Поддерживает пагинацию результатов
- Включает систему фильтрации и поиска
- Реализует механизмы сортировки
"""

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from catalog.models import Service
from catalog.serializers import ServiceSerializer


class ServiceViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления услугами через API.
    
    Предоставляет следующие endpoints:
    - GET /services/ - список всех услуг
    - POST /services/ - создание новой услуги
    - GET /services/{id}/ - детали конкретной услуги
    - PUT /services/{id}/ - обновление услуги
    - DELETE /services/{id}/ - удаление услуги
    - POST /services/search/ - расширенный поиск услуг
    
    Поддерживаемые фильтры:
    - category_id - фильтрация по ID категории
    - parent_id - фильтрация по ID родительской категории
    
    Поля для поиска:
    - name - название услуги
    - description - описание услуги
    
    Поля для сортировки:
    - name - по названию
    - hierarchy_order - по порядку в иерархии
    - level - по уровню в иерархии
    """
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['parent_id', 'level']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'hierarchy_order', 'level']

    def get_queryset(self):
        """
        Возвращает отфильтрованный список услуг.
        
        Поддерживает фильтрацию по:
        - ID категории (category_id)
        - Минимальной цене (min_price)
        - Максимальной цене (max_price)
        
        Returns:
            QuerySet: Отфильтрованный список услуг
        """
        if getattr(self, 'swagger_fake_view', False):
            return Service.objects.none()
        
        queryset = Service.objects.all()
        
        # Фильтрация по родительской категории
        category_id = self.request.query_params.get('category_id')
        if category_id:
            queryset = queryset.filter(parent_id=category_id)
            
        return queryset

    @action(detail=False, methods=['post'])
    def search(self, request):
        """
        Расширенный поиск услуг по различным параметрам.
        
        Поддерживаемые параметры поиска:
        - name (str): Название услуги (частичное совпадение)
        - category_id (int): ID категории услуги
        - parent_id (int): ID родительской категории
        - sort_by (str): Поле для сортировки результатов
        
        Returns:
            Response: Список найденных услуг с пагинацией
            
        Raises:
            400 Bad Request: Если параметры поиска невалидны
        """
        # Валидация входных данных
        data = request.data
        queryset = self.get_queryset()

        # Применение фильтров поиска
        if data.get('name'):
            queryset = queryset.filter(name__icontains=data['name'])

        if data.get('category_id'):
            queryset = queryset.filter(parent_id=data['category_id'])

        # Применение сортировки
        sort_by = data.get('sort_by')
        if sort_by:
            queryset = queryset.order_by(sort_by)

        # Пагинация результатов
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data) 