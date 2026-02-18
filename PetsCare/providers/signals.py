"""
Сигналы для автоматизации процессов провайдеров.

Содержит:
- Обработка деактивации локаций провайдеров
- Отмена бронирований при деактивации локации
- Отправка письма администратору провайдера при активации
"""

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)

# Словарь для хранения старых статусов провайдеров
_provider_old_statuses = {}


def handle_location_deactivation(sender, instance, **kwargs):
    """
    Обрабатывает деактивацию локации провайдера.
    
    При деактивации локации:
    - Отменяет все активные и будущие бронирования
    - Отправляет уведомления пользователям
    - Сохраняет историю бронирований
    """
    if instance.pk:
        try:
            # Получаем старую версию локации из базы данных
            old_instance = sender.objects.get(pk=instance.pk)
            
            # Проверяем, была ли локация активна и стала неактивной
            if old_instance.is_active and not instance.is_active:
                logger.info(f"Location {instance.id} ({instance.name}) is being deactivated. Cancelling bookings...")
                
                with transaction.atomic():
                    # Импортируем модели здесь, чтобы избежать циклических импортов
                    from booking.models import Booking, BookingStatus
                    from django.utils import timezone
                    
                    # Получаем статус "отменено"
                    cancelled_status, created = BookingStatus.objects.get_or_create(
                        name='cancelled',
                        defaults={'description': _('Booking cancelled')}
                    )
                    
                    # Находим все активные и будущие бронирования для этой локации
                    now = timezone.now()
                    active_bookings = Booking.objects.filter(
                        provider_location=instance,
                        status__name__in=['active', 'pending_confirmation', 'confirmed']
                    ).exclude(
                        start_time__lt=now  # Исключаем прошедшие бронирования
                    )
                    
                    cancelled_count = 0
                    for booking in active_bookings:
                        # Отменяем бронирование
                        booking.status = cancelled_status
                        # Добавляем сообщение о причине отмены
                        deactivation_note = _('Cancelled due to provider location deactivation.')
                        if booking.notes:
                            booking.notes = f"{booking.notes}\n{deactivation_note}"
                        else:
                            booking.notes = deactivation_note
                        booking.save()
                        cancelled_count += 1
                        
                        # TODO: Отправить уведомление пользователю
                        # from notifications.models import Notification
                        # Notification.objects.create(
                        #     user=booking.user,
                        #     title=_('Booking Cancelled'),
                        #     message=_('Your booking at {location} has been cancelled due to location deactivation.').format(
                        #         location=instance.name
                        #     ),
                        #     type='booking_cancelled'
                        # )
                        logger.info(f"Booking {booking.id} cancelled for location {instance.id}")
                    
                    logger.info(f"Location {instance.id} deactivated. {cancelled_count} bookings cancelled.")
                    
        except sender.DoesNotExist:
            # Локация создается впервые, ничего не делаем
            pass
        except Exception as e:
            logger.error(f"Error handling location deactivation for {instance.id}: {e}", exc_info=True)
            # Не прерываем сохранение, но логируем ошибку


@receiver(pre_save, sender='providers.Provider')
def store_provider_old_status(sender, instance, **kwargs):
    """
    Сохраняет старый статус провайдера перед сохранением.
    Используется для определения изменения статуса в post_save.
    """
    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            _provider_old_statuses[instance.pk] = old_instance.activation_status
        except sender.DoesNotExist:
            _provider_old_statuses[instance.pk] = None


@receiver(post_save, sender='providers.Provider')
def send_provider_activation_email(sender, instance, created, **kwargs):
    """
    Отправляет письмо при активации провайдера (manual activation).

    Примечание:
    - При акцепте оферты письма отправляются через `legal.DocumentAcceptance` (см. `billing/signals.py`).
    - Этот сигнал нужен для случая, когда провайдер переводится в `activation_status='active'` вручную (например, через админку).
    """
    # Импортируем здесь, чтобы избежать циклических импортов
    from users.models import ProviderAdmin
    
    # Пропускаем создание нового провайдера
    if created:
        return
    
    # Проверяем, что статус изменился на 'active'
    if instance.activation_status != 'active':
        # Очищаем сохраненный статус
        _provider_old_statuses.pop(instance.pk, None)
        return
    
    # Получаем старый статус из словаря
    old_status = _provider_old_statuses.pop(instance.pk, None)
    
    # Проверяем, что статус действительно изменился
    # old_status может быть None, если провайдер только что создан или статус не был сохранен
    if old_status == 'active' or old_status is None:
        # Статус уже был 'active' или провайдер только что создан
        return
    
    # Статус изменился на 'active' - отправляем письмо
    
    # Находим администратора провайдера
    try:
        provider_admin = ProviderAdmin.objects.filter(
            provider=instance,
            is_active=True
        ).select_related('user').first()
        
        if not provider_admin:
            logger.warning(f"Provider {instance.id} activated but no active admin found")
            return
        
        admin_user = provider_admin.user
        
        # Убеждаемся, что у админа есть роль provider_admin (на случай, если не назначена при одобрении заявки).
        # Доступ в приложение «Админка провайдеров» по API; is_staff для Django admin не выставляем.
        from users.models import UserType
        try:
            provider_admin_role = UserType.objects.get(name='provider_admin')
            if not admin_user.user_types.filter(name='provider_admin').exists():
                admin_user.user_types.add(provider_admin_role)
                logger.info(f"Assigned provider_admin role to {admin_user.email} during provider activation")
        except UserType.DoesNotExist:
            logger.warning(f"Provider admin role not found, cannot assign to {admin_user.email}")
        
        # Проверяем, что у провайдера есть email
        if not instance.email:
            logger.warning(f"Provider {instance.id} has no email")
            return
        
        from django.contrib.auth import get_user_model
        from users.models import ProviderForm
        User = get_user_model()
        
        # Собираем получателей (те же 3, что и при автоактивации): владелец заявки, админ провайдера, email провайдера
        recipients = []
        seen_emails = set()
        
        def add_recipient(email, user, is_admin):
            if not email or email.lower() in seen_emails:
                return
            seen_emails.add(email.lower())
            recipients.append({'email': email, 'user': user, 'is_admin': is_admin})
        
        # 1. Владелец заявки (created_by) — подавший заявку
        provider_form = ProviderForm.objects.filter(
            provider_email=instance.email
        ).order_by('-created_at').select_related('created_by').first()
        if provider_form and provider_form.created_by and provider_form.created_by.email:
            add_recipient(provider_form.created_by.email, provider_form.created_by, is_admin=True)
        
        # 2. Админ провайдера (admin_user)
        if admin_user.email:
            add_recipient(admin_user.email, admin_user, is_admin=True)
        
        # 3. Email провайдера (provider.email) — если ещё не добавлен
        if instance.email:
            try:
                provider_email_user = User.objects.get(email__iexact=instance.email)
            except User.DoesNotExist:
                provider_email_user = admin_user
            except User.MultipleObjectsReturned:
                provider_email_user = User.objects.filter(email__iexact=instance.email).first()
            add_recipient(instance.email, provider_email_user, is_admin=False)
        
        for recipient in recipients:
            _send_activation_email(instance, recipient['user'], recipient_email=recipient['email'], is_admin=recipient['is_admin'])
        
    except Exception as e:
        logger.error(f"Error sending activation email for provider {instance.id}: {e}", exc_info=True)
        # Не прерываем сохранение, но логируем ошибку


def _send_activation_email(provider, admin_user, recipient_email=None, is_admin=True):
    """
    Отправляет письмо администратору провайдера об активации.
    
    Args:
        provider: Объект Provider
        admin_user: Объект User (администратор провайдера, используется для контекста)
        recipient_email: Email получателя (по умолчанию используется provider.email)
        is_admin: True если получатель - админ провайдера (автор заявки), False если просто email провайдера
    """
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.conf import settings
    from billing.models import BillingManagerProvider
    
    # Проверяем, есть ли у пользователя пароль
    has_password = admin_user.has_usable_password()
    
    # Определяем способ входа
    login_method = 'password' if has_password else 'google'
    
    # Ссылка на приложение «Админка провайдеров» (не Django admin)
    admin_login_url = getattr(settings, 'PROVIDER_ADMIN_URL', 'http://localhost:5173')
    
    # Получаем URL инструкции на фронте
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    setup_guide_url = f"{frontend_url}/provider-setup-guide"
    
    # Получаем контакты billing_manager
    billing_manager_contacts = []
    try:
        active_managers = BillingManagerProvider.get_active_managers_for_provider(provider)
        for manager_provider in active_managers:
            effective_manager = manager_provider.get_effective_manager()
            if effective_manager and effective_manager.email:
                billing_manager_contacts.append({
                    'name': effective_manager.get_full_name() or effective_manager.email,
                    'email': effective_manager.email,
                })
    except Exception as e:
        logger.warning(f"Error getting billing manager contacts for provider {provider.id}: {e}")
    
    # Определяем email получателя (приоритет: recipient_email > provider.email)
    email_to = recipient_email or provider.email
    if not email_to:
        logger.error(f"Provider {provider.id} has no email and recipient_email not provided")
        return
    
    # Получаем информацию об админе провайдера (авторе заявки)
    # Это нужно для отображения в письме, если получатель не админ
    from users.models import ProviderAdmin
    provider_admin_obj = ProviderAdmin.objects.filter(provider=provider, is_active=True).select_related('user').first()
    admin_info = None
    if provider_admin_obj:
        admin_info = {
            'email': provider_admin_obj.user.email,
            'name': provider_admin_obj.user.get_full_name() or provider_admin_obj.user.email,
        }
    
    # Для инструкций по входу используем email админа (не получателя, если получатель не админ)
    login_email = admin_info['email'] if (not is_admin and admin_info) else email_to
    # Для определения способа входа используем админа
    admin_user_for_login = provider_admin_obj.user if (not is_admin and provider_admin_obj) else admin_user
    has_password_for_login = admin_user_for_login.has_usable_password() if admin_user_for_login else False
    login_method_for_display = 'password' if has_password_for_login else 'google'
    
    # Формируем контекст для шаблона
    context = {
        'provider_name': provider.name,
        'admin_email': email_to,  # Email получателя
        'admin_first_name': admin_user.first_name or _('User'),
        'has_password': has_password,
        'login_method': login_method,
        'login_email': login_email,  # Email для инструкций по входу (админ, если получатель не админ)
        'login_method_for_display': login_method_for_display,  # Способ входа админа
        'admin_login_url': admin_login_url,
        'setup_guide_url': setup_guide_url,
        'billing_manager_contacts': billing_manager_contacts,
        'is_admin': is_admin,  # Флаг, что получатель - админ провайдера
        'provider_admin_info': admin_info,  # Информация об админе провайдера
    }
    
    # Рендерим шаблон письма
    try:
        email_subject = _('Your provider account has been activated')
        email_body = render_to_string('email/provider_activation.html', context)
        
        # Отправляем письмо на email провайдера (из ProviderForm)
        send_mail(
            subject=email_subject,
            message='',  # Текстовая версия не нужна, используем HTML
            html_message=email_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email_to],
            fail_silently=False,
        )
        
        logger.info(f"Activation email sent to {email_to} for provider {provider.id}")
        
    except Exception as e:
        logger.error(f"Error rendering or sending activation email: {e}", exc_info=True)
        raise

