# Система уведомлений PetCare

Полная система уведомлений для платформы PetCare с поддержкой множественных каналов доставки, настраиваемых предпочтений и аналитики.

## Возможности

### Каналы доставки
- **Email** - HTML и текстовые шаблоны
- **Push-уведомления** - для мобильных приложений
- **In-app уведомления** - внутри приложения

### Типы уведомлений
- **Системные** - регистрация, сброс пароля, подтверждение email
- **Бронирования** - подтверждение, напоминания, изменения, отмены
- **Платежи** - подтверждение, неудачи, возвраты
- **Роли** - инвайты, подтверждения, истечения
- **Отзывы** - новые отзывы, ответы
- **Передержки** - статусы, обновления
- **Цены** - изменения цен услуг
- **Задолженности** - напоминания о платежах

### Настройки пользователей
- Включение/отключение по типам событий
- Выбор каналов доставки
- Время уведомлений
- Группировка уведомлений

## Архитектура

### Модели
- `Notification` - основная модель уведомлений
- `NotificationType` - типы уведомлений
- `NotificationTemplate` - шаблоны email
- `NotificationPreference` - настройки пользователей
- `Reminder` - напоминания

### Сервисы
- `NotificationService` - централизованный сервис
- `EmailService` - отправка email
- `PushService` - отправка push-уведомлений
- `InAppService` - in-app уведомления

### Задачи Celery
- `send_email_notification_task`
- `send_push_notification_task`
- `send_in_app_notification_task`
- `send_debt_reminder_task`

- `send_new_review_notification_task`
- `send_role_invite_expired_task`
- `send_pet_sitting_notification_task`
- `send_payment_failed_notification_task`
- `send_refund_notification_task`
- `send_system_maintenance_notification_task`

### Сигналы Django
- Создание/обновление бронирований
- Изменения статусов платежей
- Создание/подтверждение инвайтов ролей
- Изменения цен услуг
- Новые отзывы
- Изменения статусов передержек
- Создание задолженностей

## Установка и настройка

### 1. Зависимости
```bash
pip install celery redis django-celery-beat
```

### 2. Настройки Django
```python
# settings.py
INSTALLED_APPS = [
    # ...
    'notifications',
    'django_celery_beat',
]

# Email настройки
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'

# Celery настройки
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
```

### 3. Миграции
```bash
python manage.py makemigrations notifications
python manage.py migrate
```

### 4. Запуск Celery
```bash
# Worker
celery -A PetsCare worker -l info -Q notifications

# Beat (планировщик)
celery -A PetsCare beat -l info
```

## Использование

### Отправка уведомления
```python
from notifications.services import NotificationService

notification_service = NotificationService()

notification = notification_service.send_notification(
    user=user,
    notification_type='booking',
    title='Booking Confirmed',
    message='Your booking has been confirmed',
    channels=['email', 'push', 'in_app'],
    priority='medium',
    data={'booking_id': 123}
)
```

### Настройка предпочтений
```python
# Получение настроек
preferences = user.notification_preferences

# Обновление настроек
preferences.email_enabled = True
preferences.push_enabled = False
preferences.save()
```

### API endpoints
- `GET /api/notifications/` - список уведомлений
- `POST /api/notifications/{id}/read/` - отметить как прочитанное
- `POST /api/notifications/read-all/` - отметить все как прочитанные
- `DELETE /api/notifications/{id}/` - удалить уведомление
- `GET /api/notifications/stats/` - статистика
- `POST /api/notifications/preferences/` - обновить настройки
- `POST /api/notifications/test/` - тестовое уведомление

## Команды управления

### Отправка напоминаний о задолженности
```bash
python manage.py send_debt_reminders --min-amount 10.0 --days-overdue 7
```



### Системные уведомления
```bash
python manage.py send_system_maintenance_notifications --message "System maintenance scheduled" --user-type all
```

### Очистка старых уведомлений
```bash
python manage.py cleanup_old_notifications --days 30
```

### Тестирование email
```bash
python manage.py test_email_notifications --user-id 1
```

## Шаблоны email

### Доступные шаблоны
- `booking_confirmation.html/txt`
- `booking_reminder.html/txt`
- `booking_cancelled.html/txt`
- `payment_confirmed.html/txt`
- `payment_failed.html/txt`
- `role_invite.html/txt`
- `role_invite_accepted.html/txt`
- `role_invite_expired.html/txt`
- `email_verification.html/txt`
- `password_reset.html/txt`
- `pet_sitting.html/txt`

- `new_review.html/txt`

### Кастомизация шаблонов
```python
# Создание нового шаблона
template = NotificationTemplate.objects.create(
    name='custom_template',
    subject='Custom Subject',
    html_template='<h1>Custom HTML</h1>',
    text_template='Custom text'
)
```

## Аналитика и мониторинг

### Метрики
- Количество отправленных уведомлений
- Процент доставки
- Время отклика
- Предпочтения пользователей

### Логирование
```python
import logging
logger = logging.getLogger('notifications')

logger.info('Notification sent successfully')
logger.error('Failed to send notification')
```

## Безопасность

### Защита данных
- Шифрование конфиденциальной информации
- Валидация входных данных
- Ограничение частоты отправки

### Конфиденциальность
- Соблюдение GDPR
- Возможность отписки
- Минимальный сбор данных

## Производительность

### Оптимизации
- Асинхронная отправка через Celery
- Кэширование шаблонов
- Батчинг уведомлений
- Очистка старых данных

### Мониторинг
- Метрики производительности
- Алерты при сбоях
- Автоматическое восстановление

## Разработка

### Добавление нового типа уведомлений
1. Создать шаблоны email
2. Добавить задачу Celery
3. Настроить сигналы Django
4. Обновить API
5. Добавить тесты

### Тестирование
```bash
# Запуск тестов
python manage.py test notifications

# Тестирование email
python manage.py test_email_notifications
```

## Поддержка

### Логи
- Логи уведомлений: `logs/notifications.log`
- Логи Celery: `logs/celery.log`
- Логи ошибок: `logs/errors.log`

### Мониторинг
- Статус Celery worker
- Очереди задач
- Метрики доставки
- Ошибки отправки

### Контакты
- Email: support@petcare.com
- Документация: https://docs.petcare.com/notifications
- GitHub: https://github.com/petcare/notifications 