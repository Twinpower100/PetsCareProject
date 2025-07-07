from rest_framework import permissions
from django.utils.translation import gettext_lazy as _

class IsOwnerOrProvider(permissions.BasePermission):
    """
    Разрешение, которое проверяет, является ли пользователь владельцем бронирования
    или поставщиком услуг.
    """
    message = _('You do not have permission to perform this action.')

    def has_object_permission(self, request, view, obj):
        """
        Проверяет, имеет ли пользователь право на доступ к объекту.
        """
        # Разрешаем доступ, если пользователь является владельцем бронирования
        if hasattr(obj, 'user') and obj.user == request.user:
            return True
            
        # Разрешаем доступ, если пользователь является поставщиком услуг
        if hasattr(obj, 'provider') and hasattr(request.user, 'provider'):
            return obj.provider == request.user.provider
            
        return False

class IsProvider(permissions.BasePermission):
    """
    Разрешение, которое проверяет, является ли пользователь поставщиком услуг.
    """
    message = _('Only providers can perform this action.')

    def has_permission(self, request, view):
        """
        Проверяет, имеет ли пользователь право на выполнение действия.
        """
        return hasattr(request.user, 'provider')

    def has_object_permission(self, request, view, obj):
        """
        Проверяет, имеет ли пользователь право на доступ к объекту.
        """
        return self.has_permission(request, view) 