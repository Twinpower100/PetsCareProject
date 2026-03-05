"""
API Views для вкладки «Безопасность» аккаунта.

Содержит:
- ChangePasswordAPIView — смена пароля
- ChangeEmailAPIView — запрос смены email (Шаг 1, отправка OTP)
- ConfirmEmailChangeAPIView — подтверждение OTP-кода (Шаг 2)
- UserSessionListAPIView — список активных сессий
- UserSessionDeleteAPIView — завершение конкретной сессии
- TerminateAllSessionsAPIView — завершение всех сессий, кроме текущей
"""

import random
import string
import logging
import hashlib

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

from .security_serializers import (
    ChangePasswordSerializer,
    ChangeEmailSerializer,
    ConfirmEmailSerializer,
    UserSessionSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


# ── Throttle classes ─────────────────────────────────────────────────────

class PasswordChangeThrottle(UserRateThrottle):
    """Ограничение: 5 попыток в час."""
    rate = '5/hour'


class EmailChangeThrottle(UserRateThrottle):
    """Ограничение: 3 запроса OTP в час."""
    rate = '3/hour'


# ── Helpers ──────────────────────────────────────────────────────────────

def _generate_otp() -> str:
    """Генерирует 6-значный OTP-код."""
    return ''.join(random.choices(string.digits, k=6))


def _otp_cache_key(user_id: int) -> str:
    return f'email_change_otp:{user_id}'


def _parse_user_agent(ua_string: str) -> dict:
    """Простой парсер User-Agent без сторонних библиотек."""
    ua = ua_string or ''
    result = {'device': 'Unknown', 'browser': 'Unknown', 'os': 'Unknown'}

    # OS Detection
    if 'Windows' in ua:
        result['os'] = 'Windows'
        result['device'] = 'Desktop'
    elif 'Macintosh' in ua or 'Mac OS' in ua:
        result['os'] = 'macOS'
        result['device'] = 'Desktop'
    elif 'iPhone' in ua:
        result['os'] = 'iOS'
        result['device'] = 'Mobile'
    elif 'iPad' in ua:
        result['os'] = 'iPadOS'
        result['device'] = 'Tablet'
    elif 'Android' in ua:
        result['os'] = 'Android'
        result['device'] = 'Mobile' if 'Mobile' in ua else 'Tablet'
    elif 'Linux' in ua:
        result['os'] = 'Linux'
        result['device'] = 'Desktop'

    # Browser Detection
    if 'Edg/' in ua:
        result['browser'] = 'Edge'
    elif 'OPR/' in ua or 'Opera' in ua:
        result['browser'] = 'Opera'
    elif 'Chrome/' in ua and 'Chromium' not in ua:
        result['browser'] = 'Chrome'
    elif 'Safari/' in ua and 'Chrome' not in ua:
        result['browser'] = 'Safari'
    elif 'Firefox/' in ua:
        result['browser'] = 'Firefox'

    return result


def _get_client_ip(request) -> str:
    """Получает IP-адрес клиента."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


def _get_current_token_jti(request) -> str | None:
    """Извлекает jti текущего access-токена из заголовка Authorization."""
    import jwt
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        return None
    token_str = auth_header[7:]
    try:
        payload = jwt.decode(token_str, options={'verify_signature': False})
        return payload.get('jti')
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════
# 1. Смена пароля
# ══════════════════════════════════════════════════════════════════════════

class ChangePasswordAPIView(GenericAPIView):
    """
    POST /api/v1/security/change-password/

    Меняет пароль текущего пользователя.
    После успешной смены инвалидирует все refresh-токены, чтобы
    на других устройствах сессии закрылись.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer
    throttle_classes = [PasswordChangeThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])

        # Инвалидируем все outstanding refresh-токены (выход со всех устройств)
        tokens = OutstandingToken.objects.filter(user=user)
        for token in tokens:
            BlacklistedToken.objects.get_or_create(token=token)

        # Выдаём свежую пару токенов для текущего сеанса
        refresh = RefreshToken.for_user(user)

        logger.info('User %s changed password successfully.', user.email)

        return Response({
            'message': _('Password changed successfully. All other sessions have been terminated.'),
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_200_OK)


# ══════════════════════════════════════════════════════════════════════════
# 2. Смена email
# ══════════════════════════════════════════════════════════════════════════

class ChangeEmailAPIView(GenericAPIView):
    """
    POST /api/v1/security/change-email/

    Шаг 1: Пользователь передает текущий пароль и новый email.
    Сервер генерирует 6-значный OTP и сохраняет его в кэше (TTL 10 мин).
    OTP отправляется на *новый* email.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ChangeEmailSerializer
    throttle_classes = [EmailChangeThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        new_email = serializer.validated_data['new_email']

        otp = _generate_otp()
        cache_key = _otp_cache_key(user.id)
        cache.set(cache_key, {'otp': otp, 'new_email': new_email}, timeout=600)  # 10 min

        # Отправляем OTP на новый email
        try:
            send_mail(
                subject=_('PetCare — Email change verification code'),
                message=_(
                    'Your verification code: %(otp)s\n\n'
                    'The code is valid for 10 minutes.\n'
                    'If you did not request an email change, please ignore this email.'
                ) % {'otp': otp},
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[new_email],
                fail_silently=False,
            )
        except Exception as e:
            logger.error('Failed to send OTP email to %s: %s', new_email, e)
            return Response(
                {'detail': _('Failed to send verification email. Please try again later.')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info('OTP sent for email change: user=%s new_email=%s', user.email, new_email)
        return Response({
            'message': _('Verification code has been sent to your new email address.'),
        }, status=status.HTTP_200_OK)


class ConfirmEmailChangeAPIView(GenericAPIView):
    """
    POST /api/v1/security/confirm-email/

    Шаг 2: Пользователь вводит OTP-код. Если он совпадает — email обновляется.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ConfirmEmailSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        cache_key = _otp_cache_key(user.id)
        cached = cache.get(cache_key)

        if not cached:
            return Response(
                {'otp_code': [_('Verification code has expired. Please request a new one.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if cached['otp'] != serializer.validated_data['otp_code']:
            return Response(
                {'otp_code': [_('Invalid verification code.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_email = cached['new_email']

        # Повторная проверка уникальности (на случай гонки)
        if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
            cache.delete(cache_key)
            return Response(
                {'new_email': [_('This email has already been taken.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_email = user.email
        user.email = new_email
        user.username = new_email  # username = email
        user.save(update_fields=['email', 'username'])
        cache.delete(cache_key)

        logger.info('User email changed: %s -> %s', old_email, new_email)

        return Response({
            'message': _('Email address updated successfully.'),
            'email': new_email,
        }, status=status.HTTP_200_OK)


# ══════════════════════════════════════════════════════════════════════════
# 3. Управление сессиями
# ══════════════════════════════════════════════════════════════════════════

class UserSessionListAPIView(GenericAPIView):
    """
    GET /api/v1/security/sessions/

    Возвращает список активных refresh-токенов (= сессий) пользователя.
    Для каждой сессии парсит User-Agent и определяет is_current.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSessionSerializer

    def get(self, request):
        user = request.user
        current_jti = _get_current_token_jti(request)

        # Outstanding tokens, которые ещё НЕ blacklisted и не истекли
        tokens = OutstandingToken.objects.filter(
            user=user,
            expires_at__gt=timezone.now(),
        ).exclude(
            id__in=BlacklistedToken.objects.values_list('token_id', flat=True),
        ).order_by('-created_at')

        sessions = []
        client_ip = _get_client_ip(request)

        for idx, token in enumerate(tokens):
            # Пытаемся декодировать payload для jti
            try:
                import jwt
                payload = jwt.decode(str(token.token), options={'verify_signature': False})
                token_jti = payload.get('jti', '')
            except Exception:
                token_jti = ''

            # User-Agent хранится в token.token — SimpleJWT не хранит UA,
            # поэтому используем IP/UA текущего запроса для текущей сессии.
            is_current = token_jti == current_jti if current_jti else idx == 0

            ua_string = request.META.get('HTTP_USER_AGENT', '') if is_current else ''
            ua_parsed = _parse_user_agent(ua_string)

            sessions.append({
                'id': token.id,
                'ip_address': client_ip if is_current else '—',
                'user_agent': ua_string,
                'device': ua_parsed['device'],
                'browser': ua_parsed['browser'],
                'os': ua_parsed['os'],
                'last_activity': token.created_at,
                'is_current': is_current,
            })

        serializer = self.get_serializer(sessions, many=True)
        return Response(serializer.data)


class UserSessionDeleteAPIView(GenericAPIView):
    """
    DELETE /api/v1/security/sessions/<int:session_id>/

    Завершает конкретную сессию (добавляет refresh-токен в blacklist).
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, session_id):
        try:
            token = OutstandingToken.objects.get(id=session_id, user=request.user)
        except OutstandingToken.DoesNotExist:
            return Response(
                {'detail': _('Session not found.')},
                status=status.HTTP_404_NOT_FOUND,
            )

        BlacklistedToken.objects.get_or_create(token=token)
        logger.info('User %s terminated session %s.', request.user.email, session_id)
        return Response({'message': _('Session terminated.')}, status=status.HTTP_200_OK)


class TerminateAllSessionsAPIView(GenericAPIView):
    """
    POST /api/v1/security/sessions/terminate-all/

    Завершает все сессии пользователя, кроме текущей.
    Возвращает свежую пару токенов для текущего сеанса.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        # Blacklist всех outstanding-токенов
        tokens = OutstandingToken.objects.filter(user=user)
        count = 0
        for token in tokens:
            obj, created = BlacklistedToken.objects.get_or_create(token=token)
            if created:
                count += 1

        # Выдаём свежую пару токенов для текущего сеанса
        refresh = RefreshToken.for_user(user)

        logger.info('User %s terminated %d other sessions.', user.email, count)

        return Response({
            'message': _('All other sessions have been terminated.'),
            'terminated_count': count,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_200_OK)
