"""
Конфигурация URL для проекта PetsCare.

Этот модуль содержит корневые URL паттерны для:
1. Административного интерфейса
2. API эндпоинтов
3. Статических файлов
4. Документации API
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions
from custom_admin import custom_admin_site

# Настройки Swagger
schema_view = get_schema_view(
    openapi.Info(
        title="PetsCare API",
        default_version='v1',
        description="API для сервиса PetsCare",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@petscare.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    # Административный интерфейс
    path('admin/', custom_admin_site.urls),  # Используем кастомный админ-сайт
    
    # Документация API
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
    # API эндпоинты
    path('api/', include('users.urls')),
    path('api/', include('pets.urls')),
    path('api/', include('providers.urls')),
    path('api/', include('billing.urls')),
    path('api/', include('booking.urls')),
    path('api/', include('catalog.urls')),
    path('api/', include('sitters.urls')),
    path('api/', include('geolocation.urls')),
    path('api/', include('notifications.urls')),
    path('api/', include('access.urls')),
    path('api/', include('reports.urls')),  # Добавляем отчеты
    path('api/', include('ratings.urls')),  # Добавляем рейтинги
    path('api/', include('audit.urls')),    # Добавляем аудит
    path('api/', include('settings.urls')), # Добавляем системные настройки
    path('api/', include('analytics.urls')), # Добавляем аналитику
    
    # Аутентификация
    path('accounts/', include('allauth.urls')),
]

# Статические и медиа файлы в режиме разработки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 