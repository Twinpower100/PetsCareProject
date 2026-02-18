"""
Сигналы для автоматизации процессов биллинга.

Содержит:
- Обработка блокировки организации (деактивация всех локаций)
- Отмена бронирований при блокировке организации
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender='billing.ProviderBlocking')
def handle_provider_blocking(sender, instance, created, **kwargs):
    """
    Обрабатывает блокировку организации провайдера.
    
    При создании активной блокировки:
    - Деактивирует все локации организации
    - Отменяет все активные и будущие бронирования во всех локациях
    - Отправляет уведомления пользователям
    
    При снятии блокировки:
    - Локации остаются деактивированными (требуется ручная активация)
    """
    # Импортируем модели здесь, чтобы избежать циклических импортов
    from .models import ProviderBlocking
    from providers.models import ProviderLocation
    from booking.models import Booking, BookingStatus
    
    # Проверяем, что это действительно ProviderBlocking
    if not isinstance(instance, ProviderBlocking):
        return
    
    # Обрабатываем только активные блокировки
    if instance.status == 'active':
        provider = instance.provider
        logger.info(f"Provider {provider.id} ({provider.name}) is blocked. Deactivating all locations...")
        
        with transaction.atomic():
            # Деактивируем все локации организации
            locations = ProviderLocation.objects.filter(
                provider=provider,
                is_active=True
            )
            
            deactivated_count = 0
            cancelled_bookings_count = 0
            
            # Получаем статус "отменено"
            cancelled_status, _ = BookingStatus.objects.get_or_create(
                name='cancelled',
                defaults={'description': _('Booking cancelled due to provider blocking')}
            )
            
            now = timezone.now()
            
            for location in locations:
                # Деактивируем локацию
                location.is_active = False
                location.save(update_fields=['is_active'])
                deactivated_count += 1
                logger.info(f"Location {location.id} ({location.name}) deactivated due to provider blocking")
                
                # Отменяем все активные и будущие бронирования для этой локации
                active_bookings = Booking.objects.filter(
                    provider_location=location,
                    status__name__in=['active', 'pending_confirmation', 'confirmed']
                ).exclude(
                    start_time__lt=now  # Исключаем прошедшие бронирования
                )
                
                for booking in active_bookings:
                    booking.status = cancelled_status
                    if booking.notes:
                        booking.notes += f"\n{_('Cancelled due to provider organization blocking.')}"
                    else:
                        booking.notes = _('Cancelled due to provider organization blocking.')
                    booking.save()
                    cancelled_bookings_count += 1
                    
                    # TODO: Отправить уведомление пользователю
                    # from notifications.models import Notification
                    # Notification.objects.create(
                    #     user=booking.user,
                    #     title=_('Booking Cancelled'),
                    #     message=_('Your booking at {location} has been cancelled due to provider organization blocking.').format(
                    #         location=location.name
                    #     ),
                    #     type='booking_cancelled'
                    # )
                    logger.info(f"Booking {booking.id} cancelled for location {location.id} due to provider blocking")
            
            logger.info(
                f"Provider {provider.id} blocked. "
                f"{deactivated_count} locations deactivated, "
                f"{cancelled_bookings_count} bookings cancelled."
            )
    
    # При снятии блокировки локации остаются деактивированными
    # (требуется ручная активация администратором)
    elif instance.status == 'resolved':
        provider = instance.provider
        logger.info(
            f"Provider {provider.id} ({provider.name}) blocking resolved. "
            f"Locations remain deactivated and require manual activation."
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

