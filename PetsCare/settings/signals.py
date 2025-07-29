"""
Сигналы для системных настроек.

Этот модуль содержит сигналы для:
1. Очистки кэша при изменении настроек безопасности
2. Логирования изменений настроек
3. Применения настроек в системе
"""

import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

from .models import SecuritySettings

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SecuritySettings)
def clear_security_settings_cache(sender, instance, created, **kwargs):
    """
    Очищает кэш настроек безопасности при их изменении.
    
    Args:
        sender: Модель, которая отправила сигнал
        instance: Экземпляр модели
        created: True если запись создана, False если обновлена
        **kwargs: Дополнительные аргументы
    """
    try:
        # Очищаем кэш настроек безопасности
        cache.delete('security_settings')
        logger.info("Security settings cache cleared after save")
        
    except Exception as e:
        logger.error(f"Failed to clear security settings cache: {e}")


@receiver(post_delete, sender=SecuritySettings)
def clear_security_settings_cache_on_delete(sender, instance, **kwargs):
    """
    Очищает кэш настроек безопасности при удалении записи.
    
    Args:
        sender: Модель, которая отправила сигнал
        instance: Экземпляр модели
        **kwargs: Дополнительные аргументы
    """
    try:
        # Очищаем кэш настроек безопасности
        cache.delete('security_settings')
        logger.info("Security settings cache cleared after delete")
        
    except Exception as e:
        logger.error(f"Failed to clear security settings cache on delete: {e}") 