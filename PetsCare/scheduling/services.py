"""
Services for the scheduling module.

Этот модуль содержит сервисы для системы автоматического планирования расписания.

Основные компоненты:
1. SchedulePlannerService - основной сервис планирования
2. AvailabilityChecker - проверка доступности сотрудников
3. ConflictResolver - разрешение конфликтов
4. ScheduleOptimizer - оптимизация расписания

Особенности реализации:
- Жадный алгоритм планирования
- Учет приоритетов услуг
- Разрешение конфликтов по приоритетам
- Интеграция с существующими моделями
"""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import date, datetime, time, timedelta
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from enum import Enum

from .models import (
    Workplace, WorkplaceAllowedServices, ServicePriority,
    Vacation, SickLeave, DayOff, EmployeeSchedule, StaffingRequirement
)
from providers.models import Provider, Employee, Schedule
from catalog.models import Service


class ScheduleConflictType(Enum):
    """Типы конфликтов в расписании."""
    EMPLOYEE_UNAVAILABLE = 'employee_unavailable'
    WORKPLACE_CONFLICT = 'workplace_conflict'
    SERVICE_CONFLICT = 'service_conflict'
    TIME_OVERLAP = 'time_overlap'
    INSUFFICIENT_STAFF = 'insufficient_staff'


@dataclass
class ScheduleConflict:
    """Информация о конфликте в расписании."""
    conflict_type: ScheduleConflictType
    description: str
    severity: str  # 'low', 'medium', 'high', 'critical'
    affected_entities: List[str]
    suggested_resolution: Optional[str] = None


@dataclass
class ScheduleSlot:
    """Слот расписания для планирования."""
    employee: Employee
    service: Service
    workplace: Workplace
    start_time: time
    end_time: time
    day_of_week: int
    priority: int
    is_preferred: bool = False


class AvailabilityChecker:
    """
    Сервис для проверки доступности сотрудников.
    
    Основные функции:
    - Проверка доступности сотрудника в определенное время
    - Учет отпусков, больничных и отгулов
    - Проверка предпочтений расписания
    - Валидация рабочих часов
    """
    
    @staticmethod
    def is_employee_available(employee: Employee, target_date: date, 
                            start_time: time, end_time: time) -> Tuple[bool, List[str]]:
        """
        Проверяет доступность сотрудника в указанное время.
        
        Args:
            employee: Сотрудник для проверки
            target_date: Дата для проверки
            start_time: Время начала
            end_time: Время окончания
            
        Returns:
            Tuple[bool, List[str]]: (доступен, список причин недоступности)
        """
        reasons = []
        
        # Проверка отпусков
        vacation = Vacation.objects.filter(
            employee=employee,
            start_date__lte=target_date,
            end_date__gte=target_date,
            is_approved=True
        ).first()
        
        if vacation:
            reasons.append(f"Employee is on vacation ({vacation.vacation_type})")
            return False, reasons
        
        # Проверка больничных
        sick_leave = SickLeave.objects.filter(
            employee=employee,
            start_date__lte=target_date,
            is_confirmed=True
        ).first()
        
        if sick_leave:
            if not sick_leave.end_date or sick_leave.end_date >= target_date:
                reasons.append(f"Employee is on sick leave ({sick_leave.sick_leave_type})")
                return False, reasons
        
        # Проверка отгулов
        day_off = DayOff.objects.filter(
            employee=employee,
            date=target_date,
            is_approved=True
        ).first()
        
        if day_off:
            reasons.append(f"Employee has day off ({day_off.day_off_type})")
            return False, reasons
        
        # Проверка предпочтений расписания
        day_of_week = target_date.weekday()
        schedule_pref = EmployeeSchedule.objects.filter(
            employee=employee,
            day_of_week=day_of_week
        ).first()
        
        if schedule_pref and not schedule_pref.is_available:
            reasons.append("Employee is not available on this day according to preferences")
            return False, reasons
        
        # Проверка рабочих часов учреждения
        provider_schedule = employee.providers.filter(
            schedules__weekday=day_of_week,
            schedules__is_closed=False
        ).first()
        
        if not provider_schedule:
            reasons.append("Provider is closed on this day")
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
        return list(employee.services.all())
    
    @staticmethod
    def get_employee_preferences(employee: Employee, day_of_week: int) -> Optional[EmployeeSchedule]:
        """
        Возвращает предпочтения сотрудника для определенного дня недели.
        
        Args:
            employee: Сотрудник
            day_of_week: День недели (0-6)
            
        Returns:
            Optional[EmployeeSchedule]: Предпочтения или None
        """
        return EmployeeSchedule.objects.filter(
            employee=employee,
            day_of_week=day_of_week
        ).first()


class ConflictResolver:
    """
    Сервис для разрешения конфликтов в расписании.
    
    Основные функции:
    - Выявление конфликтов
    - Предложение решений
    - Приоритизация разрешений
    """
    
    @staticmethod
    def check_workplace_conflicts(workplace: Workplace, target_date: date,
                                 start_time: time, end_time: time,
                                 service: Service) -> List[ScheduleConflict]:
        """
        Проверяет конфликты в рабочем месте.
        
        Args:
            workplace: Рабочее место
            target_date: Дата
            start_time: Время начала
            end_time: Время окончания
            service: Услуга
            
        Returns:
            List[ScheduleConflict]: Список конфликтов
        """
        conflicts = []
        
        # Проверка разрешенных услуг
        allowed_service = WorkplaceAllowedServices.objects.filter(
            workplace=workplace,
            service=service,
            is_active=True
        ).first()
        
        if not allowed_service:
            conflicts.append(ScheduleConflict(
                conflict_type=ScheduleConflictType.SERVICE_CONFLICT,
                description=f"Service {service.name} is not allowed in workplace {workplace.name}",
                severity='high',
                affected_entities=[workplace.name, service.name]
            ))
        
        return conflicts
    
    @staticmethod
    def resolve_conflicts_by_priority(conflicts: List[ScheduleConflict]) -> List[ScheduleConflict]:
        """
        Разрешает конфликты по приоритету.
        
        Args:
            conflicts: Список конфликтов
            
        Returns:
            List[ScheduleConflict]: Отфильтрованные конфликты
        """
        # Сортируем по приоритету (critical > high > medium > low)
        priority_order = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}
        
        sorted_conflicts = sorted(
            conflicts,
            key=lambda x: priority_order.get(x.severity, 0),
            reverse=True
        )
        
        return sorted_conflicts


class SchedulePlannerService:
    """
    Основной сервис для автоматического планирования расписания.
    
    Основные функции:
    - Планирование расписания для учреждения
    - Учет всех ограничений и предпочтений
    - Генерация отчетов о планировании
    """
    
    def __init__(self, provider: Provider):
        """
        Инициализирует сервис планирования для учреждения.
        
        Args:
            provider: Учреждение для планирования
        """
        self.provider = provider
        self.availability_checker = AvailabilityChecker()
        self.conflict_resolver = ConflictResolver()
        self.conflicts = []
        self.assigned_slots = []
    
    @transaction.atomic
    def plan_schedule(self, start_date: date, end_date: date) -> Dict:
        """
        Планирует расписание для указанного периода с транзакционной защитой.
        
        Args:
            start_date: Дата начала планирования
            end_date: Дата окончания планирования
            
        Returns:
            Dict: Результат планирования
            
        Raises:
            ValidationError: Если учреждение уже обновляется другим процессом
        """
        # Блокируем учреждение на время планирования
        provider = Provider.objects.select_for_update().get(id=self.provider.id)
        
        self.conflicts = []
        self.assigned_slots = []
        
        # Получаем потребности в специалистах
        staffing_requirements = self._get_staffing_requirements()
        
        # Получаем доступных сотрудников
        available_employees = self._get_available_employees()
        
        # Получаем рабочие места
        workplaces = self._get_workplaces()
        
        # Планируем по дням
        current_date = start_date
        while current_date <= end_date:
            day_of_week = current_date.weekday()
            
            # Планируем день
            day_slots = self._plan_day(
                current_date, day_of_week, 
                staffing_requirements, available_employees, workplaces
            )
            
            self.assigned_slots.extend(day_slots)
            current_date += timedelta(days=1)
        
        return {
            'assigned_slots': self.assigned_slots,
            'conflicts': self.conflicts,
            'summary': self._generate_summary()
        }
    
    def _get_staffing_requirements(self) -> Dict[Tuple[int, Service], int]:
        """
        Получает потребности в специалистах.
        
        Returns:
            Dict[Tuple[int, Service], int]: Словарь потребностей
        """
        requirements = {}
        
        for req in StaffingRequirement.objects.filter(
            provider=self.provider,
            is_active=True
        ):
            key = (req.day_of_week, req.service)
            requirements[key] = req.required_count
        
        return requirements
    
    def _get_available_employees(self) -> List[Employee]:
        """
        Получает список доступных сотрудников учреждения.
        
        Returns:
            List[Employee]: Список сотрудников
        """
        return list(Employee.objects.filter(
            providers=self.provider,
            is_active=True
        ).prefetch_related('services', 'preferred_schedules'))
    
    def _get_workplaces(self) -> List[Workplace]:
        """
        Получает список рабочих мест учреждения.
        
        Returns:
            List[Workplace]: Список рабочих мест
        """
        return list(Workplace.objects.filter(
            provider=self.provider,
            is_active=True
        ).prefetch_related('allowed_services'))
    
    def _plan_day(self, target_date: date, day_of_week: int,
                  staffing_requirements: Dict, available_employees: List[Employee],
                  workplaces: List[Workplace]) -> List[ScheduleSlot]:
        """
        Планирует расписание на один день.
        
        Args:
            target_date: Дата планирования
            day_of_week: День недели
            staffing_requirements: Потребности в специалистах
            available_employees: Доступные сотрудники
            workplaces: Рабочие места
            
        Returns:
            List[ScheduleSlot]: Список назначенных слотов
        """
        day_slots = []
        
        # Получаем приоритеты услуг для этого дня
        service_priorities = self._get_service_priorities()
        
        # Сортируем услуги по приоритету
        sorted_services = sorted(
            service_priorities.items(),
            key=lambda x: x[1]
        )
        
        for service, priority in sorted_services:
            key = (day_of_week, service)
            required_count = staffing_requirements.get(key, 0)
            
            if required_count > 0:
                # Назначаем сотрудников для этой услуги
                service_slots = self._assign_employees_for_service(
                    service, required_count, available_employees,
                    workplaces, target_date, day_of_week, priority
                )
                day_slots.extend(service_slots)
        
        return day_slots
    
    def _get_service_priorities(self) -> Dict[Service, int]:
        """
        Получает приоритеты услуг для учреждения.
        
        Returns:
            Dict[Service, int]: Словарь приоритетов
        """
        priorities = {}
        
        for priority in ServicePriority.objects.filter(
            provider=self.provider,
            is_active=True
        ):
            priorities[priority.service] = priority.priority
        
        return priorities
    
    def _assign_employees_for_service(self, service: Service, required_count: int,
                                    available_employees: List[Employee],
                                    workplaces: List[Workplace],
                                    target_date: date, day_of_week: int,
                                    priority: int) -> List[ScheduleSlot]:
        """
        Назначает сотрудников для конкретной услуги.
        
        Args:
            service: Услуга
            required_count: Требуемое количество специалистов
            available_employees: Доступные сотрудники
            workplaces: Рабочие места
            target_date: Дата назначения
            day_of_week: День недели
            priority: Приоритет услуги
            
        Returns:
            List[ScheduleSlot]: Список назначенных слотов
        """
        slots = []
        assigned_count = 0
        
        # Фильтруем сотрудников, которые могут оказывать эту услугу
        qualified_employees = [
            emp for emp in available_employees
            if service in emp.services.all()
        ]
        
        # Сортируем по предпочтениям
        qualified_employees.sort(
            key=lambda emp: self._get_employee_preference_score(emp, day_of_week)
        )
        
        for employee in qualified_employees:
            if assigned_count >= required_count:
                break
            
            # Проверяем доступность
            is_available, reasons = self.availability_checker.is_employee_available(
                employee, target_date, time(9, 0), time(18, 0)
            )
            
            if not is_available:
                self.conflicts.append(ScheduleConflict(
                    conflict_type=ScheduleConflictType.EMPLOYEE_UNAVAILABLE,
                    description=_('Employee {} is not available: {}').format(employee, ', '.join(reasons)),
                    severity='medium',
                    affected_entities=[str(employee)]
                ))
                continue
            
            # Находим подходящее рабочее место с учетом ограничений одновременности
            workplace = self._find_suitable_workplace(
                workplaces, service, target_date, time(9, 0), time(18, 0)
            )
            
            if not workplace:
                self.conflicts.append(ScheduleConflict(
                    conflict_type=ScheduleConflictType.WORKPLACE_CONFLICT,
                    description=_('No suitable workplace found for service {}').format(service.name),
                    severity='high',
                    affected_entities=[service.name]
                ))
                continue
            
            # Создаем слот
            slot = ScheduleSlot(
                employee=employee,
                service=service,
                workplace=workplace,
                start_time=time(9, 0),  # По умолчанию 9:00-18:00
                end_time=time(18, 0),
                day_of_week=day_of_week,
                priority=priority,
                is_preferred=self._is_preferred_schedule(employee, day_of_week)
            )
            
            slots.append(slot)
            assigned_count += 1
        
        # Если не хватает специалистов
        if assigned_count < required_count:
            self.conflicts.append(ScheduleConflict(
                conflict_type=ScheduleConflictType.INSUFFICIENT_STAFF,
                description=_('Insufficient staff for service {}: required {}, assigned {}').format(
                    service.name, required_count, assigned_count),
                severity='high',
                affected_entities=[service.name],
                suggested_resolution=_('Consider hiring additional staff or adjusting requirements')
            ))
        
        return slots
    
    def _get_employee_preference_score(self, employee: Employee, day_of_week: int) -> int:
        """
        Вычисляет оценку предпочтений сотрудника для дня недели.
        
        Args:
            employee: Сотрудник
            day_of_week: День недели
            
        Returns:
            int: Оценка (меньше = лучше)
        """
        pref = self.availability_checker.get_employee_preferences(employee, day_of_week)
        
        if not pref:
            return 100  # Нет предпочтений - низкий приоритет
        
        if not pref.is_available:
            return 1000  # Недоступен - очень низкий приоритет
        
        return pref.priority
    
    def _find_suitable_workplace(self, workplaces: List[Workplace], 
                                service: Service, target_date: date = None,
                                start_time: time = None, end_time: time = None) -> Optional[Workplace]:
        """
        Находит подходящее рабочее место для услуги с учетом ограничений одновременности.
        
        Args:
            workplaces: Список рабочих мест
            service: Услуга
            target_date: Дата планирования (для проверки одновременности)
            start_time: Время начала (для проверки одновременности)
            end_time: Время окончания (для проверки одновременности)
            
        Returns:
            Optional[Workplace]: Подходящее рабочее место или None
        """
        for workplace in workplaces:
            # Проверяем, разрешена ли услуга в этом рабочем месте
            allowed_service = WorkplaceAllowedServices.objects.filter(
                workplace=workplace,
                service=service,
                is_active=True
            ).first()
            
            if not allowed_service:
                continue
            
            # Если указано время, проверяем ограничения одновременности
            if target_date and start_time and end_time:
                if not self._check_simultaneity_constraints(workplace, service, target_date, start_time, end_time):
                    continue
            
            return workplace
        
        return None
    
    def _check_simultaneity_constraints(self, workplace: Workplace, service: Service,
                                      target_date: date, start_time: time, end_time: time) -> bool:
        """
        Проверяет ограничения одновременности для рабочего места.
        
        Args:
            workplace: Рабочее место
            service: Услуга
            target_date: Дата планирования
            start_time: Время начала
            end_time: Время окончания
            
        Returns:
            bool: True если ограничения соблюдены
        """
        # Получаем все разрешенные услуги для этого рабочего места
        allowed_services = WorkplaceAllowedServices.objects.filter(
            workplace=workplace,
            is_active=True
        ).values_list('service', flat=True)
        
        # Проверяем, что текущая услуга разрешена
        if service.id not in allowed_services:
            return False
        
        # Получаем уже назначенные услуги в это время
        conflicting_assignments = [
            slot for slot in self.assigned_slots
            if (slot.workplace == workplace and 
                slot.day_of_week == target_date.weekday() and
                self._time_overlaps(slot.start_time, slot.end_time, start_time, end_time))
        ]
        
        # Проверяем ограничения одновременности
        for assignment in conflicting_assignments:
            # Если уже есть назначение в это время, проверяем совместимость
            if not self._services_can_run_simultaneously(workplace, service, assignment.service):
                return False
        
        return True
    
    def _time_overlaps(self, start1: time, end1: time, start2: time, end2: time) -> bool:
        """
        Проверяет, пересекаются ли временные интервалы.
        
        Args:
            start1: Начало первого интервала
            end1: Конец первого интервала
            start2: Начало второго интервала
            end2: Конец второго интервала
            
        Returns:
            bool: True если интервалы пересекаются
        """
        return start1 < end2 and start2 < end1
    
    def _services_can_run_simultaneously(self, workplace: Workplace, 
                                       service1: Service, service2: Service) -> bool:
        """
        Проверяет, могут ли две услуги выполняться одновременно в рабочем месте.
        
        Args:
            workplace: Рабочее место
            service1: Первая услуга
            service2: Вторая услуга
            
        Returns:
            bool: True если услуги могут выполняться одновременно
        """
        # Получаем все разрешенные комбинации услуг для этого рабочего места
        allowed_services = WorkplaceAllowedServices.objects.filter(
            workplace=workplace,
            is_active=True
        ).values_list('service', flat=True)
        
        # Если обе услуги разрешены в рабочем месте, они могут выполняться одновременно
        # (если нет специальных ограничений)
        return service1.id in allowed_services and service2.id in allowed_services
    
    def _is_preferred_schedule(self, employee: Employee, day_of_week: int) -> bool:
        """
        Проверяет, соответствует ли назначение предпочтениям сотрудника.
        
        Args:
            employee: Сотрудник
            day_of_week: День недели
            
        Returns:
            bool: True если соответствует предпочтениям
        """
        pref = self.availability_checker.get_employee_preferences(employee, day_of_week)
        return pref is not None and pref.is_available
    
    def _generate_summary(self) -> Dict:
        """
        Генерирует сводку планирования.
        
        Returns:
            Dict: Сводка планирования
        """
        total_slots = len(self.assigned_slots)
        preferred_slots = sum(1 for slot in self.assigned_slots if slot.is_preferred)
        conflict_count = len(self.conflicts)
        
        return {
            'total_slots': total_slots,
            'preferred_slots': preferred_slots,
            'preference_satisfaction_rate': (preferred_slots / total_slots * 100) if total_slots > 0 else 0,
            'conflict_count': conflict_count,
            'critical_conflicts': sum(1 for c in self.conflicts if c.severity == 'critical'),
            'high_conflicts': sum(1 for c in self.conflicts if c.severity == 'high'),
        }


class ScheduleOptimizer:
    """
    Сервис для оптимизации расписания.
    
    Основные функции:
    - Оптимизация распределения нагрузки
    - Улучшение удовлетворенности предпочтений
    - Минимизация конфликтов
    """
    
    @staticmethod
    def optimize_schedule(slots: List[ScheduleSlot]) -> List[ScheduleSlot]:
        """
        Оптимизирует расписание.
        
        Args:
            slots: Список слотов для оптимизации
            
        Returns:
            List[ScheduleSlot]: Оптимизированные слоты
        """
        # Здесь можно добавить алгоритмы оптимизации
        # Например, генетические алгоритмы, симуляция отжига и т.д.
        
        # Пока возвращаем исходные слоты
        return slots
