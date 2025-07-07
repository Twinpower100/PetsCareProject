# Настройка внешних API и ключей для MVP

## 1. Google Cloud Console
### 1.1 Google Maps API (ОБНОВЛЕНО)
1. Перейдите на [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте новый проект или выберите существующий
3. Включите следующие API:
   - Maps JavaScript API
   - Geocoding API
   - Places API
   - Geocoding API (для валидации адресов)
   - Places API (для автодополнения)
4. Создайте API ключ:
   - Перейдите в "Credentials"
   - Нажмите "Create Credentials" -> "API Key"
   - Ограничьте ключ по HTTP referrers и IP-адресам
   - Установите квоты для контроля расходов
5. Добавьте ключ в `.env`:
   ```
   GOOGLE_MAPS_API_KEY=ваш_ключ
   GOOGLE_MAPS_GEOCODING_API_KEY=ваш_ключ
   GOOGLE_MAPS_PLACES_API_KEY=ваш_ключ
   ```

### 1.2 Google OAuth 2.0 (Аутентификация)
1. В том же проекте Google Cloud:
   - Перейдите в "APIs & Services" -> "Credentials"
   - Нажмите "Create Credentials" -> "OAuth client ID"
   - Выберите тип приложения "Web application"
2. Настройте OAuth consent screen:
   - Добавьте название приложения
   - Укажите email поддержки
   - Добавьте домены приложения
3. Настройте авторизованные URI:
   - Добавьте URI перенаправления (например, `http://localhost:8000/accounts/google/login/callback/`)
   - Добавьте авторизованные JavaScript источники
4. Получите учетные данные:
   - Client ID
   - Client Secret
5. Добавьте ключи в `.env`:
   ```
   GOOGLE_OAUTH_CLIENT_ID=ваш_client_id
   GOOGLE_OAUTH_CLIENT_SECRET=ваш_client_secret
   ```

### 1.3 Gmail SMTP (Отправка писем)
1. Включите двухфакторную аутентификацию в вашем Google аккаунте
2. Создайте пароль приложения:
   - Перейдите в [Управление аккаунтом Google](https://myaccount.google.com/)
   - Безопасность -> Пароли приложений
   - Выберите "Другое" и создайте пароль
3. Добавьте учетные данные в `.env`:
   ```
   EMAIL_HOST_USER=ваш_email@gmail.com
   EMAIL_HOST_PASSWORD=ваш_пароль_приложения
   EMAIL_USE_TLS=True
   EMAIL_PORT=587
   EMAIL_HOST=smtp.gmail.com
   ```

## 2. Альтернативные сервисы геолокации (РЕЗЕРВНЫЕ)

### 2.1 OpenStreetMap Nominatim (Бесплатный)
1. Не требует регистрации и API ключей
2. Ограничения: 1 запрос в секунду
3. Добавьте в `.env`:
   ```
   USE_OPENSTREETMAP_FALLBACK=True
   ```

### 2.2 Яндекс.Карты API (Для России)
1. Перейдите на [Яндекс.Разработчики](https://developer.tech.yandex.ru/)
2. Создайте приложение
3. Получите API ключ
4. Добавьте в `.env`:
   ```
   YANDEX_MAPS_API_KEY=ваш_ключ
   USE_YANDEX_MAPS_FALLBACK=True
   ```

### 2.3 DaData API (Для России - высокое качество)
1. Зарегистрируйтесь на [DaData.ru](https://dadata.ru/)
2. Получите API ключ и Secret
3. Добавьте в `.env`:
   ```
   DADATA_API_KEY=ваш_ключ
   DADATA_SECRET_KEY=ваш_secret
   USE_DADATA_FALLBACK=True
   ```

### 2.4 HERE Geocoding API (Альтернатива Google)
1. Зарегистрируйтесь на [HERE Developer Portal](https://developer.here.com/)
2. Создайте проект и получите API ключи
3. Добавьте в `.env`:
   ```
   HERE_API_KEY=ваш_ключ
   HERE_APP_ID=ваш_app_id
   HERE_APP_CODE=ваш_app_code
   USE_HERE_FALLBACK=True
   ```

## 3. Настройка .env файла
1. Создайте файл `.env` в корне проекта
2. Добавьте все полученные ключи:
   ```
   # Основные Google Maps API
   GOOGLE_MAPS_API_KEY=ваш_ключ
   GOOGLE_MAPS_GEOCODING_API_KEY=ваш_ключ
   GOOGLE_MAPS_PLACES_API_KEY=ваш_ключ
   
   # Google OAuth
   GOOGLE_OAUTH_CLIENT_ID=ваш_client_id
   GOOGLE_OAUTH_CLIENT_SECRET=ваш_client_secret
   
   # Email
   EMAIL_HOST_USER=ваш_email@gmail.com
   EMAIL_HOST_PASSWORD=ваш_пароль_приложения
   EMAIL_USE_TLS=True
   EMAIL_PORT=587
   EMAIL_HOST=smtp.gmail.com
   
   # Резервные сервисы
   USE_OPENSTREETMAP_FALLBACK=True
   YANDEX_MAPS_API_KEY=ваш_ключ
   USE_YANDEX_MAPS_FALLBACK=True
   DADATA_API_KEY=ваш_ключ
   DADATA_SECRET_KEY=ваш_secret
   USE_DADATA_FALLBACK=True
   HERE_API_KEY=ваш_ключ
   HERE_APP_ID=ваш_app_id
   HERE_APP_CODE=ваш_app_code
   USE_HERE_FALLBACK=True
   
   # Настройки геолокации
   DEFAULT_GEOCODING_PROVIDER=google
   FALLBACK_GEOCODING_PROVIDERS=yandex,dadata,here,openstreetmap
   GEOCODING_CACHE_TTL=86400
   MAX_GEOCODING_REQUESTS_PER_DAY=2500
   ```
3. Убедитесь, что файл добавлен в `.gitignore`

## 4. Проверка настроек
После получения ключей выполните:
```bash
python manage.py check_keys
```
Это проверит доступность всех настроенных API.

## 5. Мониторинг и квоты
### 5.1 Google Maps API квоты
- Geocoding API: 2500 запросов в день (бесплатно)
- Places API: 1000 запросов в день (бесплатно)
- Настройте мониторинг в Google Cloud Console

### 5.2 Альтернативные сервисы
- OpenStreetMap: 1 запрос в секунду
- Яндекс.Карты: 25000 запросов в день
- DaData: 10000 запросов в день
- HERE: 250000 запросов в месяц

## 6. Безопасность
- Никогда не коммитьте `.env` файл в репозиторий
- Используйте разные ключи для разработки и продакшена
- Регулярно обновляйте ключи
- Ограничивайте доступ к ключам по IP и доменам где возможно
- Мониторьте использование API для предотвращения превышения лимитов
- Настройте уведомления о приближении к лимитам 