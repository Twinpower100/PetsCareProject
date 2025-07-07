# PetCare API Documentation

## Обзор

PetCare API предоставляет полный REST API для управления системой ухода за питомцами. API поддерживает все основные функции системы, включая управление пользователями, питомцами, учреждениями, бронированиями, платежами и уведомлениями.

## Базовый URL

```
https://api.petscare.com/api/v1/
```

## Аутентификация

API использует JWT (JSON Web Tokens) для аутентификации.

### Получение токена

```http
POST /api/login/
Content-Type: application/json

{
    "email": "user@example.com",
    "password": "password123"
}
```

**Ответ:**
```json
{
    "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "user": {
        "id": 1,
        "email": "user@example.com",
        "first_name": "Иван",
        "last_name": "Иванов",
        "role": "client"
    }
}
```

### Обновление токена

```http
POST /api/token/refresh/
Content-Type: application/json

{
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

### Использование токена

Добавьте заголовок `Authorization` к запросам:

```http
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

## Коды ответов

- `200` - Успешный запрос
- `201` - Ресурс создан
- `400` - Ошибка валидации
- `401` - Не авторизован
- `403` - Доступ запрещен
- `404` - Ресурс не найден
- `500` - Внутренняя ошибка сервера

## 1. Пользователи и аутентификация

### Регистрация пользователя

```http
POST /api/register/
Content-Type: application/json

{
    "email": "newuser@example.com",
    "password": "password123",
    "first_name": "Иван",
    "last_name": "Иванов",
    "phone": "+79001234567"
}
```

### Профиль пользователя

```http
GET /api/profile/
Authorization: Bearer <token>
```

**Ответ:**
```json
{
    "id": 1,
    "email": "user@example.com",
    "first_name": "Иван",
    "last_name": "Иванов",
    "phone": "+79001234567",
    "role": "client",
    "is_active": true,
    "date_joined": "2023-01-01T00:00:00Z"
}
```

### Обновление профиля

```http
PUT /api/profile/
Authorization: Bearer <token>
Content-Type: application/json

{
    "first_name": "Иван",
    "last_name": "Петров",
    "phone": "+79001234568"
}
```

## 2. Управление ролями

### Назначение роли

```http
POST /api/assign-role/
Authorization: Bearer <token>
Content-Type: application/json

{
    "user_id": 2,
    "role": "employee",
    "reason": "Назначение на должность ветеринара"
}
```

### Массовое назначение ролей

```http
POST /api/users/bulk-role-assignment/
Authorization: Bearer <token>
Content-Type: application/json

{
    "assignments": [
        {
            "user_id": 2,
            "role": "employee",
            "reason": "Назначение сотрудника"
        },
        {
            "user_id": 3,
            "role": "provider_admin",
            "reason": "Назначение администратора учреждения"
        }
    ]
}
```

### Инвайты на роли

```http
POST /api/role-invites/
Authorization: Bearer <token>
Content-Type: application/json

{
    "email": "invite@example.com",
    "role": "employee",
    "provider_id": 1,
    "expires_in_days": 7
}
```

### Принятие инвайта

```http
POST /api/role-invites/accept/
Authorization: Bearer <token>
Content-Type: application/json

{
    "invite_id": 1,
    "token": "abc123..."
}
```

## 3. Питомцы

### Список питомцев

```http
GET /api/pets/
Authorization: Bearer <token>
```

**Параметры:**
- `page` - номер страницы
- `page_size` - размер страницы
- `search` - поиск по имени
- `pet_type` - фильтр по типу питомца

### Создание питомца

```http
POST /api/pets/
Authorization: Bearer <token>
Content-Type: application/json

{
    "name": "Бобик",
    "pet_type": "dog",
    "breed": "Labrador",
    "birth_date": "2020-01-01",
    "weight": 25.5,
    "description": "Дружелюбный лабрадор"
}
```

### Детали питомца

```http
GET /api/pets/{id}/
Authorization: Bearer <token>
```

### Обновление питомца

```http
PUT /api/pets/{id}/
Authorization: Bearer <token>
Content-Type: application/json

{
    "name": "Бобик",
    "weight": 26.0,
    "description": "Обновленное описание"
}
```

### Удаление питомца

```http
DELETE /api/pets/{id}/
Authorization: Bearer <token>
```

### Документы питомца

#### Загрузка документа

```http
POST /api/pets/{id}/documents/
Authorization: Bearer <token>
Content-Type: multipart/form-data

{
    "file": <file>,
    "name": "Ветеринарный паспорт",
    "description": "Паспорт с прививками"
}
```

#### Список документов

```http
GET /api/pets/{id}/documents/
Authorization: Bearer <token>
```

#### Скачивание документа

```http
GET /api/pets/documents/{document_id}/download/
Authorization: Bearer <token>
```

## 4. Учреждения

### Список учреждений

```http
GET /api/providers/
Authorization: Bearer <token>
```

**Параметры:**
- `search` - поиск по названию
- `service_type` - фильтр по типу услуг
- `rating_min` - минимальный рейтинг
- `latitude`, `longitude`, `radius` - поиск по геолокации

### Создание учреждения

```http
POST /api/providers/
Authorization: Bearer <token>
Content-Type: application/json

{
    "name": "Ветеринарная клиника",
    "description": "Современная клиника для животных",
    "address": "ул. Ленина, 1",
    "phone_number": "+79001234567",
    "email": "clinic@example.com",
    "latitude": 55.7558,
    "longitude": 37.6176
}
```

### Детали учреждения

```http
GET /api/providers/{id}/
Authorization: Bearer <token>
```

### Обновление учреждения

```http
PUT /api/providers/{id}/
Authorization: Bearer <token>
Content-Type: application/json

{
    "name": "Обновленное название",
    "description": "Обновленное описание"
}
```

### Поиск учреждений по расстоянию

```http
GET /api/search/distance/
Authorization: Bearer <token>
```

**Параметры:**
- `latitude` - широта
- `longitude` - долгота
- `radius` - радиус поиска в км
- `service_type` - тип услуги

## 5. Сотрудники

### Список сотрудников

```http
GET /api/employees/
Authorization: Bearer <token>
```

### Создание сотрудника

```http
POST /api/employees/
Authorization: Bearer <token>
Content-Type: application/json

{
    "user_id": 2,
    "position": "Ветеринар",
    "bio": "Опытный ветеринар с 10-летним стажем",
    "specializations": [1, 2],
    "start_date": "2023-01-01",
    "is_manager": false
}
```

### Связь сотрудника с учреждением

```http
POST /api/employees/{id}/update/
Authorization: Bearer <token>
Content-Type: application/json

{
    "provider_id": 1,
    "start_date": "2023-01-01",
    "is_manager": false
}
```

## 6. Бронирования

### Список бронирований

```http
GET /api/bookings/
Authorization: Bearer <token>
```

**Параметры:**
- `status` - статус бронирования
- `provider_id` - ID учреждения
- `date_from`, `date_to` - период
- `page`, `page_size` - пагинация

### Создание бронирования

```http
POST /api/bookings/
Authorization: Bearer <token>
Content-Type: application/json

{
    "pet_id": 1,
    "provider_id": 1,
    "service_id": 1,
    "employee_id": 1,
    "date": "2023-12-25",
    "time": "14:00:00",
    "notes": "Особые пожелания"
}
```

### Детали бронирования

```http
GET /api/bookings/{id}/
Authorization: Bearer <token>
```

### Отмена бронирования

```http
POST /api/bookings/{id}/cancel/
Authorization: Bearer <token>
Content-Type: application/json

{
    "reason": "Изменение планов"
}
```

### Автоматическое бронирование

```http
POST /api/booking/auto-book-employee/
Authorization: Bearer <token>
Content-Type: application/json

{
    "pet_id": 1,
    "provider_id": 1,
    "service_id": 1,
    "date": "2023-12-25",
    "time": "14:00:00"
}
```

## 7. Платежи

### Список платежей

```http
GET /api/payments/
Authorization: Bearer <token>
```

### Создание платежа

```http
POST /api/payments/
Authorization: Bearer <token>
Content-Type: application/json

{
    "booking_id": 1,
    "amount": 1000.00,
    "payment_method": "card"
}
```

### Статус платежа

```http
GET /api/payments/{id}/status/
Authorization: Bearer <token>
```

## 8. Уведомления

### Список уведомлений

```http
GET /api/notifications/
Authorization: Bearer <token>
```

### Отметка как прочитанное

```http
POST /api/notifications/{id}/mark-as-read/
Authorization: Bearer <token>
```

### Отметить все как прочитанные

```http
POST /api/notifications/mark-all-as-read/
Authorization: Bearer <token>
```

### Настройки уведомлений

```http
GET /api/preferences/all/
Authorization: Bearer <token>
```

### Обновление настроек

```http
PUT /api/preferences/{id}/
Authorization: Bearer <token>
Content-Type: application/json

{
    "email_enabled": true,
    "push_enabled": false,
    "in_app_enabled": true
}
```

## 9. Рейтинги и отзывы

### Создание отзыва

```http
POST /api/ratings/
Authorization: Bearer <token>
Content-Type: application/json

{
    "object_type": "provider",
    "object_id": 1,
    "rating": 5,
    "comment": "Отличный сервис!"
}
```

### Список отзывов

```http
GET /api/ratings/
Authorization: Bearer <token>
```

**Параметры:**
- `object_type` - тип объекта (provider, employee, sitter)
- `object_id` - ID объекта
- `rating_min`, `rating_max` - диапазон рейтинга

### Создание жалобы

```http
POST /api/complaints/
Authorization: Bearer <token>
Content-Type: application/json

{
    "object_type": "provider",
    "object_id": 1,
    "complaint_type": "service_quality",
    "description": "Описание проблемы"
}
```

## 10. Отчеты

### Отчет по доходам

```http
GET /api/income/
Authorization: Bearer <token>
```

**Параметры:**
- `date_from`, `date_to` - период
- `provider_id` - ID учреждения
- `format` - формат (json, excel)

### Отчет по загруженности

```http
GET /api/workload/
Authorization: Bearer <token>
```

### Отчет по задолженностям

```http
GET /api/debt/
Authorization: Bearer <token>
```

### Отчет по активности

```http
GET /api/activity/
Authorization: Bearer <token>
```

## 11. Аудит

### Логи аудита

```http
GET /api/audit/logs/
Authorization: Bearer <token>
```

**Параметры:**
- `user_id` - ID пользователя
- `action` - действие
- `resource_type` - тип ресурса
- `created_after`, `created_before` - период

### Экспорт логов

```http
POST /api/audit/logs/export/
Authorization: Bearer <token>
Content-Type: application/json

{
    "format": "csv",
    "filters": {
        "created_after": "2023-01-01",
        "action": "user_login"
    }
}
```

### Активность пользователя

```http
GET /api/audit/user-activity/{user_id}/
Authorization: Bearer <token>
```

### Статистика аудита

```http
GET /api/audit/statistics/
Authorization: Bearer <token>
```

## 12. Системные настройки

### Системные настройки

```http
GET /api/settings/system/
Authorization: Bearer <token>
```

### Обновление настроек

```http
PUT /api/settings/system/
Authorization: Bearer <token>
Content-Type: application/json

{
    "site_name": "PetCare",
    "maintenance_mode": false,
    "registration_enabled": true
}
```

### Настройки функций

```http
GET /api/settings/features/
Authorization: Bearer <token>
```

### Включение/выключение функции

```http
POST /api/settings/features/
Authorization: Bearer <token>
Content-Type: application/json

{
    "feature": "notifications",
    "enabled": true,
    "reason": "Включение уведомлений"
}
```

### Настройки безопасности

```http
GET /api/settings/security/
Authorization: Bearer <token>
```

### Здоровье системы

```http
GET /api/settings/health/
Authorization: Bearer <token>
```

## 13. Аналитика

### Рост пользователей

```http
GET /api/analytics/user-growth/
Authorization: Bearer <token>
```

**Параметры:**
- `days` - количество дней для анализа

### Производительность учреждений

```http
GET /api/analytics/provider-performance/
Authorization: Bearer <token>
```

### Тренды выручки

```http
GET /api/analytics/revenue-trends/
Authorization: Bearer <token>
```

### Поведенческая аналитика

```http
GET /api/analytics/behavioral/
Authorization: Bearer <token>
```

## 14. Геолокация

### Поиск по адресу

```http
GET /api/geolocation/search/
Authorization: Bearer <token>
```

**Параметры:**
- `query` - поисковый запрос
- `country` - код страны

### Обратное геокодирование

```http
GET /api/geolocation/reverse/
Authorization: Bearer <token>
```

**Параметры:**
- `latitude` - широта
- `longitude` - долгота

### Валидация адреса

```http
POST /api/geolocation/validate/
Authorization: Bearer <token>
Content-Type: application/json

{
    "address": "ул. Ленина, 1, Москва"
}
```

## Обработка ошибок

### Формат ошибки

```json
{
    "error": "Описание ошибки",
    "code": "ERROR_CODE",
    "details": {
        "field": "Дополнительная информация"
    }
}
```

### Коды ошибок

- `VALIDATION_ERROR` - Ошибка валидации данных
- `PERMISSION_DENIED` - Недостаточно прав
- `RESOURCE_NOT_FOUND` - Ресурс не найден
- `AUTHENTICATION_FAILED` - Ошибка аутентификации
- `RATE_LIMIT_EXCEEDED` - Превышен лимит запросов
- `INTERNAL_ERROR` - Внутренняя ошибка сервера

## Ограничения

### Лимиты запросов

- **Аутентифицированные пользователи**: 1000 запросов в час
- **Неаутентифицированные пользователи**: 100 запросов в час
- **Администраторы**: 5000 запросов в час

### Размеры файлов

- **Изображения**: до 10MB
- **Документы**: до 50MB
- **Видео**: до 100MB

### Пагинация

По умолчанию API возвращает 20 элементов на страницу. Максимальный размер страницы - 100 элементов.

## Поддержка

Для получения поддержки по API:

- **Email**: api-support@petscare.com
- **Документация**: https://docs.petscare.com/api
- **Статус API**: https://status.petscare.com

## Версионирование

API использует семантическое версионирование. Текущая версия: v1.

Изменения в API будут анонсированы заранее, и старые версии будут поддерживаться в течение 12 месяцев после выпуска новой версии. 