"""
Services for the providers module.

Этот модуль содержит сервисы для безопасных операций с расписанием сотрудников.
Основной компонент - ScheduleTransactionService для защиты от конкурентного доступа.
"""

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from typing import Optional, List, Dict, Any
from datetime import date, time
import logging

from .models import Employee, Provider, Schedule, EmployeeWorkSlot
from booking.models import Booking, TimeSlot

logger = logging.getLogger(__name__)


class ScheduleTransactionService:
    """
    Сервис для безопасных операций с расписанием сотрудников.
    
    Обеспечивает защиту от конкурентного доступа при изменении
    расписания сотрудников через транзакционные блоки.
    """
    
    @staticmethod
    @transaction.atomic
    def update_employee_schedule(
        employee: Employee,
        provider: Provider,
        target_date: date,
        start_time: time,
        end_time: time,
        is_available: bool = True
    ) -> Schedule:
        """
        Обновляет расписание сотрудника с блокировкой всего расписания на день.
        
        Args:
            employee: Сотрудник
            provider: Учреждение
            target_date: Дата расписания
            start_time: Время начала
            end_time: Время окончания
            is_available: Доступность
            
        Returns:
            Schedule: Обновленное расписание
            
        Raises:
            ValidationError: Если расписание уже изменяется другим пользователем
        """
        # Блокируем ВСЁ расписание сотрудника на эту дату
        existing_schedules = Schedule.objects.select_for_update().filter(
            employee=employee,
            provider=provider,
            date=target_date
        )
        
        # Проверяем, что нет активных бронирований в это время
        if not is_available:
            conflicting_bookings = Booking.objects.filter(
                employee=employee,
                start_time__date=target_date,
                start_time__time__gte=start_time,
                end_time__time__lte=end_time,
                status__name__in=['active', 'pending_confirmation']
            ).first()
            
            if conflicting_bookings:
                raise ValidationError(_("Cannot make employee unavailable - there are active bookings"))
        
        # Обновляем или создаем расписание
        schedule, created = Schedule.objects.get_or_create(
            employee=employee,
            provider=provider,
            date=target_date,
            defaults={
                'start_time': start_time,
                'end_time': end_time,
                'is_available': is_available
            }
        )
        
        if not created:
            schedule.start_time = start_time
            schedule.end_time = end_time
            schedule.is_available = is_available
            schedule.save()
        
        logger.info(f"Employee schedule updated: {employee.id} for {target_date}")
        return schedule
    
    @staticmethod
    @transaction.atomic
    def bulk_update_schedules(
        employee: Employee,
        provider: Provider,
        schedule_data: List[Dict[str, Any]]
    ) -> List[Schedule]:
        """
        Массовое обновление расписания сотрудника с блокировкой.
        
        Args:
            employee: Сотрудник
            provider: Учреждение
            schedule_data: Список данных расписания
            
        Returns:
            List[Schedule]: Список обновленных расписаний
            
        Raises:
            ValidationError: Если есть конфликты
        """
        # Блокируем все расписания сотрудника в этом учреждении
        existing_schedules = Schedule.objects.select_for_update().filter(
            employee=employee,
            provider=provider
        )
        
        updated_schedules = []
        
        for data in schedule_data:
            target_date = data['date']
            start_time = data['start_time']
            end_time = data['end_time']
            is_available = data.get('is_available', True)
            
            # Проверяем конфликты с бронированиями
            if not is_available:
                conflicting_bookings = Booking.objects.filter(
                    employee=employee,
                    start_time__date=target_date,
                    start_time__time__gte=start_time,
                    end_time__time__lte=end_time,
                    status__name__in=['active', 'pending_confirmation']
                ).first()
                
                if conflicting_bookings:
                    raise ValidationError(_("Cannot make employee unavailable - there are active bookings"))
            
            # Обновляем или создаем расписание
            schedule, created = Schedule.objects.get_or_create(
                employee=employee,
                provider=provider,
                date=target_date,
                defaults={
                    'start_time': start_time,
                    'end_time': end_time,
                    'is_available': is_available
                }
            )
            
            if not created:
                schedule.start_time = start_time
                schedule.end_time = end_time
                schedule.is_available = is_available
                schedule.save()
            
            updated_schedules.append(schedule)
        
        logger.info(f"Bulk schedule update completed: {employee.id}")
        return updated_schedules
    
    @staticmethod
    @transaction.atomic
    def create_work_slot(
        employee: Employee,
        provider: Provider,
        date: date,
        start_time: time,
        end_time: time,
        workplace_id: Optional[int] = None
    ) -> EmployeeWorkSlot:
        """
        Создает рабочий слот с проверкой конфликтов.
        
        Args:
            employee: Сотрудник
            provider: Учреждение
            date: Дата
            start_time: Время начала
            end_time: Время окончания
            workplace_id: ID рабочего места
            
        Returns:
            EmployeeWorkSlot: Созданный рабочий слот
            
        Raises:
            ValidationError: Если есть конфликты
        """
        # Блокируем расписание сотрудника на эту дату
        Schedule.objects.select_for_update().filter(
            employee=employee,
            provider=provider,
            date=date
        ).first()
        
        # Проверяем, что сотрудник доступен в это время
        schedule = Schedule.objects.filter(
            employee=employee,
            provider=provider,
            date=date,
            start_time__lte=start_time,
            end_time__gte=end_time,
            is_available=True
        ).first()
        
        if not schedule:
            raise ValidationError(_("Employee is not available at this time"))
        
        # Проверяем конфликты с существующими слотами
        conflicting_slot = EmployeeWorkSlot.objects.filter(
            employee=employee,
            date=date,
            start_time__lt=end_time,
            end_time__gt=start_time
        ).first()
        
        if conflicting_slot:
            raise ValidationError(_("Work slot conflicts with existing schedule"))
        
        # Создаем рабочий слот
        work_slot = EmployeeWorkSlot.objects.create(
            employee=employee,
            provider=provider,
            date=date,
            start_time=start_time,
            end_time=end_time,
            workplace_id=workplace_id
        )
        
        logger.info(f"Work slot created: {work_slot.id}")
        return work_slot
    
    @staticmethod
    @transaction.atomic
    def update_work_slot(
        slot_id: int,
        new_start_time: Optional[time] = None,
        new_end_time: Optional[time] = None,
        new_workplace_id: Optional[int] = None
    ) -> EmployeeWorkSlot:
        """
        Обновляет рабочий слот с проверкой конфликтов.
        
        Args:
            slot_id: ID рабочего слота
            new_start_time: Новое время начала
            new_end_time: Новое время окончания
            new_workplace_id: Новое рабочее место
            
        Returns:
            EmployeeWorkSlot: Обновленный рабочий слот
            
        Raises:
            ValidationError: Если есть конфликты
        """
        # Блокируем слот для изменения
        work_slot = EmployeeWorkSlot.objects.select_for_update().get(id=slot_id)
        
        # Блокируем расписание сотрудника на эту дату
        Schedule.objects.select_for_update().filter(
            employee=work_slot.employee,
            provider=work_slot.provider,
            date=work_slot.date
        ).first()
        
        start_time = new_start_time or work_slot.start_time
        end_time = new_end_time or work_slot.end_time
        
        # Проверяем, что сотрудник доступен в новое время
        schedule = Schedule.objects.filter(
            employee=work_slot.employee,
            provider=work_slot.provider,
            date=work_slot.date,
            start_time__lte=start_time,
            end_time__gte=end_time,
            is_available=True
        ).first()
        
        if not schedule:
            raise ValidationError(_("Employee is not available at new time"))
        
        # Проверяем конфликты с другими слотами
        conflicting_slot = EmployeeWorkSlot.objects.filter(
            employee=work_slot.employee,
            date=work_slot.date,
            start_time__lt=end_time,
            end_time__gt=start_time
        ).exclude(id=slot_id).first()
        
        if conflicting_slot:
            raise ValidationError(_("New time conflicts with existing work slot"))
        
        # Обновляем слот
        if new_start_time is not None:
            work_slot.start_time = new_start_time
        if new_end_time is not None:
            work_slot.end_time = new_end_time
        if new_workplace_id is not None:
            work_slot.workplace_id = new_workplace_id
        
        work_slot.save()
        
        logger.info(f"Work slot updated: {work_slot.id}")
        return work_slot
    
    @staticmethod
    def check_employee_availability(
        employee: Employee,
        provider: Provider,
        target_date: date,
        start_time: time,
        end_time: time
    ) -> bool:
        """
        Проверяет доступность сотрудника без блокировки.
        
        Args:
            employee: Сотрудник
            provider: Учреждение
            target_date: Дата
            start_time: Время начала
            end_time: Время окончания
            
        Returns:
            bool: True если сотрудник доступен
        """
        # Проверяем расписание
        schedule = Schedule.objects.filter(
            employee=employee,
            provider=provider,
            date=target_date,
            start_time__lte=start_time,
            end_time__gte=end_time,
            is_available=True
        ).first()
        
        if not schedule:
            return False
        
        # Проверяем конфликты с рабочими слотами
        conflicting_slot = EmployeeWorkSlot.objects.filter(
            employee=employee,
            date=target_date,
            start_time__lt=end_time,
            end_time__gt=start_time
        ).first()
        
        if conflicting_slot:
            return False
        
        return True 