# Настройка VIES API для валидации VAT ID

## Обзор

VIES (VAT Information Exchange System) - это официальный API Европейской комиссии для проверки VAT ID компаний в странах ЕС.

**URL API:** `https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{country_code}/vat/{vat_number}`

**Документация:** https://ec.europa.eu/taxation_customs/vies/

**ВАЖНО:** Официальный REST API от Еврокомиссии **НЕ требует API ключа** и доступен бесплатно. Однако могут быть ограничения по rate limiting (количество запросов в минуту/час).

**Альтернатива:** Существует сторонний сервис `viesapi.eu`, который предоставляет доступ к VIES через REST API с ключами, но это **не** официальный API и требует регистрации и оплаты для продакшена.

## Установка зависимостей

### 1. Библиотека `requests`

✅ **Уже добавлена в `requirements.txt`** (версия 2.31.0)

Если нужно установить отдельно:
```bash
pip install requests==2.31.0
```

### 2. Библиотека `python-stdnum`

✅ **Добавлена в `requirements.txt`** (версия >= 1.19)

Используется для валидации формата VAT ID и IBAN согласно плану реализации.
Библиотека поддерживает валидацию стандартных номеров для всех стран ЕС.

Если нужно установить отдельно:
```bash
pip install python-stdnum>=1.19
```

**Примечание:** Если библиотека не установлена, система использует fallback на ручную валидацию через regex.

### Установка всех зависимостей

Или установить все зависимости:
```bash
pip install -r requirements.txt
```

### 2. Настройка кэша Django

VIES API использует Django cache framework для кэширования результатов проверки.

#### Для разработки (локальный кэш в памяти):

Добавьте в `settings.py`:

```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}
```

#### Для продакшена (Redis - рекомендуется):

1. Установите Redis:
   ```bash
   # Windows (через WSL или Docker)
   # Linux/Mac
   sudo apt-get install redis-server  # Ubuntu/Debian
   brew install redis  # Mac
   ```

2. Установите Python библиотеку:
   ```bash
   pip install django-redis
   ```

3. Добавьте в `requirements.txt`:
   ```
   django-redis==5.4.0
   ```

4. Настройте в `settings.py`:
   ```python
   CACHES = {
       'default': {
           'BACKEND': 'django_redis.cache.RedisCache',
           'LOCATION': 'redis://127.0.0.1:6379/1',
           'OPTIONS': {
               'CLIENT_CLASS': 'django_redis.client.DefaultClient',
           },
           'KEY_PREFIX': 'petcare',
           'TIMEOUT': 300,  # 5 минут по умолчанию
       }
   }
   ```

#### Альтернатива: Memcached

```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': '127.0.0.1:11211',
    }
}
```

## Проверка подключения

✅ **API протестирован и работает без ключа!**

### Тест через Python shell:

```python
python manage.py shell

from providers.vat_validation_service import validate_vat_id_vies

# Тестовый невалидный VAT ID для Германии
result = validate_vat_id_vies('DE', '123456789')
print(result)
# Результат:
# {
#     'is_valid': False,
#     'company_name': None,
#     'address': None,
#     'error': 'INVALID',
#     'cached': False,
#     'request_date': '2026-01-24T20:24:00.018Z'
# }
```

**Примечание:** Для тестирования с валидным VAT ID используйте реальный номер компании из ЕС. API работает корректно и возвращает ответы без необходимости в ключе.

### Тест через админку:

1. Откройте Django admin
2. Перейдите в "Providers" → выберите провайдера с VAT ID
3. Нажмите кнопку "Check VAT ID now"
4. Проверьте результат в поле "VAT Verification Status"

## Настройки кэширования

В `providers/vat_validation_service.py` настроены следующие параметры:

- **Валидные VAT ID:** кэшируются на 24 часа (86400 секунд)
- **Невалидные VAT ID:** кэшируются на 1 час (3600 секунд)
- **Таймаут запроса:** 10 секунд

Эти настройки можно изменить в файле `vat_validation_service.py`:

```python
CACHE_VALID_DURATION = 86400  # 24 часа
CACHE_INVALID_DURATION = 3600  # 1 час
```

## Тестовые VAT ID

Для тестирования можно использовать:

- **Валидный (тестовый):** `DE123456789` - для Германии
- **Невалидный (тестовый):** `DE000000000` - для Германии

**Важно:** Тестовые VAT ID могут работать не всегда. Для реальной проверки используйте реальные VAT ID компаний.

## Обработка ошибок

Система обрабатывает следующие ошибки:

1. **Таймаут API** - если VIES API не отвечает в течение 10 секунд
2. **Недоступность API** - если VIES API недоступен
3. **Невалидный VAT ID** - если VAT ID не найден в реестре
4. **Ошибки сети** - если нет подключения к интернету

Во всех случаях регистрация провайдера **не блокируется** (fallback), но статус проверки устанавливается в `failed`.

## Мониторинг

Логи проверки VAT ID записываются в Django logger с именем `providers.vat_validation_service`.

Для просмотра логов:

```python
import logging
logger = logging.getLogger('providers.vat_validation_service')
logger.setLevel(logging.INFO)
```

## Ограничения VIES API

1. **Rate limiting:** VIES API может ограничивать количество запросов
2. **Доступность:** API может быть временно недоступен
3. **Поддержка стран:** Только страны ЕС

Поэтому в системе реализован fallback механизм - если API недоступен, регистрация разрешена, но статус проверки будет `failed`.
