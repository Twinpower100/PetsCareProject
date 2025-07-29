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

"""
API views для геолокации с мониторингом производительности.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse

from .monitoring import get_performance_report, reset_performance_metrics, monitor


@api_view(['GET'])
@permission_classes([IsAdminUser])
def geospatial_performance_report(request):
    """
    API endpoint для получения отчета о производительности геопоиска.
    
    Доступно только администраторам.
    
    Returns:
        JSON с метриками производительности и рекомендациями
    """
    try:
        report = get_performance_report()
        return Response(report, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': f'Ошибка при получении отчета: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAdminUser])
def reset_geospatial_metrics(request):
    """
    API endpoint для сброса метрик производительности геопоиска.
    
    Доступно только администраторам.
    
    Returns:
        JSON с подтверждением сброса
    """
    try:
        reset_performance_metrics()
        return Response(
            {'message': 'Метрики производительности сброшены'},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {'error': f'Ошибка при сбросе метрик: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdminUser])
def geospatial_metrics_raw(request):
    """
    API endpoint для получения сырых метрик производительности.
    
    Доступно только администраторам.
    
    Returns:
        JSON с сырыми данными метрик
    """
    try:
        stats = monitor.get_all_stats()
        return Response(stats, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': f'Ошибка при получении метрик: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def geospatial_health_check(request):
    """
    API endpoint для проверки здоровья геопоиска.
    
    Проверяет доступность PostGIS и основных функций.
    
    Returns:
        JSON с статусом здоровья системы
    """
    try:
        from django.contrib.gis.db import connection
        from django.contrib.gis.geos import Point
        
        health_status = {
            'status': 'healthy',
            'checks': {}
        }
        
        # Проверяем подключение к базе данных
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT PostGIS_Version()")
                postgis_version = cursor.fetchone()[0]
                health_status['checks']['postgis'] = {
                    'status': 'ok',
                    'version': postgis_version
                }
        except Exception as e:
            health_status['checks']['postgis'] = {
                'status': 'error',
                'error': str(e)
            }
            health_status['status'] = 'unhealthy'
        
        # Проверяем создание Point объектов
        try:
            point = Point(37.6173, 55.7558, srid=4326)
            health_status['checks']['point_creation'] = {
                'status': 'ok',
                'coordinates': point.coords
            }
        except Exception as e:
            health_status['checks']['point_creation'] = {
                'status': 'error',
                'error': str(e)
            }
            health_status['status'] = 'unhealthy'
        
        # Проверяем основные функции геолокации
        try:
            from .utils import validate_coordinates, format_distance
            is_valid = validate_coordinates(55.7558, 37.6173)
            formatted = format_distance(1.5)
            
            health_status['checks']['geolocation_functions'] = {
                'status': 'ok',
                'validate_coordinates': is_valid,
                'format_distance': formatted
            }
        except Exception as e:
            health_status['checks']['geolocation_functions'] = {
                'status': 'error',
                'error': str(e)
            }
            health_status['status'] = 'unhealthy'
        
        # Проверяем мониторинг
        try:
            monitor_enabled = monitor.enabled
            health_status['checks']['monitoring'] = {
                'status': 'ok',
                'enabled': monitor_enabled
            }
        except Exception as e:
            health_status['checks']['monitoring'] = {
                'status': 'error',
                'error': str(e)
            }
            health_status['status'] = 'unhealthy'
        
        return Response(health_status, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {
                'status': 'error',
                'error': f'Ошибка при проверке здоровья: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def geospatial_info(request):
    """
    API endpoint для получения информации о геопоиске.
    
    Возвращает информацию о возможностях и настройках системы.
    
    Returns:
        JSON с информацией о системе геопоиска
    """
    try:
        from django.conf import settings
        
        info = {
            'system_info': {
                'postgis_enabled': True,
                'spatial_indexes': True,
                'monitoring_enabled': getattr(settings, 'GEOSPATIAL_MONITORING_ENABLED', True),
                'cache_enabled': hasattr(settings, 'CACHES'),
                'max_search_radius_km': getattr(settings, 'MAX_SEARCH_RADIUS_KM', 100),
                'default_search_radius_km': getattr(settings, 'DEFAULT_SEARCH_RADIUS_KM', 10)
            },
            'capabilities': {
                'distance_calculation': True,
                'radius_search': True,
                'nearest_neighbor_search': True,
                'spatial_filtering': True,
                'distance_annotation': True,
                'batch_processing': True
            },
            'supported_formats': {
                'coordinates': 'WGS84 (EPSG:4326)',
                'distance_units': 'kilometers',
                'point_format': 'longitude,latitude'
            }
        }
        
        return Response(info, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'Ошибка при получении информации: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


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