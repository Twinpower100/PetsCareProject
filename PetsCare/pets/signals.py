"""
Сигналы для автоматического назначения ролей при создании питомцев.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Pet


@receiver(post_save, sender=Pet)
def assign_pet_owner_role_on_pet_creation(sender, instance, created, **kwargs):
    """
    Автоматически присваивает роль 'pet_owner' пользователю при создании питомца.
    """
    if created:
        from users.models import UserType
        
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
