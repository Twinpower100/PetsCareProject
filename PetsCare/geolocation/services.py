import hashlib
import json
import time
from datetime import timedelta
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from django.db import transaction
from django.utils.translation import gettext as _

from users.models import User
from .models import Address, AddressValidation, AddressCache, UserLocation


class GoogleMapsService:
    """
    Сервис для работы с Google Maps API.
    
    Обеспечивает геокодирование адресов, автодополнение
    и валидацию через Google Maps API.
    """
    
    def __init__(self):
        """Инициализация сервиса с API ключом"""
        self.api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
        if not self.api_key:
            raise ValueError("GOOGLE_MAPS_API_KEY not configured in settings.py")
        
        self.geocoding_url = "https://maps.googleapis.com/maps/api/geocode/json"
        self.places_url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    
    def geocode_address(self, address: str, country: str = None) -> Optional[Dict[str, Any]]:
        """
        Geocoding address via Google Maps API.
        
        Args:
            address: Address to geocode
            country: Country code for search restriction
            
        Returns:
            Dictionary with geocoding results or None on error
        """
        params = {
            'address': address,
            'key': self.api_key,
            'language': 'ru'  # Russian language for better results
        }
        
        if country:
            params['region'] = country
        
        try:
            response = requests.get(self.geocoding_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data['status'] == 'OK' and data['results']:
                return self._parse_geocoding_result(data['results'][0])
            else:
                return None
                
        except requests.RequestException as e:
            print(f"Error requesting Google Maps API: {e}")
            return None
        except Exception as e:
            print(f"Geocoding error: {e}")
            return None
    
    def autocomplete_address(self, input_text: str, country: str = None, 
                           types: str = 'address') -> List[Dict[str, Any]]:
        """
        Autocomplete address via Google Places API.
        
        Args:
            input_text: Text for autocomplete
            country: Country code for search restriction
            types: Types of places to search for
            
        Returns:
            List of autocomplete options
        """
        params = {
            'input': input_text,
            'key': self.api_key,
            'language': 'ru',
            'types': types
        }
        
        if country:
            params['components'] = f'country:{country}'
        
        try:
            response = requests.get(self.places_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data['status'] == 'OK':
                return [
                    {
                        'description': prediction['description'],
                        'place_id': prediction['place_id'],
                        'types': prediction.get('types', [])
                    }
                    for prediction in data['predictions']
                ]
            else:
                return []
                
        except requests.RequestException as e:
            print(f"Error requesting Google Places API: {e}")
            return []
        except Exception as e:
            print(f"Autocomplete error: {e}")
            return []
    
    def _parse_geocoding_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parsing geocoding result from Google Maps API.
        
        Args:
            result: Result from Google Maps API
            
        Returns:
            Structured geocoding result
        """
        # Extract coordinates
        location = result['geometry']['location']
        coordinates = {
            'latitude': Decimal(str(location['lat'])),
            'longitude': Decimal(str(location['lng']))
        }
        
        # Extract geocoding accuracy
        location_type = result['geometry']['location_type']
        
        # Parse address components
        address_components = self._parse_address_components(result['address_components'])
        
        return {
            'coordinates': coordinates,
            'location_type': location_type,
            'formatted_address': result['formatted_address'],
            'address_components': address_components,
            'place_id': result.get('place_id', ''),
            'types': result.get('types', [])
        }
    
    def _parse_address_components(self, components: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Parsing address components from Google Maps API.
        
        Args:
            components: List of address components from API
            
        Returns:
            Dictionary with address components
        """
        parsed = {}
        
        for component in components:
            types = component.get('types', [])
            
            if 'country' in types:
                parsed['country'] = component['long_name']
            elif 'administrative_area_level_1' in types:
                parsed['region'] = component['long_name']
            elif 'locality' in types:
                parsed['city'] = component['long_name']
            elif 'sublocality' in types:
                parsed['district'] = component['long_name']
            elif 'route' in types:
                parsed['street'] = component['long_name']
            elif 'street_number' in types:
                parsed['house_number'] = component['long_name']
            elif 'postal_code' in types:
                parsed['postal_code'] = component['long_name']
        
        return parsed
    
    def reverse_geocode(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """
        Обратное геокодирование координат в адрес.
        
        Args:
            latitude: Широта
            longitude: Долгота
            
        Returns:
            Dict с информацией об адресе или None
        """
        params = {
            'latlng': f"{latitude},{longitude}",
            'key': self.api_key,
            'language': 'ru'
        }
        
        try:
            response = requests.get(self.geocoding_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data['status'] == 'OK' and data['results']:
                return self._parse_geocoding_result(data['results'][0])
            else:
                return None
                
        except requests.RequestException as e:
            print(f"Error requesting Google Maps API for reverse geocoding: {e}")
            return None
        except Exception as e:
            print(f"Reverse geocoding error: {e}")
            return None


class AddressValidationService:
    """
    Service for address validation.
    
    Provides full validation cycle for address:
    - Cache check
    - Geocoding via API
    - Saving results
    - Caching results
    """
    
    def __init__(self):
        """Service initialization for validation"""
        self.google_service = GoogleMapsService()
        self.cache_duration = timedelta(days=30)  # Cache for 30 days
    
    def validate_address(self, address: Address) -> bool:
        """
        Address validation with result saving.
        
        Args:
            address: Address model for validation
            
        Returns:
            True if address is valid, False otherwise
        """
        start_time = time.time()
        
        try:
            # Check cache
            cached_result = self._get_cached_result(address)
            if cached_result:
                self._update_address_from_cache(address, cached_result)
                return address.is_valid
            
            # Perform geocoding
            geocoding_result = self._geocode_address(address)
            if not geocoding_result:
                self._save_validation_result(address, False, start_time)
                return False
            
            # Update address from geocoding results
            self._update_address_from_geocoding(address, geocoding_result)
            
            # Save validation result
            is_valid = self._is_address_valid(geocoding_result)
            self._save_validation_result(address, is_valid, start_time, geocoding_result)
            
            # Cache result
            self._cache_result(address, geocoding_result)
            
            return is_valid
            
        except Exception as e:
            print(f"Address validation error for address {address.id}: {e}")
            self._save_validation_result(address, False, start_time, error=str(e))
            return False
    
    def _get_cached_result(self, address: Address) -> Optional[Dict[str, Any]]:
        """
        Getting result from cache.
        
        Args:
            address: Address model
            
        Returns:
            Cached result or None
        """
        cache_key = self._generate_cache_key(address)
        
        # Check Django cache
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data
        
        # Check database
        try:
            cache_entry = AddressCache.objects.get(
                cache_key=cache_key,
                expires_at__gt=timezone.now()
            )
            cache_entry.hit_count += 1
            cache_entry.save()
            
            # Update Django cache
            cache.set(cache_key, cache_entry.address_data, 
                     int(self.cache_duration.total_seconds()))
            
            return cache_entry.address_data
        except AddressCache.DoesNotExist:
            return None
    
    def _geocode_address(self, address: Address) -> Optional[Dict[str, Any]]:
        """
        Geocoding address.
        
        Args:
            address: Address model
            
        Returns:
            Geocoding result or None
        """
        # Form address string for geocoding
        address_string = address.get_full_address()
        
        return self.google_service.geocode_address(
            address_string, 
            country=address.country
        )
    
    def _update_address_from_geocoding(self, address: Address, 
                                     result: Dict[str, Any]) -> None:
        """
        Updating address from geocoding results.
        
        Args:
            address: Address model
            result: Geocoding result
        """
        coordinates = result['coordinates']
        components = result['address_components']
        
        # Update coordinates
        address.latitude = coordinates['latitude']
        address.longitude = coordinates['longitude']
        
        # Update formatted address
        address.formatted_address = result['formatted_address']
        
        # Update geocoding accuracy
        address.geocoding_accuracy = result['location_type']
        
        # Update address components if they are empty
        if not address.country and 'country' in components:
            address.country = components['country']
        if not address.region and 'region' in components:
            address.region = components['region']
        if not address.city and 'city' in components:
            address.city = components['city']
        if not address.postal_code and 'postal_code' in components:
            address.postal_code = components['postal_code']
        
        # Update validation status
        address.validation_status = 'valid'
        address.validated_at = timezone.now()
        
        address.save()
    
    def _update_address_from_cache(self, address: Address, 
                                 cached_result: Dict[str, Any]) -> None:
        """
        Updating address from cache.
        
        Args:
            address: Address model
            cached_result: Cached result
        """
        coordinates = cached_result['coordinates']
        
        address.latitude = coordinates['latitude']
        address.longitude = coordinates['longitude']
        address.formatted_address = cached_result['formatted_address']
        address.geocoding_accuracy = cached_result['location_type']
        address.validation_status = 'valid'
        address.validated_at = timezone.now()
        
        address.save()
    
    def _is_address_valid(self, result: Dict[str, Any]) -> bool:
        """
        Checking address validity based on geocoding result.
        
        Args:
            result: Geocoding result
            
        Returns:
            True if address is valid
        """
        # Address is considered valid if coordinates are obtained
        # and geocoding accuracy is sufficiently high
        location_type = result['location_type']
        
        valid_types = ['ROOFTOP', 'RANGE_INTERPOLATED', 'GEOMETRIC_CENTER']
        return location_type in valid_types
    
    def _save_validation_result(self, address: Address, is_valid: bool, 
                              start_time: float, result: Dict[str, Any] = None,
                              error: str = None) -> None:
        """
        Saving validation result.
        
        Args:
            address: Address model
            is_valid: Is address valid
            start_time: Validation start time
            result: Geocoding result
            error: Validation error
        """
        processing_time = time.time() - start_time
        
        validation = AddressValidation.objects.create(
            address=address,
            is_valid=is_valid,
            confidence_score=Decimal('0.95') if is_valid else Decimal('0.0'),
            api_provider='google_maps',
            processing_time=timedelta(seconds=processing_time),
            api_response=result or {},
            validation_errors=[error] if error else [],
            suggestions=[]
        )
        
        # Update address status
        if not is_valid:
            address.validation_status = 'invalid'
            address.validated_at = timezone.now()
            address.save()
    
    def _cache_result(self, address: Address, result: Dict[str, Any]) -> None:
        """
        Caching validation result.
        
        Args:
            address: Address model
            result: Geocoding result
        """
        cache_key = self._generate_cache_key(address)
        expires_at = timezone.now() + self.cache_duration
        
        # Save to Django cache
        cache.set(cache_key, result, int(self.cache_duration.total_seconds()))
        
        # Save to database
        AddressCache.objects.create(
            cache_key=cache_key,
            address_data=result,
            api_provider='google_maps',
            expires_at=expires_at,
            hit_count=1
        )
    
    def _generate_cache_key(self, address: Address) -> str:
        """
        Generating cache key for address.
        
        Args:
            address: Address model
            
        Returns:
            Cache key
        """
        # Create string for hashing
        address_string = f"{address.country}:{address.region}:{address.city}:{address.street}:{address.house_number}"
        
        # Generate MD5 hash
        return hashlib.md5(address_string.encode()).hexdigest()
    
    def autocomplete_address(self, input_text: str, country: str = None) -> List[Dict[str, Any]]:
        """
        Autocomplete address.
        
        Args:
            input_text: Text for autocomplete
            country: Country code
            
        Returns:
            List of autocomplete options
        """
        return self.google_service.autocomplete_address(input_text, country)


class DeviceLocationService:
    """
    Сервис для работы с геолокацией устройства пользователя.
    
    Обеспечивает:
    - Получение координат устройства через браузер
    - Fallback на выбор района на карте
    - Кэширование последнего местоположения
    """
    
    def __init__(self):
        """Инициализация сервиса"""
        self.cache_duration = timedelta(hours=24)  # Кэш на 24 часа
    
    def get_user_location(self, user: User) -> Optional[Dict[str, Any]]:
        """
        Получает местоположение пользователя.
        
        Приоритет:
        1. Кэшированное местоположение
        2. Геолокация устройства (через API)
        3. Выбранный район на карте
        
        Args:
            user: Пользователь
            
        Returns:
            Dict с координатами или None
        """
        # Проверяем кэш
        cached_location = self._get_cached_location(user)
        if cached_location:
            return cached_location
        
        # Если нет кэша, возвращаем None
        # Фронтенд должен запросить геолокацию устройства
        return None
    
    def check_address_requirement(self, user: User) -> Dict[str, Any]:
        """
        Проверяет, требуется ли адрес для пользователя.
        
        Логика:
        - Обычный пользователь: адрес НЕ обязателен
        - Ситтер: адрес ОБЯЗАТЕЛЕН (где оказывает услуги)
        - Учреждение: адрес ОБЯЗАТЕЛЕН (где находится учреждение)
        
        Args:
            user: Пользователь
            
        Returns:
            Dict с информацией о требовании адреса
        """
        # Проверяем роль ситтера
        is_sitter = user.has_role('pet_sitter')
        
        # Проверяем роль учреждения (администратор учреждения)
        is_provider_admin = user.has_role('provider_admin')
        
        # Проверяем, есть ли у пользователя адрес
        has_address = user.address is not None
        
        if is_sitter:
            return {
                'address_required': True,
                'role': 'sitter',
                'has_address': has_address,
                'message': _('Address is required for pet sitters to specify where services are provided'),
                'missing_address': not has_address
            }
        elif is_provider_admin:
            return {
                'address_required': True,
                'role': 'provider_admin',
                'has_address': has_address,
                'message': _('Address is required for providers to specify location'),
                'missing_address': not has_address
            }
        else:
            return {
                'address_required': False,
                'role': 'regular_user',
                'has_address': has_address,
                'message': _('Address is optional for regular users'),
                'missing_address': False
            }
    
    def validate_location_for_role(self, user: User, latitude: float = None, longitude: float = None) -> Dict[str, Any]:
        """
        Валидирует местоположение для конкретной роли пользователя.
        
        Args:
            user: Пользователь
            latitude: Широта (опционально)
            longitude: Долгота (опционально)
            
        Returns:
            Dict с результатом валидации
        """
        # Проверяем требования к адресу
        address_check = self.check_address_requirement(user)
        
        # Если адрес не требуется, возвращаем успех
        if not address_check['address_required']:
            return {
                'valid': True,
                'address_required': False,
                'message': _('Location validation passed')
            }
        
        # Если адрес требуется, но его нет
        if address_check['missing_address']:
            return {
                'valid': False,
                'address_required': True,
                'role': address_check['role'],
                'message': address_check['message'],
                'error': 'missing_address'
            }
        
        # Если адрес есть, но не переданы координаты
        if latitude is None or longitude is None:
            return {
                'valid': False,
                'address_required': True,
                'role': address_check['role'],
                'message': _('Coordinates are required for address validation'),
                'error': 'missing_coordinates'
            }
        
        # Валидируем координаты
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            return {
                'valid': False,
                'address_required': True,
                'role': address_check['role'],
                'message': _('Invalid coordinates format'),
                'error': 'invalid_coordinates'
            }
        
        return {
            'valid': True,
            'address_required': True,
            'role': address_check['role'],
            'message': _('Location validation passed')
        }
    
    def save_device_location(self, user: User, latitude: float, longitude: float, 
                           accuracy: float = None, source: str = 'device') -> Dict[str, Any]:
        """
        Сохраняет местоположение устройства пользователя.
        
        Args:
            user: Пользователь
            latitude: Широта
            longitude: Долгота
            accuracy: Точность в метрах
            source: Источник ('device', 'map', 'manual')
            
        Returns:
            Dict с сохраненными координатами
        """
        location_data = {
            'latitude': Decimal(str(latitude)),
            'longitude': Decimal(str(longitude)),
            'accuracy': accuracy,
            'source': source,
            'timestamp': timezone.now()
        }
        
        # Сохраняем в кэш
        self._cache_location(user, location_data)
        
        # Сохраняем в базу данных
        self._save_location_to_db(user, location_data)
        
        return location_data
    
    def save_map_location(self, user: User, latitude: float, longitude: float, 
                         address: str = None) -> Dict[str, Any]:
        """
        Сохраняет выбранное на карте местоположение.
        
        Args:
            user: Пользователь
            latitude: Широта
            longitude: Долгота
            address: Адрес (опционально)
            
        Returns:
            Dict с сохраненными координатами
        """
        return self.save_device_location(
            user, latitude, longitude, 
            accuracy=100,  # Примерная точность выбора на карте
            source='map'
        )
    
    def _get_cached_location(self, user: User) -> Optional[Dict[str, Any]]:
        """
        Получает кэшированное местоположение пользователя.
        
        Args:
            user: Пользователь
            
        Returns:
            Кэшированные координаты или None
        """
        cache_key = f"user_location_{user.id}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            # Проверяем, не устарел ли кэш
            timestamp = cached_data.get('timestamp')
            if timestamp and timezone.now() - timestamp < self.cache_duration:
                return cached_data
        
        return None
    
    def _cache_location(self, user: User, location_data: Dict[str, Any]) -> None:
        """
        Кэширует местоположение пользователя.
        
        Args:
            user: Пользователь
            location_data: Данные о местоположении
        """
        cache_key = f"user_location_{user.id}"
        cache.set(cache_key, location_data, int(self.cache_duration.total_seconds()))
    
    def _save_location_to_db(self, user: User, location_data: Dict[str, Any]) -> None:
        """
        Сохраняет местоположение в базу данных.
        
        Args:
            user: Пользователь
            location_data: Данные о местоположении
        """
        UserLocation.objects.update_or_create(
            user=user,
            defaults={
                'latitude': location_data['latitude'],
                'longitude': location_data['longitude'],
                'accuracy': location_data.get('accuracy'),
                'source': location_data['source'],
                'last_updated': location_data['timestamp']
            }
        )


class MapLocationService:
    """
    Сервис для работы с выбором района на карте.
    
    Обеспечивает:
    - Геокодирование выбранной точки на карте
    - Обратное геокодирование для получения адреса
    - Валидацию выбранного района
    """
    
    def __init__(self):
        """Инициализация сервиса"""
        self.google_service = GoogleMapsService()
    
    def get_location_info(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """
        Получает информацию о выбранной точке на карте.
        
        Args:
            latitude: Широта
            longitude: Долгота
            
        Returns:
            Dict с информацией о местоположении
        """
        # Обратное геокодирование для получения адреса
        address_info = self.google_service.reverse_geocode(latitude, longitude)
        
        return {
            'coordinates': {
                'latitude': Decimal(str(latitude)),
                'longitude': Decimal(str(longitude))
            },
            'address': address_info.get('formatted_address') if address_info else None,
            'address_components': address_info.get('address_components') if address_info else {},
            'location_type': address_info.get('location_type') if address_info else None
        }
    
    def validate_search_area(self, latitude: float, longitude: float, 
                           radius_km: float = 10) -> bool:
        """
        Валидирует выбранную область поиска.
        
        Args:
            latitude: Широта центра поиска
            longitude: Долгота центра поиска
            radius_km: Радиус поиска в километрах
            
        Returns:
            True если область валидна
        """
        # Проверяем, что координаты в разумных пределах
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            return False
        
        # Проверяем, что радиус поиска разумный
        if not (0.1 <= radius_km <= 100):
            return False
        
        return True 