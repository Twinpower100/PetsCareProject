"""
Минимальные настройки для диагностики
"""
from pathlib import Path
from decouple import config

# Базовые пути проекта
BASE_DIR = Path(__file__).resolve().parent.parent

# Настройки безопасности
SECRET_KEY = 'test-secret-key'
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Кастомная модель пользователя
AUTH_USER_MODEL = 'users.User'

# Настройка для django_admin_log с кастомной моделью пользователя
ADMIN_LOG_USER_FIELD = 'user_id'

# Список установленных приложений
INSTALLED_APPS = [
    'modeltranslation',  # Должно быть ПЕРВЫМ для правильной работы с переводами
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # Необходимо для allauth
    'django.contrib.gis',  # PostGIS support
    
    # Внешние приложения
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'phonenumber_field',
    'django_countries',  # Работа со странами (ISO 3166-1 alpha-2)
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'drf_yasg',
    'push_notifications',
    'django_ckeditor_5',  # WYSIWYG редактор для юридических документов
    
    # Локальные приложения
    'users',
    'pets',
    'providers',
    'booking',
    'notifications',
    'geolocation',
    'catalog',
    'billing',
    'legal',  # Юридические документы (оферты, политики)
    'ratings',
    'reports',
    'analytics',
    'audit',  # исправлено - ленивая инициализация
    'access',
    'sitters',
    'services',
    'scheduling',
    'security',  # исправлено - ленивая инициализация
    'user_analytics',
    'custom_admin',
]

# Middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'legal.middleware.LegalAPILoggingMiddleware',  # Включено - фильтр убирает длинные сообщения
]

# URL конфигурация
ROOT_URLCONF = 'urls'

# Настройки базы данных
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT'),
    }
}

# Настройки GDAL для OSGeo4W
import os
# Пути к библиотекам GDAL (можно изменить на C:\OSGeo4W если установлен туда)
OSGEO4W_ROOT = os.environ.get('OSGEO4W_ROOT', r'C:\Users\andre\AppData\Local\Programs\OSGeo4W')
if not os.path.exists(OSGEO4W_ROOT):
    # Fallback на стандартный путь OSGeo4W
    OSGEO4W_ROOT = r'C:\OSGeo4W'

GDAL_LIBRARY_PATH = os.path.join(OSGEO4W_ROOT, 'bin', 'gdal312.dll')
GEOS_LIBRARY_PATH = os.path.join(OSGEO4W_ROOT, 'bin', 'geos_c.dll')
PROJ_LIB = os.path.join(OSGEO4W_ROOT, 'share', 'proj')
GDAL_DATA = os.path.join(OSGEO4W_ROOT, 'share', 'gdal')

# Настройки времени
USE_TZ = True
USE_I18N = True

# Статические файлы
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Templates
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'PetsCare' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Поле по умолчанию
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}

# JWT настройки
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
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

# CORS настройки
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# CSRF настройки
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
CSRF_COOKIE_SECURE = False  # Для разработки (в продакшене должно быть True)
CSRF_COOKIE_HTTPONLY = True  # Защита от XSS атак
SESSION_COOKIE_SECURE = False  # Для разработки (в продакшене должно быть True)
SESSION_COOKIE_HTTPONLY = True
CSRF_USE_SESSIONS = False

# Настройки аутентификации
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'users.backends.EmailBackend',  # Кастомный бэкенд для входа по email
    'allauth.account.auth_backends.AuthenticationBackend',  # Для allauth
]

# Настройки для allauth
# SITE_ID указывает на основной Site для админки (localhost:8000)
SITE_ID = 2  # ID=2 соответствует localhost:8000 (PetCare Admin)

# Кастомные адаптеры для allauth
SOCIALACCOUNT_ADAPTER = 'users.adapters.CustomSocialAccountAdapter'
ACCOUNT_ADAPTER = 'users.adapters.CustomAccountAdapter'

# Настройки allauth для аккаунтов
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_VERIFICATION = 'none'  # Не требуем верификацию email для социальных аккаунтов
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_SIGNUP_EMAIL_ENTER_TWICE = False

# Настройки перенаправления после аутентификации
LOGIN_REDIRECT_URL = '/admin/'  # Для админки
ACCOUNT_LOGOUT_REDIRECT_URL = '/admin/login/'

# Настройки социальной аутентификации через Google
# Используем SocialApp из базы данных (стандартный подход django-allauth)
# SocialApp настраиваются через Django админку:
# - "PetsCare Frontend" для веб-клиента (React)
# - "PetsCare Admin" для Django админки
# SOCIALACCOUNT_PROVIDERS удален - используем только SocialApp из БД

# Настройки для социальных аккаунтов
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'  # Не требуем верификацию email для социальных аккаунтов
# SOCIALACCOUNT_AUTO_SIGNUP управляется через адаптер (разное поведение для админки и фронта)
SOCIALACCOUNT_AUTO_SIGNUP = True  # По умолчанию разрешено, но адаптер контролирует это для админки
SOCIALACCOUNT_QUERY_EMAIL = True  # Запрашивать email у провайдера

# Google OAuth настройки
# Теперь используются SocialApp из БД (стандартный подход django-allauth)
# Настройка через Django админку: http://127.0.0.1:8000/admin/socialaccount/socialapp/

# Google Maps API
GOOGLE_MAPS_API_KEY = config('GOOGLE_MAPS_API_KEY', default='')

# Настройки локализации
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_L10N = True

# Поддерживаемые языки
# ВАЖНО: Коды языков должны совпадать с suffix-полями (name_me, description_me и т.д.)
LANGUAGES = [
    ('en', 'English'),
    ('ru', 'Russian'),
    ('me', 'Montenegrin'),
    ('de', 'German'),
]

# Настройки modeltranslation
# Указываем языки для modeltranslation (должны совпадать с LANGUAGES выше)
# Эти языки должны совпадать с кодами в LANGUAGES выше
MODELTRANSLATION_LANGUAGES = ('en', 'ru', 'me', 'de')
MODELTRANSLATION_DEFAULT_LANGUAGE = 'en'

# Пути к файлам переводов
LOCALE_PATHS = [
    BASE_DIR / 'PetsCare' / 'locale',
]

# Настройки почты (Gmail API с OAuth2 для продакшена, SMTP для fallback)
USE_GMAIL_API = config('USE_GMAIL_API', default=False, cast=bool)  # Использовать Gmail API
GMAIL_API_FALLBACK_TO_SMTP = config('GMAIL_API_FALLBACK_TO_SMTP', default=True, cast=bool)  # Fallback на SMTP

# Gmail API настройки (OAuth2 credentials из переменных окружения)
GMAIL_CLIENT_ID = config('GMAIL_CLIENT_ID', default='')  # Client ID для Gmail API OAuth2
GMAIL_CLIENT_SECRET = config('GMAIL_CLIENT_SECRET', default='')  # Client Secret для Gmail API OAuth2
GMAIL_TOKEN_FILE = config('GMAIL_TOKEN_FILE', default=str(BASE_DIR / 'token.json'))  # Файл с токеном доступа

# Email backend (автоматический выбор между Gmail API и SMTP)
if USE_GMAIL_API:
    EMAIL_BACKEND = 'notifications.gmail_api_backend.GmailAPIBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

# SMTP настройки (для fallback или основного использования)
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='')
EMAIL_USE_SSL = False  # Не использовать SSL (используем TLS)
EMAIL_TIMEOUT = 30  # Таймаут в секундах

# Frontend URL for password reset links
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:3000')

# Celery настройки
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Логирование
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'encoding': 'utf-8',  # Указываем UTF-8 для файла логов
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        # Логирование для drf_yasg (для диагностики Swagger)
        'drf_yasg': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',  # DEBUG для диагностики проблем со схемой
            'propagate': False,
        },
        # Логирование для legal API
        'legal': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'legal.middleware': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Убираем шумные HTTP логи - только ошибки
        'django.server': {
            'handlers': ['file', 'console'],
            'level': 'ERROR',  # Только ERROR и выше (убираем WARNING о 401 и других нормальных ошибках)
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file', 'console'],  # Временно в консоль для диагностики
            'level': 'ERROR',  # Только ERROR для диагностики
            'propagate': False,
        },
        'django': {
            'handlers': ['file', 'console'],  # Временно в консоль для диагностики
            'level': 'ERROR',  # Только ошибки
            'propagate': False,
        },
        # Логи приложений - оставляем INFO для отладки
        'users': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
        'billing': {
            'handlers': ['file', 'console'],
            'level': 'INFO',  # INFO и выше (включая предупреждения)
            'propagate': False,
        },
    },
    # Root logger - для всех остальных ошибок
    'root': {
        'handlers': ['file', 'console'],
        'level': 'ERROR',  # Критические ошибки будут выводиться
    },
}

# =============================================================================
# CKEditor 5 Configuration
# =============================================================================
# Конфигурация WYSIWYG редактора для юридических документов

# Путь для загрузки файлов через CKEditor
CKEDITOR_5_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
CKEDITOR_5_UPLOAD_PATH = "ckeditor5/uploads/"

# Кастомные конфигурации редактора
CKEDITOR_5_CONFIGS = {
    'default': {
        'toolbar': [
            'heading', '|',
            'bold', 'italic', 'underline', 'strikethrough', '|',
            'bulletedList', 'numberedList', '|',
            'outdent', 'indent', '|',
            'alignment', '|',
            'link', 'blockQuote', 'insertTable', '|',
            'undo', 'redo',
        ],
        'heading': {
            'options': [
                {'model': 'paragraph', 'title': 'Paragraph', 'class': 'ck-heading_paragraph'},
                {'model': 'heading1', 'view': 'h1', 'title': 'Heading 1', 'class': 'ck-heading_heading1'},
                {'model': 'heading2', 'view': 'h2', 'title': 'Heading 2', 'class': 'ck-heading_heading2'},
                {'model': 'heading3', 'view': 'h3', 'title': 'Heading 3', 'class': 'ck-heading_heading3'},
            ]
        },
        'table': {
            'contentToolbar': ['tableColumn', 'tableRow', 'mergeTableCells']
        },
        'list': {
            'properties': {
                'styles': True,
                'startIndex': True,
                'reversed': True
            }
        },
    },
    # Расширенная конфигурация для юридических документов
    'legal': {
        'toolbar': [
            'heading', '|',
            'bold', 'italic', 'underline', 'strikethrough', '|',
            'subscript', 'superscript', '|',
            'bulletedList', 'numberedList', '|',
            'outdent', 'indent', '|',
            'alignment', '|',
            'link', 'blockQuote', 'insertTable', 'horizontalLine', '|',
            'specialCharacters', '|',
            'undo', 'redo', '|',
            'sourceEditing',
        ],
        'heading': {
            'options': [
                {'model': 'paragraph', 'title': 'Paragraph', 'class': 'ck-heading_paragraph'},
                {'model': 'heading1', 'view': 'h1', 'title': 'Heading 1', 'class': 'ck-heading_heading1'},
                {'model': 'heading2', 'view': 'h2', 'title': 'Heading 2', 'class': 'ck-heading_heading2'},
                {'model': 'heading3', 'view': 'h3', 'title': 'Heading 3', 'class': 'ck-heading_heading3'},
                {'model': 'heading4', 'view': 'h4', 'title': 'Heading 4', 'class': 'ck-heading_heading4'},
            ]
        },
        'table': {
            'contentToolbar': ['tableColumn', 'tableRow', 'mergeTableCells', 'tableProperties', 'tableCellProperties']
        },
        'list': {
            'properties': {
                'styles': True,
                'startIndex': True,
                'reversed': True
            }
        },
    },
}

# Настройки Swagger/OpenAPI (drf-yasg)
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'JWT authorization header using the Bearer scheme. Example: "Authorization: Bearer {token}"'
        }
    },
    'USE_SESSION_AUTH': False,
    'JSON_EDITOR': True,
    'SUPPORTED_SUBMIT_METHODS': ['get', 'post', 'put', 'delete', 'patch'],
    'OPERATIONS_SORTER': 'alpha',
    'TAGS_SORTER': 'alpha',
    'DOC_EXPANSION': 'none',
    'DEEP_LINKING': True,
    'SHOW_EXTENSIONS': True,
    'DEFAULT_MODEL_RENDERING': 'example',
    'VALIDATOR_URL': None,
}
