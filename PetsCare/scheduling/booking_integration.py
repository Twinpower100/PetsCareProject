"""
Booking integration service for the scheduling module.

Этот модуль содержит сервис для интеграции планирования с системой бронирования.

Основные функции:
1. Проверка существующих бронирований
2. Обновление временных слотов
3. Синхронизация с планированием
4. Поиск конфликтующих бронирований
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from providers.models import Provider, Employee
from booking.models import Booking, TimeSlot
from catalog.models import Service


class BookingIntegrationService:
    """
    Сервис для интеграции планирования с системой бронирования.
    
    Основные функции:
    - Проверка существующих бронирований
    - Обновление временных слотов
    - Синхронизация с планированием
    """
    
    def __init__(self, provider: Provider):
        """
        Инициализирует сервис интеграции с бронированиями.
        
        Args:
            provider: Учреждение
        """
        self.provider = provider
    
    def check_existing_bookings(self, start_date: date, end_date: date) -> Dict:
        """
        Проверяет существующие бронирования в периоде.
        
        Args:
            start_date: Дата начала периода
            end_date: Дата окончания периода
            
        Returns:
            Dict: Информация о бронированиях
        """
        bookings = Booking.objects.filter(
            provider=self.provider,
            start_time__date__gte=start_date,
            start_time__date__lte=end_date,
            status__name__in=['active', 'pending_confirmation']
        ).select_related('employee', 'service', 'status')
        
        booking_data = {}
        for booking in bookings:
            date_key = booking.start_time.date().isoformat()
            if date_key not in booking_data:
                booking_data[date_key] = []
            
            booking_data[date_key].append({
                'id': booking.id,
                'employee': booking.employee,
                'service': booking.service,
                'start_time': booking.start_time,
                'end_time': booking.end_time,
                'status': booking.status.name
            })
        
        return {
            'total_bookings': bookings.count(),
            'bookings_by_date': booking_data
        }
    
    def update_time_slots(self, schedule_result: Dict) -> Dict:
        """
        Обновляет временные слоты на основе планирования.
        
        Args:
            schedule_result: Результат планирования
            
        Returns:
            Dict: Результат обновления
        """
        updated_slots = []
        created_slots = []
        errors = []
        
        schedule = schedule_result.get('schedule', {})
        
        for date_str, assignments in schedule.items():
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            for assignment in assignments:
                try:
                    # Создаем или обновляем временной слот
                    slot, created = TimeSlot.objects.get_or_create(
                        employee=assignment['employee'],
                        provider=self.provider,
                        start_time=datetime.combine(date_obj, assignment['start_time']),
                        end_time=datetime.combine(date_obj, assignment['end_time']),
                        defaults={'is_available': True}
                    )
                    
                    if created:
                        created_slots.append(slot)
                    else:
                        slot.is_available = True
                        slot.save()
                        updated_slots.append(slot)
                        
                except Exception as e:
                    errors.append({
                        'assignment': assignment,
                        'error': str(e)
                    })
        
        return {
            'updated_slots': len(updated_slots),
            'created_slots': len(created_slots),
            'errors': errors
        }
    
    def find_conflicting_bookings(self, schedule_result: Dict) -> List[Dict]:
        """
        Находит конфликтующие бронирования.
        
        Args:
            schedule_result: Результат планирования
            
        Returns:
            List[Dict]: Список конфликтов
        """
        conflicts = []
        schedule = schedule_result.get('schedule', {})
        
        for date_str, assignments in schedule.items():
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            for assignment in assignments:
                # Проверяем конфликтующие бронирования
                conflicting_bookings = Booking.objects.filter(
                    employee=assignment['employee'],
                    start_time__date=date_obj,
                    start_time__lt=datetime.combine(date_obj, assignment['end_time']),
                    end_time__gt=datetime.combine(date_obj, assignment['start_time']),
                    status__name__in=['active', 'pending_confirmation']
                )
                
                for booking in conflicting_bookings:
                    conflicts.append({
                        'assignment': assignment,
                        'booking': booking,
                        'conflict_type': 'time_overlap',
                        'date': date_obj
                    })
        
        return conflicts
    
    def get_employee_booking_load(self, employee: Employee, target_date: date) -> Dict:
        """
        Получает нагрузку сотрудника по бронированиям.
        
        Args:
            employee: Сотрудник
            target_date: Дата
            
        Returns:
            Dict: Информация о нагрузке
        """
        bookings = Booking.objects.filter(
            employee=employee,
            start_time__date=target_date,
            status__name__in=['active', 'pending_confirmation']
        )
        
        total_hours = 0
        for booking in bookings:
            duration = booking.end_time - booking.start_time
            total_hours += duration.total_seconds() / 3600
        
        return {
            'total_bookings': bookings.count(),
            'total_hours': total_hours,
            'bookings': list(bookings.values('id', 'service__name', 'start_time', 'end_time'))
        }
    
    def check_workplace_conflicts(self, workplace, target_date: date,
                                start_time: datetime.time, end_time: datetime.time) -> List[Dict]:
        """
        Проверяет конфликты в рабочем месте.
        
        Args:
            workplace: Рабочее место
            target_date: Дата
            start_time: Время начала
            end_time: Время окончания
            
        Returns:
            List[Dict]: Список конфликтов
        """
        # Получаем все бронирования в рабочем месте в это время
        start_datetime = datetime.combine(target_date, start_time)
        end_datetime = datetime.combine(target_date, end_time)
        
        conflicting_bookings = Booking.objects.filter(
            provider=self.provider,
            start_time__lt=end_datetime,
            end_time__gt=start_datetime,
            status__name__in=['active', 'pending_confirmation']
        )
        
        conflicts = []
        for booking in conflicting_bookings:
            conflicts.append({
                'booking': booking,
                'conflict_type': 'workplace_overlap',
                'start_time': start_datetime,
                'end_time': end_datetime
            })
        
        return conflicts 