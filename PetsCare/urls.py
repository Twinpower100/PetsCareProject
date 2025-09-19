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
from django.shortcuts import render
from django.utils.translation import gettext as _
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions
from custom_admin import custom_admin_site
from api_root import api_root

def api_docs_view(request):
    """Простая HTML документация API"""
    from django.http import HttpResponse
    
    # Получаем переведенные строки
    auth_title = _('Authentication')
    auth_desc = _('Most endpoints require JWT token in Authorization header: Bearer <token>')
    user_reg = _('User registration')
    user_login = _('User login')
    pets_title = _('Pets')
    pets_list = _('Get user pets list')
    add_pet = _('Add new pet')
    providers_title = _('Service Providers')
    providers_list = _('Get service providers list')
    bookings_title = _('Bookings')
    bookings_list = _('Get bookings list')
    notifications_title = _('Notifications')
    notifications_list = _('Get notifications list')
    billing_title = _('Billing')
    payments_list = _('Get payments list')
    ratings_title = _('Ratings')
    ratings_list = _('Get ratings list')
    geolocation_title = _('Geolocation')
    address_search = _('Address search')
    analytics_title = _('Analytics')
    analytics_data = _('Analytics data')
    admin_title = _('Administration')
    admin_interface = _('Django admin interface')
    jwt_instruction = _('Use /api/api/login/ endpoint to get JWT token')
    header_instruction = _('All protected endpoints require header:')
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PetsCare API Documentation</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f5f5f5; }}
            .container {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            h1 {{ color: #2c3e50; text-align: center; margin-bottom: 30px; }}
            .endpoint {{ background: #f8f9fa; border-left: 4px solid #007bff; padding: 15px; margin: 15px 0; border-radius: 5px; }}
            .method {{ display: inline-block; padding: 5px 10px; border-radius: 3px; font-weight: bold; margin-right: 10px; }}
            .get {{ background: #28a745; color: white; }}
            .post {{ background: #007bff; color: white; }}
            .url {{ font-family: monospace; font-size: 16px; color: #495057; }}
            .description {{ margin-top: 10px; color: #6c757d; }}
            .auth-required {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; margin: 20px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🐾 PetsCare API Documentation</h1>
            <div class="auth-required">
                <strong>⚠️ {auth_title}</strong> {auth_desc}
            </div>
            <h2>🔐 {auth_title}</h2>
            <div class="endpoint">
                <span class="method post">POST</span>
                <span class="url">/api/api/register/</span>
                <div class="description">{user_reg}</div>
            </div>
            <div class="endpoint">
                <span class="method post">POST</span>
                <span class="url">/api/api/login/</span>
                <div class="description">{user_login}</div>
            </div>
            <h2>🐕 {pets_title}</h2>
            <div class="endpoint">
                <span class="method get">GET</span>
                <span class="url">/api/pets/</span>
                <div class="description">{pets_list}</div>
            </div>
            <div class="endpoint">
                <span class="method post">POST</span>
                <span class="url">/api/pets/</span>
                <div class="description">{add_pet}</div>
            </div>
            <h2>🏢 {providers_title}</h2>
            <div class="endpoint">
                <span class="method get">GET</span>
                <span class="url">/api/providers/</span>
                <div class="description">{providers_list}</div>
            </div>
            <h2>📅 {bookings_title}</h2>
            <div class="endpoint">
                <span class="method get">GET</span>
                <span class="url">/api/booking/</span>
                <div class="description">{bookings_list}</div>
            </div>
            <h2>🔔 {notifications_title}</h2>
            <div class="endpoint">
                <span class="method get">GET</span>
                <span class="url">/api/notifications/</span>
                <div class="description">{notifications_list}</div>
            </div>
            <h2>💳 {billing_title}</h2>
            <div class="endpoint">
                <span class="method get">GET</span>
                <span class="url">/api/billing/</span>
                <div class="description">{payments_list}</div>
            </div>
            <h2>⭐ {ratings_title}</h2>
            <div class="endpoint">
                <span class="method get">GET</span>
                <span class="url">/api/ratings/</span>
                <div class="description">{ratings_list}</div>
            </div>
            <h2>📍 {geolocation_title}</h2>
            <div class="endpoint">
                <span class="method get">GET</span>
                <span class="url">/api/geolocation/</span>
                <div class="description">{address_search}</div>
            </div>
            <h2>📊 {analytics_title}</h2>
            <div class="endpoint">
                <span class="method get">GET</span>
                <span class="url">/api/analytics/</span>
                <div class="description">{analytics_data}</div>
            </div>
            <h2>🔧 {admin_title}</h2>
            <div class="endpoint">
                <span class="method get">GET</span>
                <span class="url">/admin/</span>
                <div class="description">{admin_interface}</div>
            </div>
            <div style="margin-top: 40px; padding: 20px; background: #e9ecef; border-radius: 5px; text-align: center;">
                <p><strong>PetsCare API v1.0</strong></p>
                <p>{jwt_instruction}</p>
                <p>{header_instruction} <code>Authorization: Bearer &lt;your_token&gt;</code></p>
            </div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html_content)

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
    patterns=[
        # Рабочие приложения для Swagger
        path('api/', include('catalog.urls')),
        path('api/', include('services.urls')),
        path('api/', include('geolocation.urls')),
        path('api/', include('access.urls')),
        path('api/', include('reports.urls')),
        path('api/', include('analytics.urls')),
        path('api/', include('audit.urls')),
        path('api/', include('pets.urls')),
        path('api/', include('billing.urls')),
        path('api/', include('notifications.urls')),
        path('api/', include('ratings.urls')),
        path('api/', include('system_settings.urls')),
        path('api/', include('users.urls')),
        path('api/', include('providers.urls')),
        path('api/', include('booking.urls')),
        path('api/', include('sitters.urls')),
    ],
)

urlpatterns = [
    # Административный интерфейс
    path('admin/', custom_admin_site.urls),  # Используем кастомный админ-сайт
    
    # Документация API
    path('docs/', api_docs_view, name='api-docs'),
    
    # Документация API (Swagger/ReDoc)
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
    # Корневой API endpoint
    path('api/', api_root, name='api-root'),
    
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
    path('api/', include('reports.urls')),
    path('api/', include('ratings.urls')),
    path('api/', include('audit.urls')),
    path('api/', include('analytics.urls')),
    
    # Аутентификация
    path('accounts/', include('allauth.urls')),
]

# Статические и медиа файлы в режиме разработки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 