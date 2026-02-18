"""
Система управления правами для PetCare.

Содержит:
1. Словарь всех доступных разрешений с описаниями
2. Предопределенные наборы прав для разных ролей
3. Утилиты для работы с правами
"""

from django.utils.translation import gettext_lazy as _


# 1. СЛОВАРЬ ВСЕХ РАЗРЕШЕНИЙ С ОПИСАНИЯМИ
PERMISSION_DESCRIPTIONS = {
    # Пользователи
    'users.add_user': _('Adding new users'),
    'users.change_user': _('Editing users'),
    'users.delete_user': _('Deleting users'),
    'users.view_user': _('Viewing users'),
    
    # Питомцы
    'pets.add_pet': _('Adding new pets'),
    'pets.change_pet': _('Editing pets'),
    'pets.delete_pet': _('Deleting pets'),
    'pets.view_pet': _('Viewing pets'),
    
    # Учреждения
    'providers.add_provider': _('Adding new providers'),
    'providers.change_provider': _('Editing providers'),
    'providers.delete_provider': _('Deleting providers'),
    'providers.view_provider': _('Viewing providers'),
    
    # Бронирования
    'booking.add_booking': _('Creating bookings'),
    'booking.change_booking': _('Editing bookings'),
    'booking.delete_booking': _('Cancelling bookings'),
    'booking.view_booking': _('Viewing bookings'),
    
    # Биллинг
    'billing.add_contract': _('Creating contracts'),
    'billing.change_contract': _('Editing contracts'),
    'billing.delete_contract': _('Deleting contracts'),
    'billing.view_contract': _('Viewing contracts'),
    'billing.add_payment': _('Creating payments'),
    'billing.change_payment': _('Editing payments'),
    'billing.delete_payment': _('Deleting payments'),
    'billing.view_payment': _('Viewing payments'),
    
    # Аудит
    'audit.add_useraction': _('Creating action records'),
    'audit.change_useraction': _('Editing action records'),
    'audit.delete_useraction': _('Deleting action records'),
    'audit.view_useraction': _('Viewing action records'),
    'audit.add_securityaudit': _('Creating security audit records'),
    'audit.change_securityaudit': _('Editing security audit records'),
    'audit.delete_securityaudit': _('Deleting security audit records'),
    'audit.view_securityaudit': _('Viewing security audit records'),
    
    # Безопасность
    'security.add_securitypolicy': _('Creating security policies'),
    'security.change_securitypolicy': _('Editing security policies'),
    'security.delete_securitypolicy': _('Deleting security policies'),
    'security.view_securitypolicy': _('Viewing security policies'),
    
    # Уведомления
    'notifications.add_notification': _('Creating notifications'),
    'notifications.change_notification': _('Editing notifications'),
    'notifications.delete_notification': _('Deleting notifications'),
    'notifications.view_notification': _('Viewing notifications'),
    
    # Геолокация
    'geolocation.add_location': _('Adding locations'),
    'geolocation.change_location': _('Editing locations'),
    'geolocation.delete_location': _('Deleting locations'),
    'geolocation.view_location': _('Viewing locations'),
    
    # Рейтинги
    'ratings.add_rating': _('Creating ratings'),
    'ratings.change_rating': _('Editing ratings'),
    'ratings.delete_rating': _('Deleting ratings'),
    'ratings.view_rating': _('Viewing ratings'),
}


# 2. ПРЕДОПРЕДЕЛЕННЫЕ НАБОРЫ ПРАВ ДЛЯ РОЛЕЙ
ROLE_PERMISSION_SETS = {
    'system_admin': {
        'name': _('System Administrator'),
        'description': _('Full access to all system functions'),
        'permissions': list(PERMISSION_DESCRIPTIONS.keys()),
    },
    
    'owner': {
        'name': _('Owner'),
        'description': _('Provider owner (one per provider); same permissions as provider administrator'),
        'permissions': [
            'users.view_user', 'users.change_user',
            'pets.view_pet', 'providers.change_provider', 'providers.view_provider',
            'booking.view_booking', 'booking.change_booking',
            'billing.view_contract', 'billing.view_payment',
            'notifications.add_notification', 'notifications.view_notification',
            'ratings.view_rating',
        ]
    },
    'provider_admin': {
        'name': _('Provider Administrator'),
        'description': _('Managing provider and its employees'),
        'permissions': [
            'users.view_user', 'users.change_user',
            'pets.view_pet', 'providers.change_provider', 'providers.view_provider',
            'booking.view_booking', 'booking.change_booking',
            'billing.view_contract', 'billing.view_payment',
            'notifications.add_notification', 'notifications.view_notification',
            'ratings.view_rating',
        ]
    },
    'provider_manager': {
        'name': _('Provider Manager'),
        'description': _('Business manager of the provider'),
        'permissions': [
            'users.view_user', 'users.change_user',
            'pets.view_pet', 'providers.change_provider', 'providers.view_provider',
            'booking.view_booking', 'booking.change_booking',
            'billing.view_contract', 'billing.view_payment',
            'notifications.add_notification', 'notifications.view_notification',
            'ratings.view_rating',
        ]
    },
    'branch_manager': {
        'name': _('Branch Manager'),
        'description': _('Manager of a provider location/branch'),
        'permissions': [
            'users.view_user', 'pets.view_pet', 'providers.view_provider',
            'booking.view_booking', 'booking.change_booking',
            'notifications.view_notification', 'ratings.view_rating',
        ]
    },
    'specialist': {
        'name': _('Specialist'),
        'description': _('Service or technical worker at a branch'),
        'permissions': [
            'users.view_user', 'pets.view_pet', 'providers.view_provider',
            'booking.view_booking', 'booking.change_booking',
            'notifications.view_notification',
        ]
    },
    
    'billing_manager': {
        'name': _('Billing Manager'),
        'description': _('Managing financial operations'),
        'permissions': [
            'users.view_user', 'pets.view_pet', 'providers.view_provider',
            'booking.view_booking', 'billing.add_contract', 'billing.change_contract',
            'billing.view_contract', 'billing.add_payment', 'billing.change_payment',
            'billing.view_payment', 'notifications.view_notification',
        ]
    },
    
    'booking_manager': {
        'name': _('Booking Manager'),
        'description': _('Managing bookings and resolving conflicts'),
        'permissions': [
            'users.view_user', 'pets.view_pet', 'providers.view_provider',
            'booking.add_booking', 'booking.change_booking', 'booking.view_booking',
            'billing.view_contract', 'notifications.add_notification',
            'notifications.view_notification', 'ratings.view_rating',
        ]
    },
    
    'employee': {
        'name': _('Provider Employee'),
        'description': _('Basic rights for working with clients'),
        'permissions': [
            'users.view_user', 'pets.view_pet', 'providers.view_provider',
            'booking.view_booking', 'booking.change_booking',
            'notifications.view_notification',
        ]
    },
    
    'pet_owner': {
        'name': _('Pet Owner'),
        'description': _('Basic rights for pet owners'),
        'permissions': [
            'pets.add_pet', 'pets.change_pet', 'pets.view_pet',
            'booking.add_booking', 'booking.view_booking',
            'notifications.view_notification', 'ratings.add_rating', 'ratings.view_rating',
        ]
    },
    
    'pet_sitter': {
        'name': _('Pet Sitter'),
        'description': _('Rights for providing pet sitting services'),
        'permissions': [
            'users.view_user', 'pets.view_pet', 'providers.view_provider',
            'booking.view_booking', 'booking.change_booking',
            'notifications.view_notification', 'ratings.view_rating',
        ]
    },
    
    'basic_user': {
        'name': _('Basic User'),
        'description': _('Minimal rights for working with the system (no admin access)'),
        'permissions': [
            'users.view_user', 'pets.view_pet', 'providers.view_provider',
            'booking.view_booking', 'notifications.view_notification',
            'geolocation.view_location', 'ratings.view_rating',
        ]
    },
}


def get_permission_description(permission_codename):
    """
    Возвращает описание разрешения.
    
    Args:
        permission_codename (str): Код разрешения (например, 'users.add_user')
        
    Returns:
        str: Описание разрешения или сам код, если описание не найдено
    """
    return PERMISSION_DESCRIPTIONS.get(permission_codename, permission_codename)


def get_role_permissions(role_name):
    """
    Возвращает список разрешений для роли.
    
    Args:
        role_name (str): Название роли
        
    Returns:
        list: Список разрешений для роли
    """
    role_data = ROLE_PERMISSION_SETS.get(role_name)
    if role_data:
        return role_data['permissions']
    return []


def get_role_info(role_name):
    """
    Возвращает информацию о роли.
    
    Args:
        role_name (str): Название роли
        
    Returns:
        dict: Информация о роли (name, description, permissions)
    """
    return ROLE_PERMISSION_SETS.get(role_name, {})


def get_all_roles():
    """
    Возвращает список всех доступных ролей.
    
    Returns:
        dict: Словарь всех ролей с их информацией
    """
    return ROLE_PERMISSION_SETS


def validate_permissions(permissions_list):
    """
    Проверяет, что все разрешения в списке существуют.
    
    Args:
        permissions_list (list): Список разрешений для проверки
        
    Returns:
        tuple: (valid_permissions, invalid_permissions)
    """
    valid_permissions = []
    invalid_permissions = []
    
    for permission in permissions_list:
        if permission in PERMISSION_DESCRIPTIONS:
            valid_permissions.append(permission)
        else:
            invalid_permissions.append(permission)
    
    return valid_permissions, invalid_permissions


def get_permissions_for_app(app_name):
    """
    Возвращает все разрешения для указанного приложения.
    
    Args:
        app_name (str): Название приложения (например, 'users')
        
    Returns:
        dict: Словарь разрешений для приложения
    """
    app_permissions = {}
    for permission, description in PERMISSION_DESCRIPTIONS.items():
        if permission.startswith(f'{app_name}.'):
            app_permissions[permission] = description
    
    return app_permissions


def create_custom_role(name, description, permissions):
    """
    Создает кастомную роль с указанными разрешениями.
    
    Args:
        name (str): Название роли
        description (str): Описание роли
        permissions (list): Список разрешений
        
    Returns:
        dict: Информация о созданной роли
        
    Raises:
        ValueError: Если указаны несуществующие разрешения
    """
    valid_permissions, invalid_permissions = validate_permissions(permissions)
    
    if invalid_permissions:
        raise ValueError(f"Invalid permissions: {invalid_permissions}")
    
    role_data = {
        'name': name,
        'description': description,
        'permissions': valid_permissions
    }
    
    return role_data