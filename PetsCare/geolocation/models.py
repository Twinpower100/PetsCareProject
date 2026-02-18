from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from math import radians, cos, sin, asin, sqrt
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Point

class Location(models.Model):
    """
    Модель для хранения данных о местоположении.
    
    Содержит информацию о географических координатах и адресе пользователя.
    Поддерживает валидацию координат и автоматическое добавление даты создания.
    """
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, verbose_name=_('User'), related_name='locations', null=True, blank=True)
    point = gis_models.PointField(srid=4326, verbose_name=_('Point'))
    address = models.CharField(max_length=255, verbose_name=_('Address'))
    city = models.CharField(max_length=100, verbose_name=_('City'), blank=True)
    country = models.CharField(max_length=100, verbose_name=_('Country'), blank=True)
    postal_code = models.CharField(max_length=20, verbose_name=_('Postal Code'), blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))

    class Meta:
        verbose_name = _('Location')
        verbose_name_plural = _('Locations')
        ordering = ['-created_at']
        indexes = [
            gis_models.Index(fields=['point'], name='idx_location_point'),
        ]

    def __str__(self):
        return f"{self.user} - {self.address}"

    @property
    def coordinates(self):
        """Возвращает координаты в формате (latitude, longitude)"""
        if self.point:
            return self.point.coords
        return None

class SearchRadius(models.Model):
    """
    Модель для определения радиуса поиска для поставщиков услуг.
    
    Позволяет настраивать радиус поиска для каждого пользователя,
    с возможностью активации/деактивации.
    """
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, verbose_name=_('User'), related_name='search_radius', null=True, blank=True)
    name = models.CharField(_('Name'), max_length=100)
    radius = models.PositiveIntegerField(_('Radius In Meters'))
    is_active = models.BooleanField(_('Is Active'), default=True)

    class Meta:
        verbose_name = _('Search Radius')
        verbose_name_plural = _('Search Radii')
        ordering = ['radius']

    def __str__(self):
        return f"{self.name} ({self.radius}m)"

class LocationHistory(models.Model):
    """
    Модель для отслеживания истории местоположений.
    
    Хранит историю всех местоположений пользователя с временными метками.
    Используется для анализа перемещений и поиска ближайших поставщиков услуг.
    """
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, verbose_name=_('User'), related_name='location_history', null=True, blank=True)
    point = gis_models.PointField(srid=4326, verbose_name=_('Point'))
    address = models.CharField(max_length=255, verbose_name=_('Address'))
    city = models.CharField(max_length=100, verbose_name=_('City'), blank=True)
    country = models.CharField(max_length=100, verbose_name=_('Country'), blank=True)
    postal_code = models.CharField(max_length=20, verbose_name=_('Postal Code'), blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))

    class Meta:
        verbose_name = _('Location History')
        verbose_name_plural = _('Location History')
        ordering = ['-created_at']
        indexes = [
            gis_models.Index(fields=['point'], name='idx_location_history_point'),
            models.Index(fields=['created_at'], name='idx_location_history_created'),
        ]

    def __str__(self):
        return f"{self.user} - {self.address} ({self.created_at})"

    @property
    def coordinates(self):
        """Возвращает координаты в формате (latitude, longitude)"""
        if self.point:
            return self.point.coords
        return None

class Address(models.Model):
    """
    Модель для хранения структурированных адресов.
    
    Содержит все компоненты адреса и координаты для геолокации.
    Поддерживает валидацию через Google Maps API.
    """
    
    # Основные поля адреса
    country = models.CharField(_('Country'), max_length=100, blank=True)
    region = models.CharField(_('Region'), max_length=100, blank=True)
    city = models.CharField(_('City'), max_length=100, blank=True)
    district = models.CharField(_('District'), max_length=100, blank=True)
    street = models.CharField(_('Street'), max_length=200, blank=True)
    house_number = models.CharField(_('House Number'), max_length=20, blank=True)
    building = models.CharField(_('Building'), max_length=20, blank=True)
    apartment = models.CharField(_('Apartment'), max_length=20, blank=True)
    postal_code = models.CharField(_('Postal Code'), max_length=20, blank=True)
    
    # Форматированный адрес
    formatted_address = models.TextField(_('Formatted Address'), blank=True)
    
    # Координаты
    point = gis_models.PointField(srid=4326, verbose_name=_('Point'), null=True, blank=True)
    latitude = models.DecimalField(_('Latitude'), max_digits=10, decimal_places=7, null=True, blank=True, help_text=_('Latitude coordinate'))
    longitude = models.DecimalField(_('Longitude'), max_digits=10, decimal_places=7, null=True, blank=True, help_text=_('Longitude coordinate'))
    
    # Статус валидации
    VALIDATION_STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('valid', _('Valid')),
        ('invalid', _('Invalid')),
        ('error', _('Error')),
    ]
    validation_status = models.CharField(
        _('Validation Status'),
        max_length=20,
        choices=VALIDATION_STATUS_CHOICES,
        default='pending'
    )
    
    # Флаги состояния
    is_valid = models.BooleanField(_('Is Valid'), default=False)
    is_validated = models.BooleanField(_('Is Validated'), default=False, help_text=_('Legacy field for backward compatibility'))
    is_geocoded = models.BooleanField(_('Is Geocoded'), default=False)
    
    # Точность геокодирования
    geocoding_accuracy = models.CharField(_('Geocoding Accuracy'), max_length=50, blank=True)
    
    # Временные метки
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    validated_at = models.DateTimeField(_('Validated At'), null=True, blank=True)
    
    class Meta:
        verbose_name = _('Address')
        verbose_name_plural = _('Addresses')
        db_table = 'geolocation_address'
        
        # Индексы для оптимизации геопространственных запросов
        indexes = [
            gis_models.Index(fields=['point'], name='idx_address_coordinates'),
            gis_models.Index(fields=['point', 'validation_status'], name='idx_address_coordinates_status'),
            gis_models.Index(fields=['validation_status'], name='idx_address_validation_status'),
            gis_models.Index(fields=['city', 'region'], name='idx_address_city_region'),
            gis_models.Index(fields=['postal_code'], name='idx_address_postal_code'),
        ]

    def __str__(self):
        return self.formatted_address or f"{self.street}, {self.house_number}, {self.city}"

    @property
    def coordinates(self):
        """Возвращает координаты в формате (latitude, longitude)"""
        if self.point:
            return self.point.coords
        return None

    def get_full_address(self):
        """Возвращает полный адрес в строковом формате"""
        # Если есть formatted_address, используем его
        if self.formatted_address:
            return self.formatted_address
            
        # Иначе собираем из отдельных полей
        parts = []
        if self.street and self.house_number:
            parts.append(f"{self.street}, {self.house_number}")
        if self.building:
            parts.append(f"bld. {self.building}")
        if self.apartment:
            parts.append(f"apt. {self.apartment}")
        if self.city:
            parts.append(self.city)
        if self.region:
            parts.append(self.region)
        if self.country:
            parts.append(self.country)
        if self.postal_code:
            parts.append(self.postal_code)
        return ", ".join(parts)

    def distance_to(self, lat: float, lon: float) -> float:
        """Вычисляет расстояние до указанной точки в километрах"""
        if self.point:
            from django.contrib.gis.geos import Point
            target_point = Point(lon, lat, srid=4326)
            return self.point.distance(target_point) * 111.32  # Convert to km
        return None


class AddressValidation(models.Model):
    """
    Модель для хранения результатов валидации адресов.
    
    Содержит детальную информацию о процессе валидации,
    включая запросы к API и результаты проверок.
    """
    address = models.ForeignKey(Address, on_delete=models.CASCADE, verbose_name=_('Address'))
    
    # Результаты валидации
    is_valid = models.BooleanField(_('Is Valid'), default=False, help_text=_('Whether the address is valid'))
    confidence_score = models.DecimalField(
        _('Confidence Score'),
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Confidence score from validation (0.00-1.00)')
    )
    
    # Детали валидации
    validation_errors = models.JSONField(
        _('Validation Errors'),
        default=list,
        blank=True,
        help_text=_('List of validation errors found')
    )
    suggestions = models.JSONField(
        _('Suggestions'),
        default=list,
        blank=True,
        help_text=_('Suggested corrections for the address')
    )
    
    # API информация
    api_provider = models.CharField(
        _('API Provider'),
        max_length=50,
        default='google_maps',
        help_text=_('API provider used for validation')
    )
    api_response = models.JSONField(
        _('API Response'),
        default=dict,
        blank=True,
        help_text=_('Raw response from geocoding API')
    )
    
    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    processing_time = models.DurationField(
        _('Processing Time'),
        null=True,
        blank=True,
        help_text=_('Time taken to validate the address')
    )

    class Meta:
        verbose_name = _('Address Validation')
        verbose_name_plural = _('Address Validations')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['address', 'created_at']),
            models.Index(fields=['is_valid']),
        ]

    def __str__(self):
        return f"Validation for {self.address} - {'Valid' if self.is_valid else 'Invalid'}"


class AddressCache(models.Model):
    """
    Модель для кэширования результатов геокодирования.
    
    Уменьшает количество запросов к внешним API
    и ускоряет процесс валидации адресов.
    """
    # Ключ кэша (хеш адреса)
    cache_key = models.CharField(
        _('Cache Key'),
        max_length=64,
        unique=True,
        help_text=_('Hash of the address for caching')
    )
    
    # Данные кэша
    address_data = models.JSONField(
        _('Address Data'),
        help_text=_('Cached address data from API')
    )
    
    # API информация
    api_provider = models.CharField(
        _('API Provider'),
        max_length=50,
        default='google_maps',
        help_text=_('API provider used for this cache entry')
    )
    
    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    expires_at = models.DateTimeField(
        _('Expires At'),
        help_text=_('When this cache entry expires')
    )
    hit_count = models.PositiveIntegerField(
        _('Hit Count'),
        default=0,
        help_text=_('Number of times this cache entry was used')
    )

    class Meta:
        verbose_name = _('Address Cache')
        verbose_name_plural = _('Address Cache')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['cache_key']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"Cache: {self.cache_key} (expires: {self.expires_at})"

    @property
    def is_expired(self):
        """Проверяет, истек ли срок действия кэша"""
        from django.utils import timezone
        return timezone.now() > self.expires_at 

class UserLocation(models.Model):
    """
    Модель для хранения местоположения пользователей.
    
    Используется для:
    - Кэширования координат устройства пользователя
    - Сохранения выбранного района на карте
    - Оптимизации поиска без повторных запросов геолокации
    """
    user = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='user_location',
        verbose_name=_('User'),
        null=True,
        blank=True
    )
    point = gis_models.PointField(srid=4326, verbose_name=_('Point'))
    accuracy = models.FloatField(
        _('Accuracy'),
        null=True,
        blank=True,
        help_text=_('Location accuracy in meters')
    )
    source = models.CharField(
        _('Source'),
        max_length=20,
        choices=[
            ('device', _('Device GPS')),
            ('map', _('Map Selection')),
            ('manual', _('Manual Input'))
        ],
        default='device',
        help_text=_('Source of location data')
    )
    last_updated = models.DateTimeField(
        _('Last Updated'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('User Location')
        verbose_name_plural = _('User Locations')
        indexes = [
            gis_models.Index(fields=['point'], name='idx_user_location_point'),
            models.Index(fields=['last_updated'], name='idx_user_location_updated'),
        ]

    def __str__(self):
        return f"{self.user} - {self.point.coords if self.point else 'No coordinates'}"

    def distance_to(self, lat: float, lon: float) -> float:
        """Вычисляет расстояние до указанной точки"""
        if self.point:
            target_point = Point(lon, lat, srid=4326)
            return self.point.distance(target_point) * 111.32  # Convert to km
        return None 