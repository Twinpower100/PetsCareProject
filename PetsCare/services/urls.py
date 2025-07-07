"""
Конфигурация URL маршрутов для модуля услуг.

Этот модуль определяет все доступные API endpoints для работы с услугами:

Основные endpoints:
- GET /services/ - получение списка услуг
- POST /services/ - создание новой услуги
- GET /services/{id}/ - получение информации об услуге
- PUT /services/{id}/ - обновление услуги
- DELETE /services/{id}/ - удаление услуги
- POST /services/search/ - поиск услуг

Особенности реализации:
- Использует DefaultRouter для автоматической генерации URL
- Поддерживает все стандартные REST операции
- Включает дополнительные действия через @action декоратор
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import ServiceViewSet

# Создаем роутер для автоматической генерации URL
router = DefaultRouter()

# Регистрируем ViewSet с префиксом 'services'
router.register(r'services', ServiceViewSet, basename='service')

# Определяем список URL паттернов
urlpatterns = [
    # Включаем все URL, сгенерированные роутером
    path('', include(router.urls)),
] 