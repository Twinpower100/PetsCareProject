from celery import shared_task
from django.utils import timezone
from django.utils.translation import gettext as _
from django.core.mail import send_mail
from django.conf import settings
import logging
import requests
from decimal import Decimal

from .models import (
    ProviderBlocking, BlockingNotification,
    BlockingSystemSettings, BlockingSchedule, Currency
)
from legal.models import LegalDocument, DocumentAcceptance, LegalDocumentType
from .services import MultiLevelBlockingService

logger = logging.getLogger(__name__)


@shared_task
def update_currency_rates():
    """
    Задача для обновления курсов валют через внешний API
    """
    try:
        # Используем API exchangeratesapi.io (нужно заменить на реальный API ключ)
        response = requests.get(
            'https://api.exchangeratesapi.io/latest',
            params={
                'base': 'USD',  # Базовая валюта
                'symbols': 'EUR,RUB'  # Список валют для обновления
            }
        )
        data = response.json()

        if response.status_code == 200:
            # Обновляем курсы валют
            for code, rate in data['rates'].items():
                currency = Currency.objects.filter(code=code).first()
                if currency:
                    currency.exchange_rate = Decimal(str(rate))
                    currency.save()

            return {
                'status': 'success',
                'message': _('Currency rates updated successfully'),
                'timestamp': timezone.now().isoformat()
            }
        else:
            return {
                'status': 'error',
                'message': _('Failed to fetch currency rates: {error}').format(
                    error=data.get("error")
                ),
                'timestamp': timezone.now().isoformat()
            }

    except Exception as e:
        return {
            'status': 'error',
            'message': _('Failed to update currency rates: {error}').format(
                error=str(e)
            ),
            'timestamp': timezone.now().isoformat()
        }

@shared_task
def run_blocking_check():
    """
    Периодическая задача для автоматической проверки и блокировки учреждений по задолженности.
    """
    service = MultiLevelBlockingService()
    service.check_all_providers()

@shared_task
def check_provider_blocking(provider_id):
    """
    Проверяет необходимость блокировки конкретного учреждения.
    
    Args:
        provider_id: ID учреждения для проверки
        
    Returns:
        dict: Результат проверки
    """
    try:
        from providers.models import Provider
        
        provider = Provider.objects.get(id=provider_id)
        service = MultiLevelBlockingService()
        
        result = service.check_provider_blocking(provider)
        
        if result['should_block']:
            blocking = service.apply_blocking(
                provider,
                result['blocking_level'],
                result['reasons']
            )
            logger.info(f"Provider {provider.name} blocked at level {result['blocking_level']}")
            return {
                'provider_id': provider_id,
                'blocked': True,
                'level': result['blocking_level'],
                'reasons': result['reasons']
            }
        else:
            logger.info(f"Provider {provider.name} does not need blocking")
            return {
                'provider_id': provider_id,
                'blocked': False,
                'reason': result.get('reason', 'No blocking required')
            }
            
    except Provider.DoesNotExist:
        logger.error(f"Provider with ID {provider_id} not found")
        return {'error': 'Provider not found'}
    except Exception as e:
        logger.error(f"Error checking provider {provider_id}: {str(e)}")
        return {'error': str(e)}


@shared_task
def check_all_providers_blocking():
    """
    Проверяет все учреждения на необходимость блокировки.
    
    Returns:
        dict: Статистика проверки
    """
    try:
        # Проверяем, включена ли система блокировки
        settings = BlockingSystemSettings.get_settings()
        if not settings.is_system_enabled:
            logger.info("Blocking system is disabled")
            return {'status': 'disabled', 'message': 'Blocking system is disabled'}
        
        service = MultiLevelBlockingService()
        stats = service.check_all_providers()
        
        logger.info(f"Blocking check completed: {stats}")
        return {
            'status': 'completed',
            'statistics': stats
        }
        
    except Exception as e:
        logger.error(f"Error in check_all_providers_blocking: {str(e)}")
        return {'error': str(e)}


@shared_task
def send_blocking_notifications():
    """
    Отправляет отложенные уведомления о блокировках.
    
    Returns:
        dict: Статистика отправки
    """
    try:
        # Получаем настройки системы
        settings = BlockingSystemSettings.get_settings()
        
        # Получаем уведомления, готовые к отправке
        notifications = BlockingNotification.objects.filter(
            status='pending',
            created_at__lte=timezone.now() - timezone.timedelta(
                hours=settings.notification_delay_hours
            )
        )
        
        stats = {
            'total_notifications': notifications.count(),
            'sent': 0,
            'failed': 0,
            'errors': []
        }
        
        for notification in notifications:
            try:
                # Отправляем уведомление
                success = send_email_notification(notification)
                
                if success:
                    notification.mark_as_sent()
                    stats['sent'] += 1
                    logger.info(f"Notification sent to {notification.recipient_email}")
                else:
                    notification.mark_as_failed("Failed to send email")
                    stats['failed'] += 1
                    logger.error(f"Failed to send notification to {notification.recipient_email}")
                    
            except Exception as e:
                notification.mark_as_failed(str(e))
                stats['failed'] += 1
                stats['errors'].append(f"Error sending notification {notification.id}: {str(e)}")
                logger.error(f"Error sending notification {notification.id}: {str(e)}")
        
        logger.info(f"Notification sending completed: {stats}")
        return {
            'status': 'completed',
            'statistics': stats
        }
        
    except Exception as e:
        logger.error(f"Error in send_blocking_notifications: {str(e)}")
        return {'error': str(e)}





@shared_task
def process_blocking_schedules():
    """
    Обрабатывает расписания блокировок.
    
    Returns:
        dict: Статистика обработки расписаний
    """
    try:
        # Получаем активные расписания, которые должны выполняться сейчас
        schedules = BlockingSchedule.objects.filter(is_active=True)
        
        stats = {
            'total_schedules': schedules.count(),
            'executed': 0,
            'skipped': 0,
            'errors': []
        }
        
        for schedule in schedules:
            try:
                if schedule.should_run_now():
                    # Выполняем проверку блокировок
                    result = check_all_providers_blocking.delay()
                    
                    # Отмечаем расписание как выполненное
                    schedule.mark_as_run()
                    stats['executed'] += 1
                    
                    logger.info(f"Executed schedule {schedule.name}")
                else:
                    stats['skipped'] += 1
                    
            except Exception as e:
                stats['errors'].append(f"Error processing schedule {schedule.id}: {str(e)}")
                logger.error(f"Error processing schedule {schedule.id}: {str(e)}")
        
        logger.info(f"Schedule processing completed: {stats}")
        return {
            'status': 'completed',
            'statistics': stats
        }
        
    except Exception as e:
        logger.error(f"Error in process_blocking_schedules: {str(e)}")
        return {'error': str(e)}


def send_email_notification(notification):
    """
    Отправляет email уведомление.
    
    Args:
        notification: Объект BlockingNotification
        
    Returns:
        bool: True если отправка успешна, False в противном случае
    """
    try:
        send_mail(
            subject=notification.subject,
            message=notification.message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notification.recipient_email],
            fail_silently=False
        )
        return True
    except Exception as e:
        logger.error(f"Error sending email notification: {str(e)}")
        return False


@shared_task
def cleanup_old_notifications():
    """
    Очищает старые уведомления о блокировках.
    
    Returns:
        dict: Статистика очистки
    """
    try:
        # Удаляем уведомления старше 90 дней
        cutoff_date = timezone.now() - timezone.timedelta(days=90)
        
        old_notifications = BlockingNotification.objects.filter(
            created_at__lt=cutoff_date
        )
        
        count = old_notifications.count()
        old_notifications.delete()
        
        logger.info(f"Cleaned up {count} old notifications")
        return {
            'status': 'completed',
            'deleted_count': count
        }
        
    except Exception as e:
        logger.error(f"Error in cleanup_old_notifications: {str(e)}")
        return {'error': str(e)}


@shared_task
def update_blocking_statistics():
    """
    Обновляет статистику блокировок.
    
    Returns:
        dict: Обновленная статистика
    """
    try:
        from providers.models import Provider
        
        # Получаем статистику
        total_providers = Provider.objects.filter(is_active=True).count()
        active_blockings = ProviderBlocking.objects.filter(status='active').count()
        resolved_blockings = ProviderBlocking.objects.filter(status='resolved').count()
        
        # Рассчитываем процент заблокированных учреждений
        blocking_percentage = (active_blockings / total_providers * 100) if total_providers > 0 else 0
        
        stats = {
            'total_providers': total_providers,
            'active_blockings': active_blockings,
            'resolved_blockings': resolved_blockings,
            'blocking_percentage': round(blocking_percentage, 2)
        }
        
        logger.info(f"Updated blocking statistics: {stats}")
        return {
            'status': 'completed',
            'statistics': stats
        }
        
    except Exception as e:
        logger.error(f"Error in update_blocking_statistics: {str(e)}")
        return {'error': str(e)}


@shared_task
def activate_pending_offers():
    """
    Активирует оферты, у которых наступил effective_date.
    
    При активации новой оферты:
    - Деактивирует старую активную оферту
    - Активирует новую оферту
    - Автоматически создает ProviderOfferAcceptance для всех активных провайдеров
    - Деактивирует старые акцепты провайдеров
    
    Returns:
        dict: Статистика активации
    """
    from django.db import transaction
    from providers.models import Provider
    
    try:
        today = timezone.now().date()
        
        # Находим оферты (LegalDocument типа global_offer), которые должны быть активированы сегодня
        try:
            global_offer_type = LegalDocumentType.objects.get(code='global_offer')
        except LegalDocumentType.DoesNotExist:
            logger.warning("LegalDocumentType 'global_offer' not found. Skipping offer activation.")
            return
        
        pending_offers = LegalDocument.objects.filter(
            document_type=global_offer_type,
            is_active=False,
            effective_date=today,
            notification_sent_at__isnull=False  # Уведомления должны быть отправлены
        )
        
        stats = {
            'offers_found': pending_offers.count(),
            'activated': 0,
            'old_acceptances_deactivated': 0,
            'errors': []
        }
        
        for new_offer in pending_offers:
            try:
                with transaction.atomic():
                    # Деактивируем старую активную оферту того же типа
                    old_offer = LegalDocument.objects.filter(
                        document_type=global_offer_type,
                        is_active=True
                    ).first()
                    if old_offer:
                        old_offer.is_active = False
                        old_offer.save(update_fields=['is_active'])
                        logger.info(f"Deactivated old offer {old_offer.id} ({old_offer.version})")
                    
                    # Активируем новую оферту
                    new_offer.is_active = True
                    new_offer.save(update_fields=['is_active'])
                    logger.info(f"Activated new offer {new_offer.id} ({new_offer.version})")
                    
                    # Деактивируем старые акцепты (провайдеры должны явно акцептовать новую оферту)
                    deactivated_count = 0
                    if old_offer:
                        deactivated_count = DocumentAcceptance.objects.filter(
                            document=old_offer,
                            is_active=True
                        ).update(is_active=False)
                        
                        logger.info(
                            f"Deactivated {deactivated_count} old offer acceptances. "
                            f"Providers must explicitly accept the new offer."
                        )
                    
                    stats['activated'] += 1
                    stats['old_acceptances_deactivated'] += deactivated_count
                    
                    logger.info(
                        f"Offer {new_offer.id} activated. "
                        f"Deactivated {deactivated_count} old acceptances. "
                        f"Providers must explicitly accept the new offer to continue using the service."
                    )
            
            except Exception as e:
                error_msg = f"Error activating offer {new_offer.id}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                stats['errors'].append(error_msg)
        
        logger.info(f"Offer activation completed: {stats}")
        return {
            'status': 'completed',
            'statistics': stats
        }
    
    except Exception as e:
        logger.error(f"Error in activate_pending_offers: {str(e)}", exc_info=True)
        return {'error': str(e)} 