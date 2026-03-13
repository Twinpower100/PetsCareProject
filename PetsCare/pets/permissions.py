"""
Классы разрешений (Permissions) для модуля pets.

IsMainOwner  — пропускает запрос, если текущий пользователь является
               основным владельцем (role='main') питомца-объекта.
IsCoowner    — пропускает запрос, если пользователь является хотя бы
               совладельцем (role='main' ИЛИ 'coowner') питомца.

Использование во ViewSet:
    permission_classes = [IsAuthenticated, IsMainOwner]
    # или
    permission_classes = [IsAuthenticated, IsCoowner]
"""

from rest_framework.permissions import BasePermission
from django.utils.translation import gettext_lazy as _


class IsMainOwner(BasePermission):
    """
    Разрешает доступ только основному владельцу (role='main').

    Предназначен для опасных действий:
    - soft-delete питомца
    - передача прав основного владельца
    - приглашение / удаление совладельцев
    """
    message = _('Only the main owner can perform this action.')

    def has_object_permission(self, request, view, obj):
        pet = self._resolve_pet(obj)
        if pet is None:
            return False
        from .models import PetOwner
        return PetOwner.objects.filter(
            pet=pet, user=request.user, role='main'
        ).exists()

    @staticmethod
    def _resolve_pet(obj):
        """Получает Pet из объекта (Pet, PetHealthNote, VisitRecord и т.д.)."""
        from .models import Pet
        if isinstance(obj, Pet):
            return obj
        if hasattr(obj, 'pet'):
            return obj.pet
        return None


class IsCoowner(BasePermission):
    """
    Разрешает доступ любому владельцу (main или coowner).

    Подходит для:
    - просмотра/редактирования базовых данных питомца
    - создания записей в медкарту
    - бронирования услуг
    """
    message = _('You must be an owner or co-owner of this pet.')

    def has_object_permission(self, request, view, obj):
        pet = self._resolve_pet(obj)
        if pet is None:
            return False
        from .models import PetOwner
        return PetOwner.objects.filter(
            pet=pet, user=request.user
        ).exists()

    @staticmethod
    def _resolve_pet(obj):
        from .models import Pet
        if isinstance(obj, Pet):
            return obj
        if hasattr(obj, 'pet'):
            return obj.pet
        return None
