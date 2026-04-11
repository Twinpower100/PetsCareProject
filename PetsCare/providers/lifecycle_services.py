"""
Сервис управления жизненным циклом организаций и филиалов.

Содержит:
- применение pause / terminate / reactivate для Provider;
- применение temporary close / deactivate / reactivate для ProviderLocation;
- планирование future-dated переходов;
- audit, отмену будущих бронирований и синхронизацию ролей доступа.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from uuid import UUID, uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from booking.constants import (
    ACTIVE_BOOKING_STATUS_NAMES,
    CANCELLED_BY_PROVIDER,
    CANCELLATION_REASON_PROVIDER_UNAVAILABLE,
)

from .models import (
    EmployeeLocationRole,
    EmployeeProvider,
    Provider,
    ProviderLifecycleEvent,
    ProviderLifecycleSettings,
    ProviderLocation,
)
from .permission_service import ProviderPermissionService


class ProviderLifecycleService:
    """
    Оркестрация lifecycle-операций для Provider и ProviderLocation.
    """

    PROVIDER_ACTION_MAP = {
        'pause': (
            Provider.PARTNERSHIP_STATUS_TEMPORARILY_INACTIVE,
            ProviderLifecycleEvent.ACTION_PROVIDER_PAUSE,
        ),
        'terminate': (
            Provider.PARTNERSHIP_STATUS_TERMINATED,
            ProviderLifecycleEvent.ACTION_PROVIDER_TERMINATE,
        ),
        'reactivate': (
            Provider.PARTNERSHIP_STATUS_ACTIVE,
            ProviderLifecycleEvent.ACTION_PROVIDER_REACTIVATE,
        ),
    }
    LOCATION_ACTION_MAP = {
        'temporary_close': (
            ProviderLocation.LIFECYCLE_STATUS_TEMPORARILY_CLOSED,
            ProviderLifecycleEvent.ACTION_LOCATION_TEMP_CLOSE,
        ),
        'deactivate': (
            ProviderLocation.LIFECYCLE_STATUS_DEACTIVATED,
            ProviderLifecycleEvent.ACTION_LOCATION_DEACTIVATE,
        ),
        'reactivate': (
            ProviderLocation.LIFECYCLE_STATUS_ACTIVE,
            ProviderLifecycleEvent.ACTION_LOCATION_REACTIVATE,
        ),
    }

    @classmethod
    def transition_provider(
        cls,
        *,
        provider_id: int,
        action: str,
        effective_date,
        initiated_by=None,
        reason: str = '',
        resume_date=None,
        restore_provider_team: bool = False,
        is_staff_override: bool = False,
    ) -> dict:
        """
        Выполняет или планирует lifecycle-переход для организации.
        """
        target_status, audit_action = cls.PROVIDER_ACTION_MAP[action]
        effective_date = cls._normalize_effective_date(effective_date)
        resume_date = cls._normalize_optional_date(resume_date)
        correlation_id = uuid4()

        with transaction.atomic():
            provider = Provider.objects.select_for_update().get(pk=provider_id)
            cls._validate_provider_transition(
                provider=provider,
                action=action,
                effective_date=effective_date,
                resume_date=resume_date,
            )

            if effective_date > timezone.localdate():
                cls._store_pending_provider_transition(
                    provider=provider,
                    target_status=target_status,
                    effective_date=effective_date,
                    resume_date=resume_date,
                    reason=reason,
                    initiated_by=initiated_by,
                )
                cls._create_event(
                    entity_type=ProviderLifecycleEvent.ENTITY_PROVIDER,
                    action=audit_action,
                    provider=provider,
                    location=None,
                    previous_status=provider.partnership_status,
                    new_status=target_status,
                    effective_date=effective_date,
                    resume_date=resume_date,
                    reason=reason,
                    initiated_by=initiated_by,
                    is_staff_override=is_staff_override,
                    correlation_id=correlation_id,
                    metadata={'scheduled': True},
                )
                return {
                    'scheduled': True,
                    'effective_date': effective_date,
                    'status': target_status,
                    'correlation_id': str(correlation_id),
                }

            result = cls._apply_provider_transition_locked(
                provider=provider,
                target_status=target_status,
                effective_date=effective_date,
                resume_date=resume_date,
                reason=reason,
                initiated_by=initiated_by,
                audit_action=audit_action,
                restore_provider_team=restore_provider_team,
                is_staff_override=is_staff_override,
                correlation_id=correlation_id,
            )
            return {
                'scheduled': False,
                'effective_date': effective_date,
                'status': target_status,
                'correlation_id': str(correlation_id),
                **result,
            }

    @classmethod
    def transition_location(
        cls,
        *,
        location_id: int,
        action: str,
        effective_date,
        initiated_by=None,
        reason: str = '',
        resume_date=None,
        restore_staffing: bool = False,
        is_staff_override: bool = False,
    ) -> dict:
        """
        Выполняет или планирует lifecycle-переход для филиала.
        """
        target_status, audit_action = cls.LOCATION_ACTION_MAP[action]
        effective_date = cls._normalize_effective_date(effective_date)
        resume_date = cls._normalize_optional_date(resume_date)
        correlation_id = uuid4()

        with transaction.atomic():
            location = (
                ProviderLocation.objects.select_for_update()
                .select_related('provider')
                .get(pk=location_id)
            )
            cls._validate_location_transition(
                location=location,
                action=action,
                effective_date=effective_date,
                resume_date=resume_date,
            )

            if effective_date > timezone.localdate():
                cls._store_pending_location_transition(
                    location=location,
                    target_status=target_status,
                    effective_date=effective_date,
                    resume_date=resume_date,
                    reason=reason,
                    initiated_by=initiated_by,
                )
                cls._create_event(
                    entity_type=ProviderLifecycleEvent.ENTITY_LOCATION,
                    action=audit_action,
                    provider=location.provider,
                    location=location,
                    previous_status=location.lifecycle_status,
                    new_status=target_status,
                    effective_date=effective_date,
                    resume_date=resume_date,
                    reason=reason,
                    initiated_by=initiated_by,
                    is_staff_override=is_staff_override,
                    correlation_id=correlation_id,
                    metadata={'scheduled': True},
                )
                return {
                    'scheduled': True,
                    'effective_date': effective_date,
                    'status': target_status,
                    'correlation_id': str(correlation_id),
                }

            result = cls._apply_location_transition_locked(
                location=location,
                target_status=target_status,
                effective_date=effective_date,
                resume_date=resume_date,
                reason=reason,
                initiated_by=initiated_by,
                audit_action=audit_action,
                restore_staffing=restore_staffing,
                is_staff_override=is_staff_override,
                correlation_id=correlation_id,
            )
            cls._sync_access_roles_for_users(set(result.get('affected_user_ids', [])))
            return {
                'scheduled': False,
                'effective_date': effective_date,
                'status': target_status,
                'correlation_id': str(correlation_id),
                **result,
            }

    @classmethod
    def bulk_reactivate_locations(
        cls,
        *,
        provider_id: int,
        location_ids: list[int],
        effective_date,
        initiated_by=None,
        reason: str = '',
        restore_staffing: bool = True,
        is_staff_override: bool = False,
    ) -> dict:
        """
        Пакетная реактивация выбранных филиалов организации.
        """
        normalized_ids = list(dict.fromkeys(location_ids))
        if not normalized_ids:
            raise ValidationError(_('At least one location must be selected.'))

        provider = Provider.objects.filter(pk=provider_id).only('id').first()
        if provider is None:
            raise ValidationError(_('Organization does not exist.'))

        found_ids = set(
            ProviderLocation.objects.filter(
                provider_id=provider_id,
                id__in=normalized_ids,
            ).values_list('id', flat=True)
        )
        if found_ids != set(normalized_ids):
            raise ValidationError(_('One or more selected locations do not belong to this organization.'))

        results = []
        restored_location_ids: list[int] = []
        restored_user_ids: set[int] = set()
        for location_id in normalized_ids:
            result = cls.transition_location(
                location_id=location_id,
                action='reactivate',
                effective_date=effective_date,
                initiated_by=initiated_by,
                reason=reason,
                restore_staffing=restore_staffing,
                is_staff_override=is_staff_override,
            )
            results.append({
                'location_id': location_id,
                'status': result['status'],
                'scheduled': result['scheduled'],
                'restored_location_role_ids': result.get('restored_location_role_ids', []),
            })
            if result.get('restored_location_role_ids'):
                restored_location_ids.append(location_id)
            restored_user_ids.update(result.get('affected_user_ids', []))

        return {
            'count': len(results),
            'results': results,
            'restored_location_ids': restored_location_ids,
            'affected_user_ids': sorted(restored_user_ids),
        }

    @classmethod
    def apply_pending_transitions(cls) -> dict:
        """
        Применяет все lifecycle-переходы, чей effective_date уже наступил.
        """
        today = timezone.localdate()
        provider_ids = list(
            Provider.objects.filter(
                pending_partnership_status__gt='',
                pending_partnership_effective_date__isnull=False,
                pending_partnership_effective_date__lte=today,
            ).values_list('id', flat=True)
        )
        location_ids = list(
            ProviderLocation.objects.filter(
                pending_lifecycle_status__gt='',
                pending_lifecycle_effective_date__isnull=False,
                pending_lifecycle_effective_date__lte=today,
            ).values_list('id', flat=True)
        )

        applied_providers = 0
        applied_locations = 0

        for provider_id in provider_ids:
            provider = Provider.objects.filter(pk=provider_id).only(
                'id',
                'pending_partnership_status',
                'pending_partnership_effective_date',
                'pending_partnership_resume_date',
                'pending_partnership_reason',
                'pending_partnership_requested_by_id',
            ).first()
            if provider is None:
                continue
            action = cls._provider_action_from_status(provider.pending_partnership_status)
            if action is None:
                continue
            cls.transition_provider(
                provider_id=provider.id,
                action=action,
                effective_date=provider.pending_partnership_effective_date,
                initiated_by=provider.pending_partnership_requested_by,
                reason=provider.pending_partnership_reason,
                resume_date=provider.pending_partnership_resume_date,
            )
            applied_providers += 1

        for location_id in location_ids:
            location = ProviderLocation.objects.filter(pk=location_id).only(
                'id',
                'pending_lifecycle_status',
                'pending_lifecycle_effective_date',
                'pending_lifecycle_resume_date',
                'pending_lifecycle_reason',
                'pending_lifecycle_requested_by_id',
            ).first()
            if location is None:
                continue
            action = cls._location_action_from_status(location.pending_lifecycle_status)
            if action is None:
                continue
            cls.transition_location(
                location_id=location.id,
                action=action,
                effective_date=location.pending_lifecycle_effective_date,
                initiated_by=location.pending_lifecycle_requested_by,
                reason=location.pending_lifecycle_reason,
                resume_date=location.pending_lifecycle_resume_date,
            )
            applied_locations += 1

        return {
            'providers': applied_providers,
            'locations': applied_locations,
        }

    @classmethod
    def _apply_provider_transition_locked(
        cls,
        *,
        provider: Provider,
        target_status: str,
        effective_date,
        resume_date,
        reason: str,
        initiated_by,
        audit_action: str,
        restore_provider_team: bool,
        is_staff_override: bool,
        correlation_id: UUID,
    ) -> dict:
        """
        Применяет org-level lifecycle непосредственно внутри транзакции.
        """
        current_status = provider.partnership_status
        previous_effective_date = provider.partnership_effective_date
        now = timezone.now()
        access_until = None
        changed_location_ids: list[int] = []
        affected_user_ids: set[int] = set()
        restored_provider_link_ids: list[int] = []

        if target_status == Provider.PARTNERSHIP_STATUS_TERMINATED:
            access_until = cls._build_owner_access_until(now)

        provider.partnership_status = target_status
        provider.partnership_effective_date = effective_date
        provider.partnership_resume_date = (
            resume_date
            if target_status == Provider.PARTNERSHIP_STATUS_TEMPORARILY_INACTIVE
            else None
        )
        provider.partnership_reason = reason
        provider.partnership_status_changed_at = now
        provider.partnership_status_changed_by = initiated_by
        provider.post_termination_access_until = access_until
        provider.is_active = (
            provider.activation_status == 'active'
            and target_status == Provider.PARTNERSHIP_STATUS_ACTIVE
        )
        cls._clear_pending_provider_transition(provider)
        provider.save(update_fields=[
            'partnership_status',
            'partnership_effective_date',
            'partnership_resume_date',
            'partnership_reason',
            'partnership_status_changed_at',
            'partnership_status_changed_by',
            'post_termination_access_until',
            'pending_partnership_status',
            'pending_partnership_effective_date',
            'pending_partnership_resume_date',
            'pending_partnership_reason',
            'pending_partnership_requested_at',
            'pending_partnership_requested_by',
            'is_active',
            'updated_at',
        ])

        if target_status in {
            Provider.PARTNERSHIP_STATUS_TEMPORARILY_INACTIVE,
            Provider.PARTNERSHIP_STATUS_TERMINATED,
        }:
            location_target_status = (
                ProviderLocation.LIFECYCLE_STATUS_TEMPORARILY_CLOSED
                if target_status == Provider.PARTNERSHIP_STATUS_TEMPORARILY_INACTIVE
                else ProviderLocation.LIFECYCLE_STATUS_DEACTIVATED
            )
            location_audit_action = (
                ProviderLifecycleEvent.ACTION_LOCATION_TEMP_CLOSE
                if target_status == Provider.PARTNERSHIP_STATUS_TEMPORARILY_INACTIVE
                else ProviderLifecycleEvent.ACTION_LOCATION_DEACTIVATE
            )
            for location in (
                ProviderLocation.objects.select_for_update()
                .filter(provider=provider)
                .select_related('provider')
            ):
                if (
                    target_status == Provider.PARTNERSHIP_STATUS_TEMPORARILY_INACTIVE
                    and location.lifecycle_status == ProviderLocation.LIFECYCLE_STATUS_DEACTIVATED
                ):
                    continue
                location_result = cls._apply_location_transition_locked(
                    location=location,
                    target_status=location_target_status,
                    effective_date=effective_date,
                    resume_date=(
                        resume_date
                        if target_status == Provider.PARTNERSHIP_STATUS_TEMPORARILY_INACTIVE
                        else None
                    ),
                    reason=reason,
                    initiated_by=initiated_by,
                    audit_action=location_audit_action,
                    restore_staffing=False,
                    is_staff_override=is_staff_override,
                    correlation_id=correlation_id,
                )
                changed_location_ids.append(location.id)
                affected_user_ids.update(location_result.get('affected_user_ids', []))

        if target_status == Provider.PARTNERSHIP_STATUS_TERMINATED:
            provider_link_query = (
                EmployeeProvider.objects.select_for_update()
                .filter(provider=provider, employee__user__isnull=False)
                .filter(Q(end_date__isnull=True) | Q(end_date__gte=timezone.localdate()))
                .select_related('employee__user')
            )
            today = timezone.localdate()
            for link in provider_link_query:
                affected_user_ids.add(link.employee.user_id)
                if link.is_owner:
                    continue
                link.end_date = today
                link.is_provider_admin = False
                link.is_provider_manager = False
                link.is_manager = False
                link.save(update_fields=[
                    'end_date',
                    'is_provider_admin',
                    'is_provider_manager',
                    'is_manager',
                    'updated_at',
                ])

            role_end = timezone.now()
            location_role_query = (
                EmployeeLocationRole.objects.select_for_update()
                .filter(provider_location__provider=provider, employee__user__isnull=False)
                .filter(Q(end_date__isnull=True) | Q(end_date__gte=role_end))
                .select_related('employee__user')
            )
            for role in location_role_query:
                affected_user_ids.add(role.employee.user_id)
                role.is_active = False
                role.end_date = role_end
                role.save(update_fields=['is_active', 'end_date'])
        elif (
            target_status == Provider.PARTNERSHIP_STATUS_ACTIVE
            and current_status == Provider.PARTNERSHIP_STATUS_TERMINATED
            and restore_provider_team
        ):
            restored_provider_link_ids, restored_user_ids = cls._restore_provider_team_after_reactivation(
                provider=provider,
                terminated_effective_date=previous_effective_date,
            )
            affected_user_ids.update(restored_user_ids)

        cls._create_event(
            entity_type=ProviderLifecycleEvent.ENTITY_PROVIDER,
            action=audit_action,
            provider=provider,
            location=None,
            previous_status=current_status,
            new_status=target_status,
            effective_date=effective_date,
            resume_date=resume_date,
            reason=reason,
            initiated_by=initiated_by,
            is_staff_override=is_staff_override,
            correlation_id=correlation_id,
            metadata={
                'scheduled': False,
                'changed_location_ids': changed_location_ids,
                'restored_provider_link_ids': restored_provider_link_ids,
            },
        )

        cls._sync_access_roles_for_users(affected_user_ids)
        cls._send_org_notifications(
            provider=provider,
            target_status=target_status,
            effective_date=effective_date,
            reason=reason,
        )
        return {
            'changed_location_ids': changed_location_ids,
            'affected_user_ids': list(affected_user_ids),
            'owner_access_until': access_until.isoformat() if access_until else None,
            'restored_provider_link_ids': restored_provider_link_ids,
        }

    @classmethod
    def _apply_location_transition_locked(
        cls,
        *,
        location: ProviderLocation,
        target_status: str,
        effective_date,
        resume_date,
        reason: str,
        initiated_by,
        audit_action: str,
        restore_staffing: bool,
        is_staff_override: bool,
        correlation_id: UUID,
    ) -> dict:
        """
        Применяет lifecycle к филиалу непосредственно внутри транзакции.
        """
        current_status = location.lifecycle_status
        previous_effective_date = location.lifecycle_effective_date
        location.lifecycle_status = target_status
        location.lifecycle_effective_date = effective_date
        location.lifecycle_resume_date = (
            resume_date
            if target_status == ProviderLocation.LIFECYCLE_STATUS_TEMPORARILY_CLOSED
            else None
        )
        location.lifecycle_reason = reason
        location.lifecycle_status_changed_at = timezone.now()
        location.lifecycle_status_changed_by = initiated_by
        location.is_active = target_status == ProviderLocation.LIFECYCLE_STATUS_ACTIVE
        cls._clear_pending_location_transition(location)
        location.save(update_fields=[
            'lifecycle_status',
            'lifecycle_effective_date',
            'lifecycle_resume_date',
            'lifecycle_reason',
            'lifecycle_status_changed_at',
            'lifecycle_status_changed_by',
            'pending_lifecycle_status',
            'pending_lifecycle_effective_date',
            'pending_lifecycle_resume_date',
            'pending_lifecycle_reason',
            'pending_lifecycle_requested_at',
            'pending_lifecycle_requested_by',
            'is_active',
            'updated_at',
        ])

        cancelled_booking_ids: list[int] = []
        if target_status != ProviderLocation.LIFECYCLE_STATUS_ACTIVE:
            cancelled_booking_ids = cls._cancel_future_bookings_for_location(
                location=location,
                effective_date=effective_date,
                reason_text=reason,
            )

        affected_user_ids = set(
            EmployeeLocationRole.objects.filter(
                provider_location=location,
                employee__user__isnull=False,
            ).values_list('employee__user_id', flat=True)
        )
        restored_location_role_ids: list[int] = []
        if (
            target_status == ProviderLocation.LIFECYCLE_STATUS_ACTIVE
            and restore_staffing
        ):
            restored_location_role_ids, restored_user_ids = cls._restore_location_team_after_reactivation(
                location=location,
                inactive_since_date=previous_effective_date,
            )
            affected_user_ids.update(restored_user_ids)

        cls._create_event(
            entity_type=ProviderLifecycleEvent.ENTITY_LOCATION,
            action=audit_action,
            provider=location.provider,
            location=location,
            previous_status=current_status,
            new_status=target_status,
            effective_date=effective_date,
            resume_date=resume_date,
            reason=reason,
            initiated_by=initiated_by,
            is_staff_override=is_staff_override,
            correlation_id=correlation_id,
            metadata={
                'scheduled': False,
                'cancelled_booking_ids': cancelled_booking_ids,
                'restored_location_role_ids': restored_location_role_ids,
            },
        )
        cls._send_location_notifications(
            location=location,
            target_status=target_status,
            effective_date=effective_date,
            reason=reason,
        )
        return {
            'cancelled_booking_ids': cancelled_booking_ids,
            'affected_user_ids': list(affected_user_ids),
            'restored_location_role_ids': restored_location_role_ids,
        }

    @classmethod
    def _validate_provider_transition(cls, *, provider: Provider, action: str, effective_date, resume_date) -> None:
        """
        Валидация допустимости org-level перехода.
        """
        if effective_date is None:
            raise ValidationError(_('Effective date is required.'))
        if action == 'pause' and not resume_date:
            raise ValidationError(_('Resume date is required for organization pause.'))
        if action == 'pause' and resume_date and resume_date < effective_date:
            raise ValidationError(_('Resume date must be on or after the effective date.'))
        if action in {'pause', 'terminate'} and provider.partnership_status != Provider.PARTNERSHIP_STATUS_ACTIVE:
            raise ValidationError(_('Only active organization can be paused or terminated.'))
        if action == 'terminate' and provider.partnership_status == Provider.PARTNERSHIP_STATUS_TERMINATED:
            raise ValidationError(_('Organization is already terminated.'))
        if action == 'pause' and provider.partnership_status == Provider.PARTNERSHIP_STATUS_TERMINATED:
            raise ValidationError(_('Terminated organization cannot be paused.'))
        if action == 'reactivate':
            if provider.partnership_status == Provider.PARTNERSHIP_STATUS_ACTIVE:
                raise ValidationError(_('Organization is already active.'))
            if provider.activation_status != 'active':
                raise ValidationError(_('Organization cannot be reactivated before activation is completed.'))
            if cls._provider_has_active_blocking(provider):
                raise ValidationError(_('Organization cannot be reactivated while billing blocking is active.'))

    @classmethod
    def _validate_location_transition(cls, *, location: ProviderLocation, action: str, effective_date, resume_date) -> None:
        """
        Валидация допустимости branch-level перехода.
        """
        if effective_date is None:
            raise ValidationError(_('Effective date is required.'))
        if action == 'temporary_close' and not resume_date:
            raise ValidationError(_('Resume date is required for temporary branch closure.'))
        if action == 'temporary_close' and resume_date and resume_date < effective_date:
            raise ValidationError(_('Resume date must be on or after the effective date.'))
        if action in {'temporary_close', 'deactivate'} and location.lifecycle_status != ProviderLocation.LIFECYCLE_STATUS_ACTIVE:
            raise ValidationError(_('Only active branch can be temporarily closed or deactivated.'))
        if action == 'reactivate':
            if location.lifecycle_status == ProviderLocation.LIFECYCLE_STATUS_ACTIVE:
                raise ValidationError(_('Branch is already active.'))
            provider = location.provider
            if provider.partnership_status != Provider.PARTNERSHIP_STATUS_ACTIVE:
                raise ValidationError(_('Location cannot be reactivated while organization is not active.'))
            if provider.activation_status != 'active':
                raise ValidationError(_('Location cannot be reactivated before organization activation is completed.'))
            if cls._provider_has_active_blocking(provider):
                raise ValidationError(_('Location cannot be reactivated while billing blocking is active.'))

    @classmethod
    def _normalize_effective_date(cls, value):
        """
        Нормализует входную дату effective_date.
        """
        normalized = cls._normalize_optional_date(value)
        if normalized is None:
            raise ValidationError(_('Effective date is required.'))
        return normalized

    @classmethod
    def _normalize_optional_date(cls, value):
        """
        Приводит вход к объекту date или None.
        """
        if value in (None, '', []):
            return None
        if isinstance(value, datetime):
            return value.date()
        if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day'):
            return value
        return datetime.fromisoformat(str(value)).date()

    @classmethod
    def _provider_action_from_status(cls, status_code: str) -> str | None:
        """
        Обратное отображение status -> action для scheduled org transitions.
        """
        reverse_map = {
            Provider.PARTNERSHIP_STATUS_TEMPORARILY_INACTIVE: 'pause',
            Provider.PARTNERSHIP_STATUS_TERMINATED: 'terminate',
            Provider.PARTNERSHIP_STATUS_ACTIVE: 'reactivate',
        }
        return reverse_map.get(status_code)

    @classmethod
    def _location_action_from_status(cls, status_code: str) -> str | None:
        """
        Обратное отображение status -> action для scheduled location transitions.
        """
        reverse_map = {
            ProviderLocation.LIFECYCLE_STATUS_TEMPORARILY_CLOSED: 'temporary_close',
            ProviderLocation.LIFECYCLE_STATUS_DEACTIVATED: 'deactivate',
            ProviderLocation.LIFECYCLE_STATUS_ACTIVE: 'reactivate',
        }
        return reverse_map.get(status_code)

    @classmethod
    def _store_pending_provider_transition(
        cls,
        *,
        provider: Provider,
        target_status: str,
        effective_date,
        resume_date,
        reason: str,
        initiated_by,
    ) -> None:
        """
        Сохраняет отложенный org-level переход.
        """
        provider.pending_partnership_status = target_status
        provider.pending_partnership_effective_date = effective_date
        provider.pending_partnership_resume_date = resume_date
        provider.pending_partnership_reason = reason
        provider.pending_partnership_requested_at = timezone.now()
        provider.pending_partnership_requested_by = initiated_by
        provider.save(update_fields=[
            'pending_partnership_status',
            'pending_partnership_effective_date',
            'pending_partnership_resume_date',
            'pending_partnership_reason',
            'pending_partnership_requested_at',
            'pending_partnership_requested_by',
            'updated_at',
        ])

    @classmethod
    def _store_pending_location_transition(
        cls,
        *,
        location: ProviderLocation,
        target_status: str,
        effective_date,
        resume_date,
        reason: str,
        initiated_by,
    ) -> None:
        """
        Сохраняет отложенный branch-level переход.
        """
        location.pending_lifecycle_status = target_status
        location.pending_lifecycle_effective_date = effective_date
        location.pending_lifecycle_resume_date = resume_date
        location.pending_lifecycle_reason = reason
        location.pending_lifecycle_requested_at = timezone.now()
        location.pending_lifecycle_requested_by = initiated_by
        location.save(update_fields=[
            'pending_lifecycle_status',
            'pending_lifecycle_effective_date',
            'pending_lifecycle_resume_date',
            'pending_lifecycle_reason',
            'pending_lifecycle_requested_at',
            'pending_lifecycle_requested_by',
            'updated_at',
        ])

    @staticmethod
    def _clear_pending_provider_transition(provider: Provider) -> None:
        provider.pending_partnership_status = ''
        provider.pending_partnership_effective_date = None
        provider.pending_partnership_resume_date = None
        provider.pending_partnership_reason = ''
        provider.pending_partnership_requested_at = None
        provider.pending_partnership_requested_by = None

    @staticmethod
    def _clear_pending_location_transition(location: ProviderLocation) -> None:
        location.pending_lifecycle_status = ''
        location.pending_lifecycle_effective_date = None
        location.pending_lifecycle_resume_date = None
        location.pending_lifecycle_reason = ''
        location.pending_lifecycle_requested_at = None
        location.pending_lifecycle_requested_by = None

    @classmethod
    def _build_owner_access_until(cls, now):
        """
        Строит дедлайн read-only доступа owner после termination.
        """
        lifecycle_settings = ProviderLifecycleSettings.get_solo()
        days = lifecycle_settings.owner_post_termination_access_days
        return now + timedelta(days=days)

    @classmethod
    def _cancel_future_bookings_for_location(cls, *, location: ProviderLocation, effective_date, reason_text: str) -> list[int]:
        """
        Отменяет активные будущие бронирования филиала с effective_date.
        """
        from booking.models import Booking, BookingCancellationReason
        from notifications.models import Notification

        reason = (
            BookingCancellationReason.objects.filter(
                code=CANCELLATION_REASON_PROVIDER_UNAVAILABLE,
                is_active=True,
            ).first()
            or BookingCancellationReason.get_default_reason(CANCELLED_BY_PROVIDER)
        )
        if reason is None:
            return []

        threshold = timezone.make_aware(datetime.combine(effective_date, time.min))
        bookings = list(
            Booking.objects.select_related('user', 'pet')
            .filter(
                provider_location=location,
                status__name__in=ACTIVE_BOOKING_STATUS_NAMES,
                start_time__gte=threshold,
            )
        )
        cancelled_ids: list[int] = []
        for booking in bookings:
            booking.cancel_booking(
                cancelled_by=CANCELLED_BY_PROVIDER,
                cancelled_by_user=None,
                cancellation_reason=reason,
                cancellation_reason_text=str(
                    _('Cancelled because the provider location became unavailable.')
                ),
            )
            lifecycle_note = reason_text.strip() or str(_('Provider location became unavailable.'))
            if booking.notes:
                booking.notes = f'{booking.notes}\n{lifecycle_note}'
            else:
                booking.notes = lifecycle_note
            booking.save(update_fields=[
                'status',
                'cancelled_by',
                'cancelled_by_user',
                'cancelled_at',
                'cancellation_reason',
                'cancellation_reason_text',
                'client_attendance',
                'visit_record',
                'notes',
                'updated_at',
            ])
            cancelled_ids.append(booking.id)
            if booking.user_id:
                Notification.objects.create(
                    user=booking.user,
                    pet=booking.pet,
                    notification_type='appointment',
                    title=str(_('Booking Cancelled')),
                    message=str(
                        _('Your booking at {location} was cancelled because the branch is unavailable.')
                    ).format(location=location.name),
                    priority='high',
                    channel='all',
                )
        return cancelled_ids

    @classmethod
    def _send_org_notifications(cls, *, provider: Provider, target_status: str, effective_date, reason: str) -> None:
        """
        Отправляет уведомления org-level участникам и billing manager.
        """
        from notifications.models import Notification

        title_map = {
            Provider.PARTNERSHIP_STATUS_TEMPORARILY_INACTIVE: _('Organization Paused'),
            Provider.PARTNERSHIP_STATUS_TERMINATED: _('Organization Terminated'),
            Provider.PARTNERSHIP_STATUS_ACTIVE: _('Organization Reactivated'),
        }
        message_map = {
            Provider.PARTNERSHIP_STATUS_TEMPORARILY_INACTIVE: _(
                'Organization {provider} is paused from {effective_date}.'
            ),
            Provider.PARTNERSHIP_STATUS_TERMINATED: _(
                'Organization {provider} is terminated from {effective_date}.'
            ),
            Provider.PARTNERSHIP_STATUS_ACTIVE: _(
                'Organization {provider} is active again from {effective_date}.'
            ),
        }
        title = title_map[target_status]
        message = str(message_map[target_status]).format(
            provider=provider.name,
            effective_date=effective_date.isoformat(),
        )
        if reason.strip():
            message = f'{message} {reason.strip()}'

        for user in cls._get_org_notification_users(provider):
            Notification.objects.create(
                user=user,
                notification_type='system',
                title=str(title),
                message=message,
                priority='high',
                channel='all',
            )

    @classmethod
    def _send_location_notifications(cls, *, location: ProviderLocation, target_status: str, effective_date, reason: str) -> None:
        """
        Отправляет уведомления участникам филиала и billing manager.
        """
        from notifications.models import Notification

        title_map = {
            ProviderLocation.LIFECYCLE_STATUS_TEMPORARILY_CLOSED: _('Branch Temporarily Closed'),
            ProviderLocation.LIFECYCLE_STATUS_DEACTIVATED: _('Branch Deactivated'),
            ProviderLocation.LIFECYCLE_STATUS_ACTIVE: _('Branch Reactivated'),
        }
        message_map = {
            ProviderLocation.LIFECYCLE_STATUS_TEMPORARILY_CLOSED: _(
                'Branch {location} is temporarily closed from {effective_date}.'
            ),
            ProviderLocation.LIFECYCLE_STATUS_DEACTIVATED: _(
                'Branch {location} is deactivated from {effective_date}.'
            ),
            ProviderLocation.LIFECYCLE_STATUS_ACTIVE: _(
                'Branch {location} is active again from {effective_date}.'
            ),
        }
        title = title_map[target_status]
        message = str(message_map[target_status]).format(
            location=location.name,
            effective_date=effective_date.isoformat(),
        )
        if reason.strip():
            message = f'{message} {reason.strip()}'

        for user in cls._get_location_notification_users(location):
            Notification.objects.create(
                user=user,
                notification_type='system',
                title=str(title),
                message=message,
                priority='high',
                channel='all',
            )

    @classmethod
    def _get_org_notification_users(cls, provider: Provider):
        """
        Собирает пользователей для org-level уведомлений.
        """
        users = {}
        for link in EmployeeProvider.get_active_admin_links(provider):
            user = getattr(link.employee, 'user', None)
            if user is not None:
                users[user.id] = user
        try:
            from billing.models import BillingManagerProvider

            for manager_provider in BillingManagerProvider.get_active_managers_for_provider(provider):
                manager = manager_provider.get_effective_manager()
                if manager is not None:
                    users[manager.id] = manager
        except Exception:
            pass
        return list(users.values())

    @classmethod
    def _get_location_notification_users(cls, location: ProviderLocation):
        """
        Собирает пользователей для branch-level уведомлений.
        """
        users = {user.id: user for user in cls._get_org_notification_users(location.provider)}
        location_users = (
            EmployeeLocationRole.objects.filter(
                provider_location=location,
                employee__user__isnull=False,
            )
            .select_related('employee__user')
        )
        for role in location_users:
            users[role.employee.user_id] = role.employee.user
        return list(users.values())

    @classmethod
    def _sync_access_roles_for_users(cls, user_ids: set[int]) -> None:
        """
        Синхронизирует compatibility-role access для затронутых пользователей.
        """
        from users.models import User

        if not user_ids:
            return
        for user in User.objects.filter(id__in=user_ids):
            ProviderPermissionService.sync_user_access_roles(user)

    @classmethod
    def _create_event(
        cls,
        *,
        entity_type: str,
        action: str,
        provider: Provider,
        location: ProviderLocation | None,
        previous_status: str,
        new_status: str,
        effective_date,
        resume_date,
        reason: str,
        initiated_by,
        is_staff_override: bool,
        correlation_id: UUID,
        metadata: dict,
    ) -> ProviderLifecycleEvent:
        """
        Пишет audit event lifecycle-операции.
        """
        return ProviderLifecycleEvent.objects.create(
            entity_type=entity_type,
            action=action,
            provider=provider,
            location=location,
            previous_status=previous_status or '',
            new_status=new_status or '',
            effective_date=effective_date,
            resume_date=resume_date,
            reason=reason,
            initiated_by=initiated_by,
            is_staff_override=is_staff_override,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )

    @classmethod
    def _provider_has_active_blocking(cls, provider: Provider) -> bool:
        """
        Проверяет наличие активной billing-blocking у организации.
        """
        return provider.blockings.filter(status='active').exists()

    @classmethod
    def _restore_provider_team_after_reactivation(cls, *, provider: Provider, terminated_effective_date):
        """
        Возвращает org-level связи сотрудников, которые были отключены при termination.
        """
        if terminated_effective_date is None:
            return [], set()

        restored_link_ids: list[int] = []
        restored_user_ids: set[int] = set()
        links = (
            EmployeeProvider.objects.select_for_update()
            .filter(
                provider=provider,
                is_owner=False,
                end_date=terminated_effective_date,
                employee__user__isnull=False,
            )
            .select_related('employee__user')
        )
        for link in links:
            link.end_date = None
            link.is_provider_admin = link.role == EmployeeProvider.ROLE_PROVIDER_ADMIN
            link.is_provider_manager = link.role == EmployeeProvider.ROLE_PROVIDER_MANAGER
            link.is_manager = link.role == EmployeeProvider.ROLE_PROVIDER_MANAGER
            link.save(update_fields=[
                'end_date',
                'is_provider_admin',
                'is_provider_manager',
                'is_manager',
                'updated_at',
            ])
            restored_link_ids.append(link.id)
            restored_user_ids.add(link.employee.user_id)
        return restored_link_ids, restored_user_ids

    @classmethod
    def _restore_location_team_after_reactivation(cls, *, location: ProviderLocation, inactive_since_date):
        """
        Возвращает branch-level роли сотрудников, если филиал восстановлен после termination.
        """
        roles = EmployeeLocationRole.objects.select_for_update().filter(
            provider_location=location,
            is_active=False,
            employee__user__isnull=False,
        )
        if inactive_since_date is not None:
            roles = roles.filter(end_date__date=inactive_since_date)

        restored_role_ids: list[int] = []
        restored_user_ids: set[int] = set()
        for role in roles.select_related('employee__user'):
            role.is_active = True
            role.end_date = None
            role.save(update_fields=['is_active', 'end_date'])
            restored_role_ids.append(role.id)
            restored_user_ids.add(role.employee.user_id)

        if restored_role_ids:
            EmployeeLocationRole.sync_location_manager(location)
        return restored_role_ids, restored_user_ids
