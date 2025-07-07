"""
API views для модуля геолокации.

Этот модуль содержит представления для:
1. Получения местоположения пользователя
2. Сохранения координат устройства
3. Выбора района на карте
4. Поиска по геолокации
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from .services import DeviceLocationService, MapLocationService
from .models import UserLocation


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_location(request):
    """
    Получает текущее местоположение пользователя.
    
    Возвращает:
    - Кэшированное местоположение (если есть)
    - None если местоположение не определено
    """
    try:
        device_service = DeviceLocationService()
        location = device_service.get_user_location(request.user)
        
        if location:
            return Response({
                'success': True,
                'location': {
                    'latitude': float(location['latitude']),
                    'longitude': float(location['longitude']),
                    'accuracy': location.get('accuracy'),
                    'source': location['source'],
                    'timestamp': location['timestamp'].isoformat()
                }
            })
        else:
            return Response({
                'success': True,
                'location': None,
                'message': _('Location not available. Please enable device location or select area on map.')
            })
            
    except Exception as e:
        return Response({
            'success': False,
            'error': _('Error getting user location'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_device_location(request):
    """
    Сохраняет местоположение устройства пользователя.
    
    Параметры:
    - latitude: Широта
    - longitude: Долгота
    - accuracy: Точность в метрах (опционально)
    """
    try:
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        accuracy = request.data.get('accuracy')
        
        # Валидация параметров
        if not latitude or not longitude:
            return Response({
                'success': False,
                'error': _('Latitude and longitude are required')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            latitude = float(latitude)
            longitude = float(longitude)
            if accuracy:
                accuracy = float(accuracy)
        except ValueError:
            return Response({
                'success': False,
                'error': _('Invalid coordinates format')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Сохраняем местоположение
        device_service = DeviceLocationService()
        location_data = device_service.save_device_location(
            user=request.user,
            latitude=latitude,
            longitude=longitude,
            accuracy=accuracy,
            source='device'
        )
        
        return Response({
            'success': True,
            'message': _('Location saved successfully'),
            'location': {
                'latitude': float(location_data['latitude']),
                'longitude': float(location_data['longitude']),
                'accuracy': location_data.get('accuracy'),
                'source': location_data['source'],
                'timestamp': location_data['timestamp'].isoformat()
            }
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': _('Error saving device location'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_map_location(request):
    """
    Сохраняет выбранное на карте местоположение.
    
    Параметры:
    - latitude: Широта
    - longitude: Долгота
    - address: Адрес (опционально)
    """
    try:
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        address = request.data.get('address')
        
        # Валидация параметров
        if not latitude or not longitude:
            return Response({
                'success': False,
                'error': _('Latitude and longitude are required')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except ValueError:
            return Response({
                'success': False,
                'error': _('Invalid coordinates format')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Валидируем область поиска
        map_service = MapLocationService()
        if not map_service.validate_search_area(latitude, longitude):
            return Response({
                'success': False,
                'error': _('Invalid search area')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Сохраняем местоположение
        device_service = DeviceLocationService()
        location_data = device_service.save_map_location(
            user=request.user,
            latitude=latitude,
            longitude=longitude,
            address=address
        )
        
        # Получаем дополнительную информацию о местоположении
        location_info = map_service.get_location_info(latitude, longitude)
        
        return Response({
            'success': True,
            'message': _('Map location saved successfully'),
            'location': {
                'latitude': float(location_data['latitude']),
                'longitude': float(location_data['longitude']),
                'accuracy': location_data.get('accuracy'),
                'source': location_data['source'],
                'timestamp': location_data['timestamp'].isoformat(),
                'address': location_info.get('address'),
                'address_components': location_info.get('address_components')
            }
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': _('Error saving map location'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_location_info(request):
    """
    Получает информацию о местоположении по координатам.
    
    Параметры:
    - latitude: Широта
    - longitude: Долгота
    """
    try:
        latitude = request.GET.get('latitude')
        longitude = request.GET.get('longitude')
        
        # Валидация параметров
        if not latitude or not longitude:
            return Response({
                'success': False,
                'error': _('Latitude and longitude are required')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except ValueError:
            return Response({
                'success': False,
                'error': _('Invalid coordinates format')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Получаем информацию о местоположении
        map_service = MapLocationService()
        location_info = map_service.get_location_info(latitude, longitude)
        
        return Response({
            'success': True,
            'location_info': location_info
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': _('Error getting location info'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def clear_user_location(request):
    """
    Очищает сохраненное местоположение пользователя.
    """
    try:
        # Удаляем из базы данных
        UserLocation.objects.filter(user=request.user).delete()
        
        # Очищаем кэш
        from django.core.cache import cache
        cache_key = f"user_location_{request.user.id}"
        cache.delete(cache_key)
        
        return Response({
            'success': True,
            'message': _('Location cleared successfully')
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': _('Error clearing location'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_address_requirement(request):
    """
    Проверяет, требуется ли адрес для пользователя.
    
    Логика:
    - Обычный пользователь: адрес НЕ обязателен
    - Ситтер: адрес ОБЯЗАТЕЛЕН (где оказывает услуги)
    - Учреждение: адрес ОБЯЗАТЕЛЕН (где находится учреждение)
    """
    try:
        device_service = DeviceLocationService()
        address_check = device_service.check_address_requirement(request.user)
        
        return Response({
            'success': True,
            'address_requirement': address_check
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': _('Error checking address requirement'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_location_for_role(request):
    """
    Валидирует местоположение для конкретной роли пользователя.
    
    Параметры:
    - latitude: Широта (опционально)
    - longitude: Долгота (опционально)
    """
    try:
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        
        # Конвертируем в float если переданы
        if latitude is not None:
            try:
                latitude = float(latitude)
            except ValueError:
                return Response({
                    'success': False,
                    'error': _('Invalid latitude format')
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if longitude is not None:
            try:
                longitude = float(longitude)
            except ValueError:
                return Response({
                    'success': False,
                    'error': _('Invalid longitude format')
                }, status=status.HTTP_400_BAD_REQUEST)
        
        device_service = DeviceLocationService()
        validation_result = device_service.validate_location_for_role(
            request.user, latitude, longitude
        )
        
        return Response({
            'success': True,
            'validation': validation_result
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': _('Error validating location'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 