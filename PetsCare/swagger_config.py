"""
Конфигурация Swagger/OpenAPI для автоматической генерации документации.

Этот модуль содержит настройки для автоматической генерации
документации API на основе Django REST Framework.
"""

from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

# Создаем схему для Swagger
schema_view = get_schema_view(
    openapi.Info(
        title="PetCare API",
        default_version='v1',
        description="""
        # PetCare API Documentation
        
        Полный REST API для системы управления уходом за питомцами.
        
        ## Основные возможности:
        
        ### Пользователи и аутентификация
        - Регистрация и аутентификация пользователей
        - Управление профилями
        - Система ролей и инвайтов
        
        ### Питомцы
        - Управление питомцами и их документами
        - Медицинские записи
        - Система доступа к картам питомцев
        
        ### Учреждения и сотрудники
        - Управление учреждениями
        - Управление сотрудниками и расписаниями
        - Система услуг и цен
        
        ### Бронирования и платежи
        - Создание и управление бронированиями
        - Система платежей
        - Автоматическое планирование
        
        ### Уведомления и отчеты
        - Система уведомлений (email, push, in-app)
        - Отчеты по доходам, загруженности, задолженностям
        - Аналитика и статистика
        
        ### Безопасность и аудит
        - Система аудита всех действий
        - Логирование и мониторинг
        - Управление безопасностью
        
        ## Аутентификация
        
        API использует JWT токены для аутентификации. Для получения токена используйте endpoint `/api/login/`.
        
        ```bash
        curl -X POST https://api.petscare.com/api/login/ \\
             -H "Content-Type: application/json" \\
             -d '{"email": "user@example.com", "password": "password123"}'
        ```
        
        Добавьте полученный токен в заголовок `Authorization`:
        
        ```bash
        Authorization: Bearer <your_token>
        ```
        
        ## Коды ответов
        
        - `200` - Успешный запрос
        - `201` - Ресурс создан
        - `400` - Ошибка валидации
        - `401` - Не авторизован
        - `403` - Доступ запрещен
        - `404` - Ресурс не найден
        - `500` - Внутренняя ошибка сервера
        
        ## Ограничения
        
        - **Лимит запросов**: 1000 запросов в час для аутентифицированных пользователей
        - **Размер файлов**: до 10MB для изображений, до 50MB для документов
        - **Пагинация**: по умолчанию 20 элементов, максимум 100 на страницу
        
        ## Поддержка
        
        - **Email**: api-support@petscare.com
        - **Документация**: https://docs.petscare.com/api
        - **Статус API**: https://status.petscare.com
        """,
        terms_of_service="https://www.petscare.com/terms/",
        contact=openapi.Contact(
            email="api-support@petscare.com",
            name="PetCare API Support",
            url="https://docs.petscare.com/api"
        ),
        license=openapi.License(
            name="MIT License",
            url="https://opensource.org/licenses/MIT"
        ),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    patterns=[
        # Добавляем все URL паттерны для автоматического обнаружения
    ],
)

# Дополнительные настройки для Swagger
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'JWT токен в формате: Bearer <token>'
        }
    },
    'USE_SESSION_AUTH': False,
    'JSON_EDITOR': True,
    'SUPPORTED_SUBMIT_METHODS': [
        'get',
        'post',
        'put',
        'delete',
        'patch'
    ],
    'OPERATIONS_SORTER': 'alpha',
    'TAGS_SORTER': 'alpha',
    'DOC_EXPANSION': 'list',
    'DEEP_LINKING': True,
    'DISPLAY_OPERATION_ID': False,
    'DEFAULT_MODEL_RENDERING': 'example',
    'DEFAULT_INFO': 'PetCare API v1',
    'SCHEME': ['https', 'http'],
    'VALIDATOR_URL': None,
    'PERSIST_AUTH': True,
    'REFETCH_SCHEMA_WITH_AUTH': True,
    'REFETCH_SCHEMA_ON_LOGOUT': True,
    'OAUTH2_REDIRECT_URL': None,
    'OAUTH2_CONFIG': {
        'clientId': 'your-client-id',
        'clientSecret': 'your-client-secret',
        'realm': 'your-realm',
        'appName': 'PetCare API',
        'scopes': 'read write',
    },
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': False,
        'defaultModelsExpandDepth': 1,
        'defaultModelExpandDepth': 1,
        'defaultModelRendering': 'example',
        'displayRequestDuration': True,
        'docExpansion': 'list',
        'filter': True,
        'showExtensions': True,
        'showCommonExtensions': True,
        'syntaxHighlight.theme': 'monokai',
        'tryItOutEnabled': True,
    },
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
    'REDOC_FAVICON_HREF': 'SIDECAR',
    'SWAGGER_UI_OAUTH2_REDIRECT_URL': None,
    'SWAGGER_UI_OAUTH2_CONFIG': {
        'clientId': 'your-client-id',
        'clientSecret': 'your-client-secret',
        'realm': 'your-realm',
        'appName': 'PetCare API',
        'scopes': 'read write',
    },
}

# Настройки для Redoc
REDOC_SETTINGS = {
    'LAZY_RENDERING': True,
    'HIDE_HOSTNAME': False,
    'EXPAND_RESPONSES': '200,201',
    'PATH_IN_MIDDLE': False,
    'HIDE_LOADING': False,
    'NATIVE_SCROLLBARS': False,
    'REQUIRED_PROPS_FIRST': True,
    'NO_AUTO_AUTH': False,
    'SUPPRESS_WARNINGS': False,
    'GENERATE_CLIENT_SDK': False,
    'OAUTH2_REDIRECT_URL': None,
    'OAUTH2_CONFIG': {
        'clientId': 'your-client-id',
        'clientSecret': 'your-client-secret',
        'realm': 'your-realm',
        'appName': 'PetCare API',
        'scopes': 'read write',
    },
}

# Дополнительные теги для группировки API
API_TAGS = [
    {
        'name': 'auth',
        'description': 'Аутентификация и управление пользователями'
    },
    {
        'name': 'users',
        'description': 'Управление пользователями и ролями'
    },
    {
        'name': 'pets',
        'description': 'Управление питомцами и документами'
    },
    {
        'name': 'providers',
        'description': 'Управление учреждениями'
    },
    {
        'name': 'employees',
        'description': 'Управление сотрудниками'
    },
    {
        'name': 'bookings',
        'description': 'Бронирования и расписания'
    },
    {
        'name': 'payments',
        'description': 'Платежи и биллинг'
    },
    {
        'name': 'notifications',
        'description': 'Система уведомлений'
    },
    {
        'name': 'ratings',
        'description': 'Рейтинги и отзывы'
    },
    {
        'name': 'reports',
        'description': 'Отчеты и аналитика'
    },
    {
        'name': 'audit',
        'description': 'Аудит и логирование'
    },
    {
        'name': 'settings',
        'description': 'Системные настройки'
    },
    {
        'name': 'analytics',
        'description': 'Расширенная аналитика'
    },
    {
        'name': 'geolocation',
        'description': 'Геолокация и поиск'
    },
]

# Примеры запросов для документации
API_EXAMPLES = {
    'user_registration': {
        'summary': 'Регистрация нового пользователя',
        'value': {
            'email': 'newuser@example.com',
            'password': 'password123',
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'phone': '+79001234567'
        }
    },
    'pet_creation': {
        'summary': 'Создание нового питомца',
        'value': {
            'name': 'Бобик',
            'pet_type': 'dog',
            'breed': 'Labrador',
            'birth_date': '2020-01-01',
            'weight': 25.5,
            'description': 'Дружелюбный лабрадор'
        }
    },
    'booking_creation': {
        'summary': 'Создание бронирования',
        'value': {
            'pet_id': 1,
            'provider_id': 1,
            'service_id': 1,
            'employee_id': 1,
            'date': '2023-12-25',
            'time': '14:00:00',
            'notes': 'Особые пожелания'
        }
    },
    'rating_creation': {
        'summary': 'Создание отзыва',
        'value': {
            'object_type': 'provider',
            'object_id': 1,
            'rating': 5,
            'comment': 'Отличный сервис!'
        }
    }
}

# Настройки для автоматической генерации примеров
AUTO_GENERATE_EXAMPLES = True
EXAMPLE_FIELD_NAME = 'example'
EXAMPLE_FIELD_DESCRIPTION = 'Пример запроса'

# Настройки для валидации схемы
VALIDATE_SCHEMA = True
VALIDATION_ERRORS = True

# Настройки для кэширования документации
CACHE_TIMEOUT = 0  # Отключаем кэширование для разработки
CACHE_KEY_PREFIX = 'swagger_docs'

# Настройки для экспорта документации
EXPORT_FORMATS = ['json', 'yaml', 'html']
EXPORT_PATH = 'docs/export/'

# Настройки для версионирования
API_VERSIONS = ['v1']
DEFAULT_VERSION = 'v1'
VERSION_PARAM = 'version'
VERSION_HEADER = 'X-API-Version'

# Настройки для мониторинга API
ENABLE_API_MONITORING = True
MONITORING_ENDPOINTS = [
    '/api/health/',
    '/api/status/',
    '/api/metrics/'
]

# Настройки для ограничений API
RATE_LIMIT_ENABLED = True
RATE_LIMIT_DEFAULT = '1000/hour'
RATE_LIMIT_ADMIN = '5000/hour'
RATE_LIMIT_ANONYMOUS = '100/hour'

# Настройки для логирования API
API_LOGGING_ENABLED = True
LOG_REQUEST_BODY = True
LOG_RESPONSE_BODY = False
LOG_HEADERS = ['Authorization', 'Content-Type', 'User-Agent']
LOG_IP_ADDRESS = True
LOG_USER_ID = True

# Настройки для документации ошибок
ERROR_DOCUMENTATION = {
    '400': {
        'description': 'Ошибка валидации данных',
        'examples': {
            'validation_error': {
                'summary': 'Ошибка валидации',
                'value': {
                    'error': 'VALIDATION_ERROR',
                    'message': 'Данные не прошли валидацию',
                    'details': {
                        'email': ['Это поле обязательно'],
                        'password': ['Пароль должен содержать минимум 8 символов']
                    }
                }
            }
        }
    },
    '401': {
        'description': 'Не авторизован',
        'examples': {
            'unauthorized': {
                'summary': 'Токен отсутствует или недействителен',
                'value': {
                    'error': 'AUTHENTICATION_FAILED',
                    'message': 'Требуется аутентификация'
                }
            }
        }
    },
    '403': {
        'description': 'Доступ запрещен',
        'examples': {
            'permission_denied': {
                'summary': 'Недостаточно прав',
                'value': {
                    'error': 'PERMISSION_DENIED',
                    'message': 'У вас нет прав для выполнения этого действия'
                }
            }
        }
    },
    '404': {
        'description': 'Ресурс не найден',
        'examples': {
            'not_found': {
                'summary': 'Ресурс не найден',
                'value': {
                    'error': 'RESOURCE_NOT_FOUND',
                    'message': 'Запрашиваемый ресурс не найден'
                }
            }
        }
    },
    '429': {
        'description': 'Превышен лимит запросов',
        'examples': {
            'rate_limit': {
                'summary': 'Слишком много запросов',
                'value': {
                    'error': 'RATE_LIMIT_EXCEEDED',
                    'message': 'Превышен лимит запросов. Попробуйте позже.',
                    'retry_after': 3600
                }
            }
        }
    },
    '500': {
        'description': 'Внутренняя ошибка сервера',
        'examples': {
            'internal_error': {
                'summary': 'Внутренняя ошибка',
                'value': {
                    'error': 'INTERNAL_ERROR',
                    'message': 'Произошла внутренняя ошибка сервера'
                }
            }
        }
    }
} 