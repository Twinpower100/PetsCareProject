"""
Утилиты для работы с геолокацией.

Этот модуль содержит вспомогательные функции для работы с координатами,
расчета расстояний и геопространственных операций.
"""

from typing import Tuple, Optional, List, Dict, Any
from decimal import Decimal
from geopy.distance import geodesic
from django.db.models import Q
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance


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
        print(f"Distance calculation error: {e}")
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
        print(f"Distance calculation error: {e}")
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
    lat_field: str = 'latitude',
    lon_field: str = 'longitude'
) -> List[Tuple[Any, float]]:
    """
    Фильтрует QuerySet по расстоянию от центральной точки.
    
    Args:
        queryset: QuerySet для фильтрации
        center_lat: Широта центральной точки
        center_lon: Долгота центральной точки
        radius_km: Радиус поиска в километрах
        lat_field: Название поля с широтой
        lon_field: Название поля с долготой
        
    Returns:
        Список кортежей (объект, расстояние) в радиусе
    """
    results = []
    
    for obj in queryset:
        lat = getattr(obj, lat_field, None)
        lon = getattr(obj, lon_field, None)
        
        if lat is not None and lon is not None:
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
    lat_field: str = 'latitude',
    lon_field: str = 'longitude'
):
    """
    Добавляет аннотацию с расстоянием к QuerySet.
    
    Требует GeoDjango для работы с пространственными полями.
    
    Args:
        queryset: QuerySet для аннотации
        center_lat: Широта центральной точки
        center_lon: Долгота центральной точки
        lat_field: Название поля с широтой
        lon_field: Название поля с долготой
        
    Returns:
        QuerySet с аннотацией distance
    """
    try:
        center_point = Point(center_lon, center_lat, srid=4326)
        return queryset.annotate(
            distance=Distance(f'{lat_field}__{lon_field}', center_point)
        )
    except Exception as e:
        print(f"Distance annotation error: {e}")
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
                             radius_km: float, lat_field: str = 'latitude', 
                             lon_field: str = 'longitude') -> Any:
    """
    Оптимизирует геопространственный запрос с использованием ограничивающего прямоугольника.
    
    Это предварительная фильтрация для уменьшения количества объектов
    перед точным расчетом расстояний.
    
    Args:
        queryset: QuerySet для оптимизации
        center_lat: Широта центральной точки
        center_lon: Долгота центральной точки
        radius_km: Радиус поиска в километрах
        lat_field: Название поля с широтой
        lon_field: Название поля с долготой
        
    Returns:
        Оптимизированный QuerySet
    """
    # Получаем ограничивающий прямоугольник
    bbox = get_bounding_box(center_lat, center_lon, radius_km)
    
    # Применяем предварительную фильтрацию
    optimized_queryset = queryset.filter(
        **{
            f'{lat_field}__gte': bbox['min_lat'],
            f'{lat_field}__lte': bbox['max_lat'],
            f'{lon_field}__gte': bbox['min_lon'],
            f'{lon_field}__lte': bbox['max_lon']
        }
    )
    
    return optimized_queryset


def batch_distance_calculation(queryset, center_lat: float, center_lon: float,
                              batch_size: int = 100) -> List[Tuple[Any, float]]:
    """
    Выполняет расчет расстояний батчами для оптимизации памяти.
    
    Args:
        queryset: QuerySet для обработки
        center_lat: Широта центральной точки
        center_lon: Долгота центральной точки
        batch_size: Размер батча (по умолчанию 100)
        
    Returns:
        Список кортежей (объект, расстояние)
    """
    results = []
    
    for i in range(0, queryset.count(), batch_size):
        batch = queryset[i:i + batch_size]
        
        for obj in batch:
            # Получаем координаты объекта
            lat = getattr(obj, 'latitude', None)
            lon = getattr(obj, 'longitude', None)
            
            # Если координаты не найдены, пытаемся получить из связанного адреса
            if lat is None or lon is None:
                if hasattr(obj, 'address') and obj.address:
                    lat = obj.address.latitude
                    lon = obj.address.longitude
                elif hasattr(obj, 'provider_address') and obj.provider_address:
                    lat = obj.provider_address.latitude
                    lon = obj.provider_address.longitude
            
            if lat is not None and lon is not None:
                distance = calculate_distance(center_lat, center_lon, lat, lon)
                if distance is not None:
                    results.append((obj, distance))
    
    return results


def create_geospatial_index_hint() -> str:
    """
    Возвращает подсказку для создания геопространственных индексов.
    
    Returns:
        SQL-запрос для создания индексов
    """
    return """
    -- Рекомендуемые индексы для оптимизации геопространственных запросов
    
    -- Индекс для координат адресов
    CREATE INDEX idx_address_coordinates ON geolocation_address (latitude, longitude);
    
    -- Составной индекс для поиска по координатам и статусу
    CREATE INDEX idx_address_coordinates_status ON geolocation_address (latitude, longitude, validation_status);
    
    -- Индекс для ограничивающего прямоугольника
    CREATE INDEX idx_address_bbox ON geolocation_address (
        latitude, longitude, 
        validation_status, 
        is_valid
    );
    
    -- Для PostgreSQL с расширением PostGIS (рекомендуется):
    -- CREATE EXTENSION IF NOT EXISTS postgis;
    -- CREATE INDEX idx_address_geom ON geolocation_address USING GIST (geom);
    """ 