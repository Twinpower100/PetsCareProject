from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import UserActivity, UserConversion
# from .services import user_analytics_service  # Ленивый импорт

User = get_user_model()

@receiver(post_save, sender=User)
def track_user_registration(sender, instance, created, **kwargs):
    """Отслеживание регистрации нового пользователя"""
    if created:
        try:
            from .services import user_analytics_service
            # Создаем запись о конверсии "регистрация"
            user_analytics_service.track_user_conversion(instance, 'registration')
            
            # Создаем запись об активности
            user_analytics_service.track_user_activity(instance, 'login')
        except:
            # Если БД еще не готова, пропускаем
            pass

@receiver(post_save, sender=UserActivity)
def update_user_activity_cache(sender, instance, **kwargs):
    """Обновление кэша активности пользователя"""
    from django.core.cache import cache
    
    # Кэшируем последнюю активность пользователя
    cache_key = f"user_activity_{instance.user.id}"
    cache.set(cache_key, {
        'last_activity': instance.last_activity,
        'total_actions': instance.actions_count,
        'session_duration': instance.session_duration
    }, 3600)  # Кэш на 1 час

@receiver(post_save, sender=UserConversion)
def update_conversion_cache(sender, instance, **kwargs):
    """Обновление кэша конверсии"""
    from django.core.cache import cache
    
    # Кэшируем этапы конверсии пользователя
    cache_key = f"user_conversion_{instance.user.id}"
    conversions = cache.get(cache_key, [])
    conversions.append(instance.stage)
    cache.set(cache_key, conversions, 3600)  # Кэш на 1 час 