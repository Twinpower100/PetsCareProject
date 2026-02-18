"""
Конфигурация приложения legal.

Этот модуль содержит настройки приложения legal:
1. Управление юридическими документами
2. Типы документов
3. Переводы документов
4. Конфигурация стран
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LegalConfig(AppConfig):
    """
    Конфигурация приложения legal.
    
    Особенности:
    - Управление юридическими документами (оферты, политики)
    - Версионирование документов
    - Мультиязычность
    - Конвертация DOCX в HTML
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'legal'
    verbose_name = _('Legal Documents')
