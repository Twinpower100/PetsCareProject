"""
Фильтры для расширенного поиска питомцев.

Этот модуль содержит фильтры для:
1. Фильтрации по типу и породе питомца
2. Фильтрации по возрасту и весу
3. Фильтрации по геолокации
4. Фильтрации по медицинским условиям
5. Фильтрации по статусу и датам
"""

import django_filters
from django.db.models import Q, F, Value, IntegerField
from django.db.models.functions import ExtractYear, Now
from django.utils import timezone
from datetime import date, timedelta
from django.utils.translation import gettext_lazy as _

from .models import Pet, PetType, Breed


class PetFilter(django_filters.FilterSet):
    """
    Расширенный фильтр для поиска питомцев.
    
    Поддерживает фильтрацию по:
    - Типу и породе питомца
    - Возрасту и весу
    - Геолокации
    - Медицинским условиям
    - Статусу и датам
    """
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
    
    # Фильтрация по типу питомца
    pet_type = django_filters.ModelChoiceFilter(
        queryset=PetType.objects.all(),
        help_text=_('Filter by pet type')
    )
    
    pet_type_code = django_filters.CharFilter(
        field_name='pet_type__code',
        lookup_expr='exact',
        help_text=_('Filter by pet type code')
    )
    
    # Фильтрация по породе
    breed = django_filters.ModelChoiceFilter(
        queryset=Breed.objects.all(),
        help_text=_('Filter by breed')
    )
    
    breed_code = django_filters.CharFilter(
        field_name='breed__code',
        lookup_expr='exact',
        help_text=_('Filter by breed code')
    )
    
    # Фильтрация по возрасту
    age_min = django_filters.NumberFilter(
        method='filter_age_min',
        help_text=_('Minimum age in years')
    )
    
    age_max = django_filters.NumberFilter(
        method='filter_age_max',
        help_text=_('Maximum age in years')
    )
    
    age_range = django_filters.RangeFilter(
        method='filter_age_range',
        help_text=_('Age range in years (e.g., 2-5)')
    )
    
    # Фильтрация по весу
    weight_min = django_filters.NumberFilter(
        field_name='weight',
        lookup_expr='gte',
        help_text=_('Minimum weight in kg')
    )
    
    weight_max = django_filters.NumberFilter(
        field_name='weight',
        lookup_expr='lte',
        help_text=_('Maximum weight in kg')
    )
    
    weight_range = django_filters.RangeFilter(
        field_name='weight',
        help_text=_('Weight range in kg (e.g., 5-15)')
    )
    
    # Фильтрация по геолокации (если есть)
    location_lat = django_filters.NumberFilter(
        method='filter_by_location',
        help_text=_('Latitude for location-based search')
    )
    
    location_lng = django_filters.NumberFilter(
        method='filter_by_location',
        help_text=_('Longitude for location-based search')
    )
    
    radius_km = django_filters.NumberFilter(
        method='filter_by_location',
        help_text=_('Search radius in kilometers')
    )
    
    # Фильтрация по медицинским условиям
    has_medical_conditions = django_filters.BooleanFilter(
        method='filter_medical_conditions',
        help_text=_('Filter pets with medical conditions')
    )
    
    medical_condition = django_filters.CharFilter(
        method='filter_medical_condition',
        help_text=_('Search for specific medical condition')
    )
    
    # Фильтрация по особым потребностям
    has_special_needs = django_filters.BooleanFilter(
        method='filter_special_needs',
        help_text=_('Filter pets with special needs')
    )
    
    special_need = django_filters.CharFilter(
        method='filter_special_need',
        help_text=_('Search for specific special need')
    )
    
    # Фильтрация по датам
    created_after = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='gte',
        help_text=_('Created after this date')
    )
    
    created_before = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='lte',
        help_text=_('Created before this date')
    )
    
    updated_after = django_filters.DateFilter(
        field_name='updated_at',
        lookup_expr='gte',
        help_text=_('Updated after this date')
    )
    
    updated_before = django_filters.DateFilter(
        field_name='updated_at',
        lookup_expr='lte',
        help_text=_('Updated before this date')
    )
    
    # Фильтрация по последнему посещению
    last_visit_after = django_filters.DateFilter(
        method='filter_last_visit',
        help_text=_('Last visit after this date')
    )
    
    last_visit_before = django_filters.DateFilter(
        method='filter_last_visit',
        help_text=_('Last visit before this date')
    )
    
    # Фильтрация по владельцам
    owner = django_filters.NumberFilter(
        field_name='owners',
        lookup_expr='exact',
        help_text=_('Filter by owner ID')
    )
    
    main_owner = django_filters.NumberFilter(
        field_name='main_owner',
        lookup_expr='exact',
        help_text=_('Filter by main owner ID')
    )
    
    # Фильтрация по статусу
    is_active = django_filters.BooleanFilter(
        method='filter_active_status',
        help_text=_('Filter active/inactive pets')
    )
    
    class Meta:
        model = Pet
        fields = [
            'pet_type', 'breed', 'weight', 'created_at', 'updated_at',
            'owners', 'main_owner'
        ]
    
    def filter_age_min(self, queryset, name, value):
        """Фильтрация по минимальному возрасту."""
        if value is not None:
            max_birth_date = timezone.now().date() - timedelta(days=value * 365)
            return queryset.filter(birth_date__lte=max_birth_date)
        return queryset
    
    def filter_age_max(self, queryset, name, value):
        """Фильтрация по максимальному возрасту."""
        if value is not None:
            min_birth_date = timezone.now().date() - timedelta(days=(value + 1) * 365)
            return queryset.filter(birth_date__gt=min_birth_date)
        return queryset
    
    def filter_age_range(self, queryset, name, value):
        """Фильтрация по диапазону возраста."""
        if value.start is not None and value.stop is not None:
            max_birth_date = timezone.now().date() - timedelta(days=value.start * 365)
            min_birth_date = timezone.now().date() - timedelta(days=(value.stop + 1) * 365)
            return queryset.filter(
                birth_date__lte=max_birth_date,
                birth_date__gt=min_birth_date
            )
        return queryset
    
    def filter_by_location(self, queryset, name, value):
        """Фильтрация по геолокации с использованием PostGIS."""
        # Получаем параметры геолокации из request
        request = self.request
        if not request:
            return queryset
        
        lat = request.query_params.get('location_lat')
        lng = request.query_params.get('location_lng')
        radius = request.query_params.get('radius_km')
        
        if not all([lat, lng, radius]):
            return queryset
        
        try:
            lat = float(lat)
            lng = float(lng)
            radius = float(radius)
        except (ValueError, TypeError):
            return queryset
        
        # Используем PostGIS для фильтрации по расстоянию
        from django.contrib.gis.geos import Point
        from django.contrib.gis.db.models.functions import Distance
        
        search_point = Point(lng, lat)
        
        # Фильтруем питомцев по расстоянию от владельцев
        return queryset.filter(
            owners__address__point__distance_lte=(search_point, radius * 1000)  # radius в метрах
        ).annotate(
            distance=Distance('owners__address__point', search_point)
        ).order_by('distance')
    
    def filter_medical_conditions(self, queryset, name, value):
        """Фильтрация по наличию медицинских условий."""
        if value is True:
            return queryset.filter(
                ~Q(medical_conditions={}) & ~Q(medical_conditions__isnull=True)
            )
        elif value is False:
            return queryset.filter(
                Q(medical_conditions={}) | Q(medical_conditions__isnull=True)
            )
        return queryset
    
    def filter_medical_condition(self, queryset, name, value):
        """Поиск по конкретному медицинскому условию."""
        if value:
            return queryset.filter(
                medical_conditions__icontains=value
            )
        return queryset
    
    def filter_special_needs(self, queryset, name, value):
        """Фильтрация по наличию особых потребностей."""
        if value is True:
            return queryset.filter(
                ~Q(special_needs={}) & ~Q(special_needs__isnull=True)
            )
        elif value is False:
            return queryset.filter(
                Q(special_needs={}) | Q(special_needs__isnull=True)
            )
        return queryset
    
    def filter_special_need(self, queryset, name, value):
        """Поиск по конкретной особой потребности."""
        if value:
            return queryset.filter(
                special_needs__icontains=value
            )
        return queryset
    
    def filter_last_visit(self, queryset, name, value):
        """Фильтрация по дате последнего посещения."""
        if value:
            if name == 'last_visit_after':
                return queryset.filter(
                    records__date__gte=value
                ).distinct()
            elif name == 'last_visit_before':
                return queryset.filter(
                    records__date__lte=value
                ).distinct()
        return queryset
    
    def filter_active_status(self, queryset, name, value):
        """Фильтрация по активному статусу."""
        if value is True:
            # Активные питомцы - без недееспособности владельцев
            return queryset.exclude(
                incapacity_records__status__in=['pending_confirmation', 'confirmed_incapacity']
            )
        elif value is False:
            # Неактивные питомцы - с недееспособностью владельцев
            return queryset.filter(
                incapacity_records__status__in=['pending_confirmation', 'confirmed_incapacity']
            )
        return queryset 


class PetTypeFilter(django_filters.FilterSet):
    """Фильтр для типов питомцев."""
    
    name = django_filters.CharFilter(
        lookup_expr='icontains',
        help_text=_('Search by pet type name')
    )
    
    code = django_filters.CharFilter(
        lookup_expr='icontains',
        help_text=_('Search by pet type code')
    )
    
    class Meta:
        model = PetType
        fields = ['name', 'code']


class BreedFilter(django_filters.FilterSet):
    """Фильтр для пород питомцев."""
    
    name = django_filters.CharFilter(
        lookup_expr='icontains',
        help_text=_('Search by breed name')
    )
    
    code = django_filters.CharFilter(
        lookup_expr='icontains',
        help_text=_('Search by breed code')
    )
    
    pet_type = django_filters.ModelChoiceFilter(
        queryset=PetType.objects.all(),
        help_text=_('Filter by pet type')
    )
    
    pet_type_code = django_filters.CharFilter(
        field_name='pet_type__code',
        lookup_expr='exact',
        help_text=_('Filter by pet type code')
    )
    
    class Meta:
        model = Breed
        fields = ['name', 'code', 'pet_type'] 