from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from .models import Booking, BookingPayment, BookingReview
from django.core.mail import send_mail
from django.conf import settings

@receiver(pre_save, sender=Booking)
def validate_booking_time(sender, instance, **kwargs):
    """
    Проверка корректности времени бронирования перед сохранением.
    """
    if instance.start_time >= instance.end_time:
        raise ValueError(_('End time must be after start time.'))

@receiver(post_save, sender=Booking)
def send_booking_confirmation(sender, instance, created, **kwargs):
    """
    Отправка подтверждения бронирования по электронной почте.
    """
    if created:
        subject = _('Booking Confirmation')
        message = _(
            'Your booking has been confirmed.\n\n'
            'Details:\n'
            'Pet: {pet}\n'
            'Provider: {provider}\n'
            'Service: {service}\n'
            'Start Time: {start_time}\n'
            'End Time: {end_time}\n'
            'Price: {price}\n\n'
            'Thank you for choosing our service!'
        ).format(
            pet=instance.pet.name,
            provider=instance.provider.name,
            service=instance.service.name,
            start_time=instance.start_time,
            end_time=instance.end_time,
            price=instance.price
        )
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [instance.user.email],
            fail_silently=False,
        )

@receiver(post_save, sender=BookingPayment)
def send_payment_confirmation(sender, instance, created, **kwargs):
    """
    Отправка подтверждения платежа по электронной почте.
    """
    if created and instance.status == 'completed':
        subject = _('Payment Confirmation')
        message = _(
            'Your payment has been processed successfully.\n\n'
            'Details:\n'
            'Booking ID: {booking_id}\n'
            'Amount: {amount}\n'
            'Payment Method: {payment_method}\n'
            'Status: {status}\n\n'
            'Thank you for your payment!'
        ).format(
            booking_id=instance.booking.id,
            amount=instance.amount,
            payment_method=instance.payment_method,
            status=instance.status
        )
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [instance.booking.user.email],
            fail_silently=False,
        )

@receiver(post_save, sender=BookingReview)
def send_review_notification(sender, instance, created, **kwargs):
    """
    Отправка уведомления о новом отзыве по электронной почте.
    """
    if created:
        subject = _('New Review Received')
        message = _(
            'A new review has been submitted for your service.\n\n'
            'Details:\n'
            'Booking ID: {booking_id}\n'
            'Rating: {rating}\n'
            'Comment: {comment}\n\n'
            'Thank you for your feedback!'
        ).format(
            booking_id=instance.booking.id,
            rating=instance.rating,
            comment=instance.comment
        )
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [instance.booking.provider.user.email],
            fail_silently=False,
        ) 