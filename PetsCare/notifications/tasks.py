"""
Задачи Celery для работы с уведомлениями.

Этот модуль содержит задачи для:
1. Асинхронной отправки уведомлений
2. Обработки запланированных уведомлений
3. Массовых рассылок
4. Очистки старых уведомлений
"""

import logging
from typing import List, Dict, Any
from datetime import timedelta
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db import models
from celery import shared_task
from .services import NotificationService, PreferenceService, SchedulerService
from .models import Notification, NotificationType

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_notification_task(
    self,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    channels: List[str] = None,
    priority: str = 'medium',
    pet_id: int = None,
    data: Dict[str, Any] = None
):
    """
    Задача для асинхронной отправки уведомления.
    
    Args:
        user_id: ID пользователя-получателя
        notification_type: Тип уведомления
        title: Заголовок уведомления
        message: Текст уведомления
        channels: Каналы доставки
        priority: Приоритет уведомления
        pet_id: ID связанного питомца
        data: Дополнительные данные
    """
    try:
        from django.contrib.auth import get_user_model
        from pets.models import Pet
        
        User = get_user_model()
        
        user = User.objects.get(id=user_id)
        pet = Pet.objects.get(id=pet_id) if pet_id else None
        
        notification_service = NotificationService()
        notification = notification_service.send_notification(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            channels=channels,
            priority=priority,
            pet=pet,
            data=data
        )
        
        logger.info(f"Successfully sent notification {notification.id} to user {user_id}")
        
    except Exception as exc:
        logger.error(f"Failed to send notification to user {user_id}: {exc}")
        
        # Повторная попытка с экспоненциальной задержкой
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def send_bulk_notifications_task(
    user_ids: List[int],
    notification_type: str,
    title: str,
    message: str,
    channels: List[str] = None,
    priority: str = 'medium',
    data: Dict[str, Any] = None
):
    """
    Задача для массовой отправки уведомлений.
    
    Args:
        user_ids: Список ID пользователей
        notification_type: Тип уведомления
        title: Заголовок уведомления
        message: Текст уведомления
        channels: Каналы доставки
        priority: Приоритет уведомления
        data: Дополнительные данные
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        users = User.objects.filter(id__in=user_ids)
        
        notification_service = NotificationService()
        notifications = notification_service.send_bulk_notifications(
            users=users,
            notification_type=notification_type,
            title=title,
            message=message,
            channels=channels,
            priority=priority,
            data=data
        )
        
        logger.info(f"Successfully sent {len(notifications)} bulk notifications")
        
    except Exception as e:
        logger.error(f"Failed to send bulk notifications: {e}")


@shared_task
def process_scheduled_notifications_task():
    """
    Задача для обработки запланированных уведомлений.
    Должна выполняться периодически (например, каждую минуту).
    """
    try:
        scheduler_service = SchedulerService()
        scheduler_service.process_scheduled_notifications()
        
        logger.info("Successfully processed scheduled notifications")
        
    except Exception as e:
        logger.error(f"Failed to process scheduled notifications: {e}")


@shared_task
def schedule_booking_reminders_task(booking_id: int):
    """
    Задача для планирования напоминаний о бронировании.
    
    Args:
        booking_id: ID бронирования
    """
    try:
        from booking.models import Booking
        
        booking = Booking.objects.get(id=booking_id)
        
        scheduler_service = SchedulerService()
        scheduler_service.schedule_booking_reminders(booking)
        
        logger.info(f"Successfully scheduled reminders for booking {booking_id}")
        
    except Exception as e:
        logger.error(f"Failed to schedule reminders for booking {booking_id}: {e}")


@shared_task
def send_email_verification_task(user_id: int, verification_token: str):
    """
    Задача для отправки email верификации.
    
    Args:
        user_id: ID пользователя
        verification_token: Токен верификации
    """
    try:
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        from django.conf import settings
        
        User = get_user_model()
        user = User.objects.get(id=user_id)
        
        # Формируем ссылку для верификации
        verification_url = f"{settings.SITE_URL}{reverse('verify_email', kwargs={'token': verification_token})}"
        
        notification_service = NotificationService()
        notification = notification_service.send_notification(
            user=user,
            notification_type='email_verification',
            title=_('Verify Your Email Address'),
            message=_('Please click the link to verify your email address: ') + verification_url,
            channels=['email'],
            priority='high',
            data={'verification_token': verification_token}
        )
        
        logger.info(f"Email verification sent to user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to send email verification to user {user_id}: {e}")


@shared_task
def send_password_reset_task(user_id: int, reset_token: str):
    """
    Задача для отправки email сброса пароля.
    
    Args:
        user_id: ID пользователя
        reset_token: Токен сброса пароля
    """
    try:
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        from django.conf import settings
        
        User = get_user_model()
        user = User.objects.get(id=user_id)
        
        # Формируем ссылку для сброса пароля
        reset_url = f"{settings.SITE_URL}{reverse('password_reset_confirm', kwargs={'token': reset_token})}"
        
        notification_service = NotificationService()
        notification = notification_service.send_notification(
            user=user,
            notification_type='password_reset',
            title=_('Password Reset Request'),
            message=_('Click the link to reset your password: ') + reset_url,
            channels=['email'],
            priority='high',
            data={'reset_token': reset_token}
        )
        
        logger.info(f"Password reset email sent to user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to send password reset email to user {user_id}: {e}")


@shared_task
def send_role_invite_task(invite_id: int):
    """
    Задача для отправки уведомления о приглашении роли.
    
    Args:
        invite_id: ID приглашения
    """
    try:
        from users.models import RoleInvite
        
        invite = RoleInvite.objects.get(id=invite_id)
        
        notification_service = NotificationService()
        
        # Отправляем уведомление получателю
        notification = notification_service.send_notification(
            user=invite.invitee,
            notification_type='role_invite',
            title=_('New Role Invitation'),
            message=_('You have been invited to join as ') + invite.role.name,
            channels=['email', 'push', 'in_app'],
            priority='high',
            data={'invite_id': invite.id, 'role_name': invite.role.name}
        )
        
        logger.info(f"Role invite notification sent to user {invite.invitee.id}")
        
    except Exception as e:
        logger.error(f"Failed to send role invite notification for invite {invite_id}: {e}")


@shared_task
def send_role_invite_response_task(invite_id: int, accepted: bool):
    """
    Задача для отправки уведомления о принятии/отклонении приглашения роли.
    
    Args:
        invite_id: ID приглашения
        accepted: Принято ли приглашение
    """
    try:
        from users.models import RoleInvite
        
        invite = RoleInvite.objects.get(id=invite_id)
        
        notification_service = NotificationService()
        
        if accepted:
            title = _('Role Invitation Accepted')
            message = f"{invite.invitee.get_full_name()} accepted your invitation to join as {invite.role.name}"
        else:
            title = _('Role Invitation Declined')
            message = f"{invite.invitee.get_full_name()} declined your invitation to join as {invite.role.name}"
        
        notification = notification_service.send_notification(
            user=invite.inviter,
            notification_type='role_invite',
            title=title,
            message=message,
            channels=['email', 'push', 'in_app'],
            priority='medium',
            data={'invite_id': invite.id, 'accepted': accepted}
        )
        
        logger.info(f"Role invite response notification sent to user {invite.inviter.id}")
        
    except Exception as e:
        logger.error(f"Failed to send role invite response notification for invite {invite_id}: {e}")


@shared_task
def cleanup_old_notifications_task(days: int = 30):
    """
    Задача для очистки старых уведомлений.
    
    Args:
        days: Количество дней для хранения уведомлений
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Удаляем прочитанные уведомления старше указанного количества дней
        deleted_count = Notification.objects.filter(
            is_read=True,
            created_at__lt=cutoff_date
        ).delete()[0]
        
        logger.info(f"Cleaned up {deleted_count} old notifications")
        
    except Exception as e:
        logger.error(f"Failed to cleanup old notifications: {e}")


@shared_task
def process_reminders_task():
    """
    Задача для обработки напоминаний о процедурах питомцев.
    Должна выполняться ежедневно.
    """
    try:
        from .models import Reminder
        
        now = timezone.now()
        due_reminders = Reminder.objects.filter(
            is_active=True,
            next_notification__lte=now
        )
        
        notification_service = NotificationService()
        
        for reminder in due_reminders:
            try:
                # Отправляем уведомление владельцу питомца
                notification = notification_service.send_notification(
                    user=reminder.pet.owner,
                    notification_type='reminder',
                    title=reminder.title,
                    message=reminder.description,
                    channels=['email', 'push', 'in_app'],
                    priority='medium',
                    pet=reminder.pet,
                    data={'reminder_id': reminder.id, 'service_name': reminder.service.name}
                )
                
                # Обновляем время последнего уведомления и следующего
                reminder.last_notified = now
                reminder.next_notification = reminder.calculate_next_notification()
                reminder.save()
                
                logger.info(f"Reminder notification sent for reminder {reminder.id}")
                
            except Exception as e:
                logger.error(f"Failed to process reminder {reminder.id}: {e}")
        
        logger.info(f"Processed {due_reminders.count()} reminders")
        
    except Exception as e:
        logger.error(f"Failed to process reminders: {e}")


@shared_task
def send_booking_confirmation_task(booking_id: int):
    """
    Задача для отправки подтверждения бронирования.
    
    Args:
        booking_id: ID бронирования
    """
    try:
        from booking.models import Booking
        
        booking = Booking.objects.get(id=booking_id)
        
        notification_service = NotificationService()
        notification = notification_service.send_notification(
            user=booking.user,
            notification_type='booking',
            title=_('Booking Confirmation'),
            message=_('Your booking has been confirmed'),
            channels=['email', 'push', 'in_app'],
            priority='medium',
            pet=booking.pet,
            data={'booking_id': booking.id, 'service_name': booking.service.name}
        )
        
        logger.info(f"Booking confirmation sent for booking {booking_id}")
        
    except Exception as e:
        logger.error(f"Failed to send booking confirmation for booking {booking_id}: {e}")


@shared_task
def send_booking_cancellation_task(booking_id: int, reason: str = None):
    """
    Задача для отправки уведомления об отмене бронирования.
    
    Args:
        booking_id: ID бронирования
        reason: Причина отмены
    """
    try:
        from booking.models import Booking

        booking = Booking.objects.get(id=booking_id)

        message = _('Your booking has been cancelled')
        if reason:
            message += f": {reason}"
        
        notification_service = NotificationService()
        notification = notification_service.send_notification(
            user=booking.user,
            notification_type='cancellation',
            title=_('Booking Cancelled'),
            message=message,
            channels=['email', 'push', 'in_app'],
            priority='high',
            pet=booking.pet,
            data={'booking_id': booking.id, 'reason': reason}
        )
        
        logger.info(f"Booking cancellation notification sent for booking {booking_id}")
        
    except Exception as e:
        logger.error(f"Failed to send booking cancellation notification for booking {booking_id}: {e}")


@shared_task
def send_debt_reminder_task(user_id: int, debt_amount: float, currency: str = 'EUR'):
    """
    Задача для отправки уведомления о задолженности.
    
    Args:
        user_id: ID пользователя
        debt_amount: Сумма задолженности
        currency: Валюта
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = User.objects.get(id=user_id)
        
        notification_service = NotificationService()
        notification = notification_service.send_notification(
            user=user,
            notification_type='system',
            title=_('Payment Reminder'),
            message=_('You have outstanding payments. Please settle your debt to continue using our services.'),
            channels=['email', 'push', 'in_app'],
            priority='high',
            data={'debt_amount': debt_amount, 'currency': currency}
        )
        
        logger.info(f"Debt reminder sent to user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to send debt reminder to user {user_id}: {e}")



@shared_task
def send_new_review_notification_task(review_id: int):
    """
    Задача для отправки уведомления о новом отзыве.
    
    Args:
        review_id: ID отзыва
    """
    try:
        from ratings.models import Review
        
        review = Review.objects.get(id=review_id)
        
        notification_service = NotificationService()
        
        # Отправляем уведомление провайдеру о новом отзыве
        notification = notification_service.send_notification(
            user=review.provider.owner,
            notification_type='review',
            title=_('New Review Received'),
            message=_('You have received a new review for your service.'),
            channels=['email', 'push', 'in_app'],
            priority='medium',
            data={
                'review_id': review.id,
                'rating': review.rating,
                'service_name': review.service.name,
                'client_name': review.user.get_full_name() or review.user.email
            }
        )
        
        logger.info(f"New review notification sent for review {review_id}")
        
    except Exception as e:
        logger.error(f"Failed to send new review notification for review {review_id}: {e}")


@shared_task
def send_role_invite_expired_task(invite_id: int):
    """
    Задача для отправки уведомления об истечении инвайта роли.
    
    Args:
        invite_id: ID инвайта
    """
    try:
        from users.models import RoleInvite
        
        invite = RoleInvite.objects.get(id=invite_id)
        
        notification_service = NotificationService()
        
        # Отправляем уведомление создателю инвайта об истечении
        notification = notification_service.send_notification(
            user=invite.inviter,
            notification_type='role_invite',
            title=_('Role Invitation Expired'),
            message=_('A role invitation you sent has expired.'),
            channels=['email', 'push', 'in_app'],
            priority='medium',
            data={
                'invite_id': invite.id,
                'invitee_name': invite.invitee.get_full_name() or invite.invitee.email,
                'role_name': invite.role.name,
                'provider_name': invite.provider.name
            }
        )
        
        logger.info(f"Role invite expired notification sent for invite {invite_id}")
        
    except Exception as e:
        logger.error(f"Failed to send role invite expired notification for invite {invite_id}: {e}")


@shared_task
def send_pet_sitting_notification_task(sitting_id: int, status: str):
    """
    Задача для отправки уведомления о передержке питомца.
    
    Args:
        sitting_id: ID передержки
        status: Статус передержки
    """
    try:
        from sitters.models import PetSitting
        
        sitting = PetSitting.objects.get(id=sitting_id)
        
        notification_service = NotificationService()
        
        # Отправляем уведомление владельцу питомца
        notification = notification_service.send_notification(
            user=sitting.pet.owner,
            notification_type='pet_sitting',
            title=_('Pet Sitting Update'),
            message=_('Your pet sitting status has been updated.'),
            channels=['email', 'push', 'in_app'],
            priority='medium',
            pet=sitting.pet,
            data={
                'sitting_id': sitting.id,
                'status': status,
                'sitter_name': sitting.sitter.get_full_name() or sitting.sitter.email,
                'start_date': sitting.start_date.isoformat(),
                'end_date': sitting.end_date.isoformat()
            }
        )
        
        logger.info(f"Pet sitting notification sent for sitting {sitting_id}")
        
    except Exception as e:
        logger.error(f"Failed to send pet sitting notification for sitting {sitting_id}: {e}")


@shared_task
def send_payment_failed_notification_task(payment_id: int, reason: str = None):
    """
    Задача для отправки уведомления о неудачном платеже.
    
    Args:
        payment_id: ID платежа
        reason: Причина неудачи
    """
    try:
        from billing.models import Payment
        
        payment = Payment.objects.get(id=payment_id)
        
        notification_service = NotificationService()
        
        notification = notification_service.send_notification(
            user=payment.user,
            notification_type='payment',
            title=_('Payment Failed'),
            message=_('Your payment could not be processed. Please check your payment method.'),
            channels=['email', 'push', 'in_app'],
            priority='high',
            data={
                'payment_id': payment.id,
                'amount': payment.amount,
                'currency': payment.currency,
                'reason': reason
            }
        )
        
        logger.info(f"Payment failed notification sent for payment {payment_id}")
        
    except Exception as e:
        logger.error(f"Failed to send payment failed notification for payment {payment_id}: {e}")


@shared_task
def send_refund_notification_task(refund_id: int):
    """
    Задача для отправки уведомления о возврате средств.
    
    Args:
        refund_id: ID возврата
    """
    try:
        from billing.models import Refund
        
        refund = Refund.objects.get(id=refund_id)
        
        notification_service = NotificationService()
        
        notification = notification_service.send_notification(
            user=refund.payment.user,
            notification_type='payment',
            title=_('Refund Processed'),
            message=_('Your refund has been processed and will be credited to your account.'),
            channels=['email', 'push', 'in_app'],
            priority='medium',
        data={
                'refund_id': refund.id,
                'amount': refund.amount,
                'currency': refund.currency,
                'payment_id': refund.payment.id
            }
        )
        
        logger.info(f"Refund notification sent for refund {refund_id}")
        
    except Exception as e:
        logger.error(f"Failed to send refund notification for refund {refund_id}: {e}")


@shared_task
def send_system_maintenance_notification_task(message: str, user_ids: List[int] = None):
    """
    Задача для отправки системных уведомлений о техническом обслуживании.
    
    Args:
        message: Сообщение о техническом обслуживании
        user_ids: Список ID пользователей (если None, отправляется всем)
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        if user_ids:
            users = User.objects.filter(id__in=user_ids)
        else:
            users = User.objects.filter(is_active=True)
        
        notification_service = NotificationService()
        
        for user in users:
            try:
                notification = notification_service.send_notification(
                    user=user,
                    notification_type='system',
                    title=_('System Maintenance'),
                    message=message,
                    channels=['email', 'push', 'in_app'],
                    priority='high',
                    data={'maintenance': True}
                )
                
                logger.info(f"System maintenance notification sent to user {user.id}")
                
            except Exception as e:
                logger.error(f"Failed to send system maintenance notification to user {user.id}: {e}")
                continue
        
    except Exception as e:
        logger.error(f"Failed to send system maintenance notifications: {e}")


@shared_task
def send_upcoming_booking_reminders_task():
    """
    Задача для отправки индивидуальных напоминаний о предстоящих бронированиях.
    Проверяет каждые 15 минут, какие бронирования требуют напоминания,
    учитывая индивидуальные настройки пользователей.
    """
    try:
        from booking.models import Booking
        from django.utils import timezone
        from django.contrib.auth import get_user_model
        from .models import ReminderSettings
        
        User = get_user_model()
        notification_service = NotificationService()
        now = timezone.now()
        
        # Получаем все активные бронирования в будущем
        upcoming_bookings = Booking.objects.filter(
            start_time__gt=now,
            status='confirmed'
        ).select_related('user', 'service', 'provider', 'pet')
        
        reminders_sent = 0
        
        for booking in upcoming_bookings:
            try:
                # Получаем настройки напоминаний пользователя
                reminder_settings, created = ReminderSettings.objects.get_or_create(
                    user=booking.user,
                    defaults={
                        'reminder_time_before_booking': 120,  # 2 часа по умолчанию
                        'multiple_reminders': False,
                        'is_active': True
                    }
                )
                
                # Проверяем, нужно ли отправить напоминание
                if reminder_settings.should_send_reminder(booking.start_time):
                    # Получаем время последнего напоминания для этого бронирования
                    last_reminder = Notification.objects.filter(
                        user=booking.user,
                        notification_type='reminder',
                        data__booking_id=booking.id
                    ).order_by('-created_at').first()
                    
                    last_reminder_time = last_reminder.created_at if last_reminder else None
                    
                    # Проверяем еще раз с учетом последнего напоминания
                    if reminder_settings.should_send_reminder(booking.start_time, last_reminder_time):
                        # Вычисляем время до бронирования
                        time_until_booking = booking.start_time - now
                        hours_until_booking = int(time_until_booking.total_seconds() / 3600)
                        minutes_until_booking = int(time_until_booking.total_seconds() / 60)
                        
                        # Формируем сообщение в зависимости от времени
                        if hours_until_booking >= 24:
                            days = hours_until_booking // 24
                            time_text = _('{} days').format(days)
                        elif hours_until_booking >= 1:
                            time_text = _('{} hours').format(hours_until_booking)
                        else:
                            time_text = _('{} minutes').format(minutes_until_booking)
                        
                        # Отправляем напоминание
                        notification = notification_service.send_notification(
                            user=booking.user,
                            notification_type='reminder',
                            title=_('Upcoming Booking Reminder'),
                            message=_('Your booking for {} is in {}').format(
                                booking.service.name, time_text
                            ),
                            channels=['email', 'push', 'in_app'],
                            priority='medium',
                            pet=booking.pet,
                            data={
                                'booking_id': booking.id,
                                'service_name': booking.service.name,
                                'provider_name': booking.provider.name,
                                'start_time': booking.start_time.isoformat(),
                                'time_until_booking': time_until_booking.total_seconds(),
                                'reminder_type': 'upcoming_booking'
                            }
                        )
                        
                        reminders_sent += 1
                        logger.info(f"Booking reminder sent to user {booking.user.id} for booking {booking.id}")
                
            except Exception as e:
                logger.error(f"Failed to process reminder for booking {booking.id}: {e}")
                continue
        
        logger.info(f"Processed {upcoming_bookings.count()} bookings, sent {reminders_sent} reminders")
        
    except Exception as e:
        logger.error(f"Failed to process booking reminders: {e}")


@shared_task
def schedule_individual_booking_reminders_task(booking_id: int):
    """
    Задача для планирования индивидуальных напоминаний о конкретном бронировании.
    
    Args:
        booking_id: ID бронирования
    """
    try:
        from booking.models import Booking
        from django.utils import timezone
        from .models import ReminderSettings
        
        booking = Booking.objects.get(id=booking_id)
        
        # Получаем настройки напоминаний пользователя
        reminder_settings, created = ReminderSettings.objects.get_or_create(
            user=booking.user,
            defaults={
                'reminder_time_before_booking': 120,  # 2 часа по умолчанию
                'multiple_reminders': False,
                'is_active': True
            }
        )
        
        if not reminder_settings.is_active:
            logger.info(f"Reminder settings disabled for user {booking.user.id}")
            return
        
        # Вычисляем время следующего напоминания
        next_reminder_time = reminder_settings.get_next_reminder_time(booking.start_time)
        
        if next_reminder_time:
            # Планируем задачу на отправку напоминания
            from celery import current_app
            
            # Вычисляем задержку в секундах
            delay_seconds = int((next_reminder_time - timezone.now()).total_seconds())
            
            if delay_seconds > 0:
                # Планируем отправку напоминания
                send_individual_booking_reminder_task.apply_async(
                    args=[booking.id],
                    countdown=delay_seconds
                )
                
                logger.info(f"Scheduled reminder for booking {booking.id} at {next_reminder_time}")
            else:
                logger.info(f"Reminder time for booking {booking.id} has already passed")
        else:
            logger.info(f"No reminder needed for booking {booking.id}")
        
    except Exception as e:
        logger.error(f"Failed to schedule reminder for booking {booking_id}: {e}")


@shared_task
def send_individual_booking_reminder_task(booking_id: int):
    """
    Задача для отправки индивидуального напоминания о конкретном бронировании.
    
    Args:
        booking_id: ID бронирования
    """
    try:
        from booking.models import Booking
        from django.utils import timezone
        from .models import ReminderSettings
        
        booking = Booking.objects.get(id=booking_id)
        
        # Проверяем, что бронирование все еще активно
        if booking.status != 'confirmed':
            logger.info(f"Booking {booking_id} is no longer confirmed, skipping reminder")
            return
        
        # Получаем настройки напоминаний пользователя
        reminder_settings = ReminderSettings.objects.filter(user=booking.user).first()
        
        if not reminder_settings or not reminder_settings.is_active:
            logger.info(f"Reminder settings disabled for user {booking.user.id}")
            return
        
        # Проверяем, нужно ли отправить напоминание
        if reminder_settings.should_send_reminder(booking.start_time):
            notification_service = NotificationService()
            
            # Вычисляем время до бронирования
            time_until_booking = booking.start_time - timezone.now()
            hours_until_booking = int(time_until_booking.total_seconds() / 3600)
            minutes_until_booking = int(time_until_booking.total_seconds() / 60)
            
            # Формируем сообщение в зависимости от времени
            if hours_until_booking >= 24:
                days = hours_until_booking // 24
                time_text = _('{} days').format(days)
            elif hours_until_booking >= 1:
                time_text = _('{} hours').format(hours_until_booking)
            else:
                time_text = _('{} minutes').format(minutes_until_booking)
            
            # Отправляем напоминание
            notification = notification_service.send_notification(
                user=booking.user,
                notification_type='reminder',
                title=_('Booking Reminder'),
                message=_('Your booking for {} is in {}').format(
                    booking.service.name, time_text
                ),
                channels=['email', 'push', 'in_app'],
                priority='medium',
                pet=booking.pet,
                data={
                    'booking_id': booking.id,
                    'service_name': booking.service.name,
                    'provider_name': booking.provider.name,
                    'start_time': booking.start_time.isoformat(),
                    'time_until_booking': time_until_booking.total_seconds(),
                    'reminder_type': 'individual_booking'
                }
            )
            
            logger.info(f"Individual booking reminder sent to user {booking.user.id} for booking {booking.id}")
            
            # Планируем следующее напоминание, если включены множественные
            if reminder_settings.multiple_reminders:
                schedule_individual_booking_reminders_task.delay(booking.id)
        
    except Exception as e:
        logger.error(f"Failed to send individual reminder for booking {booking_id}: {e}") 