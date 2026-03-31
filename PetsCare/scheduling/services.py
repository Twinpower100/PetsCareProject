"""
Services for the scheduling module.

Этот модуль содержит сервисы для работы с отсутствиями сотрудников и проверки доступности.
"""

from datetime import date, time
from typing import List, Tuple, Optional
from .models import Vacation, SickLeave
from providers.models import Employee, EmployeeLocationService
from catalog.models import Service


class AvailabilityChecker:
    """
    Сервис для проверки доступности сотрудников.
    
    Основные функции:
    - Проверка доступности сотрудника в определенное время
    - Учет отпусков и больничных
    """
    
    @staticmethod
    def is_employee_available(employee: Employee, target_date: date, 
                            start_time: time | None = None, end_time: time | None = None,
                            location=None) -> Tuple[bool, List[str]]:
        """
        Проверяет доступность сотрудника в указанную дату.
        
        Args:
            employee: Сотрудник для проверки
            target_date: Дата для проверки
            start_time: Время начала (опционально)
            end_time: Время окончания (опционально)
            location: Локация для проверки (опционально). Если указана, 
                     учитываются только глобальные отпуска или отпуска в этой локации.
            
        Returns:
            Tuple[bool, List[str]]: (доступен, список причин недоступности)
        """
        from django.db.models import Q
        reasons = []
        
        # Проверка отпусков
        vacation_qs = Vacation.objects.filter(
            employee=employee,
            start_date__lte=target_date,
            end_date__gte=target_date,
            is_approved=True
        )
        if location:
            vacation_qs = vacation_qs.filter(Q(provider_location__isnull=True) | Q(provider_location=location))
        
        vacation = vacation_qs.first()
        if vacation:
            reasons.append(f"Employee is on vacation ({vacation.vacation_type})")
            return False, reasons
        
        # Проверка больничных
        sick_leave_qs = SickLeave.objects.filter(
            employee=employee,
            start_date__lte=target_date,
            is_confirmed=True
        )
        if location:
            sick_leave_qs = sick_leave_qs.filter(Q(provider_location__isnull=True) | Q(provider_location=location))
            
        sick_leave = sick_leave_qs.first()
        if sick_leave:
            if not sick_leave.end_date or sick_leave.end_date >= target_date:
                reasons.append(f"Employee is on sick leave ({sick_leave.sick_leave_type})")
                return False, reasons
        
        return True, reasons
    
    @staticmethod
    def get_employee_services(employee: Employee) -> List[Service]:
        """
        Возвращает список услуг, которые может оказывать сотрудник.
        
        Args:
            employee: Сотрудник
            
        Returns:
            List[Service]: Список услуг
        """
        service_ids = EmployeeLocationService.objects.filter(
            employee=employee
        ).values_list('service_id', flat=True).distinct()
        return list(Service.objects.filter(id__in=service_ids))
