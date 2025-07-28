# 🎯 Настройка Gmail API для отправки email

## 📋 Обзор

Система PetCare теперь поддерживает отправку email через Gmail API с OAuth2 аутентификацией вместо устаревшего SMTP. Это обеспечивает более высокую безопасность, надежность и функциональность.

## 🚀 Преимущества Gmail API

### Безопасность
- ✅ **OAuth2 аутентификация** вместо паролей
- ✅ **Токены доступа** с автоматическим обновлением
- ✅ **Безопасная передача данных** через HTTPS

### Надежность
- ✅ **Меньше блокировок** от Google
- ✅ **Высокие квоты** отправки
- ✅ **Стабильная работа** в продакшене

### Функциональность
- ✅ **Поддержка HTML писем**
- ✅ **Вложения файлов**
- ✅ **Детальная аналитика** отправки
- ✅ **Fallback на SMTP** при ошибках

## 🔧 Пошаговая настройка

### Шаг 1: Создание проекта в Google Cloud Console

1. **Перейдите на [Google Cloud Console](https://console.cloud.google.com/)**
2. **Войдите в свой Google аккаунт**
3. **Создайте новый проект** или выберите существующий:
   - Нажмите **"Создать проект"**
   - Введите название: `petcare-email`
   - Нажмите **"Создать"**

### Шаг 2: Включение Gmail API

1. **В левом меню выберите "APIs & Services" → "Library"**
2. **Найдите "Gmail API"** в поиске
3. **Нажмите на Gmail API**
4. **Нажмите "Enable"** (Включить)

### Шаг 3: Создание OAuth 2.0 учетных данных

1. **В меню слева выберите "APIs & Services" → "Credentials"**
2. **Нажмите "Create Credentials" → "OAuth 2.0 Client IDs"**
3. **Выберите тип приложения: "Desktop application"**
4. **Введите название: `PetCare Email Client`**
5. **Нажмите "Create"**
6. **Скачайте JSON файл** с учетными данными

### Шаг 4: Настройка в проекте

1. **Переименуйте скачанный файл** в `credentials.json`
2. **Поместите файл** в корень проекта PetCare
3. **Добавьте в .gitignore**:
   ```
   credentials.json
   token.json
   ```

### Шаг 5: Настройка переменных окружения

**В файл `.env` добавьте:**
```bash
# Gmail API настройки
USE_GMAIL_API=True
GMAIL_API_FALLBACK_TO_SMTP=True
GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=token.json

# SMTP fallback настройки (для резервного копирования)
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@petcare.com
```

### Шаг 6: Тестирование настройки

**Запустите команду настройки:**
```bash
python manage.py setup_gmail_api --test
```

**Ожидаемый результат:**
```
✓ Gmail API connection test successful
```

## 🧪 Тестирование отправки email

### Тестовая команда
```bash
python manage.py shell
```

```python
from django.core.mail import send_mail

# Отправка тестового письма
result = send_mail(
    subject='Test Email from PetCare',
    message='This is a test email sent via Gmail API',
    from_email='noreply@petcare.com',
    recipient_list=['test@example.com'],
    fail_silently=False
)

print(f"Email sent: {result}")
```

### Проверка логов
```bash
tail -f logs/django.log | grep "Gmail API"
```

## ⚙️ Конфигурация

### Настройки в settings.py

```python
# Gmail API настройки
USE_GMAIL_API = True  # Использовать Gmail API
GMAIL_API_FALLBACK_TO_SMTP = True  # Fallback на SMTP
GMAIL_CREDENTIALS_FILE = 'credentials.json'  # Файл с учетными данными
GMAIL_TOKEN_FILE = 'token.json'  # Файл с токеном

# Email backend (автоматический выбор)
if USE_GMAIL_API:
    EMAIL_BACKEND = 'notifications.gmail_api_backend.GmailAPIBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
```

### Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `USE_GMAIL_API` | Использовать Gmail API | `True` |
| `GMAIL_API_FALLBACK_TO_SMTP` | Fallback на SMTP | `True` |
| `GMAIL_CREDENTIALS_FILE` | Файл с учетными данными | `credentials.json` |
| `GMAIL_TOKEN_FILE` | Файл с токеном | `token.json` |

## 🔄 Fallback механизм

Система автоматически переключается на SMTP в следующих случаях:

1. **Gmail API недоступен**
2. **Ошибки аутентификации**
3. **Превышение квот**
4. **Сетевые проблемы**

### Логирование fallback
```
INFO: Gmail API connection failed, attempting SMTP fallback
INFO: Email sent successfully via SMTP fallback
```

## 📊 Мониторинг и аналитика

### Логи Gmail API
```bash
# Просмотр логов отправки
grep "Gmail API" logs/django.log

# Просмотр ошибок
grep "Error.*Gmail API" logs/django.log
```

### Google Cloud Console
1. **Перейдите в [Google Cloud Console](https://console.cloud.google.com/)**
2. **Выберите ваш проект**
3. **APIs & Services → Dashboard**
4. **Просмотрите статистику использования Gmail API**

## 🚨 Устранение неполадок

### Проблема: "Gmail API service not available"
**Решение:**
1. Проверьте установку зависимостей: `pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib`
2. Проверьте наличие файла `credentials.json`
3. Запустите: `python manage.py setup_gmail_api --check-files`

### Проблема: "Invalid credentials"
**Решение:**
1. Удалите файл `token.json`
2. Перезапустите приложение
3. Пройдите OAuth2 авторизацию заново

### Проблема: "Quota exceeded"
**Решение:**
1. Проверьте квоты в Google Cloud Console
2. Включите fallback на SMTP
3. Рассмотрите платные планы Google

### Проблема: "Network error"
**Решение:**
1. Проверьте интернет-соединение
2. Проверьте файрвол
3. Используйте SMTP fallback

## 🔒 Безопасность

### Рекомендации
- ✅ **Не публикуйте** `credentials.json` и `token.json` в репозитории
- ✅ **Добавьте файлы** в `.gitignore`
- ✅ **Используйте переменные окружения** для конфиденциальных данных
- ✅ **Регулярно обновляйте** OAuth2 токены
- ✅ **Мониторьте** использование API

### Файлы для защиты
```
credentials.json  # OAuth2 учетные данные
token.json       # Токены доступа
.env             # Переменные окружения
```

## 📈 Производительность

### Квоты Gmail API
- **Бесплатный уровень**: 1,000,000 запросов в день
- **Платные планы**: от $0.10 за 1000 запросов
- **Лимит скорости**: 250 запросов в секунду

### Оптимизация
- ✅ **Кэширование** токенов
- ✅ **Batch отправка** писем
- ✅ **Асинхронная отправка** через Celery
- ✅ **Retry логика** при ошибках

## 🎯 Следующие шаги

1. **Настройте Gmail API** по инструкции выше
2. **Протестируйте отправку** email
3. **Настройте мониторинг** и логирование
4. **Обновите документацию** команды
5. **Проведите нагрузочное тестирование**

## 📞 Поддержка

### Полезные ссылки
- [Gmail API Documentation](https://developers.google.com/gmail/api/)
- [Google Cloud Console](https://console.cloud.google.com/)
- [OAuth 2.0 Guide](https://developers.google.com/identity/protocols/oauth2)

### Команды для диагностики
```bash
# Проверка файлов
python manage.py setup_gmail_api --check-files

# Тест подключения
python manage.py setup_gmail_api --test

# Создание шаблона
python manage.py setup_gmail_api --create-credentials-template
``` 