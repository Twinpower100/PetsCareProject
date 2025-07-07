"""
Сервисы для генерации отчетов PetCare.

Этот модуль содержит сервисы для:
1. Отчетов по доходам через систему бронирования
2. Отчетов по загруженности сотрудников
3. Отчетов по дебиторской задолженности
4. Отчетов по активности учреждений
5. Отчетов по платежам
6. Отчетов по отменам бронирований
"""

from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional
from booking.models import Booking, BookingStatus, BookingCancellation
from billing.models import Contract, Payment, Invoice, BillingManagerProvider
from providers.models import Provider, Employee
from users.models import User


class ReportService:
    """Базовый класс для сервисов отчетов."""
    
    def __init__(self, user: User):
        self.user = user
    
    def get_provider_filter(self, providers: Optional[List[Provider]] = None) -> Q:
        """Возвращает фильтр по провайдерам в зависимости от роли пользователя."""
        if providers:
            return Q(provider__in=providers)
        
        if self.user.has_role('system_admin'):
            return Q()  # Все провайдеры
        
        if self.user.has_role('provider_admin'):
            # Получаем провайдеров, которыми управляет пользователь
            managed_providers = Provider.objects.filter(
                employee_providers__employee__user=self.user,
                employee_providers__is_manager=True
            )
            return Q(provider__in=managed_providers)
        
        if self.user.has_role('billing_manager'):
            # Получаем провайдеров, которыми управляет биллинг-менеджер
            managed_providers = Provider.objects.filter(
                billing_managers__billing_manager=self.user,
                billing_managers__status='active'
            )
            return Q(provider__in=managed_providers)
        
        return Q(provider__isnull=True)  # Пустой фильтр


class IncomeReportService(ReportService):
    """Сервис для генерации отчетов по доходам."""
    
    def generate_income_report(
        self, 
        start_date: datetime, 
        end_date: datetime, 
        providers: Optional[List[Provider]] = None
    ) -> Dict[str, Any]:
        """
        Генерирует отчет по доходам через систему бронирования.
        
        Args:
            start_date: Начальная дата периода
            end_date: Конечная дата периода
            providers: Список провайдеров для фильтрации
            
        Returns:
            Словарь с данными отчета
        """
        provider_filter = self.get_provider_filter(providers)
        
        # Получаем завершенные бронирования за период
        bookings = Booking.objects.filter(
            provider_filter,
            status__name='completed',
            start_time__range=(start_date, end_date)
        ).select_related('provider', 'service', 'employee')
        
        # Общая статистика
        total_income = bookings.aggregate(total=Sum('price'))['total'] or Decimal('0')
        total_bookings = bookings.count()
        
        # Статистика по провайдерам
        provider_stats = bookings.values('provider__name').annotate(
            income=Sum('price'),
            bookings_count=Count('id')
        ).order_by('-income')
        
        # Статистика по услугам
        service_stats = bookings.values('service__name').annotate(
            income=Sum('price'),
            bookings_count=Count('id')
        ).order_by('-income')
        
        # Статистика по месяцам
        monthly_stats = bookings.extra(
            select={'month': "EXTRACT(month FROM start_time)"}
        ).values('month').annotate(
            income=Sum('price'),
            bookings_count=Count('id')
        ).order_by('month')
        
        # Расчет комиссий
        commission_data = self._calculate_commissions(bookings)
        
        return {
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'summary': {
                'total_income': total_income,
                'total_bookings': total_bookings,
                'total_commission': commission_data['total_commission'],
                'average_booking_value': total_income / total_bookings if total_bookings > 0 else Decimal('0')
            },
            'by_provider': list(provider_stats),
            'by_service': list(service_stats),
            'by_month': list(monthly_stats),
            'commission_details': commission_data['details']
        }
    
    def _calculate_commissions(self, bookings) -> Dict[str, Any]:
        """Рассчитывает комиссии по бронированиям."""
        total_commission = Decimal('0')
        commission_details = []
        
        for booking in bookings:
            # Получаем активный договор для провайдера
            contract = Contract.objects.filter(
                provider=booking.provider,
                status='active',
                start_date__lte=booking.start_time.date(),
                end_date__gte=booking.start_time.date()
            ).first()
            
            if contract:
                # Получаем комиссию для услуги
                commission = contract.commissions.filter(
                    service=booking.service,
                    is_active=True,
                    start_date__lte=booking.start_time.date(),
                    end_date__gte=booking.start_time.date()
                ).first()
                
                if commission:
                    commission_amount = booking.price * (commission.rate / 100)
                    if commission.fixed_amount:
                        commission_amount = commission.fixed_amount
                    
                    total_commission += commission_amount
                    commission_details.append({
                        'booking_id': booking.id,
                        'provider': booking.provider.name,
                        'service': booking.service.name,
                        'booking_amount': booking.price,
                        'commission_rate': commission.rate,
                        'commission_amount': commission_amount
                    })
        
        return {
            'total_commission': total_commission,
            'details': commission_details
        }


class EmployeeWorkloadReportService(ReportService):
    """Сервис для генерации отчетов по загруженности сотрудников."""
    
    def generate_workload_report(
        self, 
        start_date: datetime, 
        end_date: datetime, 
        providers: Optional[List[Provider]] = None
    ) -> Dict[str, Any]:
        """
        Генерирует отчет по загруженности сотрудников.
        
        Args:
            start_date: Начальная дата периода
            end_date: Конечная дата периода
            providers: Список провайдеров для фильтрации
            
        Returns:
            Словарь с данными отчета
        """
        provider_filter = self.get_provider_filter(providers)
        
        # Получаем завершенные бронирования за период
        bookings = Booking.objects.filter(
            provider_filter,
            status__name='completed',
            start_time__range=(start_date, end_date)
        ).select_related('employee', 'provider', 'service')
        
        # Статистика по сотрудникам
        employee_stats = bookings.values(
            'employee__user__first_name',
            'employee__user__last_name',
            'employee__user__email',
            'provider__name'
        ).annotate(
            total_hours=Sum(
                (timezone.template_localtime('end_time') - timezone.template_localtime('start_time')).total_seconds() / 3600
            ),
            bookings_count=Count('id'),
            total_income=Sum('price')
        ).order_by('-total_hours')
        
        # Статистика по провайдерам
        provider_stats = bookings.values('provider__name').annotate(
            total_hours=Sum(
                (timezone.template_localtime('end_time') - timezone.template_localtime('start_time')).total_seconds() / 3600
            ),
            bookings_count=Count('id'),
            employee_count=Count('employee', distinct=True)
        ).order_by('-total_hours')
        
        # Эффективность (средний доход в час)
        for stat in employee_stats:
            if stat['total_hours'] and stat['total_hours'] > 0:
                stat['efficiency'] = stat['total_income'] / stat['total_hours']
            else:
                stat['efficiency'] = Decimal('0')
        
        return {
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'summary': {
                'total_hours': sum(stat['total_hours'] or 0 for stat in employee_stats),
                'total_bookings': sum(stat['bookings_count'] for stat in employee_stats),
                'total_employees': len(employee_stats),
                'average_efficiency': sum(stat['efficiency'] for stat in employee_stats) / len(employee_stats) if employee_stats else Decimal('0')
            },
            'by_employee': list(employee_stats),
            'by_provider': list(provider_stats)
        }


class DebtReportService(ReportService):
    """Сервис для генерации отчетов по дебиторской задолженности."""
    
    def generate_debt_report(
        self, 
        start_date: datetime, 
        end_date: datetime, 
        providers: Optional[List[Provider]] = None
    ) -> Dict[str, Any]:
        """
        Генерирует отчет по дебиторской задолженности.
        
        Args:
            start_date: Начальная дата периода
            end_date: Конечная дата периода
            providers: Список провайдеров для фильтрации
            
        Returns:
            Словарь с данными отчета
        """
        provider_filter = self.get_provider_filter(providers)
        
        # Получаем провайдеров с задолженностью
        providers_with_debt = Provider.objects.filter(provider_filter)
        
        debt_data = []
        total_debt = Decimal('0')
        
        for provider in providers_with_debt:
            # Получаем активный договор
            contract = Contract.objects.filter(
                provider=provider,
                status='active'
            ).first()
            
            if contract:
                # Рассчитываем задолженность
                debt_info = contract.calculate_debt(start_date.date(), end_date.date())
                
                if debt_info['total_debt'] > 0:
                    # Получаем историю платежей
                    payment_history = contract.payment_history.filter(
                        due_date__range=(start_date.date(), end_date.date())
                    ).order_by('-due_date')
                    
                    # Рассчитываем количество дней просрочки
                    overdue_days = 0
                    if debt_info['total_debt'] > 0:
                        latest_payment = payment_history.filter(status='paid').first()
                        if latest_payment:
                            overdue_days = (timezone.now().date() - latest_payment.payment_date).days
                        else:
                            overdue_days = (timezone.now().date() - start_date.date()).days
                    
                    debt_data.append({
                        'provider_name': provider.name,
                        'provider_id': provider.id,
                        'total_debt': debt_info['total_debt'],
                        'overdue_days': max(0, overdue_days),
                        'payment_history': list(payment_history.values(
                            'amount', 'due_date', 'payment_date', 'status'
                        )),
                        'contract_number': contract.number,
                        'contract_status': contract.status
                    })
                    
                    total_debt += debt_info['total_debt']
        
        # Сортируем по размеру задолженности
        debt_data.sort(key=lambda x: x['total_debt'], reverse=True)
        
        return {
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'summary': {
                'total_debt': total_debt,
                'providers_with_debt': len(debt_data),
                'average_debt': total_debt / len(debt_data) if debt_data else Decimal('0')
            },
            'providers': debt_data
        }


class ActivityReportService(ReportService):
    """Сервис для генерации отчетов по активности учреждений."""
    
    def generate_activity_report(
        self, 
        start_date: datetime, 
        end_date: datetime, 
        providers: Optional[List[Provider]] = None
    ) -> Dict[str, Any]:
        """
        Генерирует отчет по активности учреждений.
        
        Args:
            start_date: Начальная дата периода
            end_date: Конечная дата периода
            providers: Список провайдеров для фильтрации
            
        Returns:
            Словарь с данными отчета
        """
        provider_filter = self.get_provider_filter(providers)
        
        # Получаем все бронирования за период
        bookings = Booking.objects.filter(
            provider_filter,
            start_time__range=(start_date, end_date)
        ).select_related('provider', 'service')
        
        # Статистика по учреждениям
        provider_activity = bookings.values('provider__name').annotate(
            total_bookings=Count('id'),
            completed_bookings=Count('id', filter=Q(status__name='completed')),
            cancelled_bookings=Count('id', filter=Q(status__name__startswith='cancelled')),
            total_income=Sum('price', filter=Q(status__name='completed')),
            unique_services=Count('service', distinct=True),
            unique_customers=Count('user', distinct=True)
        ).order_by('-total_bookings')
        
        # Статистика по услугам
        service_activity = bookings.values('service__name').annotate(
            total_bookings=Count('id'),
            completed_bookings=Count('id', filter=Q(status__name='completed')),
            total_income=Sum('price', filter=Q(status__name='completed'))
        ).order_by('-total_bookings')
        
        # Статистика по дням недели
        daily_activity = bookings.extra(
            select={'day_of_week': "EXTRACT(dow FROM start_time)"}
        ).values('day_of_week').annotate(
            total_bookings=Count('id'),
            completed_bookings=Count('id', filter=Q(status__name='completed'))
        ).order_by('day_of_week')
        
        return {
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'summary': {
                'total_providers': len(provider_activity),
                'total_bookings': sum(stat['total_bookings'] for stat in provider_activity),
                'total_income': sum(stat['total_income'] or 0 for stat in provider_activity),
                'completion_rate': sum(stat['completed_bookings'] for stat in provider_activity) / 
                                 sum(stat['total_bookings'] for stat in provider_activity) * 100 if provider_activity else 0
            },
            'by_provider': list(provider_activity),
            'by_service': list(service_activity),
            'by_day': list(daily_activity)
        }


class PaymentReportService(ReportService):
    """Сервис для генерации отчетов по платежам."""
    
    def generate_payment_report(
        self, 
        start_date: datetime, 
        end_date: datetime, 
        providers: Optional[List[Provider]] = None
    ) -> Dict[str, Any]:
        """
        Генерирует отчет по платежам.
        
        Args:
            start_date: Начальная дата периода
            end_date: Конечная дата периода
            providers: Список провайдеров для фильтрации
            
        Returns:
            Словарь с данными отчета
        """
        provider_filter = self.get_provider_filter(providers)
        
        # Получаем платежи за период
        payments = Payment.objects.filter(
            booking__provider__in=Provider.objects.filter(provider_filter),
            created_at__range=(start_date, end_date)
        ).select_related('booking__provider', 'booking__service')
        
        # Получаем счета за период
        invoices = Invoice.objects.filter(
            provider_filter,
            issued_at__range=(start_date, end_date)
        ).select_related('provider', 'currency')
        
        # Статистика по платежам
        payment_stats = payments.values('payment_method').annotate(
            total_amount=Sum('amount'),
            payment_count=Count('id'),
            successful_payments=Count('id', filter=Q(status='completed'))
        ).order_by('-total_amount')
        
        # Статистика по провайдерам
        provider_payment_stats = payments.values('booking__provider__name').annotate(
            total_received=Sum('amount', filter=Q(status='completed')),
            total_expected=Sum('amount'),
            payment_count=Count('id'),
            success_rate=Count('id', filter=Q(status='completed')) * 100.0 / Count('id')
        ).order_by('-total_received')
        
        # Просроченные платежи
        overdue_payments = self._get_overdue_payments(providers)
        
        # Ожидаемые платежи
        expected_payments = self._get_expected_payments(start_date, end_date, providers)
        
        return {
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'summary': {
                'total_received': sum(stat['total_received'] or 0 for stat in provider_payment_stats),
                'total_expected': sum(stat['total_expected'] or 0 for stat in provider_payment_stats),
                'total_payments': sum(stat['payment_count'] for stat in payment_stats),
                'success_rate': sum(stat['successful_payments'] for stat in payment_stats) / 
                               sum(stat['payment_count'] for stat in payment_stats) * 100 if payment_stats else 0
            },
            'by_payment_method': list(payment_stats),
            'by_provider': list(provider_payment_stats),
            'overdue_payments': overdue_payments,
            'expected_payments': expected_payments
        }
    
    def _get_overdue_payments(self, providers: Optional[List[Provider]] = None) -> List[Dict]:
        """Получает список просроченных платежей."""
        provider_filter = self.get_provider_filter(providers)
        
        overdue_payments = []
        
        # Получаем просроченные счета
        overdue_invoices = Invoice.objects.filter(
            provider_filter,
            status='overdue'
        ).select_related('provider', 'currency')
        
        for invoice in overdue_invoices:
            overdue_days = (timezone.now().date() - invoice.issued_at.date()).days
            overdue_payments.append({
                'invoice_number': invoice.number,
                'provider_name': invoice.provider.name if invoice.provider else '',
                'amount': invoice.amount,
                'currency': invoice.currency.code if invoice.currency else '',
                'issued_at': invoice.issued_at,
                'overdue_days': overdue_days
            })
        
        return sorted(overdue_payments, key=lambda x: x['overdue_days'], reverse=True)
    
    def _get_expected_payments(self, start_date: datetime, end_date: datetime, providers: Optional[List[Provider]] = None) -> List[Dict]:
        """Получает список ожидаемых платежей."""
        provider_filter = self.get_provider_filter(providers)
        
        expected_payments = []
        
        # Получаем ожидаемые платежи по договорам
        contracts = Contract.objects.filter(
            provider_filter,
            status='active'
        )
        
        for contract in contracts:
            payment_schedule = contract.get_payment_schedule(start_date.date(), end_date.date())
            for payment in payment_schedule:
                if payment['status'] == 'pending':
                    expected_payments.append({
                        'contract_number': contract.number,
                        'provider_name': contract.provider.name,
                        'amount': payment['amount'],
                        'due_date': payment['due_date'],
                        'description': payment.get('description', '')
                    })
        
        return sorted(expected_payments, key=lambda x: x['due_date'])


class CancellationReportService(ReportService):
    """Сервис для генерации отчетов по отменам бронирований."""
    
    def generate_cancellation_report(
        self, 
        start_date: datetime, 
        end_date: datetime, 
        providers: Optional[List[Provider]] = None
    ) -> Dict[str, Any]:
        """
        Генерирует отчет по отменам бронирований.
        
        Args:
            start_date: Начальная дата периода
            end_date: Конечная дата периода
            providers: Список провайдеров для фильтрации
            
        Returns:
            Словарь с данными отчета
        """
        provider_filter = self.get_provider_filter(providers)
        
        # Получаем отмены за период
        cancellations = BookingCancellation.objects.filter(
            booking__provider__in=Provider.objects.filter(provider_filter),
            created_at__range=(start_date, end_date)
        ).select_related('booking__provider', 'booking__service', 'cancelled_by')
        
        # Статистика по провайдерам
        provider_cancellation_stats = cancellations.values('booking__provider__name').annotate(
            total_cancellations=Count('id'),
            client_cancellations=Count('id', filter=Q(cancelled_by__roles__name='pet_owner')),
            provider_cancellations=Count('id', filter=Q(cancelled_by__roles__name='employee')),
            abuse_cancellations=Count('id', filter=Q(is_abuse=True))
        ).order_by('-total_cancellations')
        
        # Статистика по причинам
        reason_stats = cancellations.values('reason').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Статистика по месяцам
        monthly_stats = cancellations.extra(
            select={'month': "EXTRACT(month FROM created_at)"}
        ).values('month').annotate(
            total_cancellations=Count('id'),
            client_cancellations=Count('id', filter=Q(cancelled_by__roles__name='pet_owner')),
            provider_cancellations=Count('id', filter=Q(cancelled_by__roles__name='employee'))
        ).order_by('month')
        
        # Детализация отмен
        cancellation_details = []
        for cancellation in cancellations:
            cancellation_details.append({
                'booking_id': cancellation.booking.id,
                'provider_name': cancellation.booking.provider.name,
                'service_name': cancellation.booking.service.name,
                'cancelled_by': f"{cancellation.cancelled_by.first_name} {cancellation.cancelled_by.last_name}",
                'reason': cancellation.reason,
                'is_abuse': cancellation.is_abuse,
                'created_at': cancellation.created_at
            })
        
        return {
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'summary': {
                'total_cancellations': len(cancellations),
                'client_cancellations': sum(stat['client_cancellations'] for stat in provider_cancellation_stats),
                'provider_cancellations': sum(stat['provider_cancellations'] for stat in provider_cancellation_stats),
                'abuse_cancellations': sum(stat['abuse_cancellations'] for stat in provider_cancellation_stats)
            },
            'by_provider': list(provider_cancellation_stats),
            'by_reason': list(reason_stats),
            'by_month': list(monthly_stats),
            'details': cancellation_details
        } 