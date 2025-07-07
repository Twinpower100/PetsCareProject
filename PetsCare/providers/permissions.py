from rest_framework import permissions

class IsEmployee(permissions.BasePermission):
    """
    Проверяет, является ли пользователь сотрудником
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_employee()

    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and request.user.is_employee() 