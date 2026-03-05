"""
Сигналы для автоматического назначения ролей при создании питомцев.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import PetOwner


@receiver(post_save, sender=PetOwner)
def assign_pet_owner_role_on_petowner_creation(sender, instance, created, **kwargs):
    """
    Автоматически присваивает роль 'pet_owner' пользователю
    при создании PetOwner записи.
    """
    # Проверяем, что Django полностью инициализирован
    from django.conf import settings
    if not settings.configured:
        return

    if created:
        from users.models import UserType

        user = instance.user
        try:
            pet_owner_role = UserType.objects.get(name='pet_owner')
            if not user.user_types.filter(name='pet_owner').exists():
                user.user_types.add(pet_owner_role)
        except UserType.DoesNotExist:
            # Если роль 'pet_owner' не существует, создаем ее
            pet_owner_role = UserType.objects.create(
                name='pet_owner',
                description='Pet owner role with rights to manage pets and bookings',
                permissions=['pets.add_pet', 'pets.change_pet', 'pets.view_pet',
                           'booking.add_booking', 'booking.view_booking',
                           'notifications.view_notification', 'ratings.add_rating', 'ratings.view_rating']
            )
            if not user.user_types.filter(name='pet_owner').exists():
                user.user_types.add(pet_owner_role)
