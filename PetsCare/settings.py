"""
Django settings for PetsCare project.

Этот файл содержит все настройки конфигурации для проекта PetsCare.
Настройки разделены на несколько секций:
1. Базовые настройки проекта
2. Настройки безопасности
3. Настройки приложений
4. Настройки базы данных
5. Настройки аутентификации
6. Настройки интернационализации
7. Настройки статических файлов
8. Настройки медиафайлов
9. Настройки email
10. Настройки push-уведомлений
11. Настройки валют и платежей
"""

from pathlib import Path
from decouple import config, Csv
from django.utils.translation import gettext_lazy as _
import os

# Базовые пути проекта
BASE_DIR = Path(__file__).resolve().parent.parent

# Настройки безопасности
SECRET_KEY = config('SECRET_KEY')
GOOGLE_MAPS_KEY = config('GOOGLE_MAPS_API_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

# Currency settings
DEFAULT_CURRENCY = 'EUR'  # Base currency for all calculations
AVAILABLE_CURRENCIES = ['USD', 'EUR', 'RUB']  # List of supported currencies

# Список установленных приложений
INSTALLED_APPS = [
    'modeltranslation',
    'django.contrib.admin',  # Нужен для LogEntry
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    
    # Third party apps
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'drf_yasg',
    'phonenumber_field',
    'push_notifications',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    
    # Local apps
    'custom_admin',  # Кастомный админ
    'users.apps.UsersConfig',
    'pets.apps.PetsConfig',
    'providers.apps.ProvidersConfig',
    'catalog.apps.CatalogConfig',
    'booking.apps.BookingConfig',
    'sitters.apps.SittersConfig',
    'billing.apps.BillingConfig',
    'geolocation.apps.GeolocationConfig',
    'notifications.apps.NotificationsConfig',
    'access.apps.AccessConfig',
    'reports',
    'scheduling.apps.SchedulingConfig',
    'ratings.apps.RatingsConfig',
    'audit.apps.AuditConfig',
]

# Middleware для обработки запросов
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'billing.middleware.ProviderBlockingMiddleware',  # Middleware для блокировки заблокированных учреждений
    'audit.services.AuditMiddleware',  # Middleware для логирования HTTP запросов
]

# Настройки URL и шаблонов
ROOT_URLCONF = 'urls'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
            BASE_DIR / 'providers' / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.media',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Настройки базы данных PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT'),
    }
}

# Валидаторы паролей
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Настройки интернационализации
LANGUAGES = [
    ('en', _('English')),
    ('ru', _('Russian')),
    ('me', _('Montenegrian')),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Настройки статических файлов
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Настройки медиафайлов
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Настройки пользовательской модели
AUTH_USER_MODEL = 'users.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Настройки аутентификации и авторизации
SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Настройки социальной аутентификации через Google
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': config('GOOGLE_CLIENT_ID'),
            'secret': config('GOOGLE_CLIENT_SECRET'),
            'key': ''
        },
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        }
    }
}

# Настройки перенаправления после аутентификации
LOGIN_REDIRECT_URL = 'users:profile'
ACCOUNT_LOGOUT_REDIRECT_URL = 'users:login'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_UNIQUE_EMAIL = True

# Google Maps API settings
GOOGLE_MAPS_API_KEY = config('GOOGLE_MAPS_API_KEY')

# Настройки валидации адресов
ADDRESS_VALIDATION_SETTINGS = {
    'CACHE_DURATION_DAYS': 30,  # Длительность кэша в днях
    'API_TIMEOUT_SECONDS': 10,  # Таймаут API запросов
    'MAX_RETRIES': 3,  # Максимальное количество попыток
    'RETRY_DELAY_SECONDS': 1,  # Задержка между попытками
    'MIN_CONFIDENCE_SCORE': 0.8,  # Минимальный уровень уверенности
    'DEFAULT_LANGUAGE': 'ru',  # Язык по умолчанию для API
    'ENABLE_CACHING': True,  # Включить кэширование
    'CLEANUP_EXPIRED_CACHE_DAYS': 7,  # Очистка истекшего кэша каждые N дней
}

# Настройки email (Gmail SMTP для разработки и тестирования)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'  # Gmail SMTP сервер
EMAIL_PORT = 587  # Порт для TLS
EMAIL_USE_TLS = True  # Использовать TLS шифрование
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='your-email@gmail.com')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='your-app-password')  # Пароль приложения Gmail
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@petcare.com')
EMAIL_USE_SSL = False  # Не использовать SSL (используем TLS)
EMAIL_TIMEOUT = 30  # Таймаут в секундах

# Настройки push-уведомлений
PUSH_NOTIFICATIONS_SETTINGS = {
    "FCM_API_KEY": config('FCM_API_KEY'),
    "FCM_ERROR_TIMEOUT": 3600,
    "WP_PRIVATE_KEY": config('WP_PRIVATE_KEY', default=''),
    "WP_CLAIMS": {
        "sub": "mailto:your-email@example.com"
    },
    "WP_ERROR_TIMEOUT": 3600,
}

# Настройки уведомлений
NOTIFICATION_SETTINGS = {
    'DEFAULT_PRIORITY': 'medium',
    'MAX_RETRIES': 3,
    'RETRY_DELAY': 300,  # seconds
    'EMAIL_TEMPLATE_DIR': BASE_DIR / 'notifications' / 'templates' / 'email',
    'PUSH_ENABLED': True,
    'PUSH_TEMPLATE_DIR': BASE_DIR / 'notifications' / 'templates' / 'push',
}

# Настройки Celery
CELERY_BROKER_URL = config('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Настройки Celery Beat для периодических задач
CELERY_BEAT_SCHEDULE = {
    'check-provider-blocking': {
        'task': 'billing.tasks.run_blocking_check',
        'schedule': 3600.0,  # Каждый час
    },
    'update-currency-rates': {
        'task': 'billing.tasks.update_currency_rates',
        'schedule': 86400.0,  # Раз в день
    },
    # Задачи уведомлений
    'process-scheduled-notifications': {
        'task': 'notifications.tasks.process_scheduled_notifications_task',
        'schedule': 60.0,  # Каждую минуту
    },
    'process-reminders': {
        'task': 'notifications.tasks.process_reminders_task',
        'schedule': 3600.0,  # Каждый час
    },
    'cleanup-old-notifications': {
        'task': 'notifications.tasks.cleanup_old_notifications_task',
        'schedule': 86400.0,  # Раз в день
    },
}

# Настройки блокировки учреждений
BLOCKING_SETTINGS = {
    'CHECK_INTERVAL_HOURS': 1,  # Интервал проверки в часах
    'DEFAULT_DEBT_THRESHOLD': 1000.00,  # Порог задолженности по умолчанию
    'DEFAULT_OVERDUE_THRESHOLD_1': 7,   # Порог 1 по умолчанию (дни)
    'DEFAULT_OVERDUE_THRESHOLD_2': 14,  # Порог 2 по умолчанию (дни)
    'DEFAULT_OVERDUE_THRESHOLD_3': 30,  # Порог 3 по умолчанию (дни)
    'NOTIFICATION_RETRY_ATTEMPTS': 3,   # Количество попыток отправки уведомлений
    'NOTIFICATION_RETRY_DELAY': 300,    # Задержка между попытками (секунды)
}

# Настройки REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),
    'DEFAULT_PARSER_CLASSES': (
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ),
}

# Настройки JWT
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
}

# Настройки CORS
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', cast=Csv(), default='')
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB
FILE_UPLOAD_PERMISSIONS = 0o644
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755

# Настройки логирования
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
} 