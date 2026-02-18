# Настройка Google OAuth для входа в админку

## Проблема: redirect_uri_mismatch

Ошибка `redirect_uri_mismatch` возникает, когда redirect URI в запросе не совпадает с настройками в Google Cloud Console.

## Решение

### 1. Откройте Google Cloud Console
- Перейдите на https://console.cloud.google.com/
- Выберите ваш проект

### 2. Перейдите в настройки OAuth 2.0
- APIs & Services → Credentials
- Найдите ваш OAuth 2.0 Client ID
- Нажмите "Edit"

### 3. Добавьте Authorized redirect URIs

Для **разработки (localhost)** добавьте:
```
http://localhost:8000/accounts/google/login/callback/
http://127.0.0.1:8000/accounts/google/login/callback/
```

Для **production** добавьте:
```
https://yourdomain.com/accounts/google/login/callback/
```

### 4. Сохраните изменения

### 5. Проверьте настройки в Django

Убедитесь, что в `.env` файле указаны:
```
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
```

### 6. Проверьте SocialApp в админке Django

1. Откройте http://127.0.0.1:8000/admin/socialaccount/socialapp/
2. Убедитесь, что SocialApp для Google существует
3. Проверьте, что `Client id` и `Secret key` заполнены правильно
4. Убедитесь, что SocialApp связан с правильным сайтом (Sites)

## Важно

- Redirect URI должен **точно совпадать** (включая слэш в конце)
- После изменения настроек в Google Cloud Console может потребоваться несколько минут для применения
- Для localhost используйте `http://`, для production - `https://`

