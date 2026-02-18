"""
Конфигурация приложения providers.

Этот модуль содержит настройки приложения providers:
1. Автоматическое поле по умолчанию
2. Имя приложения
3. Отображаемое имя
"""

from django.apps import AppConfig
from django.db.models.signals import pre_save, post_save
from django.utils.translation import gettext_lazy as _


class ProvidersConfig(AppConfig):
    """
    Конфигурация приложения providers.
    
    Особенности:
    - Управление поставщиками услуг
    - Профили организаций
    - Расписание работы
    - Управление услугами
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'providers'
    verbose_name = _('Service Providers')
    
    def ready(self):
        """
        Инициализация сигналов при запуске приложения.
        """
        from . import signals  # noqa
        from .models import ProviderLocation, Provider
        
        # Подключаем сигнал деактивации локации
        pre_save.connect(signals.handle_location_deactivation, sender=ProviderLocation)
        
        # Подключаем сигналы для отправки письма при активации провайдера
        pre_save.connect(signals.store_provider_old_status, sender=Provider)
        post_save.connect(signals.send_provider_activation_email, sender=Provider)