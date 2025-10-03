"""
Публичные API представления для каталога услуг.
Эти эндпоинты доступны без аутентификации для просмотра каталога услуг.
"""

from rest_framework import viewsets, generics, permissions
from django.db.models import Q
from .models import Service
from .serializers import ServiceSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from pets.models import PetType


class PublicServiceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Публичный ViewSet для чтения услуг и категорий.
    Доступен без аутентификации только для чтения.
    """
    queryset = Service.objects.filter(is_active=True)
    serializer_class = ServiceSerializer
    permission_classes = [permissions.AllowAny]  # Публичный доступ
    
    def get_queryset(self):
        return Service.objects.filter(is_active=True).select_related('parent')
    
    @action(detail=False, methods=['get'])
    def tree(self, request):
        """Получить дерево категорий услуг (корневые элементы)"""
        root_items = Service.objects.filter(
            parent=None, 
            is_active=True
        ).order_by('hierarchy_order', 'name')
        serializer = self.get_serializer(root_items, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def descendants(self, request, pk=None):
        """Получить потомков конкретной услуги/категории"""
        item = self.get_object()
        descendants = item.get_descendants().filter(is_active=True)
        serializer = self.get_serializer(descendants, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def ancestors(self, request, pk=None):
        """Получить предков конкретной услуги/категории"""
        item = self.get_object()
        ancestors = item.get_ancestors()
        serializer = self.get_serializer(ancestors, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Получить только категории услуг (элементы без потомков)"""
        categories = Service.objects.filter(
            children__isnull=True,
            is_active=True
        ).order_by('hierarchy_order', 'name')
        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def services(self, request):
        """Получить только услуги (элементы с потомками)"""
        services = Service.objects.filter(
            children__isnull=False,
            is_active=True
        ).order_by('hierarchy_order', 'name')
        serializer = self.get_serializer(services, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def periodic(self, request):
        """Получить периодические услуги"""
        periodic_services = Service.objects.filter(
            is_periodic=True,
            children__isnull=False,
            is_active=True
        ).order_by('hierarchy_order', 'name')
        serializer = self.get_serializer(periodic_services, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def mandatory(self, request):
        """Получить обязательные услуги"""
        mandatory_services = Service.objects.filter(
            is_mandatory=True,
            children__isnull=False,
            is_active=True
        ).order_by('hierarchy_order', 'name')
        serializer = self.get_serializer(mandatory_services, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def for_pet_type(self, request):
        """
        Получить услуги, доступные для конкретного типа животного.
        """
        pet_type_id = request.query_params.get('pet_type_id')
        if not pet_type_id:
            return Response(
                {'error': 'pet_type_id parameter is required'}, 
                status=400
            )
        
        try:
            pet_type = PetType.objects.get(id=pet_type_id)
        except PetType.DoesNotExist:
            return Response(
                {'error': 'Pet type not found'}, 
                status=404
            )
        
        # Получаем услуги, доступные для данного типа животного
        available_services = Service.objects.filter(
            Q(allowed_pet_types__isnull=True) |  # Доступны для всех типов
            Q(allowed_pet_types=pet_type),        # Или специально для этого типа
            is_active=True
        ).distinct().order_by('hierarchy_order', 'name')
        
        serializer = self.get_serializer(available_services, many=True)
        return Response(serializer.data)


class PublicServiceSearchAPIView(generics.ListAPIView):
    """
    Публичный API для поиска услуг.
    """
    serializer_class = ServiceSerializer
    permission_classes = [permissions.AllowAny]  # Публичный доступ

    def get_queryset(self):
        queryset = Service.objects.filter(is_active=True)
        query = self.request.query_params.get('q', '')
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query) |
                Q(name_en__icontains=query) |
                Q(name_ru__icontains=query) |
                Q(name_me__icontains=query) |
                Q(name_de__icontains=query)
            )
        return queryset.order_by('hierarchy_order', 'name')
