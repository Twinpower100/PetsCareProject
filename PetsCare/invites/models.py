"""
Единая модель приглашений (Invite) для всех типов инвайтов в системе.

Типы: provider_manager, provider_admin, branch_manager, specialist,
pet_co_owner, pet_transfer.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


class Invite(models.Model):
    """
    Единая модель приглашения для всех типов инвайтов в системе.

    Поддерживаемые типы:
    - provider_manager: менеджер организации (один на провайдера)
    - provider_admin: админ организации (много на провайдера)
    - branch_manager: руководитель филиала (один на локацию)
    - specialist: специалист/сотрудник в локации (много на локацию)
    - pet_co_owner: совладелец питомца
    - pet_transfer: передача прав основного владельца
    """

    # === Тип инвайта ===
    TYPE_PROVIDER_MANAGER = 'provider_manager'
    TYPE_PROVIDER_ADMIN = 'provider_admin'
    TYPE_BRANCH_MANAGER = 'branch_manager'
    TYPE_SPECIALIST = 'specialist'
    TYPE_PET_CO_OWNER = 'pet_co_owner'
    TYPE_PET_TRANSFER = 'pet_transfer'

    TYPE_CHOICES = [
        (TYPE_PROVIDER_MANAGER, _('Provider Manager')),
        (TYPE_PROVIDER_ADMIN, _('Provider Admin')),
        (TYPE_BRANCH_MANAGER, _('Branch Manager')),
        (TYPE_SPECIALIST, _('Specialist')),
        (TYPE_PET_CO_OWNER, _('Pet Co-Owner')),
        (TYPE_PET_TRANSFER, _('Pet Transfer')),
    ]

    # === Статус ===
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_DECLINED = 'declined'
    STATUS_EXPIRED = 'expired'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, _('Pending')),
        (STATUS_ACCEPTED, _('Accepted')),
        (STATUS_DECLINED, _('Declined')),
        (STATUS_EXPIRED, _('Expired')),
        (STATUS_CANCELLED, _('Cancelled')),
    ]

    # === Общие поля (есть у ВСЕХ инвайтов) ===
    invite_type = models.CharField(
        _('Invite Type'), max_length=30, choices=TYPE_CHOICES,
    )
    email = models.EmailField(
        _('Email'),
        help_text=_('Email of the invited user'),
    )
    token = models.CharField(
        _('Token'),
        max_length=6,
        unique=True,
        help_text=_('6-digit activation code'),
    )
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    expires_at = models.DateTimeField(_('Expires At'))
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    # === Кто создал ===
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_invites',
        verbose_name=_('Created By'),
        null=True,
        blank=True,
    )

    # === Контекстные FK (nullable, зависят от invite_type) ===
    provider = models.ForeignKey(
        'providers.Provider',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='invites',
        verbose_name=_('Provider'),
    )
    provider_location = models.ForeignKey(
        'providers.ProviderLocation',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='invites',
        verbose_name=_('Provider Location'),
    )
    pet = models.ForeignKey(
        'pets.Pet',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='invites',
        verbose_name=_('Pet'),
    )

    # === Метаданные приёма/отклонения ===
    accepted_at = models.DateTimeField(_('Accepted At'), null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accepted_invites',
        verbose_name=_('Accepted By'),
    )
    declined_at = models.DateTimeField(_('Declined At'), null=True, blank=True)

    # === Дополнительные поля (для совместимости с RoleInvite) ===
    position = models.CharField(_('Position'), max_length=100, blank=True)
    comment = models.TextField(_('Comment'), blank=True)
    qr_code = models.TextField(_('QR Code'), blank=True)

    class Meta:
        verbose_name = _('Invite')
        verbose_name_plural = _('Invites')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['email']),
            models.Index(fields=['invite_type', 'status']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['provider']),
            models.Index(fields=['provider_location']),
        ]
        constraints = [
            # Один активный инвайт specialist на (provider_location, email)
            models.UniqueConstraint(
                fields=['provider_location', 'email'],
                condition=models.Q(invite_type='specialist', status='pending'),
                name='invites_unique_pending_specialist_per_location_email',
            ),
        ]

    def __str__(self):
        return f"{self.get_invite_type_display()} → {self.email} ({self.status})"

    def clean(self):
        """Валидация: для каждого типа обязательны свои FK, остальные null."""
        super().clean()
        provider_types = (self.TYPE_PROVIDER_MANAGER, self.TYPE_PROVIDER_ADMIN)
        location_types = (self.TYPE_BRANCH_MANAGER, self.TYPE_SPECIALIST)
        pet_types = (self.TYPE_PET_CO_OWNER, self.TYPE_PET_TRANSFER)

        if self.invite_type in provider_types:
            if not self.provider_id:
                raise ValidationError({
                    'provider': _('Provider is required for this invite type.'),
                })
            if self.provider_location_id or self.pet_id:
                raise ValidationError(
                    _('Provider invite must not have provider_location or pet set.'),
                )
        elif self.invite_type in location_types:
            if not self.provider_location_id:
                raise ValidationError({
                    'provider_location': _('Provider location is required for this invite type.'),
                })
            if self.pet_id:
                raise ValidationError(
                    _('Location invite must not have pet set.'),
                )
            if not self.provider_id and self.provider_location_id:
                self.provider = self.provider_location.provider
        elif self.invite_type in pet_types:
            if not self.pet_id:
                raise ValidationError({
                    'pet': _('Pet is required for this invite type.'),
                })
            if self.provider_id or self.provider_location_id:
                raise ValidationError(
                    _('Pet invite must not have provider or provider_location set.'),
                )

    def save(self, *args, **kwargs):
        if self.provider_location_id and not self.provider_id:
            self.provider = self.provider_location.provider
        super().save(*args, **kwargs)

    def is_expired(self):
        """Проверяет, истёк ли срок действия инвайта."""
        return timezone.now() >= self.expires_at

    def can_be_accepted(self):
        """Проверяет, можно ли принять инвайт."""
        return self.status == self.STATUS_PENDING and not self.is_expired()

    def accept(self, user):
        """
        Универсальный метод приёма — вызывает нужный handler по invite_type.
        Выполняется внутри transaction.atomic в вызывающем коде.
        """
        from invites.services import accept_invite
        accept_invite(self, user)

    def decline(self, user):
        """Отклоняет инвайт. accepted_by не заполняем — он только для принятия."""
        if self.status != self.STATUS_PENDING:
            raise ValueError(_('Invite cannot be declined.'))
        if user.email.lower() != self.email.lower():
            raise ValueError(_('Email does not match invite.'))
        self.status = self.STATUS_DECLINED
        self.declined_at = timezone.now()
        self.save(update_fields=['status', 'declined_at'])

    def cancel(self):
        """Отменяет инвайт (создателем)."""
        if self.status != self.STATUS_PENDING:
            raise ValueError(_('Only pending invites can be cancelled.'))
        self.status = self.STATUS_CANCELLED
        self.save(update_fields=['status'])

    @staticmethod
    def generate_token():
        """Генерирует уникальный 6-значный код."""
        import random
        from django.db import IntegrityError
        for _ in range(20):
            token = ''.join(random.choices('0123456789', k=6))
            if not Invite.objects.filter(token=token).exists():
                return token
        raise IntegrityError('Could not generate unique invite token.')
