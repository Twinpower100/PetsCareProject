from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Класс разрешений, который позволяет:
    - Чтение (GET, HEAD, OPTIONS) для всех пользователей
    - Изменение (POST, PUT, PATCH, DELETE) только владельцу питомца
    
    Методы:
        has_object_permission: Проверяет права доступа к объекту
    """
    def has_object_permission(self, request, view, obj):
        """
        Проверяет права доступа к объекту.
        
        Args:
            request: HTTP запрос
            view: Представление, обрабатывающее запрос
            obj: Объект, к которому проверяются права
        
        Returns:
            bool: True если доступ разрешен, False если запрещен
        """
        # Разрешаем безопасные методы (GET, HEAD, OPTIONS) для всех
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Для остальных методов проверяем, является ли пользователь владельцем питомца
        return obj.pet.owner == request.user 