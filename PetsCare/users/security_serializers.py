"""
Сериализаторы для вкладки «Безопасность» аккаунта.

Содержит:
- ChangePasswordSerializer — смена пароля
- ChangeEmailSerializer — запрос смены email (Шаг 1)
- ConfirmEmailSerializer — подтверждение OTP-кода (Шаг 2)
- UserSessionSerializer — сериализация активных сессий
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class ChangePasswordSerializer(serializers.Serializer):
    """Сериализатор для смены пароля."""
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)
    new_password_confirm = serializers.CharField(required=True, write_only=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError(_('Current password is incorrect.'))
        return value

    def validate_new_password(self, value):
        # Используем стандартные валидаторы Django
        validate_password(value, self.context['request'].user)
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                'new_password_confirm': _('New passwords do not match.')
            })
        if attrs['old_password'] == attrs['new_password']:
            raise serializers.ValidationError({
                'new_password': _('New password must differ from the current one.')
            })
        return attrs


class ChangeEmailSerializer(serializers.Serializer):
    """Сериализатор для запроса смены email (Шаг 1)."""
    current_password = serializers.CharField(required=True, write_only=True)
    new_email = serializers.EmailField(required=True)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError(_('Password is incorrect.'))
        return value

    def validate_new_email(self, value):
        value = value.lower().strip()
        user = self.context['request'].user
        if value == user.email:
            raise serializers.ValidationError(_('New email must differ from the current one.'))
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(_('This email is already registered.'))
        return value


class ConfirmEmailSerializer(serializers.Serializer):
    """Сериализатор для подтверждения OTP-кода (Шаг 2)."""
    otp_code = serializers.CharField(required=True, min_length=6, max_length=6)


class UserSessionSerializer(serializers.Serializer):
    """Сериализатор для отображения активных сессий."""
    id = serializers.IntegerField()
    ip_address = serializers.CharField()
    user_agent = serializers.CharField()
    device = serializers.CharField()
    browser = serializers.CharField()
    os = serializers.CharField()
    last_activity = serializers.DateTimeField()
    is_current = serializers.BooleanField()
