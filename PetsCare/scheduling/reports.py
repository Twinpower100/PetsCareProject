"""
Reports service for the scheduling module.

Этот модуль содержит сервис для генерации расширенных отчетов по планированию.

Основные функции:
1. Отчет по покрытию потребности
2. Отчет по использованию рабочих мест
3. Отчет по непокрытым бронированиям
4. Финансовый отчет
5. Экспорт в Excel
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .models import StaffingRequirement
from providers.models import Provider, Employee, Schedule, LocationSchedule, ProviderLocation
from booking.models import Booking
from catalog.models import Service


class AdvancedReportGenerator:
    """
    Расширенный генератор отчетов.
    
    Основные функции:
    - Детальные отчеты по планированию
    - Анализ эффективности
    - Прогнозирование потребностей
    """
    
    def __init__(self, provider: Provider):
        """
        Инициализирует расширенный генератор отчетов.
        
        Args:
            provider: Учреждение
        """
        self.provider = provider
    
    def generate_comprehensive_report(self, start_date: date, end_date: date,
                                    schedule_result: Dict) -> Dict:
        """
        Генерирует комплексный отчет по планированию.
        
        Args:
            start_date: Дата начала периода
            end_date: Дата окончания периода
            schedule_result: Результат планирования
            
        Returns:
            Dict: Комплексный отчет
        """
        # Базовые отчеты
        coverage_report = self._generate_coverage_report(start_date, end_date, schedule_result)
        efficiency_report = self._generate_efficiency_report(start_date, end_date, schedule_result)
        financial_report = self._generate_financial_report(start_date, end_date, schedule_result)
        
        return {
            'provider': self.provider.name,
            'period': _('{} - {}').format(start_date, end_date),
            'generated_at': timezone.now(),
            'coverage': coverage_report,
            'efficiency': efficiency_report,
            'financial': financial_report,
            'summary': self._generate_summary(coverage_report, efficiency_report, financial_report)
        }
    
    def _generate_coverage_report(self, start_date: date, end_date: date,
                                schedule_result: Dict) -> Dict:
        """
        Генерирует отчет по покрытию потребностей.
        
        Args:
            start_date: Дата начала периода
            end_date: Дата окончания периода
            schedule_result: Результат планирования
            
        Returns:
            Dict: Отчет по покрытию
        """
        # Фильтруем через provider_location или provider (legacy)
        requirements = StaffingRequirement.objects.filter(
            Q(provider_location__provider=self.provider) | Q(provider=self.provider),
            is_active=True
        )
        
        coverage_data = {}
        total_required = 0
        total_assigned = 0
        
        for requirement in requirements:
            service = requirement.service
            required_count = requirement.required_count
            day_of_week = requirement.day_of_week
            
            # Подсчитываем дни в периоде
            period_days = self._count_weekdays_in_period(start_date, end_date, day_of_week)
            total_required_hours = period_days * required_count * 8
            
            # Подсчитываем назначенные часы
            assigned_hours = self._count_assigned_hours_for_service(
                schedule_result, service, start_date, end_date
            )
            
            coverage_data[service.name] = {
                'required_hours': total_required_hours,
                'assigned_hours': assigned_hours,
                'coverage_percentage': (assigned_hours / total_required_hours * 100) if total_required_hours > 0 else 0,
                'period_days': period_days,
                'daily_requirement': required_count
            }
            
            total_required += total_required_hours
            total_assigned += assigned_hours
        
        return {
            'total_required_hours': total_required,
            'total_assigned_hours': total_assigned,
            'overall_coverage_percentage': (total_assigned / total_required * 100) if total_required > 0 else 0,
            'service_coverage': coverage_data
        }
    
    def _generate_efficiency_report(self, start_date: date, end_date: date,
                                  schedule_result: Dict) -> Dict:
        """
        Генерирует отчет по эффективности планирования.
        
        Args:
            start_date: Дата начала периода
            end_date: Дата окончания периода
            schedule_result: Результат планирования
            
        Returns:
            Dict: Отчет по эффективности
        """
        # Анализируем распределение нагрузки
        employee_workload = {}
        workplace_utilization = {}
        
        schedule = schedule_result.get('schedule', {})
        
        for date_str, assignments in schedule.items():
            for assignment in assignments:
                employee = assignment['employee']
                workplace = assignment.get('workplace')
                
                # Подсчитываем нагрузку на сотрудника
                if employee.id not in employee_workload:
                    employee_workload[employee.id] = {
                        'employee': employee,
                        'total_hours': 0,
                        'days_worked': 0,
                        'services': set()
                    }
                
                hours = self._calculate_assignment_hours(assignment)
                employee_workload[employee.id]['total_hours'] += hours
                employee_workload[employee.id]['days_worked'] += 1
                employee_workload[employee.id]['services'].add(assignment['service'].name)
                
                # Подсчитываем использование рабочего места
                if workplace:
                    if workplace.id not in workplace_utilization:
                        workplace_utilization[workplace.id] = {
                            'workplace': workplace,
                            'total_hours': 0,
                            'days_used': 0
                        }
                    
                    workplace_utilization[workplace.id]['total_hours'] += hours
                    workplace_utilization[workplace.id]['days_used'] += 1
        
        return {
            'employee_workload': employee_workload,
            'workplace_utilization': workplace_utilization,
            'average_workload_per_employee': sum(w['total_hours'] for w in employee_workload.values()) / len(employee_workload) if employee_workload else 0,
            'average_workplace_utilization': sum(w['total_hours'] for w in workplace_utilization.values()) / len(workplace_utilization) if workplace_utilization else 0
        }
    
    def _generate_financial_report(self, start_date: date, end_date: date,
                                 schedule_result: Dict) -> Dict:
        """
        Генерирует финансовый отчет.
        
        Args:
            start_date: Дата начала периода
            end_date: Дата окончания периода
            schedule_result: Результат планирования
            
        Returns:
            Dict: Финансовый отчет
        """
        # Подсчитываем потенциальный доход
        potential_revenue = 0
        service_revenue = {}
        
        schedule = schedule_result.get('schedule', {})
        
        for date_str, assignments in schedule.items():
            for assignment in assignments:
                service = assignment['service']
                
                # Получаем цену услуги из первой доступной локации
                try:
                    from providers.models import ProviderLocationService
                    location_service = ProviderLocationService.objects.filter(
                        location__provider=self.provider,
                        location__is_active=True,
                        service=service,
                        is_active=True
                    ).first()
                    price = location_service.price if location_service else 0
                except:
                    price = 0
                
                hours = self._calculate_assignment_hours(assignment)
                revenue = price * (hours / 8)  # Предполагаем 8-часовой рабочий день
                
                potential_revenue += revenue
                
                if service.name not in service_revenue:
                    service_revenue[service.name] = 0
                service_revenue[service.name] += revenue
        
        return {
            'potential_revenue': potential_revenue,
            'service_revenue': service_revenue,
            'average_daily_revenue': potential_revenue / ((end_date - start_date).days + 1) if start_date != end_date else potential_revenue
        }
    
    def generate_uncovered_bookings_report(self, start_date: date, end_date: date) -> Dict:
        """
        Генерирует отчет по непокрытым бронированиям.
        
        Args:
            start_date: Дата начала периода
            end_date: Дата окончания периода
            
        Returns:
            Dict: Отчет по непокрытым бронированиям
        """
        # Получаем бронирования в периоде (через provider_location или provider legacy)
        bookings = Booking.objects.filter(
            Q(provider_location__provider=self.provider) | Q(provider=self.provider),
            start_time__date__gte=start_date,
            start_time__date__lte=end_date,
            status__name__in=['active', 'pending_confirmation']
        )
        
        uncovered_bookings = []
        
        for booking in bookings:
            # Проверяем, есть ли сотрудник для этого бронирования
            if not self._has_available_employee(booking):
                uncovered_bookings.append({
                    'booking_id': booking.id,
                    'service': booking.service.name,
                    'date': booking.start_time.date(),
                    'time': booking.start_time.time(),
                    'reason': _('No available employee')
                })
        
        return {
            'provider': self.provider.name,
            'period': _('{} - {}').format(start_date, end_date),
            'total_bookings': bookings.count(),
            'uncovered_bookings': len(uncovered_bookings),
            'uncovered_details': uncovered_bookings
        }
    
    def generate_workplace_usage_report(self, start_date: date, end_date: date,
                                      schedule_result: Dict) -> Dict:
        """
        Генерирует отчет по использованию рабочих мест.
        
        Args:
            start_date: Дата начала периода
            end_date: Дата окончания периода
            schedule_result: Результат планирования
            
        Returns:
            Dict: Отчет по использованию рабочих мест
        """
        from .models import Workplace
        
        # Фильтруем через provider_location или provider (legacy)
        workplaces = Workplace.objects.filter(
            Q(provider_location__provider=self.provider) | Q(provider=self.provider),
            is_active=True
        )
        
        usage_data = {}
        
        for workplace in workplaces:
            # Подсчитываем использование рабочего места
            usage_hours = self._count_workplace_usage(
                schedule_result, workplace, start_date, end_date
            )
            
            # Подсчитываем общее количество часов в периоде
            total_hours = self._get_total_workplace_hours(
                workplace, start_date, end_date
            )
            
            usage_data[workplace.name] = {
                'usage_hours': usage_hours,
                'total_hours': total_hours,
                'utilization_percentage': (usage_hours / total_hours * 100) if total_hours > 0 else 0
            }
        
        return {
            'provider': self.provider.name,
            'period': _('{} - {}').format(start_date, end_date),
            'workplace_usage': usage_data
        }
    
    def _count_weekdays_in_period(self, start_date: date, end_date: date, 
                                 weekday: int) -> int:
        """
        Подсчитывает количество определенных дней недели в периоде.
        
        Args:
            start_date: Дата начала периода
            end_date: Дата окончания периода
            weekday: День недели (0-6)
            
        Returns:
            int: Количество дней
        """
        count = 0
        current_date = start_date
        
        while current_date <= end_date:
            if current_date.weekday() == weekday:
                count += 1
            current_date += timedelta(days=1)
        
        return count
    
    def _count_assigned_hours_for_service(self, schedule_result: Dict, service: Service,
                                        start_date: date, end_date: date) -> int:
        """
        Подсчитывает назначенные часы для услуги.
        
        Args:
            schedule_result: Результат планирования
            service: Услуга
            start_date: Дата начала периода
            end_date: Дата окончания периода
            
        Returns:
            int: Количество часов
        """
        hours = 0
        schedule = schedule_result.get('schedule', {})
        
        for date_str, assignments in schedule.items():
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            if start_date <= date_obj <= end_date:
                for assignment in assignments:
                    if assignment['service'] == service:
                        hours += self._calculate_assignment_hours(assignment)
        
        return hours
    
    def _calculate_assignment_hours(self, assignment: Dict) -> int:
        """
        Подсчитывает часы назначения.
        
        Args:
            assignment: Назначение
            
        Returns:
            int: Количество часов
        """
        start_time = assignment.get('start_time')
        end_time = assignment.get('end_time')
        
        if start_time and end_time:
            start_dt = datetime.combine(date.today(), start_time)
            end_dt = datetime.combine(date.today(), end_time)
            duration = end_dt - start_dt
            return int(duration.total_seconds() / 3600)
        
        return 8  # По умолчанию 8 часов
    
    def _count_workplace_usage(self, schedule_result: Dict, workplace,
                              start_date: date, end_date: date) -> int:
        """
        Подсчитывает использование рабочего места.
        
        Args:
            schedule_result: Результат планирования
            workplace: Рабочее место
            start_date: Дата начала периода
            end_date: Дата окончания периода
            
        Returns:
            int: Количество часов использования
        """
        hours = 0
        current_date = start_date
        schedule = schedule_result.get('schedule', {})
        
        while current_date <= end_date:
            date_str = current_date.isoformat()
            if date_str in schedule:
                day_assignments = schedule[date_str]
                for assignment in day_assignments:
                    if assignment.get('workplace') == workplace:
                        hours += self._calculate_assignment_hours(assignment)
            
            current_date += timedelta(days=1)
        
        return hours
    
    def _get_total_workplace_hours(self, workplace, start_date: date, end_date: date) -> int:
        """
        Получает общее количество часов работы учреждения.
        Суммирует часы работы всех локаций провайдера.
        
        Args:
            workplace: Рабочее место
            start_date: Дата начала периода
            end_date: Дата окончания периода
            
        Returns:
            int: Общее количество часов
        """
        # Получаем все локации провайдера
        locations = ProviderLocation.objects.filter(provider=self.provider, is_active=True)
        
        if not locations.exists():
            return 0
        
        total_hours = 0
        current_date = start_date
        
        while current_date <= end_date:
            day_of_week = current_date.weekday()
            # Суммируем часы работы всех локаций за этот день
            for location in locations:
                try:
                    schedule = LocationSchedule.objects.get(
                        provider_location=location,
                        weekday=day_of_week
                    )
                    if not schedule.is_closed and schedule.open_time and schedule.close_time:
                        # Подсчитываем часы работы
                        open_dt = datetime.combine(current_date, schedule.open_time)
                        close_dt = datetime.combine(current_date, schedule.close_time)
                        duration = close_dt - open_dt
                        total_hours += duration.total_seconds() / 3600
                except LocationSchedule.DoesNotExist:
                    pass
            
            current_date += timedelta(days=1)
        
        return int(total_hours)
    
    def _has_available_employee(self, booking: Booking) -> bool:
        """
        Проверяет наличие доступного сотрудника для бронирования.
        
        Args:
            booking: Бронирование
            
        Returns:
            bool: True если есть доступный сотрудник
        """
        # Проверяем, есть ли сотрудник, который может оказать эту услугу
        available_employees = Employee.objects.filter(
            providers=self.provider,
            services=booking.service,
            is_active=True
        )
        
        return available_employees.exists()
    
    def _generate_summary(self, coverage_report: Dict, efficiency_report: Dict,
                         financial_report: Dict) -> Dict:
        """
        Генерирует сводку отчетов.
        
        Args:
            coverage_report: Отчет по покрытию
            efficiency_report: Отчет по эффективности
            financial_report: Финансовый отчет
            
        Returns:
            Dict: Сводка
        """
        return {
            'overall_coverage': coverage_report.get('overall_coverage_percentage', 0),
            'average_workload': efficiency_report.get('average_workload_per_employee', 0),
            'potential_revenue': financial_report.get('potential_revenue', 0),
            'recommendations': self._generate_report_recommendations(
                coverage_report, efficiency_report, financial_report
            )
        }
    
    def _generate_report_recommendations(self, coverage_report: Dict,
                                       efficiency_report: Dict,
                                       financial_report: Dict) -> List[str]:
        """
        Генерирует рекомендации на основе отчетов.
        
        Args:
            coverage_report: Отчет по покрытию
            efficiency_report: Отчет по эффективности
            financial_report: Финансовый отчет
            
        Returns:
            List[str]: Список рекомендаций
        """
        recommendations = []
        
        # Рекомендации по покрытию
        coverage = coverage_report.get('overall_coverage_percentage', 0)
        if coverage < 80:
            recommendations.append(
                _('Low coverage rate ({:.1f}%). Consider hiring additional staff or adjusting requirements.')
                .format(coverage)
            )
        elif coverage > 95:
            recommendations.append(
                _('Very high coverage rate ({:.1f}%). Consider reducing staff or increasing service offerings.')
                .format(coverage)
            )
        
        # Рекомендации по нагрузке
        avg_workload = efficiency_report.get('average_workload_per_employee', 0)
        if avg_workload < 30:
            recommendations.append(
                _('Low average workload ({:.1f} hours). Consider reducing staff or increasing service demand.')
                .format(avg_workload)
            )
        elif avg_workload > 45:
            recommendations.append(
                _('High average workload ({:.1f} hours). Consider hiring additional staff to prevent burnout.')
                .format(avg_workload)
            )
        
        # Рекомендации по доходам
        revenue = financial_report.get('potential_revenue', 0)
        if revenue > 0:
            recommendations.append(
                _('Potential revenue: ${:,.2f}. Focus on converting potential to actual bookings.')
                .format(revenue)
            )
        
        return recommendations 