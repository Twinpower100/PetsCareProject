"""
Сериализаторы для API доступа.

Этот модуль содержит сериализаторы для:
1. Управления доступом к карточкам питомцев
2. Логирования действий
3. Генерации QR-кодов доступа
"""

from rest_framework import serializers
from .models import PetAccess, AccessLog
from pets.serializers import PetSerializer
from users.serializers import UserSerializer
from django.utils.translation import gettext_lazy as _


class PetAccessSerializer(serializers.ModelSerializer):
    """
    Сериализатор для управления доступом к карточкам питомцев.
    
    Особенности:
    - Валидация прав доступа
    - Проверка срока действия
    - Автоматическое заполнение полей
    """
    pet = PetSerializer(read_only=True)
    granted_to = UserSerializer(read_only=True)
    granted_by = UserSerializer(read_only=True)
    
    class Meta:
        model = PetAccess
        fields = [
            'id', 'pet', 'granted_to', 'granted_by', 'token',
            'created_at', 'expires_at', 'permissions', 'is_active'
        ]
        read_only_fields = ['id', 'token', 'created_at', 'granted_by']

    def validate_permissions(self, value):
        """Проверяет наличие всех необходимых прав доступа"""
        required_permissions = {'read', 'book', 'write'}
        if not all(perm in value for perm in required_permissions):
            raise serializers.ValidationError(
                _("All permissions (read, book, write) must be specified")
            )
        return value

    def validate_expires_at(self, value):
        """Проверяет, что срок действия установлен в будущем"""
        from django.utils import timezone
        if value <= timezone.now():
            raise serializers.ValidationError(
                _("Expiration date must be in the future")
            )
        return value


class AccessLogSerializer(serializers.ModelSerializer):
    """
    Сериализатор для логов доступа.
    
    Особенности:
    - Только для чтения
    - Вложенные данные о доступе и пользователе
    - Автоматическая метка времени
    """
    access = PetAccessSerializer(read_only=True)
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = AccessLog
        fields = ['id', 'access', 'user', 'action', 'timestamp', 'details']
        read_only_fields = ['id', 'timestamp']


class QRCodeSerializer(serializers.Serializer):
    """
    Сериализатор для генерации QR-кодов доступа.
    
    Особенности:
    - Генерация уникального токена
    - Создание URL для QR-кода
    - Только для чтения
    """
    token = serializers.UUIDField(read_only=True)
    qr_code_url = serializers.URLField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)
    permissions = serializers.JSONField(read_only=True) 