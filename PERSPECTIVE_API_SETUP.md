# 🎯 Настройка Google Perspective API для модерации отзывов

## 📋 Обзор

Google Perspective API - это специализированный сервис для анализа токсичности контента, который будет использоваться для автоматической модерации отзывов в системе PetCare.

## 🚀 Пошаговая инструкция по получению API ключа

### Шаг 1: Создание проекта в Google Cloud Console

1. **Перейдите на [Google Cloud Console](https://console.cloud.google.com/)**
2. **Войдите в свой Google аккаунт**
3. **Создайте новый проект** или выберите существующий:
   - Нажмите **"Создать проект"**
   - Введите название: `petcare-moderation`
   - Нажмите **"Создать"**

### Шаг 2: Включение Perspective API

1. **В левом меню выберите "APIs & Services" → "Library"**
2. **Найдите API одним из способов:**
   - Поиск: `perspective`
   - Поиск: `comment analyzer`
   - Поиск: `toxicity`
3. **Найдите "Comment Analyzer API"** (это и есть Perspective API)
4. **Нажмите на API**
5. **Нажмите "Enable"** (Включить)

### Шаг 3: Создание учетных данных

#### Вариант A: API Key (проще для тестирования)

1. **В меню слева выберите "APIs & Services" → "Credentials"**
2. **Нажмите "Create Credentials" → "API Key"**
3. **Скопируйте созданный ключ**
4. **Нажмите "Restrict Key" для безопасности:**
   - **Application restrictions**: HTTP referrers
   - **API restrictions**: Select APIs → Comment Analyzer API

#### Вариант B: Service Account (рекомендуется для продакшена)

1. **В меню слева выберите "APIs & Services" → "Credentials"**
2. **Нажмите "Create Credentials" → "Service Account"**
3. **Заполните форму:**
   - **Service account name**: `petcare-moderation`
   - **Description**: `Service account for review moderation`
4. **Нажмите "Create and Continue"**
5. **Выберите роль: "Project" → "Editor"**
6. **Нажмите "Continue" → "Done"**
7. **В списке Service Accounts найдите созданный**
8. **Нажмите на email аккаунта**
9. **Перейдите на вкладку "Keys"**
10. **Нажмите "Add Key" → "Create new key"**
11. **Выберите "JSON"**
12. **Нажмите "Create"** - файл скачается автоматически

### Шаг 4: Настройка в проекте

#### Для API Key:
```bash
# В файл .env добавьте:
GOOGLE_PERSPECTIVE_API_KEY=AIzaSyC...ваш_ключ_здесь
```

#### Для Service Account:
```bash
# Переместите скачанный файл в папку проекта
# Например: PetsCare/google-credentials/service-account.json

# В файл .env добавьте:
GOOGLE_SERVICE_ACCOUNT_FILE=google-credentials/service-account.json
```

## 🧪 Тестирование настройки

### Запуск тестового скрипта:
```bash
# Тест с API Key
python test_perspective_api.py

# Проверка доступности API
python check_api_availability.py
```

### Ожидаемый результат:
```
✅ API Key работает!
Результат: {'attributeScores': {'TOXICITY': {'summaryScore': {'value': 0.1}}}}
```

## 🔧 Настройка языков

### Поддерживаемые языки:
- ✅ **English** (en)
- ✅ **Russian** (ru)
- ✅ **German** (de)
- ✅ **Spanish** (es)
- ✅ **French** (fr)
- ✅ **Italian** (it)
- ✅ **Portuguese** (pt)
- ✅ **Chinese** (zh)
- ✅ **Japanese** (jp)
- ✅ **Korean** (ko)
- ✅ **Arabic** (ar)

### Добавление нового языка:
1. **Проверьте поддержку** в [документации Perspective API](https://developers.perspectiveapi.com/s/docs-supported-languages)
2. **Добавьте код языка** в `GOOGLE_PERSPECTIVE_LANGUAGES` в `settings.py`
3. **Протестируйте** с новым языком

## ⚠️ Важные моменты

### Безопасность:
- **Не публикуйте API ключи** в репозитории
- **Используйте .env файл** для хранения ключей
- **Ограничьте API ключ** только для Comment Analyzer API
- **Добавьте .env в .gitignore**

### Лимиты и квоты:
- **Бесплатный уровень**: 1000 запросов в день
- **Платные планы**: от $0.10 за 1000 запросов
- **Мониторинг**: в Google Cloud Console → APIs & Services → Dashboard

### Обработка ошибок:
- **API недоступен**: fallback на локальные правила
- **Превышение лимитов**: логирование и уведомления
- **Неверный ключ**: проверка конфигурации

## 🎯 Следующие шаги

1. **Получите API ключ** по инструкции выше
2. **Добавьте ключ в .env файл**
3. **Запустите тестовые скрипты**
4. **Проверьте работу модерации** в системе
5. **Настройте мониторинг** и логирование

## 📞 Поддержка

### Если API недоступен:
- **Проверьте регион** - API может быть недоступен в некоторых странах
- **Обратитесь в Google Support** для получения доступа
- **Используйте fallback модерацию** как временное решение

### Полезные ссылки:
- [Perspective API Documentation](https://developers.perspectiveapi.com/)
- [Google Cloud Console](https://console.cloud.google.com/)
- [API Explorer](https://developers.google.com/apis-explorer/#p/commentanalyzer/v1alpha1/) 