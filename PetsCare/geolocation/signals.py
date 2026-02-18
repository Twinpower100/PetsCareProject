"""
Сигналы для модуля геолокации.

Содержит сигналы для:
1. Автоматической валидации адресов
2. Очистки кэша
3. Обновления связанных моделей
"""

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta

from .models import Address, AddressValidation, AddressCache
from .services import AddressValidationService


# ВРЕМЕННО ОТКЛЮЧЕНО - вызывает бесконечный цикл
# @receiver(post_save, sender=Address)
def auto_validate_address(sender, instance, created, **kwargs):
    """
    Автоматически валидирует адрес при создании или обновлении.
    
    Args:
        sender: Модель-отправитель сигнала
        instance: Экземпляр модели
        created: Флаг создания новой записи
        **kwargs: Дополнительные параметры
    """
    # Если адрес уже валидирован, не выполняем повторную валидацию
    if instance.is_validated and instance.validation_status == 'valid':
        return
    
    # Если адрес помечен как невалидный, не выполняем повторную валидацию
    if instance.validation_status == 'invalid':
        return
    
    try:
        # Выполняем валидацию через сервис
        validation_service = AddressValidationService()
        validation_service.validate_address(instance)
        
    except Exception as e:
        # В случае ошибки помечаем адрес как ожидающий валидации
        instance.validation_status = 'pending'
        Address.objects.filter(id=instance.id).update(
            validation_status='pending',
            updated_at=timezone.now()
        )


# ВРЕМЕННО ОТКЛЮЧЕНО - вызывает бесконечный цикл
# @receiver(post_save, sender=AddressValidation)
def update_address_validation_status(sender, instance, created, **kwargs):
    """
    Обновляет статус валидации адреса при создании записи валидации.
    
    Args:
        sender: Модель-отправитель сигнала
        instance: Экземпляр модели
        created: Флаг создания новой записи
        **kwargs: Дополнительные параметры
    """
    if created:
        address = instance.address
        
        # Обновляем статус адреса на основе результата валидации
        if instance.is_valid:
            address.is_validated = True
            address.validation_status = 'valid'
            address.formatted_address = instance.formatted_address
            address.latitude = instance.latitude
            address.longitude = instance.longitude
        else:
            address.validation_status = 'invalid'
        
        # Сохраняем изменения без вызова сигнала
        Address.objects.filter(id=address.id).update(
            is_validated=address.is_validated,
            validation_status=address.validation_status,
            formatted_address=address.formatted_address,
            latitude=address.latitude,
            longitude=address.longitude,
            updated_at=timezone.now()
        )


# ВРЕМЕННО ОТКЛЮЧЕНО - вызывает бесконечный цикл
# @receiver(pre_delete, sender=Address)
def cleanup_address_data(sender, instance, **kwargs):
    """
    Очищает связанные данные при удалении адреса.
    
    Args:
        sender: Модель-отправитель сигнала
        instance: Экземпляр модели
        **kwargs: Дополнительные параметры
    """
    # Удаляем связанные записи валидации
    AddressValidation.objects.filter(address=instance).delete()
    
    # Очищаем кэш для этого адреса
    cache_key = f"address_validation_{instance.id}"
    cache.delete(cache_key)


# ВРЕМЕННО ОТКЛЮЧЕНО - вызывает бесконечный цикл
# @receiver(post_save, sender=AddressCache)
def cleanup_expired_cache(sender, instance, created, **kwargs):
    """
    Очищает устаревшие записи кэша.
    
    Args:
        sender: Модель-отправитель сигнала
        instance: Экземпляр модели
        created: Флаг создания новой записи
        **kwargs: Дополнительные параметры
    """
    # Удаляем записи кэша, которые истекли
    expired_cache = AddressCache.objects.filter(
        expires_at__lt=timezone.now()
    )
    expired_cache.delete()


def cleanup_old_validation_records():
    """
    Очищает старые записи валидации (старше 30 дней).
    """
    cutoff_date = timezone.now() - timedelta(days=30)
    old_validations = AddressValidation.objects.filter(
        created_at__lt=cutoff_date
    )
    old_validations.delete()


def cleanup_old_cache_records():
    """
    Очищает старые записи кэша (старше 7 дней).
    """
    cutoff_date = timezone.now() - timedelta(days=7)
    old_cache = AddressCache.objects.filter(
        created_at__lt=cutoff_date
    )
    old_cache.delete()


# Сигналы для обновления связанных моделей при изменении адреса
# ВРЕМЕННО ОТКЛЮЧЕНО - вызывает бесконечный цикл
# @receiver(post_save, sender=Address)
def update_related_models(sender, instance, created, **kwargs):
    """
    Обновляет связанные модели при изменении адреса.
    
    Args:
        sender: Модель-отправитель сигнала
        instance: Экземпляр модели
        created: Флаг создания новой записи
        **kwargs: Дополнительные параметры
    """
    # Обновляем координаты в связанных моделях
    if instance.is_validated and instance.latitude and instance.longitude:
        # Обновляем локации провайдеров (ProviderLocation)
        from providers.models import ProviderLocation
        
        locations = ProviderLocation.objects.filter(structured_address=instance)
        for location in locations:
            # Координаты уже в structured_address, ничего не нужно обновлять
            # Но можно обновить updated_at для отслеживания изменений
            location.save(update_fields=['updated_at'])
        
        # Обновляем организации провайдеров (Provider) - только updated_at
        from providers.models import Provider
        
        providers = Provider.objects.filter(structured_address=instance)
        for provider in providers:
            provider.save(update_fields=['updated_at'])
        
        # Обновляем профили ситтеров
        from sitters.models import SitterProfile
        # SitterProfile не имеет поля address, пропускаем
        pass
        
        # Обновляем пользователей
        from users.models import User
        # User не имеет поля address, пропускаем
        pass 