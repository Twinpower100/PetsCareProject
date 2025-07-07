from django.core.exceptions import PermissionDenied
from functools import wraps
from django.utils.translation import gettext_lazy as _

def IsProviderAdmin(view_func):
    """
    Декоратор: разрешает доступ только администраторам учреждений.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.has_role('provider_admin'):
            raise PermissionDenied(_("Only provider administrators can access this page"))
        return view_func(request, *args, **kwargs)
    return wrapper

def IsBillingManager(view_func):
    """
    Декоратор: разрешает доступ только менеджерам по биллингу.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.has_role('billing_manager'):
            raise PermissionDenied(_("Only billing managers can access this page"))
        return view_func(request, *args, **kwargs)
    return wrapper

def IsSystemAdmin(view_func):
    """
    Декоратор: разрешает доступ только системным администраторам.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.has_role('system_admin'):
            raise PermissionDenied(_("Only system administrators can access this page"))
        return view_func(request, *args, **kwargs)
    return wrapper 

def IsPetSitter(view_func):
    """
    Декоратор: разрешает доступ только ситтерам (передержчикам).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.has_role('pet_sitter'):
            raise PermissionDenied(_("Only pet sitters can access this page"))
        return view_func(request, *args, **kwargs)
    return wrapper

def IsEmployee(view_func):
    """
    Декоратор: разрешает доступ только сотрудникам учреждений.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.has_role('employee'):
            raise PermissionDenied(_("Only employees can access this page"))
        return view_func(request, *args, **kwargs)
    return wrapper

def IsPetOwner(view_func):
    """
    Декоратор: разрешает доступ только владельцам питомцев.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.has_role('pet_owner'):
            raise PermissionDenied(_("Only pet owners can access this page"))
        return view_func(request, *args, **kwargs)
    return wrapper
