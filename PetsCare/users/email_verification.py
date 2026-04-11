from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import EmailVerificationToken, User


def _build_verification_url(token: str) -> str:
    """
    Собирает frontend-ссылку для подтверждения email.
    """
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    return f"{frontend_url}/verify-email?token={token}"


def send_email_verification_message(verification_token_id: int) -> None:
    """
    Отправляет письмо подтверждения email по ID токена.
    """
    verification_token = (
        EmailVerificationToken.objects
        .select_related('user')
        .filter(id=verification_token_id)
        .first()
    )
    if verification_token is None:
        return

    from django.utils import translation
    user_lang = verification_token.user.preferred_language or 'en'
    
    with translation.override(user_lang):
        verification_url = _build_verification_url(verification_token.token)
        subject = _('Verify your email address')
        message = _(
            'Welcome to PetCare.\n\n'
            'Please verify your email address to continue using owner actions:\n'
            '{verification_url}\n\n'
            'If you did not create this account, you can ignore this email.'
        ).format(verification_url=verification_url)
        html_message = _(
            '<p>Welcome to PetCare.</p>'
            '<p>Please verify your email address to continue using owner actions.</p>'
            '<p><a href="{verification_url}">{verification_url}</a></p>'
            '<p>If you did not create this account, you can ignore this email.</p>'
        ).format(verification_url=verification_url)

        send_mail(
            subject=str(subject),
            message=str(message),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            recipient_list=[verification_token.sent_to_email or verification_token.user.email],
            html_message=str(html_message),
            fail_silently=False,
        )


def issue_email_verification(user: User, *, invalidate_existing: bool) -> EmailVerificationToken:
    """
    Создает новый токен подтверждения email и отправляет письмо после коммита.
    """
    active_tokens = (
        EmailVerificationToken.objects
        .select_for_update()
        .filter(user=user, used=False, expires_at__gt=timezone.now())
    )
    if invalidate_existing:
        active_tokens.update(used=True, used_at=timezone.now())

    verification_token = EmailVerificationToken.create_for_user(user)
    transaction.on_commit(lambda: send_email_verification_message(verification_token.id))
    return verification_token


def resend_email_verification(user: User) -> EmailVerificationToken:
    """
    Переотправляет письмо подтверждения email с ограничением по частоте.
    """
    cooldown_seconds = getattr(settings, 'EMAIL_VERIFICATION_RESEND_COOLDOWN', 60)
    now = timezone.now()

    with transaction.atomic():
        locked_user = User.objects.select_for_update().get(pk=user.pk)
        if locked_user.email_verified:
            raise serializers.ValidationError({
                'detail': _('Your email address is already verified.'),
                'code': 'email_already_verified',
            })

        latest_active_token = (
            EmailVerificationToken.objects
            .select_for_update()
            .filter(user=locked_user, used=False, expires_at__gt=now)
            .order_by('-created_at')
            .first()
        )
        if latest_active_token is not None:
            seconds_since_last_send = (now - latest_active_token.created_at).total_seconds()
            if seconds_since_last_send < cooldown_seconds:
                retry_after = int(cooldown_seconds - seconds_since_last_send)
                raise serializers.ValidationError({
                    'detail': _(
                        'Please wait before requesting another verification email.'
                    ),
                    'code': 'email_verification_resend_throttled',
                    'retry_after_seconds': retry_after,
                })

        return issue_email_verification(locked_user, invalidate_existing=True)


def confirm_email_verification(token_value: str) -> User:
    """
    Подтверждает email пользователя по токену.
    """
    with transaction.atomic():
        verification_token = (
            EmailVerificationToken.objects
            .select_for_update()
            .select_related('user')
            .filter(token=token_value)
            .first()
        )
        if verification_token is None:
            raise serializers.ValidationError({
                'detail': _('This verification link is invalid.'),
                'code': 'email_verification_invalid',
            })

        verification_time = timezone.now()
        user = User.objects.select_for_update().get(pk=verification_token.user_id)

        if verification_token.used:
            if user.email_verified:
                return user
            raise serializers.ValidationError({
                'detail': _('This verification link has already been used.'),
                'code': 'email_verification_already_used',
            })

        if verification_time > verification_token.expires_at:
            raise serializers.ValidationError({
                'detail': _('This verification link has expired.'),
                'code': 'email_verification_expired',
            })

        if not user.email_verified:
            user.email_verified = True
            user.email_verified_at = verification_time
            user.save(update_fields=['email_verified', 'email_verified_at'])

        verification_token.used = True
        verification_token.used_at = verification_time
        verification_token.save(update_fields=['used', 'used_at'])

        (
            EmailVerificationToken.objects
            .filter(user=user, used=False)
            .exclude(pk=verification_token.pk)
            .update(used=True, used_at=verification_time)
        )
        return user
