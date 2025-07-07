"""
Конфигурация ASGI для проекта PetsCare.

Этот модуль содержит ASGI приложение для запуска проекта на ASGI-совместимых серверах.
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PetsCare.settings')

application = get_asgi_application() 