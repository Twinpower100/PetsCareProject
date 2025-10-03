"""
Сигналы для автоматического назначения ролей при создании профилей ситтеров.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import SitterProfile


@receiver(post_save, sender=SitterProfile)
def assign_pet_sitter_role_on_profile_creation(sender, instance, created, **kwargs):
    """
    Автоматически присваивает роль 'pet_sitter' пользователю при создании профиля ситтера.
    """
    if created:
        from users.models import UserType
        
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
