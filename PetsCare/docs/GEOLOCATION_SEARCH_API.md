# API Поиска по Геолокации

Документация по API для поиска пользователей, ситтеров и провайдеров по расстоянию.

## Обзор

Система предоставляет несколько API endpoints для поиска по геолокации:

1. **Поиск пользователей по расстоянию** - базовый поиск всех пользователей
2. **Поиск ситтеров по расстоянию** - поиск ситтеров с базовыми фильтрами
3. **Расширенный поиск ситтеров** - поиск с дополнительными фильтрами
4. **Поиск провайдеров по расстоянию** - поиск учреждений по геолокации

## Аутентификация

Все API требуют аутентификации. Используйте JWT токен в заголовке:

```
Authorization: Bearer <your_jwt_token>
```

## 1. Поиск пользователей по расстоянию

### Endpoint
```
GET /users/search/distance/
```

### Параметры запроса

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| latitude | float | Да | Широта центральной точки |
| longitude | float | Да | Долгота центральной точки |
| radius | float | Нет | Радиус поиска в км (по умолчанию 10) |
| user_type | string | Нет | Тип пользователя: 'sitter', 'pet_owner' |
| limit | int | Нет | Максимальное количество результатов (по умолчанию 20) |

### Пример запроса

```bash
curl -X GET "http://localhost:8000/users/search/distance/?latitude=55.7558&longitude=37.6176&radius=5&user_type=sitter" \
  -H "Authorization: Bearer <your_token>"
```

### Пример ответа

```json
[
  {
    "id": 1,
    "email": "sitter@example.com",
    "username": "sitter1",
    "first_name": "John",
    "last_name": "Doe",
    "user_types": ["sitter"],
    "is_active": true,
    "distance": 2.34
  }
]
```

## 2. Поиск ситтеров по расстоянию

### Endpoint
```
GET /users/search/sitters/distance/
```

### Параметры запроса

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| latitude | float | Да | Широта центральной точки |
| longitude | float | Да | Долгота центральной точки |
| radius | float | Нет | Радиус поиска в км (по умолчанию 10) |
| min_rating | float | Нет | Минимальный рейтинг ситтера |
| available | boolean | Нет | Только доступные ситтеры (true/false) |
| limit | int | Нет | Максимальное количество результатов (по умолчанию 20) |

### Пример запроса

```bash
curl -X GET "http://localhost:8000/users/search/sitters/distance/?latitude=55.7558&longitude=37.6176&radius=5&min_rating=4.5&available=true" \
  -H "Authorization: Bearer <your_token>"
```

## 3. Расширенный поиск ситтеров

### Endpoint
```
GET /providers/search/sitters/advanced/
```

### Параметры запроса

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| latitude | float | Да | Широта центральной точки |
| longitude | float | Да | Долгота центральной точки |
| radius | float | Нет | Радиус поиска в км (по умолчанию 10) |
| service_id | int | Нет | ID конкретной услуги |
| min_rating | float | Нет | Минимальный рейтинг ситтера |
| max_price | float | Нет | Максимальная цена за услугу |
| available_date | string | Нет | Дата для проверки доступности (YYYY-MM-DD) |
| available_time | string | Нет | Время для проверки доступности (HH:MM) |
| available | boolean | Нет | Только доступные ситтеры (true/false) |
| limit | int | Нет | Максимальное количество результатов (по умолчанию 20) |

### Пример запроса

```bash
curl -X GET "http://localhost:8000/providers/search/sitters/advanced/?latitude=55.7558&longitude=37.6176&radius=5&service_id=1&min_rating=4.5&max_price=1000&available_date=2024-01-15&available_time=14:00" \
  -H "Authorization: Bearer <your_token>"
```

## 4. Поиск провайдеров по расстоянию

### Endpoint
```
GET /providers/search/distance/
```

### Параметры запроса

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| latitude | float | Да | Широта центральной точки |
| longitude | float | Да | Долгота центральной точки |
| radius | float | Нет | Радиус поиска в км (по умолчанию 10) |
| service_id | int | Нет | ID конкретной услуги |
| min_rating | float | Нет | Минимальный рейтинг провайдера |
| limit | int | Нет | Максимальное количество результатов (по умолчанию 20) |

### Пример запроса

```bash
curl -X GET "http://localhost:8000/providers/search/distance/?latitude=55.7558&longitude=37.6176&radius=5&service_id=1&min_rating=4.0" \
  -H "Authorization: Bearer <your_token>"
```

### Пример ответа

```json
[
  {
    "id": 1,
    "name": "Pet Care Center",
    "description": "Professional pet care services",
    "address": {
      "id": 1,
      "formatted_address": "Moscow, Arbat St, 10"
    },
    "phone": "+7-123-456-7890",
    "email": "info@petcare.com",
    "website": "https://petcare.com",
    "rating": "4.50",
    "is_active": true,
    "services": [
      {
        "id": 1,
        "service": {
          "name": "Dog Walking",
          "price": "500.00"
        },
        "price": "500.00",
        "is_active": true
      }
    ],
    "employees": [],
    "distance": 2.34
  }
]
```

## Коды ошибок

| Код | Описание |
|-----|----------|
| 200 | Успешный запрос |
| 400 | Некорректные параметры запроса |
| 401 | Не авторизован |
| 403 | Доступ запрещен |
| 500 | Внутренняя ошибка сервера |

## Ограничения

1. **Максимальный радиус поиска**: 50 км
2. **Максимальное количество результатов**: 100
3. **Частота запросов**: 100 запросов в минуту на пользователя
4. **Кэширование**: Результаты кэшируются на 1 час

## Оптимизация производительности

### Индексы базы данных

Для оптимизации геопространственных запросов создайте индексы:

```sql
-- Базовые индексы для координат
CREATE INDEX idx_address_coordinates ON geolocation_address (latitude, longitude);
CREATE INDEX idx_address_coordinates_status ON geolocation_address (latitude, longitude, validation_status);

-- Индексы для пользователей
CREATE INDEX idx_user_address_coordinates ON users_user (address_id);
CREATE INDEX idx_user_provider_address_coordinates ON users_user (provider_address_id);
```

### Команда для создания индексов

```bash
python manage.py create_geospatial_indexes
```

### PostGIS (рекомендуется)

Для максимальной производительности используйте PostgreSQL с расширением PostGIS:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE INDEX idx_address_geom ON geolocation_address USING GIST (geom);
```

## Примеры использования

### JavaScript (Frontend)

```javascript
// Поиск ситтеров рядом
async function searchNearbySitters(lat, lon, radius = 5) {
  const response = await fetch(
    `/users/search/sitters/distance/?latitude=${lat}&longitude=${lon}&radius=${radius}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );
  
  return await response.json();
}

// Расширенный поиск ситтеров
async function advancedSitterSearch(params) {
  const queryString = new URLSearchParams(params).toString();
  const response = await fetch(
    `/providers/search/sitters/advanced/?${queryString}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );
  
  return await response.json();
}
```

### Python (Backend)

```python
from geolocation.utils import filter_by_distance, validate_coordinates

def search_providers_nearby(lat, lon, radius=10):
    """Поиск провайдеров рядом с указанной точкой."""
    
    if not validate_coordinates(lat, lon):
        return []
    
    # Получаем всех активных провайдеров
    providers = Provider.objects.filter(is_active=True)
    
    # Фильтруем по расстоянию
    nearby_providers = filter_by_distance(
        providers, lat, lon, radius,
        'structured_address__point'
    )
    
    return [provider for provider, distance in nearby_providers]
```

## Мониторинг и логирование

Все запросы к API поиска логируются с метриками:

- Время выполнения запроса
- Количество найденных результатов
- Использование кэша
- Параметры поиска

Логи доступны в Django admin панели в разделе "Geolocation Logs". 