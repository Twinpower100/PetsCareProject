"""
Модуль мониторинга производительности геопоиска.
"""

import time
import logging
from functools import wraps
from django.core.cache import cache
from django.conf import settings
from typing import Dict, Any, Optional, Callable
import json

logger = logging.getLogger(__name__)


class GeospatialPerformanceMonitor:
    """Монитор производительности геопоиска."""
    
    def __init__(self):
        self.metrics = {}
        self.enabled = getattr(settings, 'GEOSPATIAL_MONITORING_ENABLED', True)
    
    def record_metric(self, metric_name: str, value: float, tags: Optional[Dict[str, Any]] = None):
        """Записывает метрику производительности."""
        if not self.enabled:
            return
        
        if metric_name not in self.metrics:
            self.metrics[metric_name] = []
        
        metric_data = {
            'value': value,
            'timestamp': time.time(),
            'tags': tags or {}
        }
        
        self.metrics[metric_name].append(metric_data)
        
        # Ограничиваем количество записей
        if len(self.metrics[metric_name]) > 1000:
            self.metrics[metric_name] = self.metrics[metric_name][-1000:]
        
        # Логируем медленные запросы
        if metric_name == 'query_execution_time' and value > 1.0:
            logger.warning(f"Slow geospatial query: {value:.2f}s, tags: {tags}")
    
    def get_metric_stats(self, metric_name: str) -> Dict[str, Any]:
        """Получает статистику по метрике."""
        if metric_name not in self.metrics:
            return {}
        
        values = [m['value'] for m in self.metrics[metric_name]]
        
        if not values:
            return {}
        
        return {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'avg': sum(values) / len(values),
            'latest': values[-1] if values else None
        }
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Получает статистику по всем метрикам."""
        return {
            metric_name: self.get_metric_stats(metric_name)
            for metric_name in self.metrics.keys()
        }
    
    def clear_metrics(self):
        """Очищает все метрики."""
        self.metrics.clear()


# Глобальный экземпляр монитора
monitor = GeospatialPerformanceMonitor()


def monitor_geospatial_query(metric_name: str = None):
    """Декоратор для мониторинга геопоисковых запросов."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not monitor.enabled:
                return func(*args, **kwargs)
            
            # Определяем имя метрики
            metric = metric_name or f"{func.__module__}.{func.__name__}"
            
            # Извлекаем параметры для тегов
            tags = {}
            if args:
                # Пытаемся извлечь координаты и радиус
                if len(args) >= 3:
                    tags['center_lat'] = args[1] if isinstance(args[1], (int, float)) else 'unknown'
                    tags['center_lon'] = args[2] if isinstance(args[2], (int, float)) else 'unknown'
                if len(args) >= 4:
                    tags['radius_km'] = args[3] if isinstance(args[3], (int, float)) else 'unknown'
            
            # Засекаем время выполнения
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                
                # Записываем метрики
                execution_time = time.time() - start_time
                monitor.record_metric('query_execution_time', execution_time, tags)
                
                # Записываем размер результата
                if hasattr(result, '__len__'):
                    result_size = len(result)
                    monitor.record_metric('query_result_size', result_size, tags)
                
                return result
                
            except Exception as e:
                # Записываем ошибки
                execution_time = time.time() - start_time
                error_tags = {**tags, 'error': str(type(e).__name__)}
                monitor.record_metric('query_errors', 1, error_tags)
                monitor.record_metric('query_execution_time', execution_time, tags)
                raise
        
        return wrapper
    return decorator


def monitor_cache_performance(cache_key_prefix: str = "geospatial"):
    """Декоратор для мониторинга производительности кэша."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not monitor.enabled:
                return func(*args, **kwargs)
            
            metric = f"{func.__module__}.{func.__name__}_cache"
            
            # Засекаем время выполнения
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                
                execution_time = time.time() - start_time
                tags = {'cache_prefix': cache_key_prefix}
                
                monitor.record_metric('cache_execution_time', execution_time, tags)
                
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                error_tags = {'cache_prefix': cache_key_prefix, 'error': str(type(e).__name__)}
                monitor.record_metric('cache_errors', 1, error_tags)
                monitor.record_metric('cache_execution_time', execution_time, tags)
                raise
        
        return wrapper
    return decorator


class GeospatialQueryLogger:
    """Логгер для геопоисковых запросов."""
    
    def __init__(self):
        self.logger = logging.getLogger('geospatial.queries')
    
    def log_query(self, query_type: str, params: Dict[str, Any], execution_time: float, 
                  result_count: int = None, error: str = None):
        """Логирует геопоисковый запрос."""
        log_data = {
            'query_type': query_type,
            'params': params,
            'execution_time': execution_time,
            'result_count': result_count,
            'error': error,
            'timestamp': time.time()
        }
        
        if error:
            self.logger.error(f"Geospatial query error: {json.dumps(log_data)}")
        elif execution_time > 1.0:
            self.logger.warning(f"Slow geospatial query: {json.dumps(log_data)}")
        else:
            self.logger.info(f"Geospatial query: {json.dumps(log_data)}")


# Глобальный экземпляр логгера
query_logger = GeospatialQueryLogger()


def get_performance_report() -> Dict[str, Any]:
    """Генерирует отчет о производительности геопоиска."""
    stats = monitor.get_all_stats()
    
    report = {
        'summary': {
            'total_queries': stats.get('query_execution_time', {}).get('count', 0),
            'avg_execution_time': stats.get('query_execution_time', {}).get('avg', 0),
            'max_execution_time': stats.get('query_execution_time', {}).get('max', 0),
            'total_errors': stats.get('query_errors', {}).get('count', 0),
            'avg_result_size': stats.get('query_result_size', {}).get('avg', 0)
        },
        'metrics': stats,
        'recommendations': []
    }
    
    # Генерируем рекомендации
    avg_time = stats.get('query_execution_time', {}).get('avg', 0)
    if avg_time > 0.5:
        report['recommendations'].append(
            "Среднее время выполнения запросов высокое. Рассмотрите оптимизацию индексов."
        )
    
    error_rate = 0
    total_queries = stats.get('query_execution_time', {}).get('count', 0)
    total_errors = stats.get('query_errors', {}).get('count', 0)
    
    if total_queries > 0:
        error_rate = total_errors / total_queries
    
    if error_rate > 0.05:  # 5%
        report['recommendations'].append(
            f"Высокий уровень ошибок ({error_rate:.1%}). Проверьте логи и исправьте проблемы."
        )
    
    return report


def reset_performance_metrics():
    """Сбрасывает все метрики производительности."""
    monitor.clear_metrics()


# Применяем мониторинг к основным функциям геолокации
from .utils import filter_by_distance, create_distance_annotation, optimize_geospatial_query

# Оборачиваем функции мониторингом
original_filter_by_distance = filter_by_distance
original_create_distance_annotation = create_distance_annotation
original_optimize_geospatial_query = optimize_geospatial_query

@monitor_geospatial_query("filter_by_distance")
def monitored_filter_by_distance(*args, **kwargs):
    return original_filter_by_distance(*args, **kwargs)

@monitor_geospatial_query("create_distance_annotation")
def monitored_create_distance_annotation(*args, **kwargs):
    return original_create_distance_annotation(*args, **kwargs)

@monitor_geospatial_query("optimize_geospatial_query")
def monitored_optimize_geospatial_query(*args, **kwargs):
    return original_optimize_geospatial_query(*args, **kwargs)

# Заменяем оригинальные функции
import geolocation.utils
geolocation.utils.filter_by_distance = monitored_filter_by_distance
geolocation.utils.create_distance_annotation = monitored_create_distance_annotation
geolocation.utils.optimize_geospatial_query = monitored_optimize_geospatial_query 