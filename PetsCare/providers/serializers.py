"""
Serializers для API поставщиков.

Этот модуль содержит сериализаторы для:
1. Учреждений
2. Сотрудников
3. Связей между сотрудниками и учреждениями
4. Расписаний
5. Услуг учреждений
"""

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import Provider, Employee, EmployeeProvider, Schedule, LocationSchedule, EmployeeWorkSlot, EmployeeJoinRequest, ProviderLocation, ProviderLocationService
from catalog.serializers import ServiceSerializer
from catalog.models import Service
from users.serializers import UserSerializer
from users.models import EmployeeSpecialization, User
from django.db.models import Q
from geopy.distance import geodesic
from django.utils import timezone
from geolocation.utils import calculate_distance


class ProviderSerializer(serializers.ModelSerializer):
    """
    Serializer для модели Provider.
    Используется для сериализации данных учреждения.
    """
    available_categories = ServiceSerializer(
        source='available_category_levels',
        many=True,
        read_only=True
    )
    services = serializers.SerializerMethodField()
    employees = serializers.SerializerMethodField()
    distance = serializers.SerializerMethodField()
    price_info = serializers.SerializerMethodField()
    availability_info = serializers.SerializerMethodField()
    
    def get_services(self, obj):
        """
        Возвращает услуги из всех локаций провайдера.
        Используйте ProviderLocationService API для детальной информации.
        """
        # Для Swagger возвращаем пустой список, чтобы избежать циклических импортов
        if getattr(self, 'swagger_fake_view', False):
            return []
        # Ленивый импорт для избежания циклических зависимостей
        from .serializers import ProviderLocationServiceSerializer
        # Получаем все услуги из всех активных локаций
        location_services = ProviderLocationService.objects.filter(
            location__provider=obj,
            location__is_active=True,
            is_active=True
        ).select_related('location', 'service')
        return ProviderLocationServiceSerializer(location_services, many=True).data
    
    def get_employees(self, obj):
        # Для Swagger возвращаем пустой список
        if getattr(self, 'swagger_fake_view', False):
            return []
        from .serializers import EmployeeSerializer
        return EmployeeSerializer(obj.employees.all(), many=True).data
    
    def get_distance(self, obj):
        """
        Возвращает расстояние до провайдера, если указаны координаты поиска.
        Использует координаты первой активной локации провайдера.
        """
        # Получаем координаты поиска из контекста
        context = self.context
        search_lat = context.get('latitude')
        search_lon = context.get('longitude')
        
        if not search_lat or not search_lon:
            return None
        
        try:
            search_lat = float(search_lat)
            search_lon = float(search_lon)
        except (ValueError, TypeError):
            return None
        
        # Получаем координаты из первой активной локации провайдера
        # Координаты теперь хранятся в локациях (ProviderLocation), а не в организации
        location = obj.locations.filter(is_active=True).first()
        if location and location.point:
            from django.contrib.gis.geos import Point
            search_point = Point(search_lon, search_lat, srid=location.point.srid)
            distance = location.point.distance(search_point) * 111.32  # Convert to km
            return round(distance, 2) if distance is not None else None
        
        return None
    
    def get_price_info(self, obj):
        """
        Возвращает информацию о ценах на услуги из всех локаций провайдера.
        Возвращает минимальную и максимальную цену, если услуга доступна в нескольких локациях.
        """
        context = self.context
        service_id = context.get('service_id')
        
        if not service_id:
            return None
        
        try:
            service_id = int(service_id)
            # Получаем все услуги из всех активных локаций провайдера
            location_services = ProviderLocationService.objects.filter(
                location__provider=obj,
                location__is_active=True,
                service_id=service_id,
                is_active=True
            )
            
            if location_services.exists():
                prices = [float(ls.price) for ls in location_services]
                durations = [ls.duration_minutes for ls in location_services]
                tech_breaks = [ls.tech_break_minutes for ls in location_services]
                
                return {
                    'service_id': service_id,
                    'price_min': min(prices),
                    'price_max': max(prices) if len(prices) > 1 else prices[0],
                    'price': min(prices),  # Для обратной совместимости
                    'duration_minutes': durations[0] if durations else 60,
                    'tech_break_minutes': tech_breaks[0] if tech_breaks else 0,
                    'locations_count': location_services.count()
                }
        except (ValueError, TypeError):
            pass
        
        return None
    
    def get_availability_info(self, obj):
        """
        Возвращает информацию о доступности учреждения.
        """
        context = self.context
        available_date = context.get('available_date')
        available_time = context.get('available_time')
        service_id = context.get('service_id')
        
        if not available_date or not available_time:
            return None
        
        try:
            from datetime import datetime, timedelta
            from booking.models import Booking
            
            # Парсим дату и время
            date_obj = datetime.strptime(available_date, '%Y-%m-%d').date()
            time_obj = datetime.strptime(available_time, '%H:%M').time()
            datetime_obj = datetime.combine(date_obj, time_obj)
            
            # Получаем день недели (0 = понедельник)
            weekday = date_obj.weekday()
            
            # Проверяем расписание учреждения
            provider_schedule = obj.schedules.filter(weekday=weekday).first()
            if not provider_schedule or provider_schedule.is_closed:
                return {
                    'available': False,
                    'reason': 'provider_closed',
                    'message': _('Institution is closed on this day')
                }
            
            # Проверяем время работы
            if (provider_schedule.open_time and provider_schedule.close_time and
                (time_obj < provider_schedule.open_time or time_obj > provider_schedule.close_time)):
                return {
                    'available': False,
                    'reason': 'outside_hours',
                    'message': f'Учреждение работает с {provider_schedule.open_time} до {provider_schedule.close_time}'
                }
            
            # Проверяем доступность сотрудников
            if service_id:
                employees = obj.employees.filter(
                    services__id=service_id,
                    is_active=True
                )
                
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
                    slot_end_time = datetime_obj + timedelta(minutes=30)  # Предполагаем 30 минут
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
                            'position': employee.position
                        })
                
                if available_employees:
                    return {
                        'available': True,
                        'available_employees': available_employees,
                        'message': f'Доступно {len(available_employees)} сотрудников'
                    }
                else:
                    return {
                        'available': False,
                        'reason': 'no_available_employees',
                        'message': _('No available employees at this time')
                    }
            else:
                # Если услуга не указана, проверяем наличие работающих сотрудников
                if obj.employees.filter(is_active=True).exists():
                    return {
                        'available': True,
                        'message': _('There are working employees')
                    }
                else:
                    return {
                        'available': False,
                        'reason': 'no_employees',
                        'message': _('No working employees')
                    }
                    
        except (ValueError, TypeError):
            return {
                'available': False,
                'reason': 'error',
                'message': _('Error checking availability')
            }
        
        return None
    
    class Meta:
        model = Provider
        fields = [
            'id', 'name', 'structured_address',
            'phone_number', 'email', 'website', 'logo',
            'is_active', 'created_at', 'updated_at', 'available_category_levels', 'available_categories',
            'services', 'employees', 'distance', 'price_info', 'availability_info'
        ]
        read_only_fields = ['created_at', 'updated_at', 'distance', 'price_info', 'availability_info']


class EmployeeSpecializationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для специализации сотрудника.
    """
    class Meta:
        model = EmployeeSpecialization
        fields = ['id', 'name', 'description', 'permissions']
        read_only_fields = ['id', 'name', 'description', 'permissions']


class EmployeeSerializer(serializers.ModelSerializer):
    """
    Сериализатор для сотрудника учреждения.
    """
    user = UserSerializer(read_only=True)
    providers = ProviderSerializer(many=True, read_only=True)
    services = ServiceSerializer(many=True, read_only=True)
    specializations = EmployeeSpecializationSerializer(many=True, read_only=True)
    is_manager = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            'id', 'user', 'providers', 'position', 'bio', 'photo',
            'services', 'specializations', 'is_active', 'is_manager',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_is_manager(self, obj):
        """
        Проверяет, является ли сотрудник менеджером в каком-либо учреждении.
        """
        return obj.employeeprovider_set.filter(is_manager=True).exists()


class EmployeeRegistrationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для регистрации сотрудника учреждения.
    """
    user_id = serializers.IntegerField(write_only=True)
    specializations = serializers.PrimaryKeyRelatedField(
        queryset=EmployeeSpecialization.objects.filter(is_active=True),
        many=True,
        required=True
    )
    start_date = serializers.DateField(write_only=True)
    is_manager = serializers.BooleanField(write_only=True, default=False)

    class Meta:
        model = Employee
        fields = [
            'user_id', 'position', 'bio', 'photo', 'specializations',
            'start_date', 'is_manager'
        ]

    def validate_user_id(self, value):
        """
        Проверяет, что пользователь существует и не является сотрудником.
        """
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError(_("User does not exist"))
        if Employee.objects.filter(user_id=value).exists():
            raise serializers.ValidationError(_("User is already an employee"))
        return value

    def create(self, validated_data):
        """
        Создает нового сотрудника и связывает его с учреждением.
        """
        user_id = validated_data.pop('user_id')
        specializations = validated_data.pop('specializations')
        start_date = validated_data.pop('start_date')
        is_manager = validated_data.pop('is_manager')

        employee = Employee.objects.create(
            user_id=user_id,
            **validated_data
        )
        employee.specializations.set(specializations)

        # Создаем связь с учреждением
        EmployeeProvider.objects.create(
            employee=employee,
            provider=self.context['provider'],
            start_date=start_date,
            is_manager=is_manager
        )

        return employee


class EmployeeProviderSerializer(serializers.ModelSerializer):
    """
    Сериализатор для связи сотрудник-учреждение.
    """
    class Meta:
        model = EmployeeProvider
        fields = [
            'id',
            'employee',
            'provider',
            'start_date',
            'end_date',
            'is_manager',
            'is_confirmed',
            'confirmation_requested_at',
            'confirmed_at'
        ]
        read_only_fields = [
            'id',
            'employee',
            'provider',
            'is_confirmed',
            'confirmation_requested_at',
            'confirmed_at'
        ]

    def validate(self, data):
        """
        Проверяет корректность дат начала и окончания работы.
        """
        if data.get('end_date') and data['end_date'] < data['start_date']:
            raise serializers.ValidationError(
                _("End date cannot be earlier than start date")
            )
        return data


class EmployeeProviderUpdateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для обновления связи сотрудник-учреждение.
    """
    class Meta:
        model = EmployeeProvider
        fields = ['start_date', 'end_date', 'is_manager']
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, data):
        """
        Проверяет корректность дат начала и окончания работы.
        """
        if data.get('end_date') and data['end_date'] < data['start_date']:
            raise serializers.ValidationError(
                _("End date cannot be earlier than start date")
            )
        return data


class ProviderSearchSerializer(serializers.Serializer):
    """
    Serializer для поиска поставщика услуги
    """
    name = serializers.CharField(required=False)
    address = serializers.CharField(required=False)
    service_type = serializers.CharField(required=False)
    latitude = serializers.FloatField(required=False)
    longitude = serializers.FloatField(required=False)
    radius = serializers.FloatField(required=False)  # in kilometers
    min_rating = serializers.FloatField(required=False)
    available_at = serializers.DateTimeField(required=False)
    working_hours = serializers.BooleanField(required=False)
    weekend_available = serializers.BooleanField(required=False)
    language = serializers.CharField(required=False)
    specialization = serializers.CharField(required=False)
    price_min = serializers.DecimalField(required=False, max_digits=10, decimal_places=2)
    price_max = serializers.DecimalField(required=False, max_digits=10, decimal_places=2)

    def get_queryset(self):
        """
        Возвращает queryset поставщиков, соответствующих запросу.
        """
        queryset = Provider.objects.filter(is_active=True)
        data = self.validated_data

        if data.get('name'):
            queryset = queryset.filter(name__icontains=data['name'])

        if data.get('address'):
            queryset = queryset.filter(
                structured_address__formatted_address__icontains=data['address']
            )

        if data.get('service_type'):
            queryset = queryset.filter(services__category__name=data['service_type'])

        if all(key in data for key in ['latitude', 'longitude', 'radius']):
            from django.contrib.gis.geos import Point
            from django.contrib.gis.db.models.functions import Distance
            
            search_point = Point(data['longitude'], data['latitude'], srid=4326)
            radius_meters = data['radius'] * 1000  # Convert km to meters
            
            queryset = queryset.filter(
                structured_address__point__distance_lte=(search_point, radius_meters)
            ).annotate(
                distance=Distance('structured_address__point', search_point)
            ).order_by('distance')

        if data.get('min_rating'):
            queryset = queryset.filter(rating__gte=data['min_rating'])

        if data.get('available_at'):
            queryset = queryset.filter(
                Q(schedules__day_of_week=data['available_at'].weekday()) &
                Q(schedules__start_time__lte=data['available_at'].time()) &
                Q(schedules__end_time__gte=data['available_at'].time())
            )

        if data.get('working_hours'):
            current_time = timezone.now().time()
            queryset = queryset.filter(
                schedules__start_time__lte=current_time,
                schedules__end_time__gte=current_time
            )

        if data.get('weekend_available'):
            queryset = queryset.filter(
                schedules__day_of_week__in=[5, 6]  # суббота и воскресенье
            )

        if data.get('language'):
            queryset = queryset.filter(
                employees__user__languages__icontains=data['language']
            )

        if data.get('specialization'):
            queryset = queryset.filter(
                employees__specializations__name__icontains=data['specialization']
            )

        if data.get('price_min') or data.get('price_max'):
            # Фильтрация по цене через локации
            from providers.models import ProviderLocationService
            location_services_filter = ProviderLocationService.objects.filter(
                location__provider__in=queryset,
                location__is_active=True,
                is_active=True
            )
            if data.get('price_min'):
                location_services_filter = location_services_filter.filter(price__gte=data['price_min'])
            if data.get('price_max'):
                location_services_filter = location_services_filter.filter(price__lte=data['price_max'])
            # Получаем ID провайдеров с подходящими ценами
            provider_ids = location_services_filter.values_list('location__provider_id', flat=True).distinct()
            queryset = queryset.filter(id__in=provider_ids)

        return queryset.distinct()


class ServiceFilterSerializer(serializers.Serializer):
    """
    Serializer для фильтрации услуги
    """
    category = serializers.CharField(required=False)
    price_min = serializers.DecimalField(required=False, max_digits=10, decimal_places=2)
    price_max = serializers.DecimalField(required=False, max_digits=10, decimal_places=2)
    provider_id = serializers.IntegerField(required=False)
    specialization = serializers.CharField(required=False)

    def get_queryset(self):
        """
        Возвращает queryset услуг, соответствующих запросу.
        """
        queryset = ProviderLocationService.objects.filter(
            location__is_active=True,
            is_active=True
        ).select_related('location', 'service', 'location__provider')
        data = self.validated_data

        if data.get('category'):
            queryset = queryset.filter(service__category__name__icontains=data['category'])

        if data.get('price_min') or data.get('price_max'):
            price_filter = Q()
            if data.get('price_min'):
                price_filter &= Q(price__gte=data['price_min'])
            if data.get('price_max'):
                price_filter &= Q(price__lte=data['price_max'])
            queryset = queryset.filter(price_filter)

        if data.get('provider_id'):
            queryset = queryset.filter(location__provider_id=data['provider_id'])

        if data.get('specialization'):
            queryset = queryset.filter(
                provider__employees__specializations__name__icontains=data['specialization']
            )

        return queryset.distinct()


class ScheduleSerializer(serializers.ModelSerializer):
    """
    Сериализатор для расписания сотрудника.
    """
    employee = EmployeeSerializer(read_only=True)

    class Meta:
        model = Schedule
        fields = [
            'id', 'employee', 'day_of_week', 'start_time', 'end_time',
            'break_start', 'break_end', 'is_working', 'created_at',
            'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, data):
        """
        Проверяет корректность времени работы и перерыва.
        """
        if data['end_time'] <= data['start_time']:
            raise serializers.ValidationError(
                _("End time must be later than start time")
            )
        if data.get('break_start') and data.get('break_end'):
            if data['break_end'] <= data['break_start']:
                raise serializers.ValidationError(
                    _("Break end time must be later than break start time")
                )
            if data['break_start'] < data['start_time'] or data['break_end'] > data['end_time']:
                raise serializers.ValidationError(
                    _("Break time must be within working hours")
                )
        return data


# ProviderServiceSerializer удален - используйте ProviderLocationServiceSerializer


class EmployeeWorkSlotSerializer(serializers.ModelSerializer):
    """
    Сериализатор для рабочего слота сотрудника.
    """
    class Meta:
        model = EmployeeWorkSlot
        fields = '__all__'


class EmployeeJoinRequestSerializer(serializers.ModelSerializer):
    """
    Сериализатор для заявки на вступление в учреждение.
    """
    class Meta:
        model = EmployeeJoinRequest
        fields = ['id', 'user', 'provider', 'position', 'comment', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'status', 'created_at', 'updated_at', 'user']


class EmployeeProviderConfirmSerializer(serializers.ModelSerializer):
    """
    Сериализатор для подтверждения сотрудником своей роли.
    """
    class Meta:
        model = EmployeeProvider
        fields = ['is_confirmed']


class ProviderLocationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для локации провайдера (точки предоставления услуг).
    
    Основные характеристики:
    - Связь с организацией (Provider)
    - Адрес и координаты локации
    - Контактная информация
    - Список доступных услуг
    """
    provider_name = serializers.CharField(source='provider.name', read_only=True)
    full_address = serializers.SerializerMethodField()
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    available_services = serializers.SerializerMethodField()
    
    def get_full_address(self, obj):
        """
        Возвращает полный адрес локации.
        """
        return obj.get_full_address()
    
    def get_latitude(self, obj):
        """
        Возвращает широту из структурированного адреса.
        """
        if obj.structured_address and obj.structured_address.latitude:
            return float(obj.structured_address.latitude)
        return None
    
    def get_longitude(self, obj):
        """
        Возвращает долготу из структурированного адреса.
        """
        if obj.structured_address and obj.structured_address.longitude:
            return float(obj.structured_address.longitude)
        return None
    
    def get_available_services(self, obj):
        """
        Возвращает список доступных услуг в локации.
        """
        # Для Swagger возвращаем пустой список, чтобы избежать циклических импортов
        if getattr(self, 'swagger_fake_view', False):
            return []
        from .serializers import ProviderLocationServiceSerializer
        services = ProviderLocationService.objects.filter(
            location=obj,
            is_active=True
        )
        return ProviderLocationServiceSerializer(services, many=True).data
    
    class Meta:
        model = ProviderLocation
        fields = [
            'id', 'provider', 'provider_name', 'name',
            'structured_address', 'full_address',
            'latitude', 'longitude',
            'phone_number', 'email',
            'available_services',
            'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'provider_name', 'full_address', 'latitude', 'longitude', 'available_services']
    
    def validate(self, data):
        """
        Валидация данных локации.
        
        Проверяет:
        - Услуги должны быть из категорий уровня 0 организации
        """
        provider = data.get('provider')
        if provider:
            # Проверяем, что услуги из доступных категорий организации
            # (это будет проверяться при создании ProviderLocationService)
            pass
        return data


class ProviderLocationServiceSerializer(serializers.ModelSerializer):
    """
    Сериализатор для услуги в локации провайдера.
    
    Основные характеристики:
    - Связь с локацией и услугой
    - Цена услуги в конкретной локации
    - Длительность услуги
    - Технический перерыв
    """
    location_name = serializers.CharField(source='location.name', read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)
    service_details = ServiceSerializer(source='service', read_only=True)
    
    class Meta:
        model = ProviderLocationService
        fields = [
            'id', 'location', 'location_name',
            'service', 'service_name', 'service_details',
            'price', 'duration_minutes', 'tech_break_minutes',
            'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'location_name', 'service_name', 'service_details']
    
    def validate(self, data):
        """
        Валидация данных услуги локации.
        
        Проверяет:
        - Услуга должна быть из категорий уровня 0 организации
        - Цена должна быть положительной
        - Длительность должна быть положительной
        """
        location = data.get('location')
        service = data.get('service')
        
        if location and service:
            # Проверяем, что услуга из доступных категорий организации
            provider = location.provider
            available_categories = provider.available_category_levels.filter(level=0, parent__isnull=True)
            
            # Проверяем, что услуга является потомком одной из доступных категорий
            from django.db.models import Q
            if not Service.objects.filter(
                Q(id=service.id) & (
                    Q(id__in=available_categories.values_list('id', flat=True)) |
                    Q(parent_id__in=available_categories.values_list('id', flat=True))
                )
            ).exists():
                raise serializers.ValidationError(
                    _('Service must be from provider\'s available category levels (level 0).')
                )
        
        price = data.get('price')
        if price is not None and price <= 0:
            raise serializers.ValidationError(
                _('Price must be positive.')
            )
        
        duration = data.get('duration_minutes')
        if duration is not None and duration <= 0:
            raise serializers.ValidationError(
                _('Duration must be positive.')
            )
        
        return data 