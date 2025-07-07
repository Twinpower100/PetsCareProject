"""
Сериализаторы для модуля геолокации.

Этот модуль содержит сериализаторы для:
1. Местоположений (Location)
2. Радиусов поиска (SearchRadius)
3. Истории местоположений (LocationHistory)
4. Address - структурированная модель адреса
5. AddressValidation - результаты валидации
6. AddressCache - кэширование результатов геокодирования
"""

from rest_framework import serializers
from .models import Location, SearchRadius, LocationHistory, Address, AddressValidation, AddressCache
from .services import AddressValidationService
from django.utils.translation import gettext as _


class LocationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели Location.
    Преобразует данные о местоположении в JSON формат.
    
    Поля:
    - id: Уникальный идентификатор
    - user: Пользователь, которому принадлежит местоположение
    - address: Адрес местоположения
    - latitude: Широта
    - longitude: Долгота
    - city: Город
    - country: Страна
    - postal_code: Почтовый индекс
    - created_at: Дата создания
    """
    class Meta:
        model = Location
        fields = [
            'id', 'user', 'address', 'latitude', 'longitude',
            'city', 'country', 'postal_code', 'created_at'
        ]
        read_only_fields = ['id', 'user', 'created_at']


class SearchRadiusSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели SearchRadius.
    Управляет настройками радиуса поиска для пользователей.
    
    Поля:
    - id: Уникальный идентификатор
    - user: Пользователь, которому принадлежит радиус
    - radius: Значение радиуса в метрах
    - is_active: Флаг активности
    """
    class Meta:
        model = SearchRadius
        fields = ['id', 'user', 'radius', 'is_active']
        read_only_fields = ['id', 'user']


class LocationHistorySerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели LocationHistory.
    Обрабатывает историю поиска местоположений пользователей.
    
    Поля:
    - id: Уникальный идентификатор
    - user: Пользователь, выполнивший поиск
    - location: Найденное местоположение
    - search_date: Дата поиска
    """
    location = LocationSerializer(read_only=True)
    
    class Meta:
        model = LocationHistory
        fields = ['id', 'user', 'location', 'search_date']
        read_only_fields = ['id', 'user', 'search_date']


class AddressSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели Address.
    
    Особенности:
    - Валидация адреса через Google Maps API
    - Автоматическое геокодирование при сохранении
    - Поддержка частичного обновления
    """
    
    class Meta:
        model = Address
        fields = [
            'id', 'street_number', 'route', 'locality', 'administrative_area_level_1',
            'administrative_area_level_2', 'country', 'postal_code', 'formatted_address',
            'latitude', 'longitude', 'is_validated', 'validation_status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'formatted_address', 'latitude', 'longitude', 
                           'is_validated', 'validation_status', 'created_at', 'updated_at']

    def validate(self, attrs):
        """
        Валидирует данные адреса и выполняет геокодирование.
        
        Args:
            attrs (dict): Данные для валидации
            
        Returns:
            dict: Валидированные данные
            
        Raises:
            serializers.ValidationError: При ошибке валидации
        """
        # Проверяем, что указан хотя бы один компонент адреса
        required_fields = ['street_number', 'route', 'locality', 'country']
        if not any(attrs.get(field) for field in required_fields):
            raise serializers.ValidationError(
                _("At least one address component must be specified")
            )
        
        return attrs

    def create(self, validated_data):
        """
        Создает новый адрес с автоматической валидацией.
        
        Args:
            validated_data (dict): Валидированные данные
            
        Returns:
            Address: Созданный адрес
        """
        # Создаем адрес
        address = Address.objects.create(**validated_data)
        
        # Выполняем валидацию через сервис
        validation_service = AddressValidationService()
        validation_result = validation_service.validate_address(address)
        
        # Обновляем адрес результатами валидации
        if validation_result.is_valid:
            address.formatted_address = validation_result.formatted_address
            address.latitude = validation_result.latitude
            address.longitude = validation_result.longitude
            address.is_validated = True
            address.validation_status = 'valid'
        else:
            address.validation_status = 'invalid'
        
        address.save()
        return address

    def update(self, instance, validated_data):
        """
        Обновляет адрес с повторной валидацией.
        
        Args:
            instance (Address): Существующий адрес
            validated_data (dict): Новые данные
            
        Returns:
            Address: Обновленный адрес
        """
        # Обновляем поля
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Сбрасываем статус валидации
        instance.is_validated = False
        instance.validation_status = 'pending'
        instance.save()
        
        # Выполняем повторную валидацию
        validation_service = AddressValidationService()
        validation_result = validation_service.validate_address(instance)
        
        # Обновляем результаты валидации
        if validation_result.is_valid:
            instance.formatted_address = validation_result.formatted_address
            instance.latitude = validation_result.latitude
            instance.longitude = validation_result.longitude
            instance.is_validated = True
            instance.validation_status = 'valid'
        else:
            instance.validation_status = 'invalid'
        
        instance.save()
        return instance


class AddressValidationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели AddressValidation.
    """
    
    class Meta:
        model = AddressValidation
        fields = [
            'id', 'address', 'is_valid', 'formatted_address', 'latitude', 'longitude',
            'confidence_score', 'validation_details', 'api_response', 'created_at'
        ]
        read_only_fields = ['id', 'is_valid', 'formatted_address', 'latitude', 'longitude',
                           'confidence_score', 'validation_details', 'api_response', 'created_at']


class AddressCacheSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели AddressCache.
    """
    
    class Meta:
        model = AddressCache
        fields = [
            'id', 'query_hash', 'query_text', 'formatted_address', 'latitude', 'longitude',
            'api_response', 'created_at', 'expires_at'
        ]
        read_only_fields = ['id', 'query_hash', 'api_response', 'created_at', 'expires_at']


class AddressAutocompleteSerializer(serializers.Serializer):
    """
    Сериализатор для автодополнения адресов.
    """
    query = serializers.CharField(max_length=255, help_text=_("Text for autocomplete"))
    session_token = serializers.CharField(max_length=255, required=False, 
                                        help_text=_("Session token for grouping requests"))
    
    def validate_query(self, value):
        """
        Валидирует запрос автодополнения.
        
        Args:
            value (str): Текст запроса
            
        Returns:
            str: Валидированный запрос
            
        Raises:
            serializers.ValidationError: При ошибке валидации
        """
        if len(value.strip()) < 2:
            raise serializers.ValidationError(_("Query must contain at least 2 characters"))
        return value.strip()


class AddressGeocodeSerializer(serializers.Serializer):
    """
    Сериализатор для геокодирования адреса.
    """
    address = serializers.CharField(max_length=500, help_text=_("Address to geocode"))
    
    def validate_address(self, value):
        """
        Валидирует адрес для геокодирования.
        
        Args:
            value (str): Адрес
            
        Returns:
            str: Валидированный адрес
            
        Raises:
            serializers.ValidationError: При ошибке валидации
        """
        if len(value.strip()) < 5:
            raise serializers.ValidationError(_("Address must contain at least 5 characters"))
        return value.strip()


class AddressReverseGeocodeSerializer(serializers.Serializer):
    """
    Сериализатор для обратного геокодирования.
    """
    latitude = serializers.FloatField(help_text=_("Latitude"))
    longitude = serializers.FloatField(help_text=_("Longitude"))
    
    def validate(self, attrs):
        """
        Валидирует координаты для обратного геокодирования.
        
        Args:
            attrs (dict): Данные для валидации
            
        Returns:
            dict: Валидированные данные
            
        Raises:
            serializers.ValidationError: При ошибке валидации
        """
        lat = attrs.get('latitude')
        lon = attrs.get('longitude')
        
        if lat < -90 or lat > 90:
            raise serializers.ValidationError(_("Latitude must be between -90 and 90"))
        
        if lon < -180 or lon > 180:
            raise serializers.ValidationError(_("Longitude must be between -180 and 180"))
        
        return attrs 