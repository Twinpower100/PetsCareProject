# Настройка базы данных для PetCare

## Создание роли и базы данных

### 1. Создание роли pet_admin

```sql
CREATE ROLE pet_admin WITH
    LOGIN
    SUPERUSER
    CREATEDB
    CREATEROLE
    INHERIT
    REPLICATION
    BYPASSRLS
    CONNECTION LIMIT -1
    PASSWORD 'your_secure_password_here';
```

### 2. Создание базы данных

```sql
CREATE DATABASE pet_project_db
    WITH
    OWNER = pet_admin
    ENCODING = 'UTF8'
    LOCALE_PROVIDER = 'libc'
    CONNECTION LIMIT = -1
    IS_TEMPLATE = False;
```

## Необходимые расширения PostgreSQL

### Обязательные расширения

```sql
-- Основные расширения для Django
CREATE EXTENSION IF NOT EXISTS plpgsql;  -- Процедурный язык (обычно уже установлен)

-- Геолокация и пространственные данные
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Поиск и индексы
CREATE EXTENSION IF NOT EXISTS unaccent;  -- Поиск без диакритических знаков
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- Быстрый поиск по тексту
CREATE EXTENSION IF NOT EXISTS btree_gin; -- Оптимизированные индексы

-- Уникальные идентификаторы
CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; -- Генерация UUID
```

### Проверка установленных расширений

```sql
SELECT extname FROM pg_extension ORDER BY extname;
```

Ожидаемый результат:
```
extname
--------
btree_gin
pg_trgm
plpgsql
postgis
postgis_topology
unaccent
uuid-ossp
```

## Настройка через pgAdmin

### Создание роли
1. Правый клик на "Login/Group Roles" → Create → Login/Group Role
2. General: Name = `pet_admin`
3. Definition: Password = `ваш_пароль`
4. Privileges: ✅ Can login, ✅ Superuser, ✅ Create databases, ✅ Create roles
5. Connection: Connection limit = `-1`

### Создание базы данных
1. Правый клик на "Databases" → Create → Database
2. General: Database = `pet_project_db`, Owner = `pet_admin`
3. Definition: Encoding = `UTF8`, Locale provider = `libc`
4. Connection: Connection limit = `-1`

### Установка расширений
1. Выберите базу `pet_project_db`
2. Откройте Query Tool (Alt+Shift+Q)
3. Выполните SQL команды для создания расширений

## Установка PostGIS (если не установлен)

### Через Stack Builder
1. Запустите Stack Builder
2. Выберите PostgreSQL 17
3. Найдите "PostGIS Bundle"
4. ✅ Create spatial database
5. ✅ Enable All GDAL Drivers

### Альтернативно
Скачайте с https://postgis.net/windows_downloads/

## Настройка Django

### settings.py
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'pet_project_db',
        'USER': 'pet_admin',
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

### requirements.txt
```
Django>=4.2
psycopg2-binary>=2.9
django-extensions>=3.2
```

## Команды для миграций

```bash
# Создание миграций
python manage.py makemigrations

# Применение миграций
python manage.py migrate

# Создание суперпользователя
python manage.py createsuperuser
```

## Полезные команды

### Проверка подключения к базе
```python
python manage.py dbshell
```

### Сброс миграций (осторожно!)
```bash
python manage.py migrate --fake-initial
```

### Создание резервной копии
```bash
pg_dump -U pet_admin -h localhost pet_project_db > backup.sql
```

### Восстановление из резервной копии
```bash
psql -U pet_admin -h localhost pet_project_db < backup.sql
```
