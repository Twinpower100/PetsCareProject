"""
Сигналы Django для автоматической отправки уведомлений.

Этот модуль содержит сигналы для:
1. Автоматической отправки уведомлений при создании пользователей
2. Уведомлений о бронированиях
3. Уведомлений о приглашениях ролей
4. Уведомлений о блокировках учреждений
"""

import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.translation import gettext as _
from django.contrib.auth import get_user_model
from .tasks import (
    send_email_verification_task,
    send_password_reset_task,
    send_role_invite_task,
    send_role_invite_response_task,
    send_booking_confirmation_task,
    send_booking_cancellation_task,
    schedule_booking_reminders_task,
    send_price_change_notification_task,
    send_new_review_notification_task,
    send_pet_sitting_notification_task,
    send_payment_failed_notification_task,
    send_refund_notification_task,
    send_role_invite_expired_task,
    send_debt_reminder_task
)
from .services import PreferenceService, NotificationService
from django.utils import timezone

User = get_user_model()
logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_user_notification_preferences(sender, instance, created, **kwargs):
    """
    Создает настройки уведомлений по умолчанию для нового пользователя.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр пользователя
        created: Создан ли пользователь
        **kwargs: Дополнительные аргументы
    """
    if created:
        try:
            preference_service = PreferenceService()
            preference_service.create_default_preferences(instance)
            logger.info(f"Created default notification preferences for user {instance.id}")
        except Exception as e:
            logger.error(f"Failed to create notification preferences for user {instance.id}: {e}")


@receiver(post_save, sender=User)
def send_email_verification_on_registration(sender, instance, created, **kwargs):
    """
    Отправляет email верификации при регистрации нового пользователя.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр пользователя
        created: Создан ли пользователь
        **kwargs: Дополнительные аргументы
    """
    if created and instance.email:
        try:
            # Генерируем токен верификации
            from django.contrib.auth.tokens import default_token_generator
            from django.utils.http import urlsafe_base64_encode
            from django.utils.encoding import force_bytes
            
            token = default_token_generator.make_token(instance)
            uid = urlsafe_base64_encode(force_bytes(instance.pk))
            
            # Отправляем задачу на верификацию email
            send_email_verification_task.delay(instance.id, f"{uid}-{token}")
            
            logger.info(f"Email verification task queued for user {instance.id}")
            
        except Exception as e:
            logger.error(f"Failed to queue email verification for user {instance.id}: {e}")


# Сигналы для бронирований
@receiver(post_save, sender='booking.Booking')
def handle_booking_notifications(sender, instance, created, **kwargs):
    """
    Обрабатывает уведомления о бронированиях.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр бронирования
        created: Создано ли бронирование
        **kwargs: Дополнительные аргументы
    """
    try:
        if created:
            # Отправляем подтверждение бронирования
            send_booking_confirmation_task.delay(instance.id)
            
            # Планируем напоминания о бронировании
            schedule_booking_reminders_task.delay(instance.id)
            
            logger.info(f"Booking notification tasks queued for booking {instance.id}")
            
    except Exception as e:
        logger.error(f"Failed to handle booking notifications for booking {instance.id}: {e}")


@receiver(post_delete, sender='booking.Booking')
def handle_booking_cancellation_notification(sender, instance, **kwargs):
    """
    Обрабатывает уведомления об отмене бронирования.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр бронирования
        **kwargs: Дополнительные аргументы
    """
    try:
        # Отправляем уведомление об отмене
        send_booking_cancellation_task.delay(instance.id, _("Booking was cancelled"))
        
        logger.info(f"Booking cancellation notification queued for booking {instance.id}")
        
    except Exception as e:
        logger.error(f"Failed to handle booking cancellation notification for booking {instance.id}: {e}")


# Сигналы для приглашений ролей
@receiver(post_save, sender='users.RoleInvite')
def handle_role_invite_notifications(sender, instance, created, **kwargs):
    """
    Обрабатывает уведомления о приглашениях ролей.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр приглашения
        created: Создано ли приглашение
        **kwargs: Дополнительные аргументы
    """
    try:
        if created:
            # Отправляем уведомление о новом приглашении
            send_role_invite_task.delay(instance.id)
            
            logger.info(f"Role invite notification queued for invite {instance.id}")
            
    except Exception as e:
        logger.error(f"Failed to handle role invite notification for invite {instance.id}: {e}")


@receiver(post_save, sender='users.RoleInvite')
def handle_role_invite_response_notifications(sender, instance, **kwargs):
    """
    Обрабатывает уведомления о принятии/отклонении приглашений ролей.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр приглашения
        **kwargs: Дополнительные аргументы
    """
    try:
        # Проверяем, изменился ли статус приглашения
        if instance.pk:
            old_instance = sender.objects.get(pk=instance.pk)
            if old_instance.status != instance.status and instance.status in ['accepted', 'declined']:
                # Отправляем уведомление о принятии/отклонении
                send_role_invite_response_task.delay(instance.id, instance.status == 'accepted')
                
                logger.info(f"Role invite response notification queued for invite {instance.id}")
                
    except sender.DoesNotExist:
        # Это новое приглашение, обрабатывается в другом сигнале
        pass
    except Exception as e:
        logger.error(f"Failed to handle role invite response notification for invite {instance.id}: {e}")


# Сигналы для блокировок учреждений
@receiver(post_save, sender='providers.Provider')
def handle_provider_blocking_notifications(sender, instance, **kwargs):
    """
    Обрабатывает уведомления о блокировке/разблокировке учреждений.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр учреждения
        **kwargs: Дополнительные аргументы
    """
    try:
        # Проверяем, изменился ли статус блокировки
        if instance.pk:
            old_instance = sender.objects.get(pk=instance.pk)
            if old_instance.is_blocked != instance.is_blocked:
                notification_service = NotificationService()
                
                if instance.is_blocked:
                    # Уведомляем о блокировке
                    title = _('Provider Blocked')
                    message = _('Your provider account has been blocked')
                    notification_type = 'system'
                else:
                    # Уведомляем о разблокировке
                    title = _('Provider Unblocked')
                    message = _('Your provider account has been unblocked')
                    notification_type = 'system'
                
                # Отправляем уведомление владельцу учреждения
                notification = notification_service.send_notification(
                    user=instance.owner,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    channels=['email', 'push', 'in_app'],
                    priority='high',
                    data={'provider_id': instance.id, 'is_blocked': instance.is_blocked}
                )
                
                logger.info(f"Provider blocking notification sent for provider {instance.id}")
                
    except sender.DoesNotExist:
        # Это новое учреждение
        pass
    except Exception as e:
        logger.error(f"Failed to handle provider blocking notification for provider {instance.id}: {e}")


# Сигналы для изменений цен услуг
@receiver(post_save, sender='catalog.Service')
def handle_service_price_change_notifications(sender, instance, **kwargs):
    """
    Обрабатывает уведомления об изменении цен услуг.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр услуги
        **kwargs: Дополнительные аргументы
    """
    try:
        # Проверяем, изменилась ли цена
        if instance.pk:
            old_instance = sender.objects.get(pk=instance.pk)
            if old_instance.price != instance.price:
                # Отправляем задачу на уведомление об изменении цены
                send_price_change_notification_task.delay(
                    service_id=instance.id,
                    old_price=old_instance.price,
                    new_price=instance.price,
                    currency=instance.currency or 'EUR'
                )
                
                logger.info(f"Price change notification task queued for service {instance.id}")
                
    except sender.DoesNotExist:
        # Это новая услуга
        pass
    except Exception as e:
        logger.error(f"Failed to handle service price change notification for service {instance.id}: {e}")


# Сигналы для отзывов
@receiver(post_save, sender='ratings.Review')
def handle_review_notifications(sender, instance, created, **kwargs):
    """
    Обрабатывает уведомления о новых отзывах.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр отзыва
        created: Создан ли отзыв
        **kwargs: Дополнительные аргументы
    """
    try:
        if created:
            # Отправляем задачу на уведомление о новом отзыве
            send_new_review_notification_task.delay(instance.id)
            
            logger.info(f"New review notification task queued for review {instance.id}")
            
    except Exception as e:
        logger.error(f"Failed to handle review notification for review {instance.id}: {e}")


# Сигналы для напоминаний о питомцах
@receiver(post_save, sender='pets.Pet')
def handle_pet_reminder_notifications(sender, instance, created, **kwargs):
    """
    Обрабатывает уведомления о напоминаниях для питомцев.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр питомца
        created: Создан ли питомец
        **kwargs: Дополнительные аргументы
    """
    try:
        if created:
            notification_service = NotificationService()
            
            # Отправляем приветственное уведомление о питомце
            notification = notification_service.send_notification(
                user=instance.owner,
                notification_type='reminder',
                title=_('Pet Added Successfully'),
                message=_('Your pet ') + instance.name + _(' has been added to your profile'),
                channels=['email', 'push', 'in_app'],
                priority='low',
                pet=instance,
                data={'pet_id': instance.id, 'pet_name': instance.name}
            )
            
            logger.info(f"Pet reminder notification sent for pet {instance.id}")
            
    except Exception as e:
        logger.error(f"Failed to handle pet reminder notification for pet {instance.id}: {e}")


# Сигналы для передержек питомцев
@receiver(post_save, sender='sitters.PetSitting')
def handle_pet_sitting_notifications(sender, instance, **kwargs):
    """
    Обрабатывает уведомления о передержках питомцев.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр передержки
        **kwargs: Дополнительные аргументы
    """
    try:
        # Проверяем, изменился ли статус
        if instance.pk:
            old_instance = sender.objects.get(pk=instance.pk)
            if old_instance.status != instance.status:
                # Отправляем задачу на уведомление об изменении статуса
                send_pet_sitting_notification_task.delay(
                    sitting_id=instance.id,
                    status=instance.status
                )
                
                logger.info(f"Pet sitting notification task queued for sitting {instance.id}")
                
    except sender.DoesNotExist:
        # Это новая передержка
        pass
    except Exception as e:
        logger.error(f"Failed to handle pet sitting notification for sitting {instance.id}: {e}")


# Сигналы для платежей (если будут добавлены в будущем)
@receiver(post_save, sender='billing.Payment')
def handle_payment_notifications(sender, instance, created, **kwargs):
    """
    Обрабатывает уведомления о платежах.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр платежа
        created: Создан ли платеж
        **kwargs: Дополнительные аргументы
    """
    try:
        if created:
            notification_service = NotificationService()
            
            if instance.status == 'completed':
                # Отправляем подтверждение платежа
                notification = notification_service.send_notification(
                    user=instance.user,
                    notification_type='payment',
                    title=_('Payment Confirmed'),
                    message=_('Your payment has been successfully processed'),
                    channels=['email', 'push', 'in_app'],
                    priority='medium',
                    data={'payment_id': instance.id, 'amount': instance.amount}
                )
                
                logger.info(f"Payment confirmation sent for payment {instance.id}")
                
            elif instance.status == 'failed':
                from .tasks import send_payment_failed_notification_task
                
                # Отправляем уведомление о неудачном платеже
                send_payment_failed_notification_task.delay(
                    payment_id=instance.id,
                    reason=instance.failure_reason if hasattr(instance, 'failure_reason') else None
                )
                
                logger.info(f"Payment failure notification task queued for payment {instance.id}")
                
    except Exception as e:
        logger.error(f"Failed to handle payment notification for payment {instance.id}: {e}")


# Сигналы для возвратов средств
@receiver(post_save, sender='billing.Refund')
def handle_refund_notifications(sender, instance, created, **kwargs):
    """
    Обрабатывает уведомления о возвратах средств.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр возврата
        created: Создан ли возврат
        **kwargs: Дополнительные аргументы
    """
    try:
        if created:
            # Отправляем уведомление о возврате средств
            send_refund_notification_task.delay(instance.id)
            
            logger.info(f"Refund notification task queued for refund {instance.id}")
            
    except Exception as e:
        logger.error(f"Failed to handle refund notification for refund {instance.id}: {e}")


# Сигналы для истечения инвайтов ролей
@receiver(post_save, sender='users.RoleInvite')
def handle_role_invite_expiration_notifications(sender, instance, **kwargs):
    """
    Обрабатывает уведомления об истечении инвайтов ролей.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр инвайта
        **kwargs: Дополнительные аргументы
    """
    try:
        # Проверяем, истек ли инвайт
        if instance.expires_at and instance.expires_at <= timezone.now() and instance.status == 'pending':
            # Отправляем уведомление об истечении
            send_role_invite_expired_task.delay(instance.id)
            
            logger.info(f"Role invite expiration notification task queued for invite {instance.id}")
            
    except Exception as e:
        logger.error(f"Failed to handle role invite expiration notification for invite {instance.id}: {e}")


# Сигналы для задолженности
@receiver(post_save, sender='billing.Debt')
def handle_debt_notifications(sender, instance, created, **kwargs):
    """
    Обрабатывает уведомления о задолженности.
    
    Args:
        sender: Модель отправителя сигнала
        instance: Экземпляр задолженности
        created: Создана ли задолженность
        **kwargs: Дополнительные аргументы
    """
    try:
        if created or instance.amount > 0:
            # Отправляем уведомление о задолженности
            send_debt_reminder_task.delay(
                user_id=instance.user.id,
                debt_amount=instance.amount,
                currency=instance.currency or 'EUR'
            )
            
            logger.info(f"Debt reminder task queued for user {instance.user.id}")
            
    except Exception as e:
        logger.error(f"Failed to handle debt notification for debt {instance.id}: {e}") 