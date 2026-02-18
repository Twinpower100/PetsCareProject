"""
Сериализаторы для модуля геолокации.

Содержит сериализаторы для:
- Address — структурированная модель адреса
- AddressValidation — результаты валидации
- AddressCache — кэширование результатов геокодирования
"""

from rest_framework import serializers
from .models import Address, AddressValidation, AddressCache
from .services import AddressValidationService
from django.utils.translation import gettext as _


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
            'id', 'country', 'region', 'city', 'district', 'street', 'house_number',
            'building', 'apartment', 'postal_code', 'formatted_address',
            'latitude', 'longitude',
            'point', 'is_geocoded', 'validation_status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'point', 'is_geocoded', 'validation_status', 'created_at', 'updated_at']

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
        # Проверяем, что указан хотя бы один компонент адреса или форматированный адрес (для создания из геокода)
        required_fields = ['house_number', 'street', 'city', 'country']
        has_component = any(attrs.get(field) for field in required_fields)
        has_formatted = bool(attrs.get('formatted_address', '').strip())
        if not has_component and not has_formatted:
            raise serializers.ValidationError(
                _("At least one address component must be specified")
            )
        return attrs

    def create(self, validated_data):
        """
        Создаёт адрес и запускает валидацию. Сохраняем только при validation_status == 'valid';
        иначе удаляем запись и поднимаем ValidationError.
        """
        address = Address.objects.create(**validated_data)
        validation_service = AddressValidationService()
        is_valid = validation_service.validate_address(address)
        address.refresh_from_db()
        if address.validation_status != 'valid':
            address.delete()
            raise serializers.ValidationError(
                _('Address could not be validated. Please check the address and try again.')
            )
        return address

    def update(self, instance, validated_data):
        """
        Обновляет поля адреса и запускает валидацию. При неуспешной валидации
        поднимаем ValidationError (изменения уже сохранены сервисом как invalid).
        """
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        validation_service = AddressValidationService()
        validation_service.validate_address(instance)
        instance.refresh_from_db()
        if instance.validation_status != 'valid':
            raise serializers.ValidationError(
                _('Address could not be validated. Please check the address and try again.')
            )
        return instance


class AddressValidationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели AddressValidation.
    """
    
    class Meta:
        model = AddressValidation
        fields = [
            'id', 'address', 'is_valid', 'confidence_score', 'validation_errors', 'suggestions',
            'api_provider', 'api_response', 'created_at'
        ]
        read_only_fields = ['id', 'is_valid', 'confidence_score', 'validation_errors', 'suggestions',
                           'api_provider', 'api_response', 'created_at']


class AddressCacheSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели AddressCache.
    """
    
    class Meta:
        model = AddressCache
        fields = [
            'id', 'cache_key', 'address_data', 'api_provider',
            'created_at', 'expires_at'
        ]
        read_only_fields = ['id', 'cache_key', 'address_data', 'api_provider', 'created_at', 'expires_at']


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


class PlaceDetailsSerializer(serializers.Serializer):
    """Сериализатор для запроса Place Details по place_id."""
    place_id = serializers.CharField(max_length=512, help_text=_("Google Place ID from autocomplete prediction"))

    def validate_place_id(self, value):
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError(_("place_id is required"))
        return v


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