"""
Модели для управления доступом.

Этот модуль содержит модели для:
1. Управления доступом к карточкам питомцев
2. Логирования действий с доступом
3. Общего управления правами доступа
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import uuid
from django.apps import apps
from django.conf import settings
from django.utils.translation import gettext_lazy as _

User = get_user_model()

class PetAccess(models.Model):
    """
    Модель для управления доступом к карточке питомца.
    
    Особенности:
    - Уникальный токен доступа
    - Срок действия
    - Гибкая система прав
    - Отслеживание кто и кому выдал доступ
    """
    pet = models.ForeignKey(
        'pets.Pet',
        on_delete=models.CASCADE,
        verbose_name=_('Pet')
    )
    granted_to = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='pet_granted_accesses',
        verbose_name=_('Granted To')
    )
    granted_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='granted_accesses_by',
        verbose_name=_('Granted By')
    )
    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        verbose_name=_('Access Token')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )
    expires_at = models.DateTimeField(
        verbose_name=_('Expires At')
    )
    permissions = models.JSONField(
        default=dict,
        verbose_name=_('Permissions'),
        help_text=_('JSON with access permissions (read, book, write)')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Is Active')
    )

    class Meta:
        verbose_name = _('Pet Access')
        verbose_name_plural = _('Pet Accesses')
        unique_together = ['pet', 'granted_to']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"Access to {self.pet} for {self.granted_to}"

    def is_expired(self):
        """Проверяет, истек ли срок действия доступа"""
        return timezone.now() > self.expires_at

    def has_permission(self, permission):
        """Проверяет наличие указанного права доступа"""
        return self.permissions.get(permission, False)

    def revoke(self):
        """Отзывает доступ, делая его неактивным"""
        self.is_active = False
        self.save()

class AccessLog(models.Model):
    """
    Модель для логирования действий с доступом.
    
    Особенности:
    - Отслеживание всех действий с доступом
    - Хранение деталей в JSON
    - Автоматическая метка времени
    """
    access = models.ForeignKey(
        PetAccess,
        on_delete=models.CASCADE,
        verbose_name=_('Access')
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_('User')
    )
    action = models.CharField(
        max_length=50,
        verbose_name=_('Action')
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Timestamp')
    )
    details = models.JSONField(
        default=dict,
        verbose_name=_('Details')
    )

    class Meta:
        verbose_name = _('Access Log')
        verbose_name_plural = _('Access Logs')
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user} - {self.action} - {self.timestamp}"

class Access(models.Model):
    """
    Модель для управления общими правами доступа.
    
    Особенности:
    - Гибкая система типов доступа
    - Отслеживание активности
    - Автоматические метки времени
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_('User'),
        related_name='accesses'
    )
    pet = models.ForeignKey('pets.Pet', on_delete=models.CASCADE)
    granted_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_('Granted To'),
        related_name='general_granted_accesses'
    )
    access_type = models.CharField(
        max_length=50,
        verbose_name=_('Access Type')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Is Active')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )

    class Meta:
        verbose_name = _('Access')
        verbose_name_plural = _('Accesses')
        ordering = ['-created_at']
        unique_together = ['user', 'granted_to', 'access_type']

    def __str__(self):
        return f"{self.user} -> {self.granted_to} ({self.access_type})" 