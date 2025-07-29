# Руководство по использованию PostGIS функций в PetCare

## Обзор

PetCare использует PostgreSQL с расширением PostGIS для эффективного геопоиска и пространственных запросов. Все координатные поля переведены с `DecimalField` на `PointField` для оптимизации производительности.

## Основные функции

### 1. Фильтрация по расстоянию

```python
from geolocation.utils import filter_by_distance

# Поиск объектов в радиусе от центральной точки
results = filter_by_distance(
    queryset=Provider.objects.all(),
    center_lat=55.7558,
    center_lon=37.6173,
    radius_km=10,
    point_field='point'
)

# Результат: список кортежей (объект, расстояние_в_км)
for provider, distance in results:
    print(f"{provider.name}: {distance:.2f} км")
```

### 2. Создание аннотации расстояния

```python
from geolocation.utils import create_distance_annotation

# Добавление поля distance к QuerySet
queryset = create_distance_annotation(
    Provider.objects.all(),
    center_lat=55.7558,
    center_lon=37.6173,
    point_field='point'
)

# Теперь у каждого объекта есть поле distance
for provider in queryset:
    print(f"{provider.name}: {provider.distance.km:.2f} км")
```

### 3. Оптимизация геопространственных запросов

```python
from geolocation.utils import optimize_geospatial_query

# Оптимизированный запрос с фильтрацией и аннотацией
queryset = optimize_geospatial_query(
    Provider.objects.all(),
    center_lat=55.7558,
    center_lon=37.6173,
    radius_km=10,
    point_field='point'
)
```

### 4. Батчевый расчет расстояний

```python
from geolocation.utils import batch_distance_calculation

# Расчет расстояний батчами для больших наборов данных
results = batch_distance_calculation(
    Provider.objects.all(),
    center_lat=55.7558,
    center_lon=37.6173,
    batch_size=100
)
```

## API Endpoints

### Поиск провайдеров по расстоянию

```
GET /api/providers/search-by-distance/
```

**Параметры:**
- `latitude` (float): Широта центральной точки
- `longitude` (float): Долгота центральной точки
- `radius` (float): Радиус поиска в километрах (по умолчанию 10)
- `service_id` (int): ID услуги для фильтрации
- `min_rating` (float): Минимальный рейтинг
- `price_min` (float): Минимальная цена
- `price_max` (float): Максимальная цена
- `sort_by` (str): Сортировка (distance, rating, price_asc, price_desc)
- `limit` (int): Максимальное количество результатов

**Пример:**
```
GET /api/providers/search-by-distance/?latitude=55.7558&longitude=37.6173&radius=5&service_id=1&sort_by=distance
```

### Поиск ситтеров по расстоянию

```
GET /api/sitters/search-by-distance/
```

**Параметры:** аналогично провайдерам

### Мониторинг производительности

```
GET /api/geolocation/performance-report/  # Только для админов
GET /api/geolocation/health-check/        # Для всех пользователей
GET /api/geolocation/info/                # Информация о системе
```

## Модели с PostGIS

### Address

```python
from geolocation.models import Address
from django.contrib.gis.geos import Point

# Создание адреса с координатами
address = Address.objects.create(
    street="Красная площадь, 1",
    city="Москва",
    country="Россия",
    point=Point(37.6173, 55.7558, srid=4326)
)

# Получение координат
lat, lon = address.point.coords
```

### Provider

```python
from providers.models import Provider

# Поиск ближайших провайдеров
nearest = Provider.find_nearest(
    lat=55.7558,
    lon=37.6173,
    radius=10,
    limit=5
)

# Расчет расстояния до провайдера
distance = provider.distance_to(55.7558, 37.6173)
```

## Фильтры

### PetFilter

```python
from pets.filters import PetFilter

# Фильтрация питомцев по геолокации
filter_params = {
    'location_lat': 55.7558,
    'location_lng': 37.6173,
    'radius_km': 5
}

pet_filter = PetFilter(filter_params, request=request)
queryset = pet_filter.qs
```

## Утилиты

### Валидация координат

```python
from geolocation.utils import validate_coordinates

# Проверка корректности координат
is_valid = validate_coordinates(55.7558, 37.6173)  # True
is_valid = validate_coordinates(91, 37.6173)       # False
```

### Форматирование расстояния

```python
from geolocation.utils import format_distance

formatted = format_distance(0.5)   # "500 m"
formatted = format_distance(1.5)   # "1.5 km"
formatted = format_distance(15)    # "15 km"
```

## Настройки

### settings.py

```python
# Включение PostGIS
INSTALLED_APPS = [
    'django.contrib.gis',
    # ...
]

# Настройки базы данных
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        # ...
    }
}

# Настройки геопоиска
GEOSPATIAL_MONITORING_ENABLED = True
MAX_SEARCH_RADIUS_KM = 100
DEFAULT_SEARCH_RADIUS_KM = 10
```

## Производительность

### Рекомендации

1. **Используйте пространственные индексы** - они создаются автоматически для всех PointField
2. **Ограничивайте радиус поиска** - большие радиусы замедляют запросы
3. **Используйте батчевую обработку** для больших наборов данных
4. **Кэшируйте результаты** часто используемых запросов

### Мониторинг

```python
from geolocation.monitoring import get_performance_report

# Получение отчета о производительности
report = get_performance_report()
print(f"Среднее время запроса: {report['summary']['avg_execution_time']:.3f}s")
```

## Миграция данных

### Создание Point из координат

```python
from django.contrib.gis.geos import Point

# Создание Point объекта
point = Point(longitude, latitude, srid=4326)

# Обновление модели
provider.point = point
provider.save()
```

### Массовая миграция

```python
from django.contrib.gis.geos import Point

# Миграция всех провайдеров
for provider in Provider.objects.all():
    if provider.latitude and provider.longitude:
        provider.point = Point(provider.longitude, provider.latitude, srid=4326)
        provider.save()
```

## Обработка ошибок

### Fallback механизм

Все PostGIS функции имеют fallback механизм для случаев, когда PostGIS недоступен:

```python
try:
    # PostGIS версия
    results = filter_by_distance(queryset, lat, lon, radius, 'point')
except Exception as e:
    # Fallback к старому методу
    results = _fallback_filter_by_distance(queryset, lat, lon, radius)
```

## Тестирование

### Запуск тестов

```bash
# Тесты геолокации
python manage.py test geolocation.tests

# Тесты провайдеров
python manage.py test providers.tests

# Все тесты
python manage.py test
```

### Тестовые данные

```python
from django.contrib.gis.geos import Point

# Создание тестовых адресов
moscow = Address.objects.create(
    street="Красная площадь",
    city="Москва",
    point=Point(37.6173, 55.7558, srid=4326)
)
```

## Поддержка

При возникновении проблем:

1. Проверьте логи Django
2. Используйте health check endpoint
3. Проверьте метрики производительности
4. Убедитесь, что PostGIS установлен и настроен 