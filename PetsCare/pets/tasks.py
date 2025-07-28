"""
Периодические задачи для обработки недееспособности владельцев питомцев.

Этот модуль содержит Celery задачи для:
1. Автоматической проверки неактивных владельцев
2. Обработки автоматических действий по истечении дедлайнов
3. Отправки уведомлений
"""

import logging
from celery import shared_task
from django.utils import timezone
from django.db import transaction

from .services import PetOwnerIncapacityService
from .models import PetOwnerIncapacity

logger = logging.getLogger(__name__)


@shared_task
def check_inactive_owners_task():
    """
    Периодическая задача для проверки неактивных владельцев питомцев.
    
    Эта задача:
    1. Находит питомцев с неактивными основными владельцами
    2. Создает записи о недееспособности
    3. Отправляет уведомления всем владельцам
    """
    logger.info("Starting inactive owners check task")
    
    try:
        service = PetOwnerIncapacityService()
        created_records = service.check_inactive_owners()
        
        logger.info(f"Inactive owners check completed. Created {len(created_records)} incapacity records")
        
        return {
            'status': 'success',
            'records_created': len(created_records),
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in inactive owners check task: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def process_deadline_actions_task():
    """
    Периодическая задача для обработки автоматических действий по истечении дедлайнов.
    
    Эта задача:
    1. Находит записи о недееспособности с истекшим дедлайном
    2. Выполняет автоматические действия (удаление питомца или назначение совладельца)
    3. Отправляет уведомления о выполненных действиях
    """
    logger.info("Starting deadline actions processing task")
    
    try:
        service = PetOwnerIncapacityService()
        stats = service.process_deadline_actions()
        
        logger.info(f"Deadline actions processing completed. Stats: {stats}")
        
        return {
            'status': 'success',
            'stats': stats,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in deadline actions processing task: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def send_incapacity_notifications_task():
    """
    Периодическая задача для отправки уведомлений о недееспособности.
    
    Эта задача:
    1. Находит неотправленные уведомления
    2. Отправляет их через email
    3. Обновляет статус уведомлений
    """
    logger.info("Starting incapacity notifications sending task")
    
    try:
        from .models import PetIncapacityNotification
        
        # Находим неотправленные уведомления
        pending_notifications = PetIncapacityNotification.objects.filter(
            status='pending'
        ).select_related('recipient', 'incapacity_record')
        
        sent_count = 0
        failed_count = 0
        
        for notification in pending_notifications:
            try:
                service = PetOwnerIncapacityService()
                success = service._send_email_notification(notification)
                
                if success:
                    sent_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Error sending notification {notification.id}: {str(e)}")
                failed_count += 1
        
        logger.info(f"Incapacity notifications sending completed. Sent: {sent_count}, Failed: {failed_count}")
        
        return {
            'status': 'success',
            'sent_count': sent_count,
            'failed_count': failed_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in incapacity notifications sending task: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def cleanup_old_incapacity_records_task():
    """
    Периодическая задача для очистки старых записей о недееспособности.
    
    Эта задача удаляет записи старше определенного периода для экономии места в БД.
    """
    logger.info("Starting old incapacity records cleanup task")
    
    try:
        # Удаляем записи старше 1 года
        cutoff_date = timezone.now() - timezone.timedelta(days=365)
        
        with transaction.atomic():
            old_records = PetOwnerIncapacity.objects.filter(
                created_at__lt=cutoff_date,
                status__in=['resolved', 'auto_deleted', 'coowner_assigned']
            )
            
            deleted_count = old_records.count()
            old_records.delete()
        
        logger.info(f"Old incapacity records cleanup completed. Deleted {deleted_count} records")
        
        return {
            'status': 'success',
            'deleted_count': deleted_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in old incapacity records cleanup task: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        } 