"""
Конфигурация WSGI для проекта PetsCare.

Этот модуль содержит WSGI приложение для запуска проекта на WSGI-совместимых серверах.
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PetsCare.settings')

application = get_wsgi_application() 