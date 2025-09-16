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

from users.serializers import UserSerializer
from .models import Provider, Employee, EmployeeProvider, Schedule, ProviderService, ProviderSchedule, EmployeeWorkSlot, EmployeeJoinRequest, SchedulePattern
from booking.models import Booking
from .serializers import (
    ProviderSerializer, EmployeeSerializer, EmployeeProviderSerializer,
    ScheduleSerializer, ProviderServiceSerializer,
    EmployeeRegistrationSerializer,
    EmployeeProviderUpdateSerializer,
    ProviderScheduleSerializer, EmployeeWorkSlotSerializer,
    EmployeeJoinRequestSerializer, EmployeeProviderConfirmSerializer
)
# from users.permissions import IsProviderAdmin  # Класс определен ниже в этом файле
from users.models import User


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
from django.core.mail import send_mail
from django.utils.timezone import timezone
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from .permissions import IsEmployee
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta
from geolocation.utils import filter_by_distance, validate_coordinates, calculate_distance
from django.contrib.gis.geos import Point
from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
import logging

logger = logging.getLogger(__name__)


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
    - Фильтрация по услугам, рейтингу, цене и доступности
    - Сортировка по расстоянию, рейтингу и цене
    - Возвращает расстояние до каждого провайдера
    - Исключает заблокированные учреждения
    
    Параметры запроса:
    - latitude: Широта центральной точки
    - longitude: Долгота центральной точки
    - radius: Радиус поиска в километрах (по умолчанию 10)
    - service_id: ID конкретной услуги для фильтрации
    - min_rating: Минимальный рейтинг провайдера
    - price_min: Минимальная цена услуги
    - price_max: Максимальная цена услуги
    - available_date: Дата для проверки доступности (YYYY-MM-DD)
    - available_time: Время для проверки доступности (HH:MM)
    - available: Только доступные учреждения (true/false)
    - sort_by: Сортировка (distance, rating, price_asc, price_desc)
    - limit: Максимальное количество результатов (по умолчанию 20)
    
    Права доступа:
    - Требуется аутентификация
    """
    serializer_class = ProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Возвращает провайдеров в указанном радиусе с фильтрацией по цене и доступности.
        """
        from billing.models import ProviderBlocking
        from booking.models import Booking
        from datetime import datetime, timedelta
        
        # Получаем параметры запроса
        latitude = self.request.query_params.get('latitude')
        longitude = self.request.query_params.get('longitude')
        radius = float(self.request.query_params.get('radius', 10))
        service_id = self.request.query_params.get('service_id')
        min_rating = self.request.query_params.get('min_rating')
        price_min = self.request.query_params.get('price_min')
        price_max = self.request.query_params.get('price_max')
        available_date = self.request.query_params.get('available_date')
        available_time = self.request.query_params.get('available_time')
        available_only = self.request.query_params.get('available', '').lower() == 'true'
        sort_by = self.request.query_params.get('sort_by', 'distance')
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
        
        # Фильтрация по цене
        if service_id and (price_min or price_max):
            try:
                service_id = int(service_id)
                price_filter = Q(services__service_id=service_id, services__is_active=True)
                
                if price_min:
                    try:
                        price_min_val = float(price_min)
                        price_filter &= Q(services__price__gte=price_min_val)
                    except (ValueError, TypeError):
                        pass
                
                if price_max:
                    try:
                        price_max_val = float(price_max)
                        price_filter &= Q(services__price__lte=price_max_val)
                    except (ValueError, TypeError):
                        pass
                
                queryset = queryset.filter(price_filter).distinct()
            except (ValueError, TypeError):
                pass
        
        # Фильтрация по доступности
        if available_only and available_date and available_time:
            try:
                # Парсим дату и время
                date_obj = datetime.strptime(available_date, '%Y-%m-%d').date()
                time_obj = datetime.strptime(available_time, '%H:%M').time()
                datetime_obj = datetime.combine(date_obj, time_obj)
                
                # Получаем день недели (0 = понедельник)
                weekday = date_obj.weekday()
                
                # Проверяем доступность слотов
                available_provider_ids = []
                
                for provider in queryset:
                    # Проверяем расписание учреждения
                    provider_schedule = provider.schedules.filter(weekday=weekday).first()
                    if not provider_schedule or provider_schedule.is_closed:
                        continue
                    
                    # Проверяем время работы
                    if (provider_schedule.open_time and provider_schedule.close_time and
                        (time_obj < provider_schedule.open_time or time_obj > provider_schedule.close_time)):
                        continue
                    
                    # Проверяем свободные слоты сотрудников
                    if service_id:
                        # Ищем сотрудников с этой услугой
                        employees = provider.employees.filter(
                            services__id=service_id,
                            is_active=True
                        )
                        
                        # Проверяем доступность хотя бы одного сотрудника
                        has_available_employee = False
                        for employee in employees:
                            # Проверяем расписание сотрудника
                            employee_schedule = employee.schedules.filter(day_of_week=weekday).first()
                            if not employee_schedule or not employee_schedule.is_working:
                                continue
                            
                            # Проверяем время работы сотрудника
                            if (employee_schedule.start_time and employee_schedule.end_time and
                                (time_obj < employee_schedule.start_time or time_obj > employee_schedule.end_time)):
                                continue
                            
                            # Проверяем, нет ли уже бронирования в это время
                            slot_end_time = datetime_obj + timedelta(minutes=30)  # Предполагаем 30 минут
                            conflicting_booking = Booking.objects.filter(
                                employee=employee,
                                scheduled_date=date_obj,
                                scheduled_time__lt=slot_end_time.time(),
                                scheduled_time__gt=datetime_obj.time(),
                                status__in=['confirmed', 'pending']
                            ).exists()
                            
                            if not conflicting_booking:
                                has_available_employee = True
                                break
                        
                        if has_available_employee:
                            available_provider_ids.append(provider.id)
                    else:
                        # Если услуга не указана, считаем доступным если есть работающие сотрудники
                        if provider.employees.filter(is_active=True).exists():
                            available_provider_ids.append(provider.id)
                
                # Фильтруем только доступные учреждения
                if available_provider_ids:
                    queryset = queryset.filter(id__in=available_provider_ids)
                else:
                    return Provider.objects.none()
                    
            except (ValueError, TypeError):
                pass
        
        # Фильтруем провайдеров с адресами
        queryset = queryset.filter(address__isnull=False).distinct()
        
        # Получаем провайдеров в радиусе
        providers_with_distance = filter_by_distance(
            queryset, lat, lon, radius, 'address__point'
        )
        
        # Сортировка
        if sort_by == 'rating':
            providers_with_distance.sort(key=lambda x: (-x[0].rating, x[1]))
        elif sort_by == 'price_asc' and service_id:
            # Сортировка по возрастанию цены
            providers_with_distance.sort(key=lambda x: (
                x[0].services.filter(service_id=service_id).first().price if x[0].services.filter(service_id=service_id).exists() else float('inf'),
                x[1]
            ))
        elif sort_by == 'price_desc' and service_id:
            # Сортировка по убыванию цены
            providers_with_distance.sort(key=lambda x: (
                -x[0].services.filter(service_id=service_id).first().price if x[0].services.filter(service_id=service_id).exists() else float('-inf'),
                x[1]
            ))
        else:
            # Сортировка по расстоянию (по умолчанию)
            providers_with_distance.sort(key=lambda x: (x[1], -x[0].rating))
        
        # Возвращаем только объекты провайдеров
        return [provider for provider, distance in providers_with_distance[:limit]]
    
    def get_serializer_context(self):
        """
        Добавляет контекст для расчета расстояний и информации о ценах/доступности в сериализатор.
        """
        context = super().get_serializer_context()
        context['latitude'] = self.request.query_params.get('latitude')
        context['longitude'] = self.request.query_params.get('longitude')
        context['service_id'] = self.request.query_params.get('service_id')
        context['available_date'] = self.request.query_params.get('available_date')
        context['available_time'] = self.request.query_params.get('available_time')
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
            queryset, lat, lon, radius, 'address__point'
        )
        
        # Если ситтер не найден по основному адресу, ищем по адресу провайдера
        if not sitters_with_distance:
            sitters_with_distance = filter_by_distance(
                queryset, lat, lon, radius, 'provider_address__point'
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


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def check_provider_availability(request, provider_id):
    """
    Проверяет доступность учреждения в указанное время.
    
    Args:
        request: HTTP запрос
        provider_id: ID учреждения
    
    Параметры запроса:
    - date: Дата для проверки (YYYY-MM-DD)
    - time: Время для проверки (HH:MM)
    - service_id: ID услуги (опционально)
    - duration_minutes: Продолжительность услуги в минутах (по умолчанию 30)
    
    Returns:
        JSON ответ с информацией о доступности
    """
    try:
        from datetime import datetime, timedelta
        from booking.models import Booking
        
        # Получаем параметры
        date_str = request.GET.get('date')
        time_str = request.GET.get('time')
        service_id = request.GET.get('service_id')
        duration_minutes = int(request.GET.get('duration_minutes', 30))
        
        if not date_str or not time_str:
            return Response({
                'success': False,
                'message': _('Date and time must be specified')
            }, status=400)
        
        # Получаем учреждение
        try:
            provider = Provider.objects.get(id=provider_id, is_active=True)
        except Provider.DoesNotExist:
            return Response({
                'success': False,
                'message': _('Institution not found')
            }, status=404)
        
        # Парсим дату и время
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            time_obj = datetime.strptime(time_str, '%H:%M').time()
            datetime_obj = datetime.combine(date_obj, time_obj)
        except ValueError:
            return Response({
                'success': False,
                'message': _('Invalid date or time format')
            }, status=400)
        
        # Получаем день недели
        weekday = date_obj.weekday()
        
        # Проверяем расписание учреждения
        provider_schedule = provider.schedules.filter(weekday=weekday).first()
        if not provider_schedule or provider_schedule.is_closed:
            return Response({
                'success': True,
                'provider_id': provider_id,
                'available': False,
                'reason': 'provider_closed',
                'message': _('Institution is closed on this day')
            })
        
        # Проверяем время работы
        if (provider_schedule.open_time and provider_schedule.close_time and
            (time_obj < provider_schedule.open_time or time_obj > provider_schedule.close_time)):
            return Response({
                'success': True,
                'provider_id': provider_id,
                'available': False,
                'reason': 'outside_hours',
                'message': _('Institution works from {} to {}').format(provider_schedule.open_time, provider_schedule.close_time)
            })
        
        # Проверяем доступность сотрудников
        if service_id:
            try:
                service_id = int(service_id)
                employees = provider.employees.filter(
                    services__id=service_id,
                    is_active=True
                )
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid service ID')
                }, status=400)
        else:
            employees = provider.employees.filter(is_active=True)
        
        available_employees = []
        for employee in employees:
            # Проверяем расписание сотрудника
            employee_schedule = employee.schedules.filter(day_of_week=weekday).first()
            if not employee_schedule or not employee_schedule.is_working:
                continue
            
            # Проверяем время работы сотрудника
            if (employee_schedule.start_time and employee_schedule.end_time and
                (time_obj < employee_schedule.start_time or time_obj > employee_schedule.end_time)):
                continue
            
            # Проверяем, нет ли уже бронирования в это время
            slot_end_time = datetime_obj + timedelta(minutes=duration_minutes)
            conflicting_booking = Booking.objects.filter(
                employee=employee,
                scheduled_date=date_obj,
                scheduled_time__lt=slot_end_time.time(),
                scheduled_time__gt=datetime_obj.time(),
                status__in=['confirmed', 'pending']
            ).exists()
            
            if not conflicting_booking:
                available_employees.append({
                    'id': employee.id,
                    'name': f"{employee.user.first_name} {employee.user.last_name}",
                    'position': employee.position,
                    'services': list(employee.services.values_list('id', 'name'))
                })
        
        if available_employees:
            return Response({
                'success': True,
                'provider_id': provider_id,
                'available': True,
                'available_employees': available_employees,
                'message': _('{} employees available').format(len(available_employees))
            })
        else:
            return Response({
                'success': True,
                'provider_id': provider_id,
                'available': False,
                'reason': 'no_available_employees',
                'message': _('No available employees at this time')
            })
            
    except Exception as e:
        logger.error(f"Error checking provider availability: {e}")
        return Response({
            'success': False,
            'message': _('Error checking availability')
        }, status=500)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_provider_prices(request, provider_id):
    """
    Получает информацию о ценах на услуги в учреждении.
    
    Args:
        request: HTTP запрос
        provider_id: ID учреждения
    
    Параметры запроса:
    - service_id: ID конкретной услуги (опционально)
    
    Returns:
        JSON ответ с информацией о ценах
    """
    try:
        # Получаем учреждение
        try:
            provider = Provider.objects.get(id=provider_id, is_active=True)
        except Provider.DoesNotExist:
            return Response({
                'success': False,
                'message': _('Institution not found')
            }, status=404)
        
        # Получаем параметры
        service_id = request.GET.get('service_id')
        
        # Получаем услуги
        if service_id:
            try:
                service_id = int(service_id)
                provider_services = provider.provider_services.filter(
                    service_id=service_id,
                    is_active=True
                )
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid service ID')
                }, status=400)
        else:
            provider_services = provider.provider_services.filter(is_active=True)
        
        # Сериализуем данные
        from .serializers import ProviderServiceSerializer
        serializer = ProviderServiceSerializer(provider_services, many=True)
        
        return Response({
            'success': True,
            'provider_id': provider_id,
            'services': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Error getting provider prices: {e}")
        return Response({
            'success': False,
            'message': _('Error getting price information')
        }, status=500) 


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_provider_available_slots(request, provider_id):
    """
    Gets available time slots for a specific service at an institution.
    
    Args:
        request: HTTP request
        provider_id: Institution ID
    
    Query parameters:
    - service_id: Service ID (required)
    - date: Date for checking availability (YYYY-MM-DD, optional)
    - time: Time for checking availability (HH:MM, optional)
    - duration_minutes: Service duration in minutes (optional, default from service)
    - horizon_days: Search horizon in days (optional, default 7)
    
    Returns:
        JSON response with available slots information
    """
    try:
        # Get institution
        try:
            provider = Provider.objects.get(id=provider_id, is_active=True)
        except Provider.DoesNotExist:
            return Response({
                'success': False,
                'message': _('Institution not found')
            }, status=404)
        
        # Get parameters
        service_id = request.GET.get('service_id')
        date_str = request.GET.get('date')
        time_str = request.GET.get('time')
        duration_minutes = request.GET.get('duration_minutes')
        horizon_days = int(request.GET.get('horizon_days', 7))
        
        # Validate required parameters
        if not service_id:
            return Response({
                'success': False,
                'message': _('Service ID is required')
            }, status=400)
        
        try:
            service_id = int(service_id)
        except ValueError:
            return Response({
                'success': False,
                'message': _('Invalid service ID')
            }, status=400)
        
        # Get service information
        try:
            provider_service = provider.provider_services.get(
                service_id=service_id,
                is_active=True
            )
        except ProviderService.DoesNotExist:
            return Response({
                'success': False,
                'message': _('Service not found at this institution')
            }, status=404)
        
        # Use service duration if not specified
        if not duration_minutes:
            duration_minutes = provider_service.duration_minutes
        else:
            try:
                duration_minutes = int(duration_minutes)
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid duration format')
                }, status=400)
        
        # Parse date and time if provided
        requested_date = None
        requested_time = None
        requested_datetime = None
        
        if date_str:
            try:
                requested_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid date format')
                }, status=400)
        
        if time_str:
            try:
                requested_time = datetime.strptime(time_str, '%H:%M').time()
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid time format')
                }, status=400)
        
        if requested_date and requested_time:
            requested_datetime = datetime.combine(requested_date, requested_time)
        
        # Get available slots
        available_slots = []
        next_available_slot = None
        requested_slot_info = None
        
        # Determine search start date
        if requested_date:
            search_start_date = requested_date
        else:
            search_start_date = timezone.now().date()
        
        # Search for available slots
        current_date = search_start_date
        end_date = current_date + timedelta(days=horizon_days)
        
        while current_date <= end_date:
            weekday = current_date.weekday()
            
            # Check institution schedule
            provider_schedule = provider.schedules.filter(weekday=weekday).first()
            if not provider_schedule or provider_schedule.is_closed:
                current_date += timedelta(days=1)
                continue
            
            # Get working hours
            open_time = provider_schedule.open_time
            close_time = provider_schedule.close_time
            
            if not open_time or not close_time:
                current_date += timedelta(days=1)
                continue
            
            # Get employees for this service
            employees = provider.employees.filter(
                services__id=service_id,
                is_active=True
            )
            
            if not employees.exists():
                current_date += timedelta(days=1)
                continue
            
            # Generate time slots for this day
            current_time = open_time
            slot_end_time = (datetime.combine(current_date, current_time) + 
                           timedelta(minutes=duration_minutes)).time()
            
            while slot_end_time <= close_time:
                # Check if this slot is available
                slot_available = True
                available_employees = []
                
                for employee in employees:
                    # Check employee schedule
                    employee_schedule = employee.schedules.filter(day_of_week=weekday).first()
                    if not employee_schedule or not employee_schedule.is_working:
                        continue
                    
                    # Check employee working hours
                    if (employee_schedule.start_time and employee_schedule.end_time and
                        (current_time < employee_schedule.start_time or 
                         slot_end_time > employee_schedule.end_time)):
                        continue
                    
                    # Check for booking conflicts
                    slot_start_datetime = datetime.combine(current_date, current_time)
                    slot_end_datetime = datetime.combine(current_date, slot_end_time)
                    
                    conflicting_booking = Booking.objects.filter(
                        employee=employee,
                        scheduled_date=current_date,
                        scheduled_time__lt=slot_end_datetime.time(),
                        scheduled_time__gt=slot_start_datetime.time(),
                        status__in=['confirmed', 'pending']
                    ).exists()
                    
                    if not conflicting_booking:
                        available_employees.append({
                            'id': employee.id,
                            'name': f"{employee.user.first_name} {employee.user.last_name}",
                            'position': employee.position
                        })
                
                if available_employees:
                    slot_info = {
                        'date': current_date.strftime('%Y-%m-%d'),
                        'time': current_time.strftime('%H:%M'),
                        'end_time': slot_end_time.strftime('%H:%M'),
                        'duration_minutes': duration_minutes,
                        'available_employees': available_employees,
                        'price': float(provider_service.price)
                    }
                    
                    available_slots.append(slot_info)
                    
                    # Check if this is the requested slot
                    if (requested_datetime and 
                        current_date == requested_date and 
                        current_time == requested_time):
                        requested_slot_info = {
                            'date': current_date.strftime('%Y-%m-%d'),
                            'time': current_time.strftime('%H:%M'),
                            'available': True,
                            'available_employees': available_employees
                        }
                    
                    # Find next available slot
                    if not next_available_slot:
                        next_available_slot = slot_info
                
                # Move to next slot (30-minute intervals)
                current_time = (datetime.combine(current_date, current_time) + 
                              timedelta(minutes=30)).time()
                slot_end_time = (datetime.combine(current_date, current_time) + 
                               timedelta(minutes=duration_minutes)).time()
            
            current_date += timedelta(days=1)
        
        # If requested slot was not found, mark it as unavailable
        if requested_datetime and not requested_slot_info:
            requested_slot_info = {
                'date': requested_date.strftime('%Y-%m-%d'),
                'time': requested_time.strftime('%H:%M'),
                'available': False,
                'reason': 'slot_unavailable'
            }
        
        # Sort available slots by date, time, and price
        available_slots.sort(key=lambda x: (x['date'], x['time'], x['price']))
        
        return Response({
            'success': True,
            'provider_id': provider_id,
            'service_id': service_id,
            'requested_slot': requested_slot_info,
            'next_available_slot': next_available_slot,
            'available_slots': available_slots,
            'total_slots_found': len(available_slots)
        })
        
    except Exception as e:
        logger.error(f'Error getting provider available slots: {e}')
        return Response({
            'success': False,
            'message': _('Error getting available slots')
        }, status=500) 


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def search_providers_map_availability(request):
    """
    Search for institutions on map with nearest available slots for selected service and time.
    
    Args:
        request: HTTP request
    
    Query parameters:
    - latitude: User latitude (required)
    - longitude: User longitude (required)
    - service_id: Service ID (required)
    - date: Date for checking availability (YYYY-MM-DD, optional)
    - time: Time for checking availability (HH:MM, optional)
    - radius: Search radius in kilometers (optional, default 10)
    - min_rating: Minimum institution rating (optional)
    - price_min: Minimum service price (optional)
    - price_max: Maximum service price (optional)
    - sort_by: Sort order (distance, rating, price_asc, price_desc, availability)
    - limit: Maximum results (optional, default 20)
    
    Returns:
        JSON response with institutions and their availability information
    """
    try:
        # Get and validate coordinates
        latitude = request.GET.get('latitude')
        longitude = request.GET.get('longitude')
        
        if not latitude or not longitude:
            return Response({
                'success': False,
                'message': _('Latitude and longitude are required')
            }, status=400)
        
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except ValueError:
            return Response({
                'success': False,
                'message': _('Invalid coordinates format')
            }, status=400)
        
        if not validate_coordinates(latitude, longitude):
            return Response({
                'success': False,
                'message': _('Invalid coordinates')
            }, status=400)
        
        # Get and validate service_id
        service_id = request.GET.get('service_id')
        if not service_id:
            return Response({
                'success': False,
                'message': _('Service ID is required')
            }, status=400)
        
        try:
            service_id = int(service_id)
        except ValueError:
            return Response({
                'success': False,
                'message': _('Invalid service ID')
            }, status=400)
        
        # Get other parameters
        radius = float(request.GET.get('radius', 10))
        min_rating = request.GET.get('min_rating')
        price_min = request.GET.get('price_min')
        price_max = request.GET.get('price_max')
        sort_by = request.GET.get('sort_by', 'distance')
        limit = int(request.GET.get('limit', 20))
        
        date_str = request.GET.get('date')
        time_str = request.GET.get('time')
        
        # Parse date and time if provided
        requested_date = None
        requested_time = None
        requested_datetime = None
        
        if date_str:
            try:
                requested_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid date format')
                }, status=400)
        
        if time_str:
            try:
                requested_time = datetime.strptime(time_str, '%H:%M').time()
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid time format')
                }, status=400)
        
        if requested_date and requested_time:
            requested_datetime = datetime.combine(requested_date, requested_time)
        
        # Get providers in radius
        providers = Provider.objects.filter(is_active=True)
        
        # Filter by distance using PostGIS
        providers = filter_by_distance(providers, latitude, longitude, radius, 'address__point')
        
        # Filter by rating
        if min_rating:
            try:
                min_rating = float(min_rating)
                providers = providers.filter(rating__gte=min_rating)
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid rating format')
                }, status=400)
        
        # Filter by price
        if price_min or price_max:
            providers = providers.filter(
                provider_services__service_id=service_id,
                provider_services__is_active=True
            )
            
            if price_min:
                try:
                    price_min = float(price_min)
                    providers = providers.filter(provider_services__price__gte=price_min)
                except ValueError:
                    return Response({
                        'success': False,
                        'message': _('Invalid minimum price format')
                    }, status=400)
            
            if price_max:
                try:
                    price_max = float(price_max)
                    providers = providers.filter(provider_services__price__lte=price_max)
                except ValueError:
                    return Response({
                        'success': False,
                        'message': _('Invalid maximum price format')
                    }, status=400)
        
        # Limit results
        providers = providers[:limit]
        
        # Get availability information for each provider
        providers_with_availability = []
        
        for provider in providers:
            # Calculate distance using PostGIS
            if hasattr(provider, 'address') and provider.address and provider.address.point:
                distance = provider.address.point.distance(Point(longitude, latitude)) * 111.32  # Convert to km
                distance = round(distance, 2) if distance else None
            else:
                distance = None
            
            # Get service price
            try:
                provider_service = provider.provider_services.get(
                    service_id=service_id,
                    is_active=True
                )
                price = float(provider_service.price)
                duration_minutes = provider_service.duration_minutes
            except ProviderService.DoesNotExist:
                continue
            
            # Check availability
            availability_info = check_provider_slot_availability(
                provider, service_id, requested_date, requested_time, duration_minutes
            )
            
            provider_info = {
                'id': provider.id,
                'name': provider.name,
                'address': provider.address.full_address if provider.address else None,
                'rating': provider.rating,
                'distance': distance,
                'price': price,
                'duration_minutes': duration_minutes,
                'requested_slot_available': availability_info['requested_slot_available'],
                'next_available_slot': availability_info['next_available_slot'],
                'availability_reason': availability_info['reason']
            }
            
            providers_with_availability.append(provider_info)
        
        # Sort results
        if sort_by == 'distance':
            providers_with_availability.sort(key=lambda x: (x['distance'] or float('inf')))
        elif sort_by == 'rating':
            providers_with_availability.sort(key=lambda x: (x['rating'] or 0), reverse=True)
        elif sort_by == 'price_asc':
            providers_with_availability.sort(key=lambda x: x['price'])
        elif sort_by == 'price_desc':
            providers_with_availability.sort(key=lambda x: x['price'], reverse=True)
        elif sort_by == 'availability':
            # Sort by availability first, then by distance
            providers_with_availability.sort(key=lambda x: (
                not x['requested_slot_available'],
                x['distance'] or float('inf')
            ))
        
        return Response({
            'success': True,
            'search_params': {
                'latitude': latitude,
                'longitude': longitude,
                'service_id': service_id,
                'radius': radius,
                'requested_date': date_str,
                'requested_time': time_str
            },
            'providers': providers_with_availability,
            'total_found': len(providers_with_availability)
        })
        
    except Exception as e:
        logger.error(f'Error searching providers map availability: {e}')
        return Response({
            'success': False,
            'message': _('Error searching institutions')
        }, status=500)


def check_provider_slot_availability(provider, service_id, requested_date, requested_time, duration_minutes):
    """
    Helper function to check slot availability for a provider.
    
    Args:
        provider: Provider instance
        service_id: Service ID
        requested_date: Requested date (optional)
        requested_time: Requested time (optional)
        duration_minutes: Service duration in minutes
    
    Returns:
        Dictionary with availability information
    """
    try:
        # If no date/time specified, find nearest available slot
        if not requested_date:
            requested_date = timezone.now().date()
        
        # Check if requested slot is available
        requested_slot_available = False
        next_available_slot = None
        reason = 'available'
        
        if requested_time:
            # Check specific time slot
            weekday = requested_date.weekday()
            
            # Check provider schedule
            provider_schedule = provider.schedules.filter(weekday=weekday).first()
            if not provider_schedule or provider_schedule.is_closed:
                reason = 'institution_closed'
            else:
                # Check working hours
                if (provider_schedule.open_time and provider_schedule.close_time and
                    (requested_time < provider_schedule.open_time or 
                     requested_time > provider_schedule.close_time)):
                    reason = 'outside_hours'
                else:
                    # Check employee availability
                    employees = provider.employees.filter(
                        services__id=service_id,
                        is_active=True
                    )
                    
                    if not employees.exists():
                        reason = 'no_employees'
                    else:
                        slot_end_time = (datetime.combine(requested_date, requested_time) + 
                                       timedelta(minutes=duration_minutes)).time()
                        
                        available_employees = []
                        for employee in employees:
                            # Check employee schedule
                            employee_schedule = employee.schedules.filter(day_of_week=weekday).first()
                            if not employee_schedule or not employee_schedule.is_working:
                                continue
                            
                            # Check employee working hours
                            if (employee_schedule.start_time and employee_schedule.end_time and
                                (requested_time < employee_schedule.start_time or 
                                 slot_end_time > employee_schedule.end_time)):
                                continue
                            
                            # Check for booking conflicts
                            conflicting_booking = Booking.objects.filter(
                                employee=employee,
                                scheduled_date=requested_date,
                                scheduled_time__lt=slot_end_time,
                                scheduled_time__gt=requested_time,
                                status__in=['confirmed', 'pending']
                            ).exists()
                            
                            if not conflicting_booking:
                                available_employees.append(employee.id)
                        
                        if available_employees:
                            requested_slot_available = True
                            reason = 'available'
                        else:
                            reason = 'slot_occupied'
        
        # Find next available slot if requested slot is not available
        if not requested_slot_available:
            next_available_slot = find_next_available_slot(
                provider, service_id, requested_date, duration_minutes
            )
        
        return {
            'requested_slot_available': requested_slot_available,
            'next_available_slot': next_available_slot,
            'reason': reason
        }
        
    except Exception as e:
        logger.error(f'Error checking provider slot availability: {e}')
        return {
            'requested_slot_available': False,
            'next_available_slot': None,
            'reason': 'error'
        }


def find_next_available_slot(provider, service_id, start_date, duration_minutes):
    """
    Helper function to find next available slot for a provider.
    
    Args:
        provider: Provider instance
        service_id: Service ID
        start_date: Start date for search
        duration_minutes: Service duration in minutes
    
    Returns:
        Dictionary with next available slot info or None
    """
    try:
        current_date = start_date
        end_date = current_date + timedelta(days=7)  # Search for 7 days
        
        while current_date <= end_date:
            weekday = current_date.weekday()
            
            # Check provider schedule
            provider_schedule = provider.schedules.filter(weekday=weekday).first()
            if not provider_schedule or provider_schedule.is_closed:
                current_date += timedelta(days=1)
                continue
            
            # Get working hours
            open_time = provider_schedule.open_time
            close_time = provider_schedule.close_time
            
            if not open_time or not close_time:
                current_date += timedelta(days=1)
                continue
            
            # Get employees
            employees = provider.employees.filter(
                services__id=service_id,
                is_active=True
            )
            
            if not employees.exists():
                current_date += timedelta(days=1)
                continue
            
            # Check time slots
            current_time = open_time
            slot_end_time = (datetime.combine(current_date, current_time) + 
                           timedelta(minutes=duration_minutes)).time()
            
            while slot_end_time <= close_time:
                # Check if slot is available
                for employee in employees:
                    # Check employee schedule
                    employee_schedule = employee.schedules.filter(day_of_week=weekday).first()
                    if not employee_schedule or not employee_schedule.is_working:
                        continue
                    
                    # Check employee working hours
                    if (employee_schedule.start_time and employee_schedule.end_time and
                        (current_time < employee_schedule.start_time or 
                         slot_end_time > employee_schedule.end_time)):
                        continue
                    
                    # Check for booking conflicts
                    conflicting_booking = Booking.objects.filter(
                        employee=employee,
                        scheduled_date=current_date,
                        scheduled_time__lt=slot_end_time,
                        scheduled_time__gt=current_time,
                        status__in=['confirmed', 'pending']
                    ).exists()
                    
                    if not conflicting_booking:
                        return {
                            'date': current_date.strftime('%Y-%m-%d'),
                            'time': current_time.strftime('%H:%M'),
                            'employee_id': employee.id,
                            'employee_name': f"{employee.user.first_name} {employee.user.last_name}"
                        }
                
                # Move to next slot (30-minute intervals)
                current_time = (datetime.combine(current_date, current_time) + 
                              timedelta(minutes=30)).time()
                slot_end_time = (datetime.combine(current_date, current_time) + 
                               timedelta(minutes=duration_minutes)).time()
            
            current_date += timedelta(days=1)
        
        return None
        
    except Exception as e:
        logger.error(f'Error finding next available slot: {e}')
        return None 