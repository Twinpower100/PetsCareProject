"""
Утилиты для работы с геолокацией.

Этот модуль содержит вспомогательные функции для работы с координатами,
расчета расстояний и геопространственных операций.
"""

import logging
from typing import Tuple, Optional, List, Dict, Any
from decimal import Decimal
from geopy.distance import geodesic
from django.db.models import Q
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance

logger = logging.getLogger(__name__)


def calculate_distance(
    lat1: float, 
    lon1: float, 
    lat2: float, 
    lon2: float
) -> Optional[float]:
    """
    Вычисляет расстояние между двумя точками на поверхности Земли.
    
    Использует формулу гаверсинуса для точного расчета расстояния
    по поверхности сферы.
    
    Args:
        lat1: Широта первой точки
        lon1: Долгота первой точки
        lat2: Широта второй точки
        lon2: Долгота второй точки
        
    Returns:
        Расстояние в километрах или None при ошибке
    """
    try:
        point1 = (float(lat1), float(lon1))
        point2 = (float(lat2), float(lon2))
        
        return geodesic(point1, point2).kilometers
    except (ValueError, TypeError) as e:
        logger.error(f"Distance calculation error: {e}")
        return None


def calculate_distance_from_coordinates(
    point1: Tuple[float, float], 
    point2: Tuple[float, float]
) -> Optional[float]:
    """
    Вычисляет расстояние между двумя точками, заданными кортежами координат.
    
    Args:
        point1: Кортеж (широта, долгота) первой точки
        point2: Кортеж (широта, долгота) второй точки
        
    Returns:
        Расстояние в километрах или None при ошибке
    """
    try:
        return geodesic(point1, point2).kilometers
    except (ValueError, TypeError) as e:
        logger.error(f"Distance calculation error: {e}")
        return None


def is_within_radius(
    center_lat: float,
    center_lon: float,
    target_lat: float,
    target_lon: float,
    radius_km: float
) -> bool:
    """
    Проверяет, находится ли целевая точка в пределах указанного радиуса.
    
    Args:
        center_lat: Широта центральной точки
        center_lon: Долгота центральной точки
        target_lat: Широта целевой точки
        target_lon: Долгота целевой точки
        radius_km: Радиус в километрах
        
    Returns:
        True, если точка находится в радиусе, False иначе
    """
    distance = calculate_distance(center_lat, center_lon, target_lat, target_lon)
    return distance is not None and distance <= radius_km


def filter_by_distance(
    queryset,
    center_lat: float,
    center_lon: float,
    radius_km: float,
    point_field: str = 'point'
) -> List[Tuple[Any, float]]:
    """
    Фильтрует QuerySet по расстоянию от центральной точки используя PostGIS.
    
    Args:
        queryset: QuerySet для фильтрации
        center_lat: Широта центральной точки
        center_lon: Долгота центральной точки
        radius_km: Радиус поиска в километрах
        point_field: Название поля с PointField
        
    Returns:
        Список кортежей (объект, расстояние) в радиусе
    """
    try:
        center_point = Point(center_lon, center_lat, srid=4326)
        
        # Используем PostGIS геооператоры для фильтрации
        filtered_queryset = queryset.filter(
            **{f'{point_field}__distance_lte': (center_point, radius_km * 1000)}
        ).annotate(
            distance=Distance(point_field, center_point)
        ).order_by('distance')
        
        # Конвертируем в список кортежей для совместимости
        results = []
        for obj in filtered_queryset:
            # Конвертируем расстояние из метров в километры
            distance_km = float(obj.distance.km) if obj.distance else 0
            results.append((obj, distance_km))
        
        return results
        
    except Exception as e:
        logger.error(f"PostGIS filter error: {e}")
        # Fallback к старому методу если PostGIS недоступен
        return _fallback_filter_by_distance(
            queryset, center_lat, center_lon, radius_km, point_field
        )


def _fallback_filter_by_distance(
    queryset,
    center_lat: float,
    center_lon: float,
    radius_km: float,
    point_field: str = 'point'
) -> List[Tuple[Any, float]]:
    """
    Fallback метод для фильтрации по расстоянию без PostGIS.
    """
    results = []
    
    for obj in queryset:
        point = getattr(obj, point_field, None)
        
        if point is not None:
            # Используем координаты из Point объекта
            lat, lon = point.coords
            distance = calculate_distance(center_lat, center_lon, lat, lon)
            if distance is not None and distance <= radius_km:
                results.append((obj, distance))
    
    # Сортируем по расстоянию
    results.sort(key=lambda x: x[1])
    
    return results


def get_bounding_box(
    center_lat: float,
    center_lon: float,
    radius_km: float
) -> Dict[str, float]:
    """
    Вычисляет ограничивающий прямоугольник для поиска по радиусу.
    
    Это приближенный метод для предварительной фильтрации
    перед точным расчетом расстояний.
    
    Args:
        center_lat: Широта центральной точки
        center_lon: Долгота центральной точки
        radius_km: Радиус в километрах
        
    Returns:
        Словарь с границами: {'min_lat', 'max_lat', 'min_lon', 'max_lon'}
    """
    # Приблизительно 1 градус = 111 км
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * abs(center_lat) / 90.0)
    
    return {
        'min_lat': center_lat - lat_delta,
        'max_lat': center_lat + lat_delta,
        'min_lon': center_lon - lon_delta,
        'max_lon': center_lon + lon_delta
    }


def create_distance_annotation(
    queryset,
    center_lat: float,
    center_lon: float,
    point_field: str = 'point'
):
    """
    Добавляет аннотацию с расстоянием к QuerySet используя PostGIS.
    
    Args:
        queryset: QuerySet для аннотации
        center_lat: Широта центральной точки
        center_lon: Долгота центральной точки
        point_field: Название поля с PointField
        
    Returns:
        QuerySet с аннотацией distance
    """
    try:
        center_point = Point(center_lon, center_lat, srid=4326)
        return queryset.annotate(
            distance=Distance(point_field, center_point)
        )
    except Exception as e:
        logger.error(f"PostGIS annotation error: {e}")
        # Возвращаем исходный queryset если PostGIS недоступен
        return queryset


def validate_coordinates(lat: float, lon: float) -> bool:
    """
    Проверяет корректность географических координат.
    
    Args:
        lat: Широта
        lon: Долгота
        
    Returns:
        True, если координаты корректны, False иначе
    """
    try:
        lat = float(lat)
        lon = float(lon)
        
        return -90 <= lat <= 90 and -180 <= lon <= 180
    except (ValueError, TypeError):
        return False


def format_distance(distance_km: float) -> str:
    """
    Форматирует расстояние для отображения пользователю.
    
    Args:
        distance_km: Расстояние в километрах
        
    Returns:
        Отформатированная строка расстояния
    """
    if distance_km < 1:
        return f"{int(distance_km * 1000)} m"
    elif distance_km < 10:
        return f"{distance_km:.1f} km"
    else:
        return f"{int(distance_km)} km"


def cache_search_results(cache_key: str, results: List[Tuple[Any, float]], 
                        timeout: int = 3600) -> None:
    """
    Кэширует результаты поиска для оптимизации производительности.
    
    Args:
        cache_key: Ключ для кэширования
        results: Список результатов поиска с расстояниями
        timeout: Время жизни кэша в секундах (по умолчанию 1 час)
    """
    from django.core.cache import cache
    
    # Сохраняем результаты в кэше
    cache.set(cache_key, results, timeout)


def get_cached_search_results(cache_key: str) -> Optional[List[Tuple[Any, float]]]:
    """
    Получает закэшированные результаты поиска.
    
    Args:
        cache_key: Ключ для кэширования
        
    Returns:
        Список результатов поиска или None, если кэш не найден
    """
    from django.core.cache import cache
    
    return cache.get(cache_key)


def generate_search_cache_key(search_type: str, **params) -> str:
    """
    Генерирует ключ кэша для результатов поиска.
    
    Args:
        search_type: Тип поиска (users, sitters, providers)
        **params: Параметры поиска
        
    Returns:
        Уникальный ключ кэша
    """
    import hashlib
    import json
    
    # Создаем строку для хеширования
    params_str = json.dumps(params, sort_keys=True)
    cache_string = f"{search_type}:{params_str}"
    
    # Генерируем MD5 хеш
    return hashlib.md5(cache_string.encode()).hexdigest()


def optimize_geospatial_query(queryset, center_lat: float, center_lon: float, 
                             radius_km: float, point_field: str = 'point') -> Any:
    """
    Оптимизирует геопространственный запрос с использованием PostGIS.
    
    Использует PostGIS геооператоры для эффективной фильтрации
    по расстоянию без необходимости предварительной фильтрации.
    
    Args:
        queryset: QuerySet для оптимизации
        center_lat: Широта центральной точки
        center_lon: Долгота центральной точки
        radius_km: Радиус поиска в километрах
        point_field: Название поля с PointField
        
    Returns:
        Оптимизированный QuerySet с аннотацией расстояния
    """
    try:
        center_point = Point(center_lon, center_lat, srid=4326)
        
        # Используем PostGIS для эффективной фильтрации и аннотации
        optimized_queryset = queryset.filter(
            **{f'{point_field}__distance_lte': (center_point, radius_km * 1000)}
        ).annotate(
            distance=Distance(point_field, center_point)
        ).order_by('distance')
        
        return optimized_queryset
        
    except Exception as e:
        logger.error(f"PostGIS optimization error: {e}")
        # Fallback к старому методу если PostGIS недоступен
        return _fallback_optimize_geospatial_query(
            queryset, center_lat, center_lon, radius_km, point_field
        )


def _fallback_optimize_geospatial_query(queryset, center_lat: float, center_lon: float, 
                                       radius_km: float, point_field: str = 'point') -> Any:
    """
    Fallback метод для оптимизации геопространственных запросов без PostGIS.
    """
    # Получаем ограничивающий прямоугольник
    bbox = get_bounding_box(center_lat, center_lon, radius_km)
    
    # Применяем предварительную фильтрацию по координатам
    # Это работает только если у объекта есть отдельные поля latitude/longitude
    optimized_queryset = queryset
    
    # Пытаемся применить фильтрацию по координатам если они доступны
    try:
        optimized_queryset = queryset.filter(
            **{
                f'{point_field}__x__gte': bbox['min_lon'],
                f'{point_field}__x__lte': bbox['max_lon'],
                f'{point_field}__y__gte': bbox['min_lat'],
                f'{point_field}__y__lte': bbox['max_lat']
            }
        )
    except:
        # Если не удалось применить фильтрацию, возвращаем исходный queryset
        pass
    
    return optimized_queryset


def batch_distance_calculation(queryset, center_lat: float, center_lon: float,
                              batch_size: int = 100) -> List[Tuple[Any, float]]:
    """
    Выполняет расчет расстояний батчами для оптимизации памяти используя PostGIS.
    
    Args:
        queryset: QuerySet для обработки
        center_lat: Широта центральной точки
        center_lon: Долгота центральной точки
        batch_size: Размер батча (по умолчанию 100)
        
    Returns:
        Список кортежей (объект, расстояние)
    """
    try:
        center_point = Point(center_lon, center_lat, srid=4326)
        results = []
        
        for i in range(0, queryset.count(), batch_size):
            batch = queryset[i:i + batch_size]
            
            # Используем PostGIS для батчевой обработки
            for obj in batch:
                point = getattr(obj, 'point', None)
                
                if point is not None:
                    # Используем PostGIS для расчета расстояния
                    distance = point.distance(center_point) * 111.32  # Convert to km
                    results.append((obj, distance))
        
        return results
        
    except Exception as e:
        logger.error(f"PostGIS batch calculation error: {e}")
        # Fallback к старому методу если PostGIS недоступен
        return _fallback_batch_distance_calculation(
            queryset, center_lat, center_lon, batch_size
        )


def _fallback_batch_distance_calculation(queryset, center_lat: float, center_lon: float,
                                        batch_size: int = 100) -> List[Tuple[Any, float]]:
    """
    Fallback метод для батчевого расчета расстояний без PostGIS.
    """
    results = []
    
    for i in range(0, queryset.count(), batch_size):
        batch = queryset[i:i + batch_size]
        
        for obj in batch:
            # Получаем координаты объекта
            point = getattr(obj, 'point', None)
            
            # Если point не найден, пытаемся получить из связанного адреса
            if point is None:
                if hasattr(obj, 'address') and obj.address:
                    point = obj.address.point
                elif hasattr(obj, 'structured_address') and obj.structured_address:
                    point = obj.structured_address.point
            
            if point is not None:
                # Используем координаты из Point объекта
                lat, lon = point.coords
                distance = calculate_distance(center_lat, center_lon, lat, lon)
                if distance is not None:
                    results.append((obj, distance))
    
    return results


def create_geospatial_index_hint() -> str:
    """
    Возвращает подсказку для создания геопространственных индексов PostGIS.
    
    Returns:
        SQL-запрос для создания индексов
    """
    return """
    -- Рекомендуемые индексы для оптимизации геопространственных запросов с PostGIS
    
    -- Включение расширения PostGIS (если еще не включено)
    CREATE EXTENSION IF NOT EXISTS postgis;
    
    -- GiST индекс для PointField в модели Address
    CREATE INDEX idx_address_point_gist ON geolocation_address USING GIST (point);
    
    -- GiST индекс для PointField в модели Location
    CREATE INDEX idx_location_point_gist ON geolocation_location USING GIST (point);
    
    -- GiST индекс для PointField в модели LocationHistory
    CREATE INDEX idx_location_history_point_gist ON geolocation_locationhistory USING GIST (point);
    
    -- GiST индекс для PointField в модели UserLocation
    CREATE INDEX idx_user_location_point_gist ON geolocation_userlocation USING GIST (point);
    
    -- GiST индекс для PointField в модели ProviderLocation (через structured_address)
    CREATE INDEX idx_provider_location_address_point_gist ON geolocation_address USING GIST (point)
    WHERE id IN (SELECT structured_address_id FROM providers_providerlocation WHERE structured_address_id IS NOT NULL);
    
    -- Составные индексы для оптимизации запросов с дополнительными условиями
    
    -- Address с валидацией
    CREATE INDEX idx_address_point_status ON geolocation_address USING GIST (point) 
    WHERE validation_status = 'valid';
    
    -- ProviderLocation с активностью (через structured_address)
    CREATE INDEX idx_provider_location_active ON providers_providerlocation (is_active)
    WHERE is_active = true AND structured_address_id IS NOT NULL;
    
    -- UserLocation с источником
    CREATE INDEX idx_user_location_point_source ON geolocation_userlocation USING GIST (point) 
    WHERE source = 'device';
    
    -- Для оптимизации запросов по времени (LocationHistory)
    CREATE INDEX idx_location_history_point_time ON geolocation_locationhistory 
    USING GIST (point, created_at);
    
    -- Для оптимизации запросов по пользователю и времени (UserLocation)
    CREATE INDEX idx_user_location_point_user ON geolocation_userlocation 
    USING GIST (point, user_id);
    
    -- Анализ статистики для оптимизации запросов
    ANALYZE geolocation_address;
    ANALYZE geolocation_location;
    ANALYZE geolocation_locationhistory;
    ANALYZE geolocation_userlocation;
    ANALYZE providers_provider;
    ANALYZE providers_providerlocation;
    """ 