"""
Services for provider operations.

Этот модуль содержит сервисы для безопасных операций с учреждениями.
Основной компонент - ProviderTransactionService для защиты от конкурентного доступа.
"""

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from typing import Optional, List, Dict, Any
from datetime import date, time
import logging

from .models import Provider, ProviderService, ProviderSchedule
from booking.models import Booking, TimeSlot

logger = logging.getLogger(__name__)


class ProviderTransactionService:
    """
    Сервис для безопасных операций с учреждениями.
    
    Обеспечивает защиту от конкурентного доступа при изменении
    настроек учреждений через транзакционные блоки.
    """
    
    @staticmethod
    @transaction.atomic
    def update_provider_settings(
        provider_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Provider:
        """
        Обновляет настройки учреждения с блокировкой.
        
        Args:
            provider_id: ID учреждения
            name: Название
            description: Описание
            address: Адрес
            phone: Телефон
            email: Email
            is_active: Активность
            
        Returns:
            Provider: Обновленное учреждение
            
        Raises:
            ValidationError: Если учреждение уже обновляется другим пользователем
        """
        # Блокируем учреждение для изменения
        provider = Provider.objects.select_for_update().get(id=provider_id)
        
        # Обновляем поля
        if name is not None:
            provider.name = name
        if description is not None:
            provider.description = description
        if address is not None:
            provider.address = address
        if phone is not None:
            provider.phone = phone
        if email is not None:
            provider.email = email
        if is_active is not None:
            provider.is_active = is_active
        
        provider.save()
        
        logger.info(f"Provider settings updated: {provider.id}")
        return provider
    
    @staticmethod
    @transaction.atomic
    def update_provider_service(
        provider_service_id: int,
        price: Optional[float] = None,
        duration: Optional[int] = None,
        is_active: Optional[bool] = None
    ) -> ProviderService:
        """
        Обновляет услугу учреждения с блокировкой.
        
        Args:
            provider_service_id: ID услуги учреждения
            price: Цена
            duration: Продолжительность
            is_active: Активность
            
        Returns:
            ProviderService: Обновленная услуга
            
        Raises:
            ValidationError: Если услуга уже обновляется другим пользователем
        """
        # Блокируем услугу учреждения для изменения
        provider_service = ProviderService.objects.select_for_update().get(id=provider_service_id)
        
        # Блокируем учреждение
        Provider.objects.select_for_update().get(id=provider_service.provider.id)
        
        # Проверяем, что нет активных бронирований для этой услуги
        if is_active is False:
            active_bookings = Booking.objects.filter(
                provider=provider_service.provider,
                service=provider_service.service,
                status__name__in=['active', 'pending_confirmation']
            ).first()
            
            if active_bookings:
                raise ValidationError(_("Cannot deactivate service - there are active bookings"))
        
        # Обновляем поля
        if price is not None:
            provider_service.price = price
        if duration is not None:
            provider_service.duration = duration
        if is_active is not None:
            provider_service.is_active = is_active
        
        provider_service.save()
        
        logger.info(f"Provider service updated: {provider_service.id}")
        return provider_service
    
    @staticmethod
    @transaction.atomic
    def update_provider_schedule(
        provider_id: int,
        weekday: int,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        is_closed: Optional[bool] = None
    ) -> ProviderSchedule:
        """
        Обновляет расписание учреждения с блокировкой.
        
        Args:
            provider_id: ID учреждения
            weekday: День недели (0-6)
            start_time: Время начала
            end_time: Время окончания
            is_closed: Закрыто
            
        Returns:
            ProviderSchedule: Обновленное расписание
            
        Raises:
            ValidationError: Если расписание уже обновляется другим пользователем
        """
        # Блокируем учреждение
        provider = Provider.objects.select_for_update().get(id=provider_id)
        
        # Блокируем расписание учреждения на этот день
        schedule = ProviderSchedule.objects.select_for_update().filter(
            provider=provider,
            weekday=weekday
        ).first()
        
        # Проверяем, что нет активных бронирований в это время
        if is_closed is True:
            # Получаем даты для этого дня недели в будущем
            from datetime import date, timedelta
            today = date.today()
            days_ahead = weekday - today.weekday()
            if days_ahead <= 0:  # Целевой день уже прошел на этой неделе
                days_ahead += 7
            
            target_date = today + timedelta(days=days_ahead)
            
            active_bookings = Booking.objects.filter(
                provider=provider,
                start_time__date=target_date,
                status__name__in=['active', 'pending_confirmation']
            ).first()
            
            if active_bookings:
                raise ValidationError(_("Cannot close provider - there are active bookings"))
        
        # Обновляем или создаем расписание
        if schedule:
            if start_time is not None:
                schedule.start_time = start_time
            if end_time is not None:
                schedule.end_time = end_time
            if is_closed is not None:
                schedule.is_closed = is_closed
            schedule.save()
        else:
            schedule = ProviderSchedule.objects.create(
                provider=provider,
                weekday=weekday,
                start_time=start_time or "09:00",
                end_time=end_time or "18:00",
                is_closed=is_closed or False
            )
        
        logger.info(f"Provider schedule updated: {provider.id} for weekday {weekday}")
        return schedule
    
    @staticmethod
    @transaction.atomic
    def bulk_update_provider_services(
        provider_id: int,
        services_data: List[Dict[str, Any]]
    ) -> List[ProviderService]:
        """
        Массовое обновление услуг учреждения с блокировкой.
        
        Args:
            provider_id: ID учреждения
            services_data: Список данных услуг
            
        Returns:
            List[ProviderService]: Список обновленных услуг
            
        Raises:
            ValidationError: Если есть конфликты
        """
        # Блокируем учреждение
        provider = Provider.objects.select_for_update().get(id=provider_id)
        
        updated_services = []
        
        for data in services_data:
            service_id = data['service_id']
            price = data.get('price')
            duration = data.get('duration')
            is_active = data.get('is_active')
            
            # Блокируем услугу учреждения
            provider_service = ProviderService.objects.select_for_update().filter(
                provider=provider,
                service_id=service_id
            ).first()
            
            if not provider_service:
                raise ValidationError(_("Provider service not found"))
            
            # Проверяем активные бронирования при деактивации
            if is_active is False:
                active_bookings = Booking.objects.filter(
                    provider=provider,
                    service=provider_service.service,
                    status__name__in=['active', 'pending_confirmation']
                ).first()
                
                if active_bookings:
                    raise ValidationError(_("Cannot deactivate service - there are active bookings"))
            
            # Обновляем поля
            if price is not None:
                provider_service.price = price
            if duration is not None:
                provider_service.duration = duration
            if is_active is not None:
                provider_service.is_active = is_active
            
            provider_service.save()
            updated_services.append(provider_service)
        
        logger.info(f"Bulk provider services update completed: {provider.id}")
        return updated_services
    
    @staticmethod
    def check_provider_availability(
        provider_id: int,
        target_date: date,
        start_time: time,
        end_time: time
    ) -> bool:
        """
        Проверяет доступность учреждения без блокировки.
        
        Args:
            provider_id: ID учреждения
            target_date: Дата
            start_time: Время начала
            end_time: Время окончания
            
        Returns:
            bool: True если учреждение доступно
        """
        provider = Provider.objects.get(id=provider_id)
        
        if not provider.is_active:
            return False
        
        # Проверяем расписание учреждения
        weekday = target_date.weekday()
        schedule = ProviderSchedule.objects.filter(
            provider=provider,
            weekday=weekday,
            is_closed=False
        ).first()
        
        if not schedule:
            return False
        
        # Проверяем рабочие часы
        if start_time < schedule.start_time or end_time > schedule.end_time:
            return False
        
        return True 