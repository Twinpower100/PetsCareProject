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
from .models import Provider, Employee, EmployeeProvider, Schedule, LocationSchedule, HolidayShift, EmployeeWorkSlot, EmployeeJoinRequest, ProviderLocation, ProviderLocationService
from .contact_validators import validate_phone_contact, validate_email_contact
from catalog.serializers import ServiceSerializer
from catalog.models import Service
from pets.models import PetType
from users.serializers import UserSerializer
from users.models import EmployeeSpecialization, User, ProviderAdmin as UserProviderAdmin
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
        # EmployeeBriefSerializer без providers, чтобы не уходить в рекурсию Provider->employees->Employee->providers->Provider->employees
        from .serializers import EmployeeBriefSerializer
        return EmployeeBriefSerializer(obj.employees.all(), many=True).data
    
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


class EmployeeBriefSerializer(serializers.ModelSerializer):
    """
    Краткий сериализатор сотрудника без вложенных providers.
    Используется в ProviderSerializer.get_employees, чтобы избежать рекурсии
    (EmployeeSerializer -> ProviderSerializer -> get_employees -> ...).
    Услуги берутся из EmployeeLocationService (агрегат по всем локациям).
    """
    user = UserSerializer(read_only=True)
    services = serializers.SerializerMethodField()
    specializations = EmployeeSpecializationSerializer(many=True, read_only=True)
    is_manager = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            'id', 'user',
            'services', 'specializations', 'is_active', 'is_manager',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_services(self, obj):
        """Уникальные услуги сотрудника по всем локациям (EmployeeLocationService)."""
        from catalog.models import Service
        ids = obj.location_services.values_list('service_id', flat=True).distinct()
        return ServiceSerializer(Service.objects.filter(id__in=ids), many=True).data

    def get_is_manager(self, obj):
        return obj.employeeprovider_set.filter(is_manager=True).exists()


class EmployeeSerializer(serializers.ModelSerializer):
    """
    Сериализатор для сотрудника учреждения.
    Услуги берутся из EmployeeLocationService (агрегат по всем локациям).
    """
    user = UserSerializer(read_only=True)
    providers = ProviderSerializer(many=True, read_only=True)
    services = serializers.SerializerMethodField()
    specializations = EmployeeSpecializationSerializer(many=True, read_only=True)
    is_manager = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            'id', 'user', 'providers',
            'services', 'specializations', 'is_active', 'is_manager',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_services(self, obj):
        """Уникальные услуги сотрудника по всем локациям (EmployeeLocationService)."""
        from catalog.models import Service
        ids = obj.location_services.values_list('service_id', flat=True).distinct()
        return ServiceSerializer(Service.objects.filter(id__in=ids), many=True).data

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
            'user_id', 'specializations',
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
            # Поиск по услугам сотрудников в локациях (EmployeeLocationService)
            queryset = queryset.filter(
                employees__location_services__service__parent__name=data['service_type']
            ).distinct()

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
    Сериализатор для локации провайдера (филиала).
    
    Основные характеристики:
    - Связь с организацией (Provider)
    - Адрес и координаты локации
    - Контактная информация
    - Список доступных услуг
    """
    provider_name = serializers.CharField(source='provider.name', read_only=True)
    # Код страны (ISO 3166-1 alpha-2) для API праздников и правил «закрыто в праздники»
    country = serializers.SerializerMethodField()
    full_address = serializers.SerializerMethodField()
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    available_services = serializers.SerializerMethodField()
    schedule_filled = serializers.SerializerMethodField()
    employees_count = serializers.SerializerMethodField()
    staff_schedule_filled = serializers.SerializerMethodField()
    manager = serializers.SerializerMethodField()
    manager_filled = serializers.SerializerMethodField()
    manager_invite_pending_email = serializers.SerializerMethodField()
    provider_currency_code = serializers.SerializerMethodField()
    served_pet_types = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=PetType.objects.all().order_by('code'),
        required=False,
        allow_empty=True,
        help_text=_('Pet types (e.g. dog, cat) that this location serves. Required before adding services and prices.'),
    )
    served_pet_types_details = serializers.SerializerMethodField()

    def get_served_pet_types_details(self, obj):
        """Список {id, code, name} по выбранным типам животных для отображения на фронте."""
        if getattr(self, 'swagger_fake_view', False):
            return []
        if not hasattr(obj, 'served_pet_types'):
            return []
        return [
            {'id': pt.id, 'code': pt.code, 'name': getattr(pt, 'name_en', None) or pt.name}
            for pt in obj.served_pet_types.all().order_by('code')
        ]

    def get_country(self, obj):
        """Страна локации: только из адреса локации (structured_address). Адрес обязателен — страны провайдера нет в поле."""
        if obj.structured_address and getattr(obj.structured_address, 'country', None):
            c = (obj.structured_address.country or '').strip().upper()
            if len(c) == 2:
                return c
            # Частые названия стран из геокода (long_name) → ISO 3166-1 alpha-2
            country_name_to_code = {
                'RUSSIA': 'RU', 'RUSSIAN FEDERATION': 'RU',
                'GERMANY': 'DE', 'DEUTSCHLAND': 'DE',
                'UNITED STATES': 'US', 'UNITED STATES OF AMERICA': 'US', 'USA': 'US',
                'FRANCE': 'FR', 'UNITED KINGDOM': 'GB', 'UK': 'GB', 'GREAT BRITAIN': 'GB',
                'AUSTRIA': 'AT', 'SWITZERLAND': 'CH', 'BELARUS': 'BY', 'UKRAINE': 'UA',
                'KAZAKHSTAN': 'KZ', 'SERBIA': 'RS', 'MONTENEGRO': 'ME',
            }
            return country_name_to_code.get(c)
        return None

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

    def get_schedule_filled(self, obj):
        """True если у локации есть хотя бы один рабочий день (LocationSchedule с is_closed=False и заданными open_time, close_time)."""
        if getattr(self, 'swagger_fake_view', False):
            return False
        return LocationSchedule.objects.filter(
            provider_location=obj,
            is_closed=False
        ).exclude(open_time__isnull=True).exclude(close_time__isnull=True).exists()

    def get_employees_count(self, obj):
        """Количество сотрудников, привязанных к этой локации (активные)."""
        if getattr(self, 'swagger_fake_view', False):
            return 0
        return obj.employees.filter(is_active=True).count()

    def get_staff_schedule_filled(self, obj):
        """True если у локации нет активных сотрудников или у всех активных сотрудников есть хотя бы одна запись расписания (Schedule) для этой локации."""
        if getattr(self, 'swagger_fake_view', False):
            return True
        active = obj.employees.filter(is_active=True)
        if not active.exists():
            return True
        for emp in active:
            if not Schedule.objects.filter(employee=emp, provider_location=obj).exists():
                return False
        return True

    def get_manager(self, obj):
        """Данные руководителя точки (имя, фамилия, email, телефон) для отображения во вкладке «Общая информация». Только для поддержки/эскалации."""
        if getattr(self, 'swagger_fake_view', False):
            return None
        if not obj.manager_id:
            return None
        u = obj.manager
        pn = getattr(u, 'phone_number', None)
        phone_str = str(pn) if pn is not None else ''
        return {
            'first_name': u.first_name or '',
            'last_name': u.last_name or '',
            'email': u.email or '',
            'phone_number': phone_str,
        }

    def get_manager_filled(self, obj):
        """True если у локации назначен руководитель (для семафора на списке локаций)."""
        return obj.manager_id is not None

    def get_manager_invite_pending_email(self, obj):
        """Email, на который отправлено приглашение, если инвайт ещё не истёк (для отображения «Приглашение отправлено на …»)."""
        if getattr(self, 'swagger_fake_view', False):
            return None
        invite = getattr(obj, 'manager_invites', None)
        if not invite:
            return None
        active = invite.filter(expires_at__gt=timezone.now()).order_by('-created_at').first()
        return active.email if active else None

    def get_provider_currency_code(self, obj):
        """Код валюты провайдера (для отображения цен на вкладке «Услуги и цены»)."""
        if getattr(self, 'swagger_fake_view', False):
            return None
        provider = getattr(obj, 'provider', None)
        if not provider:
            return None
        inv = getattr(provider, 'invoice_currency', None)
        return getattr(inv, 'code', None) if inv else None

    class Meta:
        model = ProviderLocation
        fields = [
            'id', 'provider', 'provider_name', 'name',
            'structured_address', 'full_address', 'country',
            'latitude', 'longitude',
            'phone_number', 'email',
            'served_pet_types',
            'served_pet_types_details',
            'available_services',
            'schedule_filled',
            'employees_count',
            'staff_schedule_filled',
            'manager',
            'manager_filled',
            'manager_invite_pending_email',
            'provider_currency_code',
            'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'provider_name', 'country', 'full_address', 'latitude', 'longitude', 'served_pet_types_details', 'available_services', 'schedule_filled', 'employees_count', 'staff_schedule_filled', 'manager', 'manager_filled', 'manager_invite_pending_email', 'provider_currency_code']

    def validate_phone_number(self, value):
        """Валидация формата телефона (10–15 цифр, E.164-подобный)."""
        if not value:
            return value
        ok, err = validate_phone_contact(value)
        if not ok:
            raise serializers.ValidationError(err)
        return value.strip()

    def validate_email(self, value):
        """Валидация формата email."""
        if not value:
            return value
        ok, err = validate_email_contact(value)
        if not ok:
            raise serializers.ValidationError(err)
        return value.strip().lower()
    
    def validate(self, data):
        """
        Валидация данных локации.
        
        Проверяет:
        - Адрес обязателен при создании точки предоставления услуг
        - Услуги должны быть из категорий уровня 0 организации
        - При создании можно подставлять phone/email из организации (предзаполнение)
        """
        if not self.instance:
            if not data.get('structured_address'):
                raise serializers.ValidationError({
                    'structured_address': _('Address is required for the service location.')
                })
        provider = data.get('provider') or (self.instance.provider if self.instance else None)
        if provider:
            # Предзаполнение: если phone_number или email не переданы, взять из организации
            if not data.get('phone_number') and getattr(provider, 'phone_number', None):
                data.setdefault('phone_number', provider.phone_number)
            if not data.get('email') and getattr(provider, 'email', None):
                data.setdefault('email', provider.email)
        return data


class ProviderLocationServiceSerializer(serializers.ModelSerializer):
    """
    Сериализатор для одной записи услуги в локации (локация + услуга + тип животного + размер).
    При создании API может передать pet_type_id вместо pet_type.
    """
    location_name = serializers.CharField(source='location.name', read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)
    service_details = ServiceSerializer(source='service', read_only=True)
    pet_type_code = serializers.CharField(source='pet_type.code', read_only=True)
    pet_type_id = serializers.IntegerField(required=False, write_only=True, allow_null=True)

    class Meta:
        model = ProviderLocationService
        fields = [
            'id', 'location', 'location_name',
            'service', 'service_name', 'service_details',
            'pet_type', 'pet_type_id', 'pet_type_code', 'size_code',
            'price', 'duration_minutes', 'tech_break_minutes',
            'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'location_name', 'service_name', 'service_details', 'pet_type_code']
    
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
            # Та же логика, что в ProviderAvailableCatalogServicesAPIView: услуга должна быть
            # в множестве «корни + все потомки» доступных категорий уровня 0.
            provider = location.provider
            root_ids = list(
                provider.available_category_levels.filter(level=0, parent__isnull=True)
                .values_list('id', flat=True)
            )
            if not root_ids:
                raise serializers.ValidationError(
                    _('Service must be from provider\'s available category levels (level 0).')
                )
            allowed_ids = set(root_ids)
            frontier_ids = set(root_ids)
            while frontier_ids:
                child_ids = set(
                    Service.objects.filter(parent_id__in=frontier_ids, is_active=True)
                    .values_list('id', flat=True)
                ) - allowed_ids
                if not child_ids:
                    break
                allowed_ids.update(child_ids)
                frontier_ids = child_ids
            if service.id not in allowed_ids:
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
        # API может передать pet_type_id при создании; приводим к pet_type для модели
        pet_type_id = data.pop('pet_type_id', None)
        if pet_type_id is not None:
            from pets.models import PetType
            try:
                data['pet_type'] = PetType.objects.get(pk=pet_type_id)
            except PetType.DoesNotExist:
                raise serializers.ValidationError(_('Invalid pet type.'))
        pet_type = data.get('pet_type')
        if not self.instance and not pet_type:
            raise serializers.ValidationError(_('Pet type is required when creating a location service.'))
        if pet_type and location:
            served_ids = set(location.served_pet_types.values_list('id', flat=True))
            if pet_type.id not in served_ids:
                raise serializers.ValidationError(
                    _('Pet type must be one of the location\'s served pet types.')
                )
        if not self.instance and not data.get('size_code'):
            raise serializers.ValidationError(_('Size code is required when creating a location service.'))
        return data


# --- Тело PUT матрицы цен (LocationServicePricesUpdateAPIView) ---

class ServiceVariantWriteSerializer(serializers.Serializer):
    """Тело варианта цены по размеру (S/M/L/XL) для PUT матрицы цен."""
    size_code = serializers.ChoiceField(choices=['S', 'M', 'L', 'XL'])
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    duration_minutes = serializers.IntegerField(min_value=1)


class LocationServicePriceItemWriteSerializer(serializers.Serializer):
    """Один элемент матрицы: тип животного + базовая цена/длительность + варианты по размерам."""
    pet_type_id = serializers.IntegerField()
    base_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    base_duration_minutes = serializers.IntegerField(min_value=1)
    variants = serializers.ListField(
        child=ServiceVariantWriteSerializer(),
        required=False,
        default=list
    )

    def validate_pet_type_id(self, value):
        if not PetType.objects.filter(pk=value).exists():
            raise serializers.ValidationError(_('Invalid pet type.'))
        return value


class LocationServicePricesUpdateSerializer(serializers.Serializer):
    """Тело PUT запроса на обновление матрицы цен по услуге локации."""
    prices = serializers.ListField(child=LocationServicePriceItemWriteSerializer())


class LocationScheduleSerializer(serializers.ModelSerializer):
    """
    Сериализатор расписания работы локации (дни недели, время открытия/закрытия).
    provider_location задаётся из URL (location_pk) при создании в view.
    """
    weekday_display = serializers.CharField(source='get_weekday_display', read_only=True)
    open_time = serializers.TimeField(required=False, allow_null=True, input_formats=['%H:%M:%S', '%H:%M'])
    close_time = serializers.TimeField(required=False, allow_null=True, input_formats=['%H:%M:%S', '%H:%M'])

    class Meta:
        model = LocationSchedule
        fields = [
            'id', 'provider_location', 'weekday', 'weekday_display',
            'open_time', 'close_time', 'is_closed',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'weekday_display']
        extra_kwargs = {'provider_location': {'required': False}}

    def validate(self, data):
        """Валидация: если не выходной, то open_time и close_time должны быть заданы и open_time < close_time."""
        is_closed = data.get('is_closed', getattr(self.instance, 'is_closed', False))
        open_t = data.get('open_time') if 'open_time' in data else getattr(self.instance, 'open_time', None)
        close_t = data.get('close_time') if 'close_time' in data else getattr(self.instance, 'close_time', None)
        # При закрытом дне принудительно null (на случай пустых строк от клиента).
        if is_closed:
            data['open_time'] = None
            data['close_time'] = None
            return data
        if open_t is None or close_t is None:
            raise serializers.ValidationError(
                _('Open time and close time are required when the location is not closed on this day.')
            )
        if open_t >= close_t:
            raise serializers.ValidationError(
                _('Open time must be before close time.')
            )
        return data


class HolidayShiftSerializer(serializers.ModelSerializer):
    """
    Сериализатор смены в праздничный день.
    provider_location задаётся из URL (location_pk) при создании.
    Валидация (дата должна быть праздником в глобальном календаре, start < end) выполняется в модели.
    """
    class Meta:
        model = HolidayShift
        fields = ['id', 'provider_location', 'date', 'start_time', 'end_time']
        read_only_fields = []
        extra_kwargs = {'provider_location': {'required': False}}


class ProviderAdminListSerializer(serializers.ModelSerializer):
    """
    Сериализатор списка админов провайдера для страницы персонала.
    Возвращает пользователя и роль (owner / provider_admin), чтобы отображать владельца учреждения.
    """
    user = UserSerializer(read_only=True)
    role = serializers.CharField(read_only=True)

    class Meta:
        model = UserProviderAdmin
        fields = ['id', 'user', 'role', 'is_active', 'created_at']
        read_only_fields = ['id', 'user', 'role', 'is_active', 'created_at']
