"""Default provider RBAC roles, resources, and permissions."""

from __future__ import annotations

from providers.models import ProviderRolePermission


ROLE_DEFINITIONS = [
    {
        'code': 'owner',
        'name': 'Owner',
        'description': 'Business owner with full organization control.',
        'level': 1,
    },
    {
        'code': 'provider_admin',
        'name': 'Organization Admin',
        'description': 'Administrative access across the whole organization.',
        'level': 2,
    },
    {
        'code': 'provider_manager',
        'name': 'Organization Manager',
        'description': 'Business management across all branches.',
        'level': 3,
    },
    {
        'code': 'branch_manager',
        'name': 'Branch Manager',
        'description': 'Manager of assigned branches only.',
        'level': 4,
    },
    {
        'code': 'worker',
        'name': 'Worker',
        'description': 'Branch staff member with own-record access only.',
        'level': 5,
    },
]


RESOURCE_DEFINITIONS = [
    {'code': 'dashboard', 'name': 'Dashboard', 'description': 'Provider admin dashboard.', 'parent_code': None, 'sort_order': 10},
    {'code': 'org', 'name': 'Organization', 'description': 'Organization-level settings group.', 'parent_code': None, 'sort_order': 20},
    {'code': 'org.profile', 'name': 'Organization Profile', 'description': 'General organization profile and contacts.', 'parent_code': 'org', 'sort_order': 21},
    {'code': 'org.legal', 'name': 'Organization Legal', 'description': 'Legal requisites and legal documents.', 'parent_code': 'org', 'sort_order': 22},
    {'code': 'org.billing', 'name': 'Organization Billing', 'description': 'Billing, invoices, and settlements.', 'parent_code': 'org', 'sort_order': 23},
    {'code': 'org.deactivation', 'name': 'Organization Deactivation', 'description': 'Organization deactivation controls.', 'parent_code': 'org', 'sort_order': 24},
    {'code': 'locations', 'name': 'Locations', 'description': 'Branch/location management group.', 'parent_code': None, 'sort_order': 30},
    {'code': 'locations.list', 'name': 'Location Directory', 'description': 'Location list and branch creation.', 'parent_code': 'locations', 'sort_order': 31},
    {'code': 'locations.settings', 'name': 'Location Settings', 'description': 'Branch settings and configuration.', 'parent_code': 'locations', 'sort_order': 32},
    {'code': 'locations.schedule', 'name': 'Location Schedules', 'description': 'Location and staff schedules.', 'parent_code': 'locations', 'sort_order': 33},
    {'code': 'locations.services', 'name': 'Location Services', 'description': 'Services and price matrix at branches.', 'parent_code': 'locations', 'sort_order': 34},
    {'code': 'staff', 'name': 'Staff', 'description': 'Staff management group.', 'parent_code': None, 'sort_order': 40},
    {'code': 'staff.list', 'name': 'Staff Directory', 'description': 'Staff list and staff records.', 'parent_code': 'staff', 'sort_order': 41},
    {'code': 'staff.roles', 'name': 'Staff Roles', 'description': 'Role assignment and branch manager assignment.', 'parent_code': 'staff', 'sort_order': 42},
    {'code': 'staff.invite', 'name': 'Staff Invites', 'description': 'Staff invite creation and cancellation.', 'parent_code': 'staff', 'sort_order': 43},
    {'code': 'staff.fire', 'name': 'Staff Offboarding', 'description': 'Staff deactivation and dismissal.', 'parent_code': 'staff', 'sort_order': 44},
    {'code': 'bookings', 'name': 'Bookings', 'description': 'Booking management.', 'parent_code': None, 'sort_order': 50},
    {'code': 'bookings.create_manual', 'name': 'Manual Booking Creation', 'description': 'Manual booking creation flow.', 'parent_code': 'bookings', 'sort_order': 51},
    {'code': 'visits', 'name': 'Visits', 'description': 'Visit operations and visit list.', 'parent_code': None, 'sort_order': 60},
    {'code': 'visits.protocol', 'name': 'Visit Protocol', 'description': 'Visit protocol and medical/service notes.', 'parent_code': 'visits', 'sort_order': 61},
    {'code': 'clients', 'name': 'Clients', 'description': 'Client and pet read access.', 'parent_code': None, 'sort_order': 70},
    {'code': 'reports', 'name': 'Reports', 'description': 'Reporting group.', 'parent_code': None, 'sort_order': 80},
    {'code': 'reports.financial', 'name': 'Financial Reports', 'description': 'Financial and settlement reports.', 'parent_code': 'reports', 'sort_order': 81},
    {'code': 'reports.operational', 'name': 'Operational Reports', 'description': 'Operational and roster reports.', 'parent_code': 'reports', 'sort_order': 82},
    {'code': 'settings', 'name': 'Settings', 'description': 'Settings group.', 'parent_code': None, 'sort_order': 90},
    {'code': 'settings.integrations', 'name': 'Integrations', 'description': 'External integrations and connection settings.', 'parent_code': 'settings', 'sort_order': 91},
    {'code': 'settings.notifications', 'name': 'Notifications', 'description': 'Notification preferences and configuration.', 'parent_code': 'settings', 'sort_order': 92},
    {'code': 'reviews', 'name': 'Reviews', 'description': 'Reviews and feedback management.', 'parent_code': None, 'sort_order': 100},
]


ALL_ROLE_CODES = [item['code'] for item in ROLE_DEFINITIONS]
ALL_RESOURCE_CODES = [item['code'] for item in RESOURCE_DEFINITIONS]


def _matrix_entry(crud: str = '', scope: str = ProviderRolePermission.SCOPE_ALL) -> dict:
    crud = crud.upper()
    return {
        'can_create': 'C' in crud,
        'can_read': 'R' in crud,
        'can_update': 'U' in crud,
        'can_delete': 'D' in crud,
        'scope': scope,
    }


PERMISSION_MATRIX = {
    'owner': {
        'dashboard': _matrix_entry('R'),
        'org.profile': _matrix_entry('CRUD'),
        'org.legal': _matrix_entry('CRUD'),
        'org.billing': _matrix_entry('CRUD'),
        'org.deactivation': _matrix_entry('D'),
        'locations.list': _matrix_entry('CRUD'),
        'locations.settings': _matrix_entry('CRUD'),
        'locations.schedule': _matrix_entry('CRUD'),
        'locations.services': _matrix_entry('CRUD'),
        'staff.list': _matrix_entry('CRUD'),
        'staff.roles': _matrix_entry('CRUD'),
        'staff.invite': _matrix_entry('CRUD'),
        'staff.fire': _matrix_entry('D'),
        'bookings': _matrix_entry('CRUD'),
        'bookings.create_manual': _matrix_entry('C'),
        'visits': _matrix_entry('CRUD'),
        'visits.protocol': _matrix_entry('CRUD'),
        'clients': _matrix_entry('R'),
        'reports.financial': _matrix_entry('R'),
        'reports.operational': _matrix_entry('R'),
        'settings.integrations': _matrix_entry('CRUD'),
        'settings.notifications': _matrix_entry('CRUD'),
        'reviews': _matrix_entry('RU'),
    },
    'provider_admin': {
        'dashboard': _matrix_entry('R'),
        'org.profile': _matrix_entry('RU'),
        'org.legal': _matrix_entry('R'),
        'org.billing': _matrix_entry('R'),
        'locations.list': _matrix_entry('CRUD'),
        'locations.settings': _matrix_entry('CRUD'),
        'locations.schedule': _matrix_entry('CRUD'),
        'locations.services': _matrix_entry('CRUD'),
        'staff.list': _matrix_entry('CRUD'),
        'staff.roles': _matrix_entry('CRUD'),
        'staff.invite': _matrix_entry('CRUD'),
        'staff.fire': _matrix_entry('D'),
        'bookings': _matrix_entry('CRUD'),
        'bookings.create_manual': _matrix_entry('C'),
        'visits': _matrix_entry('CRUD'),
        'visits.protocol': _matrix_entry('CRUD'),
        'clients': _matrix_entry('R'),
        'reports.financial': _matrix_entry('R'),
        'reports.operational': _matrix_entry('R'),
        'settings.integrations': _matrix_entry('CRUD'),
        'settings.notifications': _matrix_entry('CRUD'),
        'reviews': _matrix_entry('RU'),
    },
    'provider_manager': {
        'dashboard': _matrix_entry('R'),
        'org.profile': _matrix_entry('R'),
        'org.billing': _matrix_entry('R'),
        'locations.list': _matrix_entry('R'),
        'locations.settings': _matrix_entry('RU'),
        'locations.schedule': _matrix_entry('CRUD'),
        'locations.services': _matrix_entry('CRUD'),
        'staff.list': _matrix_entry('CRUD'),
        'staff.roles': _matrix_entry('R'),
        'staff.invite': _matrix_entry('CRUD'),
        'staff.fire': _matrix_entry('D'),
        'bookings': _matrix_entry('CRUD'),
        'bookings.create_manual': _matrix_entry('C'),
        'visits': _matrix_entry('CRUD'),
        'visits.protocol': _matrix_entry('CRUD'),
        'clients': _matrix_entry('R'),
        'reports.financial': _matrix_entry('R'),
        'reports.operational': _matrix_entry('R'),
        'settings.integrations': _matrix_entry('R'),
        'settings.notifications': _matrix_entry('RU'),
        'reviews': _matrix_entry('RU'),
    },
    'branch_manager': {
        'dashboard': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'org.profile': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'locations.list': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'locations.settings': _matrix_entry('RU', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'locations.schedule': _matrix_entry('CRUD', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'locations.services': _matrix_entry('CRUD', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'staff.list': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'staff.invite': _matrix_entry('CR', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'staff.fire': _matrix_entry('D', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'bookings': _matrix_entry('CRUD', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'bookings.create_manual': _matrix_entry('C', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'visits': _matrix_entry('CRUD', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'visits.protocol': _matrix_entry('CRUD', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'clients': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'reports.financial': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'reports.operational': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'settings.notifications': _matrix_entry('RU', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'reviews': _matrix_entry('RU', ProviderRolePermission.SCOPE_OWN_BRANCH),
    },
    'worker': {
        'dashboard': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_ONLY),
        'locations.list': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'locations.schedule': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_ONLY),
        'locations.services': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_BRANCH),
        'bookings': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_ONLY),
        'visits': _matrix_entry('RU', ProviderRolePermission.SCOPE_OWN_ONLY),
        'visits.protocol': _matrix_entry('CRU', ProviderRolePermission.SCOPE_OWN_ONLY),
        'clients': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_ONLY),
        'reports.operational': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_ONLY),
        'settings.notifications': _matrix_entry('RU', ProviderRolePermission.SCOPE_OWN_ONLY),
        'reviews': _matrix_entry('R', ProviderRolePermission.SCOPE_OWN_ONLY),
    },
}


def get_matrix_entry(role_code: str, resource_code: str) -> dict:
    return PERMISSION_MATRIX.get(role_code, {}).get(resource_code, _matrix_entry('', ProviderRolePermission.SCOPE_ALL))
