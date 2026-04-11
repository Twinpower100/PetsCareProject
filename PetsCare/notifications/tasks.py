"""
Задачи Celery для работы с уведомлениями.

Этот модуль содержит задачи для:
1. Асинхронной отправки уведомлений
2. Обработки запланированных уведомлений
3. Массовых рассылок
4. Очистки старых уведомлений
"""

from datetime import timedelta
import logging
from typing import Any, Dict, List

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext as _
from celery import shared_task
from .services import NotificationService, SchedulerService
from .models import Notification
from .periodic_procedure_reminders import PeriodicProcedureReminderService
from .upcoming_booking_reminders import UpcomingBookingReminderService

logger = logging.getLogger(__name__)
User = get_user_model()

try:
    from ratings.models import Review
except Exception:
    Review = None

try:
    from sitters.models import PetSitting
except Exception:
    PetSitting = None

try:
    from billing.models import Payment, Refund
except Exception:
    Payment = None
    Refund = None


def _get_pet_owner(pet):
    """Возвращает владельца питомца для старых и новых моделей."""
    return getattr(pet, 'owner', None) or getattr(pet, 'main_owner', None)


def _get_review_author(review):
    """Возвращает автора отзыва с обратной совместимостью по старым полям."""
    return getattr(review, 'user', None) or getattr(review, 'author', None)


def _get_provider_owner(provider):
    """Возвращает owner провайдера, даже если он не хранится прямым FK."""
    owner = getattr(provider, 'owner', None)
    if owner is not None:
        return owner

    try:
        from providers.models import EmployeeProvider
        owner_link = EmployeeProvider.objects.select_related('employee__user').filter(
            provider=provider,
            is_owner=True,
        ).first()
        if owner_link is not None:
            return owner_link.employee.user
    except Exception:
        return None
    return None


def _get_payment_user(payment):
    """Возвращает пользователя из текущей модели платежа (при наличии)."""
    return getattr(payment, 'user', None)


def _get_payment_currency(payment):
    """Возвращает код/значение валюты, если оно доступно в модели."""
    currency = getattr(payment, 'currency', None)
    if hasattr(currency, 'code'):
        return currency.code
    return currency


@shared_task(bind=True, max_retries=3)
def send_notification_task(
    self,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    channels: List[str] | None = None,
    priority: str = 'medium',
    pet_id: int | None = None,
    data: Dict[str, Any] | None = None
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
    channels: List[str] | None = None,
    priority: str = 'medium',
    data: Dict[str, Any] | None = None
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
        
        users = list(User.objects.filter(id__in=user_ids))
        
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
        notification_service.send_notification(
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
        notification_service.send_notification(
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
def process_reminders_task(reference_time=None):
    """
    Задача для обработки напоминаний о процедурах питомцев.
    Должна выполняться ежедневно.
    """
    try:
        results = PeriodicProcedureReminderService().send_due_reminders(reference_time=reference_time)
        logger.info(
            "Processed %s periodic procedure records and sent %s reminders",
            results['processed_count'],
            results['sent_count'],
        )
        return results
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
        notification_service.send_notification(
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
def send_booking_cancellation_task(booking_id: int, reason: str | None = None):
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
        notification_service.send_notification(
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
        user = User.objects.get(id=user_id)
        
        notification_service = NotificationService()
        notification_service.send_notification(
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
        review_model = Review
        if review_model is None:
            from ratings.models import Review as review_model

        review = review_model.objects.get(id=review_id)
        review_author = _get_review_author(review)
        provider_owner = _get_provider_owner(review.provider)

        notification_service = NotificationService()
        
        # Отправляем уведомление провайдеру о новом отзыве
        notification_service.send_notification(
            user=provider_owner,
            notification_type='review',
            title=_('New Review Received'),
            message=_('You have received a new review for your service.'),
            channels=['email', 'push', 'in_app'],
            priority='medium',
            data={
                'review_id': review.id,
                'rating': review.rating,
                'service_name': review.service.name,
                'client_name': review_author.get_full_name() or review_author.email
            }
        )
        
        logger.info(f"New review notification sent for review {review_id}")
        
    except Exception as e:
        logger.error(f"Failed to send new review notification for review {review_id}: {e}")


@shared_task
def send_invite_created_task(invite_id: int):
    """
    Универсальная задача: уведомление о создании инвайта (invites.Invite).
    Отправляется приглашённому (по email).
    """
    try:
        from invites.models import Invite
        from users.models import User
        invite = Invite.objects.select_related('provider', 'provider_location', 'pet', 'created_by').get(id=invite_id)
        try:
            invitee = User.objects.get(email__iexact=invite.email)
        except User.DoesNotExist:
            logger.info(f"Invite {invite_id} for non-existing user {invite.email}, skip in-app notification")
            return
        notification_service = NotificationService()
        title = _('New Invitation')
        message = _('You have been invited. Check your email for the activation code.')
        notification_service.send_notification(
            user=invitee,
            notification_type='role_invite',
            title=title,
            message=message,
            channels=['email', 'push', 'in_app'],
            priority='high',
            data={'invite_id': invite.id, 'invite_type': invite.invite_type}
        )
        logger.info(f"Invite created notification sent for invite {invite_id}")
    except Invite.DoesNotExist:
        logger.warning(f"Invite {invite_id} not found for send_invite_created_task")
    except Exception as e:
        logger.error(f"Failed to send invite created notification for invite {invite_id}: {e}")


@shared_task
def send_invite_response_task(invite_id: int, accepted: bool):
    """
    Универсальная задача: уведомление создателю о принятии/отклонении инвайта (invites.Invite).
    """
    try:
        from invites.models import Invite
        from users.models import User
        invite = Invite.objects.select_related('provider', 'created_by').get(id=invite_id)
        if not invite.created_by_id:
            return
        notification_service = NotificationService()
        try:
            accepted_user = User.objects.get(email__iexact=invite.email)
            name = accepted_user.get_full_name() or invite.email
        except User.DoesNotExist:
            name = invite.email
        if accepted:
            title = _('Invitation Accepted')
            message = _('%(email)s accepted your invitation.') % {'email': name}
        else:
            title = _('Invitation Declined')
            message = _('%(email)s declined your invitation.') % {'email': name}
        notification_service.send_notification(
            user=invite.created_by,
            notification_type='role_invite',
            title=title,
            message=message,
            channels=['email', 'push', 'in_app'],
            priority='medium',
            data={'invite_id': invite.id, 'accepted': accepted}
        )
        logger.info(f"Invite response notification sent for invite {invite_id}")
    except Invite.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f"Failed to send invite response notification for invite {invite_id}: {e}")


@shared_task
def send_invite_expired_task(invite_id: int):
    """
    Универсальная задача: уведомление создателю об истечении инвайта (invites.Invite).
    """
    try:
        from invites.models import Invite
        invite = Invite.objects.select_related('created_by').get(id=invite_id)
        if not invite.created_by_id:
            return
        notification_service = NotificationService()
        notification_service.send_notification(
            user=invite.created_by,
            notification_type='role_invite',
            title=_('Invitation Expired'),
            message=_('An invitation you sent has expired.'),
            channels=['email', 'push', 'in_app'],
            priority='medium',
            data={'invite_id': invite.id}
        )
        logger.info(f"Invite expired notification sent for invite {invite_id}")
    except Invite.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f"Failed to send invite expired notification for invite {invite_id}: {e}")


@shared_task
def send_pet_sitting_notification_task(sitting_id: int, status: str):
    """
    Задача для отправки уведомления о передержке питомца.
    
    Args:
        sitting_id: ID передержки
        status: Статус передержки
    """
    try:
        sitting_model = PetSitting
        if sitting_model is None:
            from sitters.models import PetSitting as sitting_model

        sitting = sitting_model.objects.get(id=sitting_id)
        
        notification_service = NotificationService()
        
        # Отправляем уведомление владельцу питомца
        notification_service.send_notification(
            user=_get_pet_owner(sitting.pet),
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
def send_payment_failed_notification_task(payment_id: int, reason: str | None = None):
    """
    Задача для отправки уведомления о неудачном платеже.
    
    Args:
        payment_id: ID платежа
        reason: Причина неудачи
    """
    try:
        payment_model = Payment
        if payment_model is None:
            from billing.models import Payment as payment_model

        payment = payment_model.objects.get(id=payment_id)
        
        notification_service = NotificationService()
        
        notification_service.send_notification(
            user=_get_payment_user(payment),
            notification_type='payment',
            title=_('Payment Failed'),
            message=_('Your payment could not be processed. Please check your payment method.'),
            channels=['email', 'push', 'in_app'],
            priority='high',
            data={
                'payment_id': payment.id,
                'amount': payment.amount,
                'currency': _get_payment_currency(payment),
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
        refund_model = Refund
        if refund_model is None:
            from billing.models import Refund as refund_model

        refund = refund_model.objects.get(id=refund_id)
        
        notification_service = NotificationService()
        
        notification_service.send_notification(
            user=_get_payment_user(refund.payment),
            notification_type='payment',
            title=_('Refund Processed'),
            message=_('Your refund has been processed and will be credited to your account.'),
            channels=['email', 'push', 'in_app'],
            priority='medium',
            data={
                'refund_id': refund.id,
                'amount': refund.amount,
                'currency': _get_payment_currency(refund),
                'payment_id': refund.payment.id
            }
        )
        
        logger.info(f"Refund notification sent for refund {refund_id}")
        
    except Exception as e:
        logger.error(f"Failed to send refund notification for refund {refund_id}: {e}")


@shared_task
def send_system_maintenance_notification_task(message: str, user_ids: List[int] | None = None):
    """
    Задача для отправки системных уведомлений о техническом обслуживании.
    
    Args:
        message: Сообщение о техническом обслуживании
        user_ids: Список ID пользователей (если None, отправляется всем)
    """
    try:
        if user_ids:
            users = User.objects.filter(id__in=user_ids)
        else:
            users = User.objects.filter(is_active=True)
        
        notification_service = NotificationService()
        
        for user in users:
            try:
                notification_service.send_notification(
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
    Отправляет due email reminder по будущим active-бронированиям.
    """
    try:
        results = UpcomingBookingReminderService().send_due_reminders()
        logger.info(
            "Processed %s active upcoming bookings and sent %s reminders",
            results['processed_count'],
            results['sent_count'],
        )
        return results
    except Exception as e:
        logger.error(f"Failed to process booking reminders: {e}")


@shared_task
def schedule_individual_booking_reminders_task(booking_id: int):
    """
    Совместимый entry point для получения следующего reminder time.
    """
    try:
        next_reminder_time = UpcomingBookingReminderService().get_next_reminder_time_for_booking(booking_id)
        if next_reminder_time is None:
            logger.info("No upcoming reminder is scheduled for booking %s", booking_id)
            return

        logger.info(
            "Upcoming reminder for booking %s is expected at %s",
            booking_id,
            next_reminder_time.isoformat(),
        )
        return next_reminder_time.isoformat()
    except Exception as e:
        logger.error(f"Failed to schedule reminder for booking {booking_id}: {e}")


@shared_task
def send_individual_booking_reminder_task(booking_id: int):
    """
    Совместимый entry point для отправки reminder одного booking через единый MVP flow.
    """
    try:
        sent_count = UpcomingBookingReminderService().send_due_reminders_for_booking(booking_id)
        logger.info(
            "Processed individual upcoming reminder flow for booking %s, sent %s reminders",
            booking_id,
            sent_count,
        )
        return sent_count
    except Exception as e:
        logger.error(f"Failed to send individual reminder for booking {booking_id}: {e}") 
