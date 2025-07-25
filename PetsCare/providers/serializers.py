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
from .models import Provider, Employee, EmployeeProvider, Schedule, ProviderService, ProviderSchedule, EmployeeWorkSlot, EmployeeJoinRequest
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
    
    def get_services(self, obj):
        from .serializers import ProviderServiceSerializer
        return ProviderServiceSerializer(obj.provider_services.all(), many=True).data
    
    def get_employees(self, obj):
        from .serializers import EmployeeSerializer
        return EmployeeSerializer(obj.employees.all(), many=True).data
    
    def get_distance(self, obj):
        """
        Возвращает расстояние до провайдера, если указаны координаты поиска.
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
        
        # Получаем координаты провайдера
        if hasattr(obj, 'address') and obj.address:
            provider_lat = obj.address.latitude
            provider_lon = obj.address.longitude
            
            if provider_lat is not None and provider_lon is not None:
                distance = calculate_distance(search_lat, search_lon, provider_lat, provider_lon)
                return round(distance, 2) if distance is not None else None
        
        return None
    
    class Meta:
        model = Provider
        fields = [
            'id', 'name', 'description', 'address', 'location',
            'phone_number', 'email', 'website', 'logo', 'rating',
            'is_active', 'created_at', 'updated_at', 'available_category_levels', 'available_categories',
            'services', 'employees', 'distance'
        ]
        read_only_fields = ['created_at', 'updated_at', 'distance']

    def validate_rating(self, value):
        """
        Проверяет, что рейтинг находится в диапазоне от 0 до 5.
        """
        if value < 0 or value > 5:
            raise serializers.ValidationError(
                _("Rating must be between 0 and 5")
            )
        return value


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
            'position',
            'start_date',
            'end_date',
            'is_confirmed',
            'confirmation_requested_at',
            'confirmed_at',
            'is_active'
        ]
        read_only_fields = [
            'id',
            'employee',
            'provider',
            'is_confirmed',
            'confirmation_requested_at',
            'confirmed_at',
            'is_active'
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
            queryset = queryset.filter(address__icontains=data['address'])

        if data.get('service_type'):
            queryset = queryset.filter(services__category__name=data['service_type'])

        if all(key in data for key in ['latitude', 'longitude', 'radius']):
            search_point = (data['latitude'], data['longitude'])
            providers_in_radius = []
            
            for provider in queryset:
                if provider.latitude and provider.longitude:
                    provider_point = (provider.latitude, provider.longitude)
                    distance = geodesic(search_point, provider_point).kilometers
                    if distance <= data['radius']:
                        providers_in_radius.append(provider.id)
            
            queryset = queryset.filter(id__in=providers_in_radius)

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
            price_filter = Q()
            if data.get('price_min'):
                price_filter &= Q(provider_services__price__gte=data['price_min'])
            if data.get('price_max'):
                price_filter &= Q(provider_services__price__lte=data['price_max'])
            queryset = queryset.filter(price_filter)

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
        queryset = ProviderService.objects.all()
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
            queryset = queryset.filter(provider_id=data['provider_id'])

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


class ProviderServiceSerializer(serializers.ModelSerializer):
    """
    Сериализатор для услуги учреждения.
    """
    provider = ProviderSerializer(read_only=True)
    service = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.filter(is_active=True),
        help_text=_('Select service from catalog')
    )

    class Meta:
        model = ProviderService
        fields = [
            'id', 'provider', 'service', 'price', 'duration_minutes', 
            'tech_break_minutes', 'base_price', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_price(self, value):
        """
        Проверяет, что цена не отрицательная.
        """
        if value < 0:
            raise serializers.ValidationError(
                _("Price cannot be negative")
            )
        return value

    def validate(self, data):
        """
        Проверяет корректность данных услуги учреждения.
        """
        # Проверяем, что базовая цена не меньше основной цены
        base_price = data.get('base_price')
        price = data.get('price')
        
        if base_price and price and base_price < price:
            raise serializers.ValidationError(
                _("Base price cannot be less than main price")
            )
        
        return data


class ProviderScheduleSerializer(serializers.ModelSerializer):
    """
    Сериализатор для расписания учреждения.
    """
    class Meta:
        model = ProviderSchedule
        fields = '__all__'


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