from rest_framework import viewsets, generics, permissions, status
from django.db.models import Q
from .models import Service
from .serializers import ServiceSerializer, ServiceCompatibilitySerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from pets.models import PetType


class ServiceViewSet(viewsets.ModelViewSet):
    """
    ViewSet для работы с услугами и категориями.
    Поддерживает иерархическую структуру.
    """
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Service.objects.select_related('parent').all()
    
    @action(detail=False, methods=['get'])
    def tree(self, request):
        root_items = Service.objects.filter(parent=None)
        serializer = self.get_serializer(root_items, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def descendants(self, request, pk=None):
        item = self.get_object()
        descendants = item.get_descendants()
        serializer = self.get_serializer(descendants, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def ancestors(self, request, pk=None):
        item = self.get_object()
        ancestors = item.get_ancestors()
        serializer = self.get_serializer(ancestors, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def categories(self, request):
        categories = Service.objects.filter(children__isnull=True)
        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def services(self, request):
        services = Service.objects.filter(children__isnull=False)
        serializer = self.get_serializer(services, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def periodic(self, request):
        periodic_services = Service.objects.filter(
            is_periodic=True,
            children__isnull=False
        )
        serializer = self.get_serializer(periodic_services, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def mandatory(self, request):
        mandatory_services = Service.objects.filter(
            is_mandatory=True,
            children__isnull=False
        )
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
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            pet_type = PetType.objects.get(id=pet_type_id)
        except PetType.DoesNotExist:
            return Response(
                {'error': 'Pet type not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Получаем услуги, доступные для данного типа животного
        available_services = Service.objects.filter(
            Q(allowed_pet_types__isnull=True) |  # Доступны для всех типов
            Q(allowed_pet_types=pet_type)        # Или специально для этого типа
        ).distinct()
        
        serializer = self.get_serializer(available_services, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def check_compatibility(self, request):
        """
        Проверить совместимость услуги с типом животного.
        """
        serializer = ServiceCompatibilitySerializer(data=request.data)
        if serializer.is_valid():
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ServiceCategoryListCreateAPIView(generics.ListCreateAPIView):
    """
    API для получения списка категорий и создания новых.
    """
    queryset = Service.objects.filter(children__isnull=True)
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated]


class ServiceCategoryRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для получения, обновления и удаления категории.
    """
    queryset = Service.objects.filter(children__isnull=True)
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated]


class ServiceListCreateAPIView(generics.ListCreateAPIView):
    """
    API для получения списка услуг и создания новых.
    """
    queryset = Service.objects.filter(children__isnull=False)
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated]


class ServiceRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для получения, обновления и удаления услуги.
    """
    queryset = Service.objects.filter(children__isnull=False)
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated]


class ServiceSearchAPIView(generics.ListAPIView):
    """
    API для поиска услуг.
    """
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Service.objects.all()
        query = self.request.query_params.get('q', '')
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query)
            )
        return queryset 


class PublicServiceCategoriesAPIView(generics.ListAPIView):
    """
    Публичный API для получения корневых категорий услуг (уровень 0).
    Доступен без аутентификации для отображения в подвале и навигации.
    """
    serializer_class = ServiceSerializer
    permission_classes = [permissions.AllowAny]  # Публичный доступ

    def get_queryset(self):
        """
        Возвращает только корневые категории услуг (parent=None, level=0).
        """
        return Service.objects.filter(
            parent=None,
            level=0,
            is_active=True
        ).order_by('hierarchy_order', 'name')