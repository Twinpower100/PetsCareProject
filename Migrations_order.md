# Порядок миграций проекта PetCare

## Обзор

Данный документ описывает правильный порядок создания миграций для всех приложений проекта PetCare на основе анализа зависимостей между моделями.

## Принципы определения порядка

1. **Базовые модели** - создаются первыми (User, базовые настройки)
2. **Модели без внешних зависимостей** - создаются после базовых
3. **Модели с зависимостями** - создаются после моделей, от которых зависят
4. **Связанные модели** - создаются в логическом порядке

## Порядок миграций по приложениям

### 1. users (Пользователи)
**Приоритет: ВЫСОКИЙ (1-й)**

**Модели:**
- `User` (расширенная модель пользователя)
- `UserProfile` 
- `UserRole`
- `UserGroup`

**Внешние зависимости:** Отсутствуют (не ссылается на модели других приложений)
**Зависимые приложения:** Все остальные приложения используют модели User

---

### 2. settings (Системные настройки)
**Приоритет: ВЫСОКИЙ (2-й)**

**Модели:**
- `SecuritySettings`
- `RatingDecaySettings` 
- `BlockingScheduleSettings`

**Внешние зависимости:** `User` (для полей updated_by)
**Зависимые приложения:** security, billing

---

### 3. geolocation (Геолокация)
**Приоритет: ВЫСОКИЙ (3-й)**

**Модели:**
- `Address`
- `AddressValidation`
- `AddressCache`
- `LocationHistory`
- `SearchRadius`
- `UserLocation`

**Внешние зависимости:** `User` (для Location, SearchRadius, LocationHistory, UserLocation)
**Зависимые приложения:** pets, providers, sitters, booking

---

### 4. catalog (Каталог услуг)
**Приоритет: ВЫСОКИЙ (4-й)**

**Модели:**
- `ServiceCategory`
- `Service`
- `ServicePrice`
- `ServiceSchedule`

**Внешние зависимости:** Отсутствуют (не ссылается на модели других приложений)
**Зависимые приложения:** providers, booking, scheduling

---

### 5. providers (Учреждения)
**Приоритет: СРЕДНИЙ (5-й)**

**Модели:**
- `Provider`
- `Employee`
- `ProviderService`
- `ProviderSchedule`
- `ProviderRating`
- `ProviderReview`

**Внешние зависимости:** 
- `User` (для Employee)
- `Address` (для Provider)
- `Service` (для ProviderService)

**Зависимые приложения:** booking, billing, scheduling, ratings

---

### 6. pets (Питомцы)
**Приоритет: СРЕДНИЙ (6-й)**

**Модели:**
- `Pet`
- `PetType`
- `PetBreed`
- `PetDocument`
- `DocumentType`
- `PetFilter`
- `PetIncapacity`
- `PetIncapacityHistory`

**Внешние зависимости:**
- `User` (для Pet owner)
- `Address` (для Pet location)

**Зависимые приложения:** booking, access, sitters

---

### 7. sitters (Передержка)
**Приоритет: СРЕДНИЙ (7-й)**

**Модели:**
- `SitterProfile`
- `PetSittingAd`
- `PetSittingResponse`
- `PetSitting`
- `Review`
- `Conversation`
- `Message`

**Внешние зависимости:**
- `User` (для SitterProfile, PetSittingAd)
- `Pet` (для PetSittingAd, PetSitting)
- `Address` (для PetSittingAd)

**Зависимые приложения:** ratings

---

### 8. access (Доступ)
**Приоритет: СРЕДНИЙ (8-й)**

**Модели:**
- `PetAccess`
- `AccessLog`
- `Access`

**Внешние зависимости:**
- `User` (для всех моделей)
- `Pet` (для PetAccess, Access)

**Зависимые приложения:** Отсутствуют

---

### 9. booking (Бронирование)
**Приоритет: СРЕДНИЙ (9-й)**

**Модели:**
- `Booking`
- `BookingService`
- `BookingStatus`
- `BookingPayment`
- `BookingReview`

**Внешние зависимости:**
- `User` (для Booking)
- `Pet` (для Booking)
- `Provider` (для Booking)
- `Service` (для BookingService)
- `Address` (для Booking location)

**Зависимые приложения:** billing, ratings

---

### 10. scheduling (Планирование)
**Приоритет: СРЕДНИЙ (10-й)**

**Модели:**
- `Workplace`
- `WorkplaceAllowedServices`
- `ServicePriority`
- `Vacation`
- `SickLeave`
- `DayOff`
- `EmployeeSchedule`
- `StaffingRequirement`

**Внешние зависимости:**
- `Provider` (для Workplace, ServicePriority, StaffingRequirement)
- `Employee` (для Vacation, SickLeave, DayOff, EmployeeSchedule)
- `Service` (для WorkplaceAllowedServices, ServicePriority, StaffingRequirement)

**Зависимые приложения:** Отсутствуют

---

### 11. notifications (Уведомления)
**Приоритет: НИЗКИЙ (11-й)**

**Модели:**
- `Notification`
- `NotificationTemplate`
- `NotificationRule`
- `ReminderSettings`
- `NotificationLog`

**Внешние зависимости:**
- `User` (для всех моделей)

**Зависимые приложения:** Отсутствуют

---

### 12. billing (Биллинг)
**Приоритет: НИЗКИЙ (12-й)**

**Модели:**
- `Payment`
- `PaymentMethod`
- `Invoice`
- `InvoiceItem`
- `ProviderBlocking`
- `BlockingRule`
- `BlockingTemplate`
- `BlockingSystemSettings`
- `BlockingNotification`

**Внешние зависимости:**
- `User` (для Payment, ProviderBlocking)
- `Provider` (для ProviderBlocking)
- `Booking` (для Payment, Invoice)

**Зависимые приложения:** Отсутствуют

---

### 13. ratings (Рейтинги)
**Приоритет: НИЗКИЙ (13-й)**

**Модели:**
- `Rating`
- `Review`
- `RatingCategory`
- `RatingWeight`

**Внешние зависимости:**
- `User` (для Rating, Review)
- `Provider` (для Rating, Review)
- `SitterProfile` (для Rating, Review)
- `Booking` (для Rating, Review)

**Зависимые приложения:** Отсутствуют

---

### 14. audit (Аудит)
**Приоритет: НИЗКИЙ (14-й)**

**Модели:**
- `AuditLog`
- `ModelChange`
- `UserAction`

**Внешние зависимости:**
- `User` (для всех моделей)

**Зависимые приложения:** Отсутствуют

---

### 15. security (Безопасность)
**Приоритет: НИЗКИЙ (15-й)**

**Модели:**
- `SecurityThreat`
- `IPBlacklist`
- `ThreatPattern`
- `SecurityPolicy`
- `PolicyViolation`
- `SessionPolicy`
- `AccessPolicy`
- `DataClassificationPolicy`

**Внешние зависимости:**
- `User` (для SecurityThreat, PolicyViolation)

**Зависимые приложения:** Отсутствуют

---

### 16. user_analytics (Аналитика пользователей)
**Приоритет: НИЗКИЙ (16-й)**

**Модели:**
- `UserGrowth`
- `UserActivity`
- `UserConversion`
- `UserMetrics`

**Внешние зависимости:**
- `User` (для UserActivity, UserConversion)

**Зависимые приложения:** Отсутствуют

---

### 17. reports (Отчеты)
**Приоритет: НИЗКИЙ (17-й)**

**Модели:**
- `Report`
- `ReportTemplate`
- `ReportSchedule`

**Внешние зависимости:**
- `User` (для Report)

**Зависимые приложения:** Отсутствуют

---

## Команды для создания миграций

### Создание миграций в правильном порядке:

```bash
# 1. Базовые приложения
python manage.py makemigrations users
python manage.py makemigrations settings
python manage.py makemigrations geolocation
python manage.py makemigrations catalog

# 2. Основные бизнес-модели
python manage.py makemigrations providers
python manage.py makemigrations pets
python manage.py makemigrations sitters
python manage.py makemigrations access

# 3. Функциональные модули
python manage.py makemigrations booking
python manage.py makemigrations scheduling
python manage.py makemigrations notifications
python manage.py makemigrations billing

# 4. Дополнительные модули
python manage.py makemigrations ratings
python manage.py makemigrations audit
python manage.py makemigrations security
python manage.py makemigrations user_analytics
python manage.py makemigrations reports
```

### Применение миграций:

```bash
# Применить все миграции
python manage.py migrate

# Или по приложениям в том же порядке
python manage.py migrate users
python manage.py migrate settings
python manage.py migrate geolocation
python manage.py migrate catalog
python manage.py migrate providers
python manage.py migrate pets
python manage.py migrate sitters
python manage.py migrate access
python manage.py migrate booking
python manage.py migrate scheduling
python manage.py migrate notifications
python manage.py migrate billing
python manage.py migrate ratings
python manage.py migrate audit
python manage.py migrate security
python manage.py migrate user_analytics
python manage.py migrate reports
```

## Важные замечания

1. **Порядок критичен** - нарушение порядка может привести к ошибкам внешних ключей
2. **Проверка зависимостей** - перед созданием миграций убедитесь, что все зависимости созданы
3. **Тестирование** - после каждой группы миграций рекомендуется тестировать приложение
4. **Резервные копии** - всегда создавайте резервные копии базы данных перед миграциями

## Схема зависимостей

```
users (базовое)
├── settings
├── geolocation
├── catalog
├── providers
│   ├── booking
│   ├── scheduling
│   └── billing
├── pets
│   ├── access
│   ├── sitters
│   └── booking
├── notifications
├── ratings
├── audit
├── security
├── user_analytics
└── reports
```

## Заключение

Данный порядок миграций обеспечивает корректное создание всех таблиц базы данных без нарушения целостности внешних ключей. Следование этому порядку гарантирует успешное развертывание проекта.
