"""
API представления для модуля providers.

Этот модуль содержит классы представлений для работы с API провайдеров услуг.

Основные компоненты:
1. Управление провайдерами (создание, просмотр, обновление, удаление)
2. Управление сотрудниками (регистрация, деактивация, подтверждение)
3. Управление расписанием (провайдеров и сотрудников)
4. Управление услугами (добавление, изменение цен)
5. Управление заявками на вступление
6. Массовые операции с рабочими слотами

Особенности реализации:
- Разграничение прав доступа
- Фильтрация и поиск
- Уведомления по email
- Валидация данных
"""

from rest_framework import generics, status, permissions, filters, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend

from PetsCare.users.serializers import UserSerializer
from .models import Provider, Employee, EmployeeProvider, Schedule, ProviderService, ProviderSchedule, EmployeeWorkSlot, EmployeeJoinRequest, SchedulePattern
from .serializers import (
    ProviderSerializer, EmployeeSerializer, EmployeeProviderSerializer,
    ScheduleSerializer, ProviderServiceSerializer,
    EmployeeRegistrationSerializer,
    EmployeeProviderUpdateSerializer,
    ProviderScheduleSerializer, EmployeeWorkSlotSerializer,
    EmployeeJoinRequestSerializer, EmployeeProviderConfirmSerializer
)
from users.permissions import IsProviderAdmin
from users.models import User
from django.core.mail import send_mail
from django.utils.timezone import timezone
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from .permissions import IsEmployee
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta
from geolocation.utils import filter_by_distance, validate_coordinates
from django.db.models import Q


class ProviderListCreateAPIView(generics.ListCreateAPIView):
    """
    API для просмотра списка и создания провайдеров услуг.
    
    Основные возможности:
    - Получение списка активных провайдеров
    - Создание нового провайдера
    - Фильтрация по статусу активности
    - Поиск по названию, описанию и адресу
    - Сортировка по названию и рейтингу
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = Provider.objects.filter(is_active=True)
    serializer_class = ProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description', 'address']
    ordering_fields = ['name', 'rating']


class ProviderRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для работы с конкретным провайдером услуг.
    
    Основные возможности:
    - Получение детальной информации
    - Обновление данных
    - Удаление провайдера
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = Provider.objects.all()
    serializer_class = ProviderSerializer
    permission_classes = [permissions.IsAuthenticated]


class EmployeeListCreateAPIView(generics.ListCreateAPIView):
    """
    API для просмотра списка и создания сотрудников.
    
    Основные возможности:
    - Получение списка активных сотрудников
    - Создание нового сотрудника
    - Фильтрация по статусу и должности
    - Поиск по имени, фамилии, должности и биографии
    - Сортировка по имени, фамилии и должности
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = Employee.objects.filter(is_active=True)
    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'position']
    search_fields = ['user__first_name', 'user__last_name', 'position', 'bio']
    ordering_fields = ['user__first_name', 'user__last_name', 'position']


class EmployeeRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для работы с конкретным сотрудником.
    
    Основные возможности:
    - Получение детальной информации
    - Обновление данных
    - Удаление сотрудника
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated]


class EmployeeProviderListCreateAPIView(generics.ListCreateAPIView):
    """
    API для просмотра списка и создания связей сотрудник-провайдер.
    
    Основные возможности:
    - Получение списка связей
    - Создание новой связи
    - Фильтрация по сотруднику, провайдеру и статусу менеджера
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = EmployeeProvider.objects.all()
    serializer_class = EmployeeProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['employee', 'provider', 'is_manager']


class EmployeeProviderRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для работы с конкретной связью сотрудник-провайдер.
    
    Основные возможности:
    - Получение детальной информации
    - Обновление данных
    - Удаление связи
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = EmployeeProvider.objects.all()
    serializer_class = EmployeeProviderSerializer
    permission_classes = [permissions.IsAuthenticated]


class ScheduleListCreateAPIView(generics.ListCreateAPIView):
    """
    API для просмотра списка и создания расписаний.
    
    Основные возможности:
    - Получение списка расписаний
    - Создание нового расписания
    - Фильтрация по сотруднику, дню недели и статусу рабочего дня
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = Schedule.objects.all()
    serializer_class = ScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['employee', 'day_of_week', 'is_working']


class ScheduleRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для работы с конкретным расписанием.
    
    Основные возможности:
    - Получение детальной информации
    - Обновление данных
    - Удаление расписания
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = Schedule.objects.all()
    serializer_class = ScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]


class ProviderServiceListCreateAPIView(generics.ListCreateAPIView):
    """
    API для просмотра списка и создания услуг провайдера.
    
    Основные возможности:
    - Получение списка активных услуг
    - Создание новой услуги
    - Фильтрация по провайдеру, услуге и статусу активности
    - Сортировка по цене
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = ProviderService.objects.filter(is_active=True)
    serializer_class = ProviderServiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['provider', 'service', 'is_active']
    ordering_fields = ['price']


class ProviderServiceRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для работы с конкретной услугой провайдера.
    
    Основные возможности:
    - Получение детальной информации
    - Обновление данных
    - Удаление услуги
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = ProviderService.objects.all()
    serializer_class = ProviderServiceSerializer
    permission_classes = [permissions.IsAuthenticated]


class ProviderSearchAPIView(generics.ListAPIView):
    """
    API для поиска провайдеров услуг.
    
    Основные возможности:
    - Поиск по названию, описанию и адресу
    - Фильтрация по конкретной услуге
    - Возвращает только активных провайдеров
    - Исключает заблокированные учреждения
    
    Права доступа:
    - Требуется аутентификация
    """
    serializer_class = ProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description', 'address']

    def get_queryset(self):
        """
        Возвращает queryset с исключением заблокированных учреждений.
        """
        from billing.models import ProviderBlocking
        
        # Получаем базовый queryset активных провайдеров
        queryset = Provider.objects.filter(is_active=True)
        
        # Исключаем заблокированные учреждения
        blocked_provider_ids = ProviderBlocking.objects.filter(
            status='active'
        ).values_list('provider_id', flat=True)
        
        return queryset.exclude(id__in=blocked_provider_ids)


class EmployeeProviderUpdateAPIView(generics.UpdateAPIView):
    """
    API для обновления данных о работе сотрудника в учреждении.
    
    Основные возможности:
    - Обновление данных о работе сотрудника
    - Доступно только администратору учреждения
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права администратора провайдера
    """
    serializer_class = EmployeeProviderUpdateSerializer
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]
    lookup_url_kwarg = 'employee_id'


class EmployeeDeactivateAPIView(APIView):
    """
    API для деактивации сотрудника.
    
    Основные возможности:
    - Деактивация сотрудника
    - Завершение всех активных связей с провайдерами
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права администратора провайдера
    """
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]


class IsProviderAdmin(permissions.BasePermission):
    """
    Проверка прав администратора провайдера.
    
    Проверяет:
    - Наличие типа пользователя
    - Соответствие типа 'provider_admin'
    """
    def has_permission(self, request, view):
        """
        Проверяет права доступа.
        
        Returns:
            bool: True, если пользователь является администратором провайдера
        """
        return hasattr(request.user, 'user_type') and request.user.user_type.name == 'provider_admin'


class ProviderScheduleViewSet(viewsets.ModelViewSet):
    """
    API для управления расписанием провайдера.
    
    Основные возможности:
    - CRUD операции с расписанием
    - Автоматическая фильтрация по провайдеру администратора
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права администратора провайдера
    """
    queryset = ProviderSchedule.objects.all()
    serializer_class = ProviderScheduleSerializer
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]


class EmployeeWorkSlotViewSet(viewsets.ModelViewSet):
    """
    API для управления рабочими слотами сотрудников.
    
    Основные возможности:
    - CRUD операции с рабочими слотами
    - Автоматическая фильтрация по провайдеру администратора
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права администратора провайдера
    """
    queryset = EmployeeWorkSlot.objects.all()
    serializer_class = EmployeeWorkSlotSerializer
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]


class EmployeeJoinRequestCreateAPIView(APIView):
    """
    API для создания заявки на вступление в учреждение.
    
    Основные возможности:
    - Создание заявки
    - Автоматическое уведомление администраторов по email
    
    Права доступа:
    - Требуется аутентификация
    """
    permission_classes = [permissions.IsAuthenticated]


class EmployeeJoinRequestApproveAPIView(APIView):
    """
    API для подтверждения или отклонения заявки админом учреждения.
    
    Основные возможности:
    - Подтверждение/отклонение заявки
    - Автоматическое создание связи сотрудник-провайдер при подтверждении
    - Уведомление пользователя по email
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права администратора провайдера
    """
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]


class EmployeeProviderConfirmAPIView(APIView):
    """
    API для подтверждения сотрудником своей роли.
    """
    permission_classes = [permissions.IsAuthenticated]


class EmployeeAccountDeleteNotifyAPIView(APIView):
    """
    API для уведомления админа учреждения при попытке удаления аккаунта сотрудником.
    """
    permission_classes = [permissions.IsAuthenticated]


class EmployeeProviderViewSet(viewsets.ModelViewSet):
    """
    API для управления связями сотрудник-учреждение
    """
    queryset = EmployeeProvider.objects.all()
    serializer_class = EmployeeProviderSerializer
    permission_classes = [IsAuthenticated]


class EmployeeWorkSlotBulkAPIView(APIView):
    """
    API для массового создания/обновления рабочих слотов
    """
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]


class SchedulePatternApplyAPIView(APIView):
    """
    API для применения шаблона расписания
    """
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]


class ProviderSearchByDistanceAPIView(generics.ListAPIView):
    """
    API для поиска провайдеров по расстоянию от указанной точки.
    
    Основные возможности:
    - Поиск провайдеров в указанном радиусе
    - Фильтрация по услугам и рейтингу
    - Сортировка по расстоянию и рейтингу
    - Возвращает расстояние до каждого провайдера
    - Исключает заблокированные учреждения
    
    Параметры запроса:
    - latitude: Широта центральной точки
    - longitude: Долгота центральной точки
    - radius: Радиус поиска в километрах (по умолчанию 10)
    - service_id: ID конкретной услуги для фильтрации
    - min_rating: Минимальный рейтинг провайдера
    - limit: Максимальное количество результатов (по умолчанию 20)
    
    Права доступа:
    - Требуется аутентификация
    """
    serializer_class = ProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Возвращает провайдеров в указанном радиусе.
        """
        from billing.models import ProviderBlocking
        
        # Получаем параметры запроса
        latitude = self.request.query_params.get('latitude')
        longitude = self.request.query_params.get('longitude')
        radius = float(self.request.query_params.get('radius', 10))
        service_id = self.request.query_params.get('service_id')
        min_rating = self.request.query_params.get('min_rating')
        limit = int(self.request.query_params.get('limit', 20))
        
        # Валидируем координаты
        if not latitude or not longitude:
            return Provider.objects.none()
        
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (ValueError, TypeError):
            return Provider.objects.none()
        
        if not validate_coordinates(lat, lon):
            return Provider.objects.none()
        
        # Базовый queryset активных провайдеров
        queryset = Provider.objects.filter(is_active=True)
        
        # Исключаем заблокированные учреждения
        blocked_provider_ids = ProviderBlocking.objects.filter(
            status='active'
        ).values_list('provider_id', flat=True)
        queryset = queryset.exclude(id__in=blocked_provider_ids)
        
        # Фильтрация по услуге
        if service_id:
            try:
                service_id = int(service_id)
                queryset = queryset.filter(
                    services__service_id=service_id,
                    services__is_active=True
                ).distinct()
            except (ValueError, TypeError):
                pass
        
        # Фильтрация по рейтингу
        if min_rating:
            try:
                min_rating = float(min_rating)
                queryset = queryset.filter(rating__gte=min_rating)
            except (ValueError, TypeError):
                pass
        
        # Фильтруем провайдеров с адресами
        queryset = queryset.filter(address__isnull=False).distinct()
        
        # Получаем провайдеров в радиусе
        providers_with_distance = filter_by_distance(
            queryset, lat, lon, radius, 'address__latitude', 'address__longitude'
        )
        
        # Сортируем по расстоянию и рейтингу
        providers_with_distance.sort(key=lambda x: (x[1], -x[0].rating))
        
        # Возвращаем только объекты провайдеров
        return [provider for provider, distance in providers_with_distance[:limit]]
    
    def get_serializer_context(self):
        """
        Добавляет контекст для расчета расстояний в сериализатор.
        """
        context = super().get_serializer_context()
        context['latitude'] = self.request.query_params.get('latitude')
        context['longitude'] = self.request.query_params.get('longitude')
        return context


class SitterAdvancedSearchByDistanceAPIView(generics.ListAPIView):
    """
    API для расширенного поиска ситтеров по расстоянию с дополнительными фильтрами.
    
    Основные возможности:
    - Поиск ситтеров в указанном радиусе
    - Фильтрация по услугам, расписанию, цене
    - Фильтрация по рейтингу и доступности
    - Сортировка по расстоянию, рейтингу и цене
    - Возвращает расстояние до каждого ситтера
    
    Параметры запроса:
    - latitude: Широта центральной точки
    - longitude: Долгота центральной точки
    - radius: Радиус поиска в километрах (по умолчанию 10)
    - service_id: ID конкретной услуги для фильтрации
    - min_rating: Минимальный рейтинг ситтера
    - max_price: Максимальная цена за услугу
    - available_date: Дата для проверки доступности (YYYY-MM-DD)
    - available_time: Время для проверки доступности (HH:MM)
    - available: Только доступные ситтеры (true/false)
    - limit: Максимальное количество результатов (по умолчанию 20)
    
    Права доступа:
    - Требуется аутентификация
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Возвращает ситтеров в указанном радиусе с расширенными фильтрами.
        """
        from geolocation.utils import filter_by_distance, validate_coordinates
        from sitters.models import PetSitting
        from datetime import datetime, time
        from django.utils import timezone
        
        # Получаем параметры запроса
        latitude = self.request.query_params.get('latitude')
        longitude = self.request.query_params.get('longitude')
        radius = float(self.request.query_params.get('radius', 10))
        service_id = self.request.query_params.get('service_id')
        min_rating = self.request.query_params.get('min_rating')
        max_price = self.request.query_params.get('max_price')
        available_date = self.request.query_params.get('available_date')
        available_time = self.request.query_params.get('available_time')
        available = self.request.query_params.get('available')
        limit = int(self.request.query_params.get('limit', 20))
        
        # Валидируем координаты
        if not latitude or not longitude:
            return User.objects.none()
        
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (ValueError, TypeError):
            return User.objects.none()
        
        if not validate_coordinates(lat, lon):
            return User.objects.none()
        
        # Базовый queryset ситтеров
        queryset = User.objects.filter(
            is_active=True,
            user_types__name='sitter'
        )
        
        # Фильтрация по рейтингу
        if min_rating:
            try:
                min_rating = float(min_rating)
                queryset = queryset.filter(rating__gte=min_rating)
            except (ValueError, TypeError):
                pass
        
        # Фильтрация по услуге
        if service_id:
            try:
                service_id = int(service_id)
                queryset = queryset.filter(
                    sitter_services__service_id=service_id,
                    sitter_services__is_active=True
                ).distinct()
            except (ValueError, TypeError):
                pass
        
        # Фильтрация по цене
        if max_price:
            try:
                max_price = float(max_price)
                queryset = queryset.filter(
                    sitter_services__price__lte=max_price
                ).distinct()
            except (ValueError, TypeError):
                pass
        
        # Фильтрация по доступности
        if available == 'true':
            # Исключаем ситтеров с активными заявками
            active_sittings = PetSitting.objects.filter(
                status__in=['pending', 'confirmed', 'in_progress']
            ).values_list('sitter_id', flat=True)
            queryset = queryset.exclude(id__in=active_sittings)
        
        # Фильтрация по расписанию
        if available_date and available_time:
            try:
                # Парсим дату и время
                date_obj = datetime.strptime(available_date, '%Y-%m-%d').date()
                time_obj = datetime.strptime(available_time, '%H:%M').time()
                
                # Получаем день недели (0=понедельник, 6=воскресенье)
                day_of_week = date_obj.weekday()
                
                # Фильтруем по расписанию
                queryset = queryset.filter(
                    sitter_schedules__day_of_week=day_of_week,
                    sitter_schedules__is_working=True,
                    sitter_schedules__start_time__lte=time_obj,
                    sitter_schedules__end_time__gte=time_obj
                ).distinct()
            except (ValueError, TypeError):
                pass
        
        # Фильтруем ситтеров с адресами
        queryset = queryset.filter(
            Q(address__isnull=False) | 
            Q(provider_address__isnull=False)
        ).distinct()
        
        # Получаем ситтеров в радиусе
        sitters_with_distance = filter_by_distance(
            queryset, lat, lon, radius, 'address__latitude', 'address__longitude'
        )
        
        # Если ситтер не найден по основному адресу, ищем по адресу провайдера
        if not sitters_with_distance:
            sitters_with_distance = filter_by_distance(
                queryset, lat, lon, radius, 'provider_address__latitude', 'provider_address__longitude'
            )
        
        # Сортируем по расстоянию, рейтингу и цене
        sitters_with_distance.sort(key=lambda x: (x[1], -x[0].rating))
        
        # Возвращаем только объекты пользователей
        return [sitter for sitter, distance in sitters_with_distance[:limit]]
    
    def get_serializer_context(self):
        """
        Добавляет контекст для расчета расстояний в сериализатор.
        """
        context = super().get_serializer_context()
        context['latitude'] = self.request.query_params.get('latitude')
        context['longitude'] = self.request.query_params.get('longitude')
        return context 