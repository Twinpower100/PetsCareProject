"""
Сигналы для автоматизации процессов биллинга.

Содержит:
- Логирование изменений блокировки организации
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender='billing.ProviderBlocking')
def handle_provider_blocking(sender, instance, created, **kwargs):
    """
    Обрабатывает блокировку организации провайдера.

    Владелец и публичный поиск ограничиваются через billing middleware и
    booking search policy. Здесь не меняем lifecycle филиалов и не отменяем
    существующие записи автоматически, чтобы уровни L1/L2/L3 не схлопывались
    в одинаковую полную блокировку.
    """
    from .models import ProviderBlocking

    if not isinstance(instance, ProviderBlocking):
        return

    if instance.status == 'active':
        provider = instance.provider
        logger.info(
            "Provider %s (%s) blocking is active at level %s. "
            "Access restrictions are enforced without changing location lifecycle.",
            provider.id,
            provider.name,
            instance.blocking_level,
        )
    elif instance.status == 'resolved':
        provider = instance.provider
        logger.info(
            "Provider %s (%s) blocking resolved.",
            provider.id,
            provider.name,
        )


# УДАЛЕНО: Сигнал для PublicOffer - модель удалена
# Уведомления об изменениях оферты теперь обрабатываются в приложении legal
# @receiver(post_save, sender='billing.PublicOffer')
# def handle_new_offer_version(sender, instance, created, **kwargs):


@receiver(post_save, sender='legal.DocumentAcceptance')
def handle_offer_acceptance(sender, instance, created, **kwargs):
    """
    Обрабатывает принятие оферты провайдером (Owner) на фронтенде.
    
    Флоу:
    1. Owner принимает оферту на фронтенде (React) → создается DocumentAcceptance через API
    2. Этот сигнал автоматически активирует провайдера (activation_status='active', is_active=True)
    3. Отправляет письмо Owner'у об успешной активации провайдера
    
    Примечание:
    - Оферта принимается на фронтенде, не через письмо
    - Активация происходит только при создании нового акцепта (created=True)
    - Активация происходит только если провайдер еще не активирован
    - Письмо отправляется ПОСЛЕ принятия оферты и активации (уведомление об успехе)
    - Обрабатываются только акцепты оферт (global_offer) для провайдеров
    """
    from legal.models import DocumentAcceptance
    from legal.services import DocumentAcceptanceService
    
    # Обрабатываем только создание нового акцепта
    if not created:
        return
    
    # Проверяем, что это действительно DocumentAcceptance
    if not isinstance(instance, DocumentAcceptance):
        return
    
    # Обрабатываем только оферты провайдеров (global_offer)
    if not instance.provider or not instance.document:
        return
    
    if instance.document.document_type.code != 'global_offer':
        return
    
    # Используем сервис для обработки акцепта
    service = DocumentAcceptanceService()
    result = service.handle_offer_acceptance(instance)
    
    if not result.get('success'):
        logger.error(f"Error handling offer acceptance {instance.id}: {result.get('error')}")

