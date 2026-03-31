"""Provider RBAC permission service and compatibility sync helpers."""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from users.models import UserType

from .models import (
    EmployeeLocationRole,
    EmployeeProvider,
    Provider,
    ProviderLocation,
    ProviderResource,
    ProviderRole,
    ProviderRolePermission,
)
from .rbac_defaults import PERMISSION_MATRIX, RESOURCE_DEFINITIONS, ROLE_DEFINITIONS, get_matrix_entry


ROLE_PRIORITY = {
    'owner': 1,
    'provider_admin': 2,
    'provider_manager': 3,
    'branch_manager': 4,
    'worker': 5,
}
SCOPE_PRIORITY = {
    ProviderRolePermission.SCOPE_OWN_ONLY: 1,
    ProviderRolePermission.SCOPE_OWN_BRANCH: 2,
    ProviderRolePermission.SCOPE_ALL: 3,
}
PROVIDER_ACCESS_ROLE_NAMES = (
    'owner',
    'provider_admin',
    'provider_manager',
    'branch_manager',
    'specialist',
    'worker',
)


class ProviderPermissionService:
    """Central provider RBAC service with compatibility fallbacks."""

    _permission_cache_attr = '_provider_permission_cache'
    _roles_cache_attr = '_provider_role_cache'
    _branch_cache_attr = '_provider_branch_locations_cache'
    _member_cache_attr = '_provider_member_locations_cache'
    _member_backed_branch_read_resources = frozenset({
        'locations.list',
        'locations.services',
    })

    @classmethod
    def _get_provider_id(cls, provider) -> int | None:
        return getattr(provider, 'id', provider)

    @staticmethod
    def _is_system_like(user) -> bool:
        if not getattr(user, 'is_authenticated', False):
            return False
        if getattr(user, 'is_superuser', False):
            return True
        is_system_admin = getattr(user, 'is_system_admin', None)
        if callable(is_system_admin):
            try:
                return bool(is_system_admin())
            except TypeError:
                return False
        return False

    @classmethod
    def _get_cache(cls, user, attr_name: str) -> dict:
        cache = getattr(user, attr_name, None)
        if cache is None:
            cache = {}
            setattr(user, attr_name, cache)
        return cache

    @classmethod
    def _get_active_provider_links(cls, user, provider):
        provider_id = cls._get_provider_id(provider)
        today = timezone.localdate()
        return EmployeeProvider.objects.filter(
            employee__user=user,
            employee__is_active=True,
            provider_id=provider_id,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).select_related('employee', 'provider')

    @classmethod
    def _get_active_location_roles(cls, user, provider):
        provider_id = cls._get_provider_id(provider)
        now = timezone.now()
        return EmployeeLocationRole.objects.filter(
            employee__user=user,
            employee__is_active=True,
            provider_location__provider_id=provider_id,
            provider_location__is_active=True,
            is_active=True,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=now)
        ).select_related('employee', 'provider_location', 'provider_location__provider')

    @classmethod
    def get_user_branch_locations(cls, user, provider):
        provider_id = cls._get_provider_id(provider)
        cache = cls._get_cache(user, cls._branch_cache_attr)
        if provider_id in cache:
            return cache[provider_id]

        if cls._is_system_like(user):
            queryset = ProviderLocation.objects.filter(
                provider_id=provider_id,
                is_active=True,
            ).select_related('provider', 'manager')
            cache[provider_id] = queryset
            return queryset

        now = timezone.now()
        queryset = ProviderLocation.objects.filter(
            provider_id=provider_id,
            is_active=True,
        ).filter(
            Q(manager=user)
            | (
                Q(employee_roles__employee__user=user)
                & Q(employee_roles__employee__is_active=True)
                & Q(employee_roles__is_active=True)
                & (Q(employee_roles__end_date__isnull=True) | Q(employee_roles__end_date__gte=now))
                & Q(employee_roles__role=EmployeeLocationRole.ROLE_BRANCH_MANAGER)
            )
        ).select_related('provider', 'manager').distinct()
        cache[provider_id] = queryset
        return queryset

    @classmethod
    def get_user_member_locations(cls, user, provider):
        provider_id = cls._get_provider_id(provider)
        cache = cls._get_cache(user, cls._member_cache_attr)
        if provider_id in cache:
            return cache[provider_id]

        if cls._is_system_like(user):
            queryset = ProviderLocation.objects.filter(
                provider_id=provider_id,
                is_active=True,
            ).select_related('provider', 'manager')
            cache[provider_id] = queryset
            return queryset

        now = timezone.now()
        queryset = ProviderLocation.objects.filter(
            provider_id=provider_id,
            is_active=True,
        ).filter(
            Q(manager=user)
            | (
                Q(employee_roles__employee__user=user)
                & Q(employee_roles__employee__is_active=True)
                & Q(employee_roles__is_active=True)
                & (Q(employee_roles__end_date__isnull=True) | Q(employee_roles__end_date__gte=now))
            )
        ).select_related('provider', 'manager').distinct()
        cache[provider_id] = queryset
        return queryset

    @classmethod
    def _branch_scope_includes_member_locations(cls, resource_code: str, action: str) -> bool:
        return action == 'read' and resource_code in cls._member_backed_branch_read_resources

    @classmethod
    def get_location_ids_for_scope(cls, user, provider, resource_code: str, scope: str, action: str = 'read') -> set[int]:
        provider_id = cls._get_provider_id(provider)
        if cls._is_system_like(user):
            return set(
                ProviderLocation.objects.filter(
                    provider_id=provider_id,
                    is_active=True,
                ).values_list('id', flat=True)
            )

        member_location_ids = set(
            cls.get_user_member_locations(user, provider).values_list('id', flat=True)
        )
        if scope == ProviderRolePermission.SCOPE_OWN_ONLY:
            return member_location_ids

        branch_location_ids = set(
            cls.get_user_branch_locations(user, provider).values_list('id', flat=True)
        )
        if scope == ProviderRolePermission.SCOPE_OWN_BRANCH:
            if cls._branch_scope_includes_member_locations(resource_code, action):
                branch_location_ids.update(member_location_ids)
            return branch_location_ids

        return set(
            ProviderLocation.objects.filter(
                provider_id=provider_id,
                is_active=True,
            ).values_list('id', flat=True)
        )

    @classmethod
    def get_user_roles_for_provider(cls, user, provider) -> list[str]:
        provider_id = cls._get_provider_id(provider)
        cache = cls._get_cache(user, cls._roles_cache_attr)
        if provider_id in cache:
            return cache[provider_id]

        if cls._is_system_like(user):
            roles = [role['code'] for role in ROLE_DEFINITIONS]
            cache[provider_id] = roles
            return roles

        roles: set[str] = set()
        provider_links = list(cls._get_active_provider_links(user, provider))
        for link in provider_links:
            roles.update(link.get_effective_role_codes())

        active_location_roles = list(cls._get_active_location_roles(user, provider))
        if any(role.role == EmployeeLocationRole.ROLE_BRANCH_MANAGER for role in active_location_roles):
            roles.add(ProviderRole.CODE_BRANCH_MANAGER)
        if active_location_roles:
            roles.add(ProviderRole.CODE_WORKER)

        branch_locations = cls.get_user_branch_locations(user, provider)
        if branch_locations.exists():
            roles.add(ProviderRole.CODE_BRANCH_MANAGER)

        member_locations = cls.get_user_member_locations(user, provider)
        if member_locations.exists():
            roles.add(ProviderRole.CODE_WORKER)

        sorted_roles = sorted(roles, key=lambda code: ROLE_PRIORITY.get(code, 100))
        cache[provider_id] = sorted_roles
        return sorted_roles

    @classmethod
    def get_primary_role(cls, user, provider) -> str | None:
        roles = cls.get_user_roles_for_provider(user, provider)
        return roles[0] if roles else None

    @classmethod
    def _get_role_permission_rows(cls, role_codes: list[str]) -> list[dict]:
        queryset = list(
            ProviderRolePermission.objects.filter(
                role__code__in=role_codes,
                role__is_active=True,
                resource__is_active=True,
            ).select_related('role', 'resource')
        )
        if queryset:
            return [
                {
                    'role_code': item.role.code,
                    'resource_code': item.resource.code,
                    'can_create': item.can_create,
                    'can_read': item.can_read,
                    'can_update': item.can_update,
                    'can_delete': item.can_delete,
                    'scope': item.scope,
                }
                for item in queryset
            ]

        rows: list[dict] = []
        for role_code in role_codes:
            for resource in RESOURCE_DEFINITIONS:
                if resource['code'] not in PERMISSION_MATRIX.get(role_code, {}):
                    continue
                entry = get_matrix_entry(role_code, resource['code'])
                rows.append({
                    'role_code': role_code,
                    'resource_code': resource['code'],
                    **entry,
                })
        return rows

    @classmethod
    def _merge_permission(cls, current: dict, incoming: dict) -> dict:
        merged = dict(current)
        for action_key in ('can_create', 'can_read', 'can_update', 'can_delete'):
            merged[action_key] = bool(current.get(action_key)) or bool(incoming.get(action_key))
        current_scope = current.get('scope') or ProviderRolePermission.SCOPE_OWN_ONLY
        incoming_scope = incoming.get('scope') or ProviderRolePermission.SCOPE_OWN_ONLY
        merged['scope'] = incoming_scope if SCOPE_PRIORITY.get(incoming_scope, 0) >= SCOPE_PRIORITY.get(current_scope, 0) else current_scope
        return merged

    @classmethod
    def get_user_permissions(cls, user, provider) -> dict:
        provider_id = cls._get_provider_id(provider)
        cache = cls._get_cache(user, cls._permission_cache_attr)
        if provider_id in cache:
            return cache[provider_id]

        if cls._is_system_like(user):
            permissions = {}
            resources = ProviderResource.objects.filter(is_active=True).values_list('code', flat=True)
            resource_codes = list(resources) or [item['code'] for item in RESOURCE_DEFINITIONS]
            for code in resource_codes:
                permissions[code] = {
                    'can_create': True,
                    'can_read': True,
                    'can_update': True,
                    'can_delete': True,
                    'scope': ProviderRolePermission.SCOPE_ALL,
                }
            cache[provider_id] = permissions
            return permissions

        role_codes = cls.get_user_roles_for_provider(user, provider)
        permissions: dict[str, dict] = {}
        for row in cls._get_role_permission_rows(role_codes):
            resource_code = row['resource_code']
            if not any(row[key] for key in ('can_create', 'can_read', 'can_update', 'can_delete')):
                continue
            current = permissions.get(resource_code, {
                'can_create': False,
                'can_read': False,
                'can_update': False,
                'can_delete': False,
                'scope': ProviderRolePermission.SCOPE_OWN_ONLY,
            })
            permissions[resource_code] = cls._merge_permission(current, row)

        cache[provider_id] = permissions
        return permissions

    @classmethod
    def check_permission(
        cls,
        user,
        provider,
        resource_code,
        action,
        target_location=None,
        target_employee=None,
    ) -> bool:
        if cls._is_system_like(user):
            return True

        action_key = f'can_{action}'
        permission = cls.get_user_permissions(user, provider).get(resource_code)
        if not permission or not permission.get(action_key):
            return False

        scope = permission.get('scope') or ProviderRolePermission.SCOPE_OWN_ONLY
        if scope == ProviderRolePermission.SCOPE_ALL:
            return True

        member_location_ids = cls.get_location_ids_for_scope(
            user,
            provider,
            resource_code,
            ProviderRolePermission.SCOPE_OWN_ONLY,
            action=action,
        )
        branch_location_ids = cls.get_location_ids_for_scope(
            user,
            provider,
            resource_code,
            ProviderRolePermission.SCOPE_OWN_BRANCH,
            action=action,
        )

        if scope == ProviderRolePermission.SCOPE_OWN_BRANCH:
            if target_location is None and target_employee is None:
                return bool(branch_location_ids)
            target_location_id = getattr(target_location, 'id', target_location)
            if target_location_id is not None:
                return target_location_id in branch_location_ids
            if target_employee is not None:
                return target_employee.locations.filter(id__in=branch_location_ids).exists()
            return False

        employee_profile = getattr(user, 'employee_profile', None)
        if target_employee is not None:
            if employee_profile is None:
                return False
            return getattr(target_employee, 'id', None) == getattr(employee_profile, 'id', None)
        target_location_id = getattr(target_location, 'id', target_location)
        if target_location_id is not None:
            return target_location_id in member_location_ids
        return bool(employee_profile)

    @classmethod
    def ensure_provider_access_roles(cls, user) -> set[str]:
        today = timezone.localdate()
        now = timezone.now()
        active_provider_links = EmployeeProvider.objects.filter(
            employee__user=user,
            employee__is_active=True,
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        active_location_roles = EmployeeLocationRole.objects.filter(
            employee__user=user,
            employee__is_active=True,
            is_active=True,
            provider_location__is_active=True,
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=now))

        roles: set[str] = set()
        if active_provider_links.filter(is_owner=True).exists():
            roles.add('owner')
        if active_provider_links.filter(is_provider_admin=True).exists():
            roles.add('provider_admin')
        if active_provider_links.filter(is_provider_manager=True).exists():
            roles.add('provider_manager')
        if active_location_roles.filter(role=EmployeeLocationRole.ROLE_BRANCH_MANAGER).exists() or ProviderLocation.objects.filter(manager=user, is_active=True).exists():
            roles.add('branch_manager')
        if active_location_roles.exists() or active_provider_links.filter(role=EmployeeProvider.ROLE_WORKER).exists():
            roles.add('specialist')
            roles.add('worker')
        return roles

    @classmethod
    def sync_user_access_roles(cls, user) -> set[str]:
        target_roles = cls.ensure_provider_access_roles(user)
        existing_roles = set(user.user_types.filter(name__in=PROVIDER_ACCESS_ROLE_NAMES).values_list('name', flat=True))

        for role_name in target_roles - existing_roles:
            role, _ = UserType.objects.get_or_create(name=role_name)
            user.user_types.add(role)

        for role_name in existing_roles - target_roles:
            user.remove_role(role_name)

        return target_roles


def build_provider_permissions_payload(user, provider: Provider) -> dict:
    permissions = ProviderPermissionService.get_user_permissions(user, provider)
    branch_location_ids = list(
        ProviderPermissionService.get_user_branch_locations(user, provider).values_list('id', flat=True)
    )
    return {
        'roles': ProviderPermissionService.get_user_roles_for_provider(user, provider),
        'primary_role': ProviderPermissionService.get_primary_role(user, provider),
        'permissions': permissions,
        'branch_location_ids': branch_location_ids,
    }
