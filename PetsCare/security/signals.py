from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.core.cache import cache
import logging

from .models import SecurityThreat, IPBlacklist

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SecurityThreat)
def security_threat_created(sender, instance, created, **kwargs):
    """Обработчик создания новой угрозы безопасности"""
    if created:
        try:
            # Очистить кэш статистики
            cache.delete('security_stats')
            
            # Логировать критическую угрозу
            if instance.severity == 'critical':
                logger.critical(
                    f"CRITICAL SECURITY THREAT: {instance.threat_type} "
                    f"from {instance.ip_address} at {instance.detected_at}"
                )
            
            # Отправить уведомление администраторам (если настроено)
            # TODO: Интегрировать с системой уведомлений
            
        except Exception as e:
            logger.error(f"Error handling security threat signal: {e}")


@receiver(post_save, sender=IPBlacklist)
def ip_blacklist_updated(sender, instance, created, **kwargs):
    """Обработчик обновления черного списка IP"""
    try:
        # Очистить кэш IP блокировок
        cache.delete(f'ip_blacklist_{instance.ip_address}')
        cache.delete('security_stats')
        
        if created:
            logger.warning(
                f"IP {instance.ip_address} blocked due to: {instance.reason}"
            )
        
    except Exception as e:
        logger.error(f"Error handling IP blacklist signal: {e}")


@receiver(post_save, sender=SecurityThreat)
def security_threat_resolved(sender, instance, **kwargs):
    """Обработчик разрешения угрозы"""
    if instance.status in ['resolved', 'false_positive'] and instance.resolved_at:
        try:
            # Очистить кэш статистики
            cache.delete('security_stats')
            
            logger.info(
                f"Security threat {instance.id} resolved by {instance.resolved_by} "
                f"at {instance.resolved_at}"
            )
            
        except Exception as e:
            logger.error(f"Error handling threat resolution signal: {e}") 