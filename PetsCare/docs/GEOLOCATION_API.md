# API Геолокации и Поиска

## Обзор

Новая система геопоиска обеспечивает удобный поиск ситтеров и учреждений по местоположению с учетом ролей пользователей.

## Логика по ролям пользователей

### 1. Обычный пользователь (pet_owner)
- **Адрес**: НЕ обязателен
- **Геолокация**: Используется для поиска ближайших ситтеров/учреждений
- **Источники**: Устройство → Карта → Ручной ввод

### 2. Ситтер (pet_sitter)
- **Адрес**: ОБЯЗАТЕЛЕН (где оказывает услуги)
- **Причина**: Клиенты должны знать, где будет оказываться услуга
- **Валидация**: Адрес должен быть заполнен и валидирован

### 3. Учреждение (provider_admin)
- **Адрес**: ОБЯЗАТЕЛЕН (где находится учреждение)
- **Причина**: Клиенты должны знать местоположение учреждения
- **Валидация**: Адрес должен быть заполнен и валидирован

## Принципы работы

### 1. Приоритет определения местоположения
1. **Геолокация устройства** (приоритет) - автоматическое получение координат через браузер
2. **Выбор района на карте** (fallback) - интерактивная карта для выбора центра поиска
3. **Ручной ввод адреса** (последний вариант) - автодополнение через Google Places API

### 2. Кэширование местоположения
- Местоположение кэшируется на 24 часа
- Сохраняется в базе данных для оптимизации
- Автоматическое обновление при изменении

## API Endpoints

### Проверка требований к адресу

**GET** `/api/geolocation/check-address-requirement/`

Проверяет, требуется ли адрес для пользователя в зависимости от его роли.

**Ответ:**
```json
{
    "success": true,
    "address_requirement": {
        "address_required": true,
        "role": "sitter",
        "has_address": false,
        "message": "Address is required for pet sitters to specify where services are provided",
        "missing_address": true
    }
}
```

### Валидация местоположения для роли

**POST** `/api/geolocation/validate-location-for-role/`

Валидирует местоположение для конкретной роли пользователя.

**Параметры:**
```json
{
    "latitude": 55.7558,
    "longitude": 37.6176
}
```

**Ответ при успехе:**
```json
{
    "success": true,
    "validation": {
        "valid": true,
        "address_required": true,
        "role": "sitter",
        "message": "Location validation passed"
    }
}
```

**Ответ при ошибке:**
```json
{
    "success": true,
    "validation": {
        "valid": false,
        "address_required": true,
        "role": "sitter",
        "message": "Address is required for pet sitters to specify where services are provided",
        "error": "missing_address"
    }
}
```

### Получение местоположения пользователя

**GET** `/api/geolocation/user-location/`

Получает текущее местоположение пользователя из кэша.

**Ответ при наличии местоположения:**
```json
{
    "success": true,
    "location": {
        "latitude": 55.7558,
        "longitude": 37.6176,
        "accuracy": 50,
        "source": "device",
        "timestamp": "2024-05-15T10:00:00Z"
    }
}
```

**Ответ при отсутствии местоположения:**
```json
{
    "success": true,
    "location": null,
    "message": "Location not available. Please enable device location or select area on map."
}
```

### Сохранение местоположения устройства

**POST** `/api/geolocation/device-location/`

Сохраняет координаты, полученные от устройства пользователя.

**Параметры:**
```json
{
    "latitude": 55.7558,
    "longitude": 37.6176,
    "accuracy": 50
}
```

**Ответ:**
```json
{
    "success": true,
    "message": "Location saved successfully",
    "location": {
        "latitude": 55.7558,
        "longitude": 37.6176,
        "accuracy": 50,
        "source": "device",
        "timestamp": "2024-05-15T10:00:00Z"
    }
}
```

### Сохранение выбранного района на карте

**POST** `/api/geolocation/map-location/`

Сохраняет координаты, выбранные пользователем на карте.

**Параметры:**
```json
{
    "latitude": 55.7558,
    "longitude": 37.6176,
    "address": "Москва, Красная площадь"
}
```

**Ответ:**
```json
{
    "success": true,
    "message": "Map location saved successfully",
    "location": {
        "latitude": 55.7558,
        "longitude": 37.6176,
        "accuracy": 100,
        "source": "map",
        "timestamp": "2024-05-15T10:00:00Z",
        "address": "Москва, Красная площадь",
        "address_components": {
            "city": "Москва",
            "street": "Красная площадь"
        }
    }
}
```

### Получение информации о местоположении

**GET** `/api/geolocation/location-info/?latitude=55.7558&longitude=37.6176`

Получает информацию о местоположении по координатам (обратное геокодирование).

**Ответ:**
```json
{
    "success": true,
    "location_info": {
        "coordinates": {
            "latitude": 55.7558,
            "longitude": 37.6176
        },
        "address": "Москва, Красная площадь",
        "address_components": {
            "country": "Россия",
            "city": "Москва",
            "street": "Красная площадь"
        },
        "location_type": "ROOFTOP"
    }
}
```

### Очистка местоположения

**DELETE** `/api/geolocation/clear-location/`

Очищает сохраненное местоположение пользователя.

**Ответ:**
```json
{
    "success": true,
    "message": "Location cleared successfully"
}
```

## Обновленный API поиска ситтеров

### Поиск ситтеров с учетом ролей

**GET** `/api/sitters/search/`

**Параметры:**
- `latitude`, `longitude` - координаты (опционально)
- `radius` - радиус поиска в км (по умолчанию 10)
- `service_type` - тип услуги (опционально)
- `price_min`, `price_max` - диапазон цен (опционально)
- `rating_min` - минимальный рейтинг (опционально)

**Логика работы по ролям:**

#### Для обычного пользователя:
1. Если переданы координаты - использует их
2. Если координаты не переданы - использует местоположение пользователя
3. Если местоположение не определено - требует включить геолокацию

#### Для ситтера:
1. Проверяет наличие адреса (обязательно)
2. Если адреса нет - возвращает ошибку с требованием заполнить адрес
3. Если адрес есть - использует его координаты для поиска

#### Для учреждения:
1. Проверяет наличие адреса (обязательно)
2. Если адреса нет - возвращает ошибку с требованием заполнить адрес
3. Если адрес есть - использует его координаты для поиска

**Ответ при успехе:**
```json
{
    "success": true,
    "sitters": [
        {
            "id": 1,
            "name": "Иванов Иван",
            "rating": 4.8,
            "hourly_rate": 500,
            "services": ["Выгул", "Присмотр"],
            "experience_years": 3,
            "bio": "Опытный ситтер",
            "distance_km": 2.5,
            "location": {
                "latitude": 55.7558,
                "longitude": 37.6176,
                "address": "Москва, ул. Примерная, 1"
            }
        }
    ],
    "search_params": {
        "latitude": 55.7558,
        "longitude": 37.6176,
        "radius_km": 10,
        "location_source": "user_location",
        "total_found": 1
    },
    "user_role_info": {
        "role": "regular_user",
        "address_required": false,
        "has_address": true
    }
}
```

**Ответ при отсутствии местоположения (обычный пользователь):**
```json
{
    "success": false,
    "error": "Location not available",
    "message": "Please enable device location or select area on map",
    "requires_location": true
}
```

**Ответ при отсутствии адреса (ситтер/учреждение):**
```json
{
    "success": false,
    "error": "Address required",
    "message": "Address is required for pet sitters to specify where services are provided",
    "role": "sitter",
    "requires_address": true
}
```

## Интеграция с фронтендом

### JavaScript для проверки требований к адресу

```javascript
// Проверка требований к адресу
async function checkAddressRequirement() {
    try {
        const response = await fetch('/api/geolocation/check-address-requirement/', {
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        if (data.success) {
            const requirement = data.address_requirement;
            
            if (requirement.address_required && requirement.missing_address) {
                // Показываем форму для заполнения адреса
                showAddressForm(requirement.role, requirement.message);
                return false;
            }
            
            return true;
        }
    } catch (error) {
        console.error('Error checking address requirement:', error);
    }
}

// Валидация местоположения для роли
async function validateLocationForRole(latitude, longitude) {
    try {
        const response = await fetch('/api/geolocation/validate-location-for-role/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ latitude, longitude })
        });
        
        const data = await response.json();
        if (data.success) {
            const validation = data.validation;
            
            if (!validation.valid) {
                // Показываем ошибку валидации
                showValidationError(validation.message, validation.error);
                return false;
            }
            
            return true;
        }
    } catch (error) {
        console.error('Error validating location:', error);
    }
}

// Обновленный поиск ситтеров
async function searchSitters() {
    // Сначала проверяем требования к адресу
    const addressOk = await checkAddressRequirement();
    if (!addressOk) {
        return;
    }
    
    // Получаем местоположение
    const location = await getDeviceLocation();
    if (!location) {
        showMapSelection();
        return;
    }
    
    // Выполняем поиск
    try {
        const response = await fetch(`/api/sitters/search/?latitude=${location.latitude}&longitude=${location.longitude}&radius=10`);
        const data = await response.json();
        
        if (data.success) {
            displaySitters(data.sitters);
        } else {
            handleSearchError(data);
        }
    } catch (error) {
        console.error('Error searching sitters:', error);
    }
}
```

## Преимущества новой системы

### 1. **Учет ролей пользователей**
- Разные требования для разных типов пользователей
- Автоматическая проверка обязательности адреса
- Соответствие бизнес-логике

### 2. **Удобство для пользователя**
- Автоматическое определение местоположения для обычных пользователей
- Четкие требования для ситтеров и учреждений
- Интерактивный выбор района на карте

### 3. **Точность**
- GPS координаты устройства более точны
- Обязательная валидация адресов для ситтеров и учреждений
- Актуальное местоположение

### 4. **Производительность**
- Кэширование местоположения
- Меньше запросов к API геокодирования
- Быстрый поиск без повторного определения местоположения

### 5. **Гибкость**
- Fallback на выбор района на карте
- Поддержка ручного ввода адреса
- Различные источники местоположения

## Миграция с старой системы

### Для фронтенда:
1. Добавить проверку требований к адресу перед поиском
2. Заменить прямые запросы к API поиска на новую логику
3. Добавить запрос геолокации устройства
4. Интегрировать интерактивную карту
5. Обработать случаи отказа в доступе к геолокации

### Для бэкенда:
1. Новая система полностью совместима со старой
2. Старые API продолжают работать
3. Постепенная миграция на новые endpoints
4. Автоматическая проверка ролей пользователей 