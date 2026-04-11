from django.utils.translation import gettext_lazy as _
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied


EMAIL_VERIFICATION_REQUIRED_CODE = 'email_verification_required'


def require_verified_email_for_owner_action(user) -> None:
    """
    Блокирует owner-действие до подтверждения email.
    """
    if not getattr(user, 'is_authenticated', False):
        return
    if getattr(user, 'email_verified', True):
        return
    raise PermissionDenied({
        'detail': _('You need to verify your email address before using this action.'),
        'code': EMAIL_VERIFICATION_REQUIRED_CODE,
    })


class IsVerifiedForOwnerWriteActions(permissions.BasePermission):
    """
    Разрешает чтение, но блокирует owner-запись до подтверждения email.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        require_verified_email_for_owner_action(request.user)
        return True
