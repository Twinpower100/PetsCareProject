from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from .models import UserAction, SecurityAudit, AuditSettings
from .services import LoggingService, SecurityAuditService

# Инициализируем сервисы
logging_service = LoggingService()
audit_service = SecurityAuditService()


@receiver(post_save, sender=UserAction)
def log_user_action_created(sender, instance, created, **kwargs):
    """Логирует создание записи действия пользователя"""
    if created:
        # Логируем создание лога (мета-логирование)
        logging_service.log_system_event(
            'user_action_created',
            {
                'action_id': instance.id,
                'user_id': instance.user.id if instance.user else None,
                'action_type': instance.action_type,
            }
        )


@receiver(post_save, sender=SecurityAudit)
def log_security_audit_created(sender, instance, created, **kwargs):
    """Логирует создание записи аудита безопасности"""
    if created:
        # Логируем создание аудита
        logging_service.log_system_event(
            'security_audit_created',
            {
                'audit_id': instance.id,
                'user_id': instance.user.id if instance.user else None,
                'audit_type': instance.audit_type,
                'is_critical': instance.is_critical,
            }
        )


# Сигналы для критически важных моделей
@receiver(post_save, sender='users.User')
def log_user_changes(sender, instance, created, **kwargs):
    """Логирует изменения пользователей"""
    if created:
        logging_service.log_action(
            user=instance,
            action_type='create',
            content_object=instance,
            details={'user_type': getattr(instance, 'user_type', 'unknown')}
        )
    else:
        logging_service.log_action(
            user=instance,
            action_type='update',
            content_object=instance,
            details={'user_type': getattr(instance, 'user_type', 'unknown')}
        )


@receiver(post_save, sender='pets.Pet')
def log_pet_changes(sender, instance, created, **kwargs):
    """Логирует изменения питомцев"""
    if created:
        logging_service.log_action(
            user=instance.owner,
            action_type='create',
            content_object=instance,
            details={'pet_name': instance.name, 'pet_type': instance.pet_type}
        )
    else:
        logging_service.log_action(
            user=instance.owner,
            action_type='update',
            content_object=instance,
            details={'pet_name': instance.name, 'pet_type': instance.pet_type}
        )


@receiver(post_delete, sender='pets.Pet')
def log_pet_deletion(sender, instance, **kwargs):
    """Логирует удаление питомцев"""
    logging_service.log_action(
        user=instance.owner,
        action_type='delete',
        content_object=instance,
        details={'pet_name': instance.name, 'pet_type': instance.pet_type}
    )


@receiver(post_save, sender='booking.Booking')
def log_booking_changes(sender, instance, created, **kwargs):
    """Логирует изменения бронирований"""
    if created:
        logging_service.log_action(
            user=instance.pet_owner,
            action_type='booking',
            content_object=instance,
            details={
                'booking_id': instance.id,
                'pet_name': instance.pet.name,
                'sitter_name': instance.sitter.get_full_name(),
                'start_date': instance.start_date.isoformat(),
                'end_date': instance.end_date.isoformat(),
            }
        )
    else:
        # Логируем изменения статуса
        if hasattr(instance, '_state') and hasattr(instance._state, 'fields_cache'):
            old_status = instance._state.fields_cache.get('status')
            if old_status and old_status != instance.status:
                logging_service.log_action(
                    user=instance.pet_owner,
                    action_type='update',
                    content_object=instance,
                    details={
                        'booking_id': instance.id,
                        'old_status': old_status,
                        'new_status': instance.status,
                    }
                )


@receiver(post_save, sender='billing.Contract')
def log_contract_changes(sender, instance, created, **kwargs):
    """Логирует изменения договоров"""
    if created:
        audit_service.audit_financial_operation(
            user=instance.provider.admin_user,
            operation='contract_created',
            amount=float(instance.commission_rate),
            currency='%',
            content_object=instance,
            details={
                'provider_name': instance.provider.name,
                'commission_rate': instance.commission_rate,
            }
        )
    else:
        audit_service.audit_financial_operation(
            user=instance.provider.admin_user,
            operation='contract_updated',
            amount=float(instance.commission_rate),
            currency='%',
            content_object=instance,
            details={
                'provider_name': instance.provider.name,
                'commission_rate': instance.commission_rate,
            }
        )


@receiver(post_save, sender='billing.Payment')
def log_payment_operations(sender, instance, created, **kwargs):
    """Логирует платежные операции"""
    if created:
        audit_service.audit_financial_operation(
            user=instance.user,
            operation='payment_created',
            amount=float(instance.amount),
            currency=instance.currency,
            content_object=instance,
            details={
                'payment_method': instance.payment_method,
                'status': instance.status,
                'booking_id': instance.booking.id if instance.booking else None,
            }
        )
    else:
        # Логируем изменения статуса платежа
        if hasattr(instance, '_state') and hasattr(instance._state, 'fields_cache'):
            old_status = instance._state.fields_cache.get('status')
            if old_status and old_status != instance.status:
                audit_service.audit_financial_operation(
                    user=instance.user,
                    operation='payment_status_changed',
                    amount=float(instance.amount),
                    currency=instance.currency,
                    content_object=instance,
                    details={
                        'old_status': old_status,
                        'new_status': instance.status,
                        'payment_method': instance.payment_method,
                    }
                )


@receiver(post_save, sender='access.RoleInvite')
def log_invite_management(sender, instance, created, **kwargs):
    """Логирует управление инвайтами"""
    if created:
        audit_service.audit_invite_management(
            user=instance.invited_by,
            invite=instance,
            action='create',
            reason=f"Invite for role {instance.role}"
        )
    else:
        # Логируем изменения статуса инвайта
        if hasattr(instance, '_state') and hasattr(instance._state, 'fields_cache'):
            old_status = instance._state.fields_cache.get('status')
            if old_status and old_status != instance.status:
                if instance.status == 'accepted':
                    audit_service.audit_invite_management(
                        user=instance.invited_user,
                        invite=instance,
                        action='accept',
                        reason=f"Accepted invite for role {instance.role}"
                    )
                elif instance.status == 'rejected':
                    audit_service.audit_invite_management(
                        user=instance.invited_user,
                        invite=instance,
                        action='reject',
                        reason=f"Rejected invite for role {instance.role}"
                    )


@receiver(post_delete, sender='access.RoleInvite')
def log_invite_deletion(sender, instance, **kwargs):
    """Логирует удаление инвайтов"""
    audit_service.audit_invite_management(
        user=instance.invited_by,
        invite=instance,
        action='delete',
        reason=f"Deleted invite for role {instance.role}"
    )


# Сигналы для блокировки/разблокировки
@receiver(post_save, sender='providers.Provider')
def log_provider_blocking(sender, instance, **kwargs):
    """Логирует блокировку/разблокировку учреждений"""
    if hasattr(instance, '_state') and hasattr(instance._state, 'fields_cache'):
        old_is_blocked = instance._state.fields_cache.get('is_blocked')
        if old_is_blocked is not None and old_is_blocked != instance.is_blocked:
            action = 'block' if instance.is_blocked else 'unblock'
            audit_service.audit_blocking_operation(
                user=instance.admin_user,
                target=instance,
                action=action,
                reason=f"Provider {action}ed",
                duration=None
            )


@receiver(post_save, sender='users.User')
def log_user_blocking(sender, instance, **kwargs):
    """Логирует блокировку/разблокировку пользователей"""
    if hasattr(instance, '_state') and hasattr(instance._state, 'fields_cache'):
        old_is_active = instance._state.fields_cache.get('is_active')
        if old_is_active is not None and old_is_active != instance.is_active:
            action = 'block' if not instance.is_active else 'unblock'
            audit_service.audit_blocking_operation(
                user=None,  # Системная операция
                target=instance,
                action=action,
                reason=f"User {action}ed",
                duration=None
            )


# Сигналы для передачи прав владения
@receiver(post_save, sender='pets.Pet')
def log_ownership_transfer(sender, instance, **kwargs):
    """Логирует передачу прав владения питомцем"""
    if hasattr(instance, '_state') and hasattr(instance._state, 'fields_cache'):
        old_owner = instance._state.fields_cache.get('owner')
        if old_owner and old_owner != instance.owner:
            audit_service.audit_ownership_transfer(
                user=old_owner,  # Кто передал права
                pet=instance,
                old_owner=old_owner,
                new_owner=instance.owner,
                reason="Pet ownership transferred"
            ) 