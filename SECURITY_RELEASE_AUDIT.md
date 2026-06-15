# PetCare Security Release Audit

Дата аудита: 2026-06-15

Контекст: окружение формально тестовое, фактически pre-release. Таблица фиксирует действия для backend, public web, provider admin, Docker/local/server deployment. Пользовательские security-сообщения и UI-тексты должны сохранять i18n для 4 языков: English, Russian, German, Montenegrin (`en`, `ru`, `de`, `me/cnr`).

| # | Что сделать | Когда сделать | Сделано |
|---:|---|---|---|
| 1 | Снять с Git-индекса tracked production env-файлы фронтов и `keys_found.txt`; оставить реальные значения только локально/в секретах CI/CD/на сервере. | Сейчас | True |
| 2 | Добавить `.env.production` в `.gitignore` public web и provider admin. | Сейчас | True |
| 3 | Добавить safe `.env.example` для public web; provider admin template проверить на placeholder-значения. | Сейчас | True |
| 4 | Исключить `.env.production` из Docker build context фронтов; передавать публичные build-time значения через build args/env. | Сейчас | True |
| 5 | Убрать hardcoded Google OAuth Client ID fallback и логирование `VITE_GOOGLE_CLIENT_ID` из public web. | Сейчас | True |
| 6 | Убрать hardcoded Google OAuth Client ID fallback из provider admin. | Сейчас | True |
| 7 | Перевести Django `DEBUG` default в безопасное значение `False`; включать локальный DEBUG только явно через env. | Сейчас | True |
| 8 | Сделать secure cookie flags env-driven с production-safe default: `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_SECURE`, `SameSite=Lax`, `HttpOnly=True`. | Сейчас | True |
| 9 | Включить базовые Django security settings: `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY`, HSTS defaults для non-DEBUG, `REFERRER_POLICY`. | Сейчас | True |
| 10 | Отключить `/docs/`, `/swagger/`, `/redoc/` вне DEBUG по умолчанию; включать только явным `ENABLE_API_DOCS=True`. | Сейчас | True |
| 11 | В Swagger вне DEBUG оставить только read-only submit methods, чтобы интерактивные write-запросы не были доступны случайно. | Сейчас | True |
| 12 | Убрать hardcoded default `POSTGRES_PASSWORD=123qwerty987` из `docker-compose.yml`; требовать `DB_PASSWORD` из env. | Сейчас | True |
| 13 | Добавить security headers в Caddy: HSTS, `nosniff`, `DENY` frame, `strict-origin-when-cross-origin`, ограниченный `Permissions-Policy`. | Сейчас | True |
| 14 | Добавить Caddy-level 404 для `/docs*`, `/swagger*`, `/redoc*`, чтобы proxy не отдавал frontend fallback вместо отключенной API-документации. | Сейчас | True |
| 15 | Исправить `pack_deploy.ps1`: не паковать `.env*`, `Credentials.md`, `token.json`, `keys_found.txt`, deploy artifacts; включать актуальный `Caddyfile`. | Сейчас | True |
| 16 | Добавить краткие требования по cyber security во все найденные агентские правила: backend `.cursorrules`, public web `.cursorrules`, provider admin `.cursorrules`, admin compliance md. | Сейчас | True |
| 17 | Ротировать все секреты, которые когда-либо лежали в tracked `.env.production`, `keys_found.txt`, локальных deploy-копиях или передавались агентам: `SECRET_KEY`, DB password, Gmail/OAuth tokens, Google/API keys. | До релиза | False |
| 18 | Ограничить публичные Google OAuth/Maps keys в Google Cloud по доменам pre-release/prod, bundle/package where applicable и API scopes. | До релиза | False |
| 19 | Удалить или изолировать `deploy_tmp`, локальные `deploy*.tar`, `*.backup`, `Credentials.md`, `token.json` из рабочих/deploy директорий; хранить их вне репозитория и вне Docker context. | До релиза | False |
| 20 | Проверить историю Git на утечки секретов (`git log`, secret scanner) и при необходимости очистить историю/BFG + ротировать ключи. | До релиза | False |
| 21 | Провести ручной review всех `AllowAny` endpoint: login/register/password reset, public catalog/legal, invite acceptance, system settings; подтвердить минимальность данных и rate limiting. | До релиза | False |
| 22 | Добавить throttling/rate limiting для login, registration, password reset, invite acceptance, verification endpoints и публичного geolocation/search. | До релиза | False |
| 23 | Перевести refresh token из `localStorage` в более защищенную схему (HttpOnly Secure cookie или BFF/session) либо формально принять риск для MVP. | При релизе | False |
| 24 | Проверить production env на сервере: `DEBUG=False`, строгие `ALLOWED_HOSTS`, только нужные `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS`, `ENABLE_API_DOCS=False`, HTTPS scheme. | Перед выкладкой на сервер | False |
| 25 | Запустить `python manage.py check --deploy` в production-like env и устранить оставшиеся warnings, которые применимы к текущей архитектуре за Caddy. | Перед релизом | False |
| 26 | Проверить, что локальная версия, локальный Docker и сервер используют один commit/tag backend, public web и provider admin. | Перед выкладкой | False |
| 27 | Зафиксировать процедуру секретов: `.env.example` без реальных значений, локальные `.env*` не трекаются, серверные секреты обновляются через защищенный канал. | Перед релизом | False |
| 28 | Добавить автоматическую secret-scan проверку в CI/pre-commit для трех репозиториев. | После текущего hardening, до релиза | True |
| 29 | Проверить HTTP response headers на local Docker и сервере (`curl -I`): HSTS, nosniff, frame deny, referrer policy, permissions policy. | После деплоя | True |
| 30 | Проверить, что API docs возвращают 404 на production/pre-release при `ENABLE_API_DOCS=False`. | После деплоя | True |
