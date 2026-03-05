"""
Бизнес-логика приёма инвайтов и утилита условного снятия UserType.

Каждый accept handler реализует текущую логику из старых API views;
обязательно назначает UserType принявшему; при замене роли вызывает
maybe_remove_role для предыдущего пользователя.
"""
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


def _get_employee(user):
    """Возвращает Employee для user (get_or_create)."""
    from providers.models import Employee
    return Employee.objects.get_or_create(user=user, defaults={'is_active': True})[0]


def _active_employee_provider_q():
    """Q-объект для активных записей EmployeeProvider."""
    today = timezone.now().date()
    return Q(end_date__isnull=True) | Q(end_date__gte=today)


def maybe_remove_role(user, role_name):
    """
    Условно снимает UserType у пользователя.
    Снимает ТОЛЬКО если у пользователя не осталось ни одной
    активной связи, требующей эту роль.
    """
    from providers.models import EmployeeProvider
    from billing.models import BillingManagerProvider
    from pets.models import Pet

    if role_name == 'provider_admin':
        has_active = EmployeeProvider.objects.filter(
            employee__user=user,
            is_provider_admin=True,
            end_date__isnull=True,
        ).exists()
        if not has_active:
            user.remove_role('provider_admin')

    elif role_name == 'provider_manager':
        has_active = EmployeeProvider.objects.filter(
            employee__user=user,
            is_provider_manager=True,
            end_date__isnull=True,
        ).exists()
        if not has_active:
            user.remove_role('provider_manager')

    elif role_name == 'employee':
        has_active = EmployeeProvider.objects.filter(
            employee__user=user,
            end_date__isnull=True,
        ).exists()
        if not has_active:
            user.remove_role('employee')

    elif role_name == 'billing_manager':
        has_active = BillingManagerProvider.objects.filter(
            billing_manager=user,
            status__in=['active', 'vacation', 'temporary'],
        ).exists()
        if not has_active:
            user.remove_role('billing_manager')

    elif role_name == 'branch_manager':
        from providers.models import ProviderLocation
        has_active = ProviderLocation.objects.filter(manager=user).exists()
        if not has_active:
            user.remove_role('branch_manager')

    elif role_name == 'pet_owner':
        from pets.models import PetOwner
        has_pets = PetOwner.objects.filter(
            user=user,
            pet__is_active=True,
        ).exists()
        if not has_pets:
            user.remove_role('pet_owner')

    elif role_name == 'specialist':
        has_active = EmployeeProvider.objects.filter(
            employee__user=user,
            end_date__isnull=True,
        ).exists()
        if not has_active:
            user.remove_role('specialist')


def accept_invite(invite, user):
    """
    Принимает инвайт пользователем. Вызывается из invite.accept(user).
    Маршрутизирует по invite_type и вызывает соответствующий handler.
    Ожидается вызов внутри transaction.atomic.
    """
    from invites.models import Invite

    if not invite.can_be_accepted():
        raise ValueError(_('Invite cannot be accepted.'))
    if user.email.lower() != invite.email.lower():
        raise ValueError(_('Email does not match invite.'))

    handlers = {
        Invite.TYPE_PROVIDER_MANAGER: _accept_provider_manager,
        Invite.TYPE_PROVIDER_ADMIN: _accept_provider_admin,
        Invite.TYPE_BRANCH_MANAGER: _accept_branch_manager,
        Invite.TYPE_SPECIALIST: _accept_specialist,
        Invite.TYPE_PET_CO_OWNER: _accept_pet_co_owner,
        Invite.TYPE_PET_TRANSFER: _accept_pet_transfer,
    }
    handler = handlers.get(invite.invite_type)
    if not handler:
        raise ValueError(_('Unknown invite type.'))
    handler(invite, user)

    invite.status = Invite.STATUS_ACCEPTED
    invite.accepted_at = timezone.now()
    invite.accepted_by = user
    invite.save(update_fields=['status', 'accepted_at', 'accepted_by'])


def _accept_provider_manager(invite, user):
    """Принимает инвайт менеджера организации."""
    from providers.models import EmployeeProvider

    provider = invite.provider
    today = timezone.now().date()

    old_manager_eps = list(
        EmployeeProvider.objects.filter(
            provider=provider,
            is_provider_manager=True,
            end_date__isnull=True,
        ).select_related('employee__user')
    )
    old_manager_users = [ep.employee.user for ep in old_manager_eps]

    EmployeeProvider.objects.filter(
        provider=provider,
        is_provider_manager=True,
        end_date__isnull=True,
    ).update(is_provider_manager=False, is_manager=False)

    employee = _get_employee(user)
    ep, created = EmployeeProvider.objects.get_or_create(
        employee=employee,
        provider=provider,
        start_date=today,
        defaults={
            'end_date': None,
            'role': EmployeeProvider.ROLE_PROVIDER_MANAGER,
            'is_owner': False,
            'is_provider_manager': True,
            'is_provider_admin': False,
            'is_manager': True,
        },
    )
    if not created:
        ep.is_provider_manager = True
        ep.is_manager = True
        ep.save(update_fields=['is_provider_manager', 'is_manager'])

    # Назначаем только UserType, соответствующий роли по инвайту (manager, не admin).
    user.add_role('provider_manager')

    for old_user in old_manager_users:
        if old_user.pk != user.pk:
            maybe_remove_role(old_user, 'provider_manager')
            maybe_remove_role(old_user, 'provider_admin')


def _accept_provider_admin(invite, user):
    """Принимает инвайт админа организации."""
    from providers.models import EmployeeProvider

    provider = invite.provider
    today = timezone.now().date()
    employee = _get_employee(user)
    ep = EmployeeProvider.objects.filter(
        employee=employee,
        provider=provider,
        end_date__isnull=True,
    ).first()
    if not ep:
        EmployeeProvider.objects.create(
            employee=employee,
            provider=provider,
            start_date=today,
            end_date=None,
            role=EmployeeProvider.ROLE_PROVIDER_ADMIN,
            is_owner=False,
            is_provider_manager=False,
            is_provider_admin=True,
            is_manager=False,
        )
    elif not ep.is_provider_admin:
        ep.is_provider_admin = True
        ep.role = EmployeeProvider.ROLE_PROVIDER_ADMIN
        ep.save(update_fields=['is_provider_admin', 'role'])
    user.add_role('provider_admin')


def _accept_branch_manager(invite, user):
    """Принимает инвайт руководителя филиала."""
    from providers.models import EmployeeProvider, ProviderLocation

    location = invite.provider_location
    provider = location.provider
    old_manager = location.manager

    location.manager = user
    location.save(update_fields=['manager'])

    employee = _get_employee(user)
    ep = EmployeeProvider.objects.filter(
        employee=employee,
        provider=provider,
        end_date__isnull=True,
    ).first()
    if not ep:
        EmployeeProvider.objects.create(
            employee=employee,
            provider=provider,
            start_date=timezone.now().date(),
            end_date=None,
            role=EmployeeProvider.ROLE_SERVICE_WORKER,
            is_owner=False,
            is_provider_manager=False,
            is_provider_admin=False,
            is_manager=False,
        )
    if not employee.locations.filter(pk=location.pk).exists():
        employee.locations.add(location)

    user.add_role('branch_manager')
    if old_manager and old_manager.pk != user.pk:
        maybe_remove_role(old_manager, 'branch_manager')


def _accept_specialist(invite, user):
    """Принимает инвайт в персонал филиала."""
    from providers.models import Employee, EmployeeProvider

    location = invite.provider_location
    provider = location.provider
    employee, _ = Employee.objects.get_or_create(
        user=user,
        defaults={'is_active': True},
    )
    ep = EmployeeProvider.objects.filter(
        employee=employee,
        provider=provider,
        end_date__isnull=True,
    ).first()
    if not ep:
        EmployeeProvider.objects.create(
            employee=employee,
            provider=provider,
            start_date=timezone.now().date(),
            end_date=None,
            role=EmployeeProvider.ROLE_SERVICE_WORKER,
            is_owner=False,
            is_provider_manager=False,
            is_provider_admin=False,
            is_manager=False,
        )
    if not employee.locations.filter(pk=location.pk).exists():
        employee.locations.add(location)
    user.add_role('specialist')


def _accept_pet_co_owner(invite, user):
    """Принимает инвайт совладельца питомца."""
    from pets.models import PetOwner
    PetOwner.objects.get_or_create(
        pet=invite.pet, user=user,
        defaults={'role': 'coowner'},
    )
    user.add_role('pet_owner')


def _accept_pet_transfer(invite, user):
    """Принимает инвайт передачи прав основного владельца."""
    from pets.models import PetOwner
    pet = invite.pet
    old_main_owner = pet.main_owner

    # Понижаем текущего main → coowner
    PetOwner.objects.filter(
        pet=pet, role='main'
    ).update(role='coowner')

    # Назначаем нового main (или создаём)
    po, created = PetOwner.objects.get_or_create(
        pet=pet, user=user,
        defaults={'role': 'main'},
    )
    if not created:
        PetOwner.objects.filter(pk=po.pk).update(role='main')

    user.add_role('pet_owner')
    if old_main_owner and old_main_owner.pk != user.pk:
        maybe_remove_role(old_main_owner, 'pet_owner')