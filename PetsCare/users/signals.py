"""
Сигналы для автоматического назначения ролей пользователям.

Содержит:
1. Автоматическое назначение basic_user при регистрации
2. Автоматическое назначение pet_owner при создании питомца
3. Автоматическое назначение pet_sitter при создании профиля ситтера
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import UserType

User = get_user_model()


@receiver(post_save, sender=User)
def assign_basic_user_role(sender, instance, created, **kwargs):
    """
    Автоматически присваивает роль 'basic_user' новому пользователю при регистрации.
    """
    if created:
        try:
            basic_user_role = UserType.objects.get(name='basic_user')
            instance.user_types.add(basic_user_role)
        except UserType.DoesNotExist:
            # Если роль 'basic_user' не существует, создаем ее
            basic_user_role = UserType.objects.create(
                name='basic_user',
                description='Basic user role with minimal system access',
                permissions=['users.view_user', 'pets.view_pet', 'providers.view_provider', 
                           'booking.view_booking', 'notifications.view_notification',
                           'geolocation.view_location', 'ratings.view_rating']
            )
            instance.user_types.add(basic_user_role)


@receiver(post_save, sender='pets.Pet')
def assign_pet_owner_role(sender, instance, created, **kwargs):
    """
    Автоматически присваивает роль 'pet_owner' пользователю при создании первого питомца.
    """
    if created:
        try:
            pet_owner_role = UserType.objects.get(name='pet_owner')
            if not instance.main_owner.user_types.filter(name='pet_owner').exists():
                instance.main_owner.user_types.add(pet_owner_role)
        except UserType.DoesNotExist:
            # Если роль 'pet_owner' не существует, создаем ее
            pet_owner_role = UserType.objects.create(
                name='pet_owner',
                description='Pet owner role with rights to manage pets and bookings',
                permissions=['pets.add_pet', 'pets.change_pet', 'pets.view_pet',
                           'booking.add_booking', 'booking.view_booking',
                           'notifications.view_notification', 'ratings.add_rating', 'ratings.view_rating']
            )
            if not instance.main_owner.user_types.filter(name='pet_owner').exists():
                instance.main_owner.user_types.add(pet_owner_role)


@receiver(post_save, sender='sitters.SitterProfile')
def assign_pet_sitter_role(sender, instance, created, **kwargs):
    """
    Автоматически присваивает роль 'pet_sitter' пользователю при создании профиля ситтера.
    """
    if created:
        try:
            pet_sitter_role = UserType.objects.get(name='pet_sitter')
            if not instance.user.user_types.filter(name='pet_sitter').exists():
                instance.user.user_types.add(pet_sitter_role)
        except UserType.DoesNotExist:
            # Если роль 'pet_sitter' не существует, создаем ее
            pet_sitter_role = UserType.objects.create(
                name='pet_sitter',
                description='Pet sitter role with rights to provide pet sitting services',
                permissions=['users.view_user', 'pets.view_pet', 'providers.view_provider',
                           'booking.view_booking', 'booking.change_booking',
                           'notifications.view_notification', 'ratings.view_rating']
            )
            if not instance.user.user_types.filter(name='pet_sitter').exists():
                instance.user.user_types.add(pet_sitter_role)
