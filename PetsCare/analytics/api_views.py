"""
API views для расширенной аналитики.

Этот модуль содержит API endpoints для:
1. Аналитики роста пользователей
2. Производительности учреждений
3. Трендов выручки
4. Поведенческой аналитики
"""

import logging
from datetime import datetime, timedelta
from django.utils.translation import gettext as _
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncDate, TruncMonth, ExtractHour, ExtractWeekDay

from users.models import User
from providers.models import Provider, Employee
from billing.models import Payment, Invoice
from booking.models import Booking
from users.permissions import IsSystemAdmin

logger = logging.getLogger(__name__)


class UserGrowthAnalyticsAPIView(APIView):
    """
    API для аналитики роста пользователей.
    """
    permission_classes = [IsSystemAdmin]

    def get(self, request):
        """Получает аналитику роста пользователей."""
        try:
            # Параметры фильтрации
            days = int(request.GET.get('days', 30))
            start_date = timezone.now() - timedelta(days=days)
            
            # Общая статистика
            total_users = User.objects.count()
            new_users = User.objects.filter(date_joined__gte=start_date).count()
            active_users = User.objects.filter(last_login__gte=start_date).count()
            
            # Рост по дням
            daily_growth = User.objects.filter(
                date_joined__gte=start_date
            ).annotate(
                date=TruncDate('date_joined')
            ).values('date').annotate(
                count=Count('id')
            ).order_by('date')
            
            # Рост по месяцам
            monthly_growth = User.objects.filter(
                date_joined__gte=start_date
            ).annotate(
                month=TruncMonth('date_joined')
            ).values('month').annotate(
                count=Count('id')
            ).order_by('month')
            
            # Статистика по ролям
            role_stats = User.objects.values('role').annotate(
                count=Count('id')
            ).order_by('-count')
            
            # Статистика по статусу
            status_stats = User.objects.values('is_active').annotate(
                count=Count('id')
            )
            
            # Конверсия (регистрация -> активность)
            registered_users = User.objects.filter(date_joined__gte=start_date).count()
            activated_users = User.objects.filter(
                date_joined__gte=start_date,
                is_active=True
            ).count()
            conversion_rate = (activated_users / registered_users * 100) if registered_users > 0 else 0
            
            return Response({
                'period': {
                    'days': days,
                    'start_date': start_date.isoformat(),
                    'end_date': timezone.now().isoformat()
                },
                'overview': {
                    'total_users': total_users,
                    'new_users': new_users,
                    'active_users': active_users,
                    'conversion_rate': round(conversion_rate, 2)
                },
                'daily_growth': list(daily_growth),
                'monthly_growth': list(monthly_growth),
                'role_stats': list(role_stats),
                'status_stats': list(status_stats)
            })
            
        except Exception as e:
            logger.error(f"Failed to get user growth analytics: {e}")
            return Response(
                {'error': _('Failed to get user growth analytics')},
                status=status.HTTP_400_BAD_REQUEST
            )


class ProviderPerformanceAnalyticsAPIView(APIView):
    """
    API для аналитики производительности учреждений.
    """
    permission_classes = [IsSystemAdmin]

    def get(self, request):
        """Получает аналитику производительности учреждений."""
        try:
            # Параметры фильтрации
            days = int(request.GET.get('days', 30))
            start_date = timezone.now() - timedelta(days=days)
            
            # Общая статистика
            total_providers = Provider.objects.count()
            active_providers = Provider.objects.filter(is_active=True).count()
            new_providers = Provider.objects.filter(created_at__gte=start_date).count()
            
            # Топ учреждений по выручке
            top_providers_revenue = Provider.objects.annotate(
                total_revenue=Sum('invoices__amount')
            ).filter(
                invoices__created_at__gte=start_date
            ).values(
                'id', 'name', 'total_revenue'
            ).order_by('-total_revenue')[:10]
            
            # Топ учреждений по количеству бронирований
            top_providers_bookings = Provider.objects.annotate(
                total_bookings=Count('bookings')
            ).filter(
                bookings__created_at__gte=start_date
            ).values(
                'id', 'name', 'total_bookings'
            ).order_by('-total_bookings')[:10]
            
            # Статистика по рейтингам
            rating_stats = Provider.objects.aggregate(
                avg_rating=Avg('rating'),
                min_rating=Avg('rating'),
                max_rating=Avg('rating')
            )
            
            # Статистика по сотрудникам
            employee_stats = Provider.objects.annotate(
                employee_count=Count('employees')
            ).aggregate(
                avg_employees=Avg('employee_count'),
                max_employees=Avg('employee_count'),
                min_employees=Avg('employee_count')
            )
            
            # Статистика по услугам
            service_stats = Provider.objects.annotate(
                service_count=Count('provider_services')
            ).aggregate(
                avg_services=Avg('service_count'),
                max_services=Avg('service_count'),
                min_services=Avg('service_count')
            )
            
            return Response({
                'period': {
                    'days': days,
                    'start_date': start_date.isoformat(),
                    'end_date': timezone.now().isoformat()
                },
                'overview': {
                    'total_providers': total_providers,
                    'active_providers': active_providers,
                    'new_providers': new_providers,
                    'activation_rate': round((active_providers / total_providers * 100), 2) if total_providers > 0 else 0
                },
                'top_providers_revenue': list(top_providers_revenue),
                'top_providers_bookings': list(top_providers_bookings),
                'rating_stats': rating_stats,
                'employee_stats': employee_stats,
                'service_stats': service_stats
            })
            
        except Exception as e:
            logger.error(f"Failed to get provider performance analytics: {e}")
            return Response(
                {'error': _('Failed to get provider performance analytics')},
                status=status.HTTP_400_BAD_REQUEST
            )


class RevenueTrendsAnalyticsAPIView(APIView):
    """
    API для аналитики трендов выручки.
    """
    permission_classes = [IsSystemAdmin]

    def get(self, request):
        """Получает аналитику трендов выручки."""
        try:
            # Параметры фильтрации
            days = int(request.GET.get('days', 30))
            start_date = timezone.now() - timedelta(days=days)
            
            # Общая выручка
            total_revenue = Payment.objects.filter(
                created_at__gte=start_date,
                status='completed'
            ).aggregate(
                total=Sum('amount')
            )['total'] or 0
            
            # Выручка по дням
            daily_revenue = Payment.objects.filter(
                created_at__gte=start_date,
                status='completed'
            ).annotate(
                date=TruncDate('created_at')
            ).values('date').annotate(
                revenue=Sum('amount')
            ).order_by('date')
            
            # Выручка по месяцам
            monthly_revenue = Payment.objects.filter(
                created_at__gte=start_date,
                status='completed'
            ).annotate(
                month=TruncMonth('created_at')
            ).values('month').annotate(
                revenue=Sum('amount')
            ).order_by('month')
            
            # Статистика по статусам платежей
            payment_status_stats = Payment.objects.filter(
                created_at__gte=start_date
            ).values('status').annotate(
                count=Count('id'),
                total_amount=Sum('amount')
            ).order_by('-total_amount')
            
            # Статистика по типам услуг
            service_revenue_stats = Payment.objects.filter(
                created_at__gte=start_date,
                status='completed'
            ).values(
                'booking__service__name'
            ).annotate(
                count=Count('id'),
                total_amount=Sum('amount')
            ).order_by('-total_amount')[:10]
            
            # Средний чек
            avg_check = Payment.objects.filter(
                created_at__gte=start_date,
                status='completed'
            ).aggregate(
                avg_amount=Avg('amount')
            )['avg_amount'] or 0
            
            # Конверсия платежей
            total_payments = Payment.objects.filter(created_at__gte=start_date).count()
            completed_payments = Payment.objects.filter(
                created_at__gte=start_date,
                status='completed'
            ).count()
            payment_conversion_rate = (completed_payments / total_payments * 100) if total_payments > 0 else 0
            
            return Response({
                'period': {
                    'days': days,
                    'start_date': start_date.isoformat(),
                    'end_date': timezone.now().isoformat()
                },
                'overview': {
                    'total_revenue': float(total_revenue),
                    'avg_check': float(avg_check),
                    'payment_conversion_rate': round(payment_conversion_rate, 2)
                },
                'daily_revenue': list(daily_revenue),
                'monthly_revenue': list(monthly_revenue),
                'payment_status_stats': list(payment_status_stats),
                'service_revenue_stats': list(service_revenue_stats)
            })
            
        except Exception as e:
            logger.error(f"Failed to get revenue trends analytics: {e}")
            return Response(
                {'error': _('Failed to get revenue trends analytics')},
                status=status.HTTP_400_BAD_REQUEST
            )


class BehavioralAnalyticsAPIView(APIView):
    """
    API для поведенческой аналитики.
    """
    permission_classes = [IsSystemAdmin]

    def get(self, request):
        """Получает поведенческую аналитику."""
        try:
            # Параметры фильтрации
            days = int(request.GET.get('days', 30))
            start_date = timezone.now() - timedelta(days=days)
            
            # Статистика сессий
            session_stats = {
                'total_sessions': 0,  # В реальной реализации будет из модели сессий
                'avg_session_duration': 0,
                'bounce_rate': 0
            }
            
            # Статистика поиска
            search_stats = {
                'total_searches': 0,  # В реальной реализации будет из логов поиска
                'popular_queries': [],
                'search_conversion_rate': 0
            }
            
            # Статистика бронирований
            booking_stats = Booking.objects.filter(
                created_at__gte=start_date
            ).aggregate(
                total_bookings=Count('id'),
                completed_bookings=Count('id', filter=Q(status='completed')),
                cancelled_bookings=Count('id', filter=Q(status='cancelled'))
            )
            
            # Конверсия поиск -> бронирование
            if booking_stats['total_bookings'] > 0:
                booking_conversion_rate = (booking_stats['completed_bookings'] / booking_stats['total_bookings']) * 100
            else:
                booking_conversion_rate = 0
            
            # Статистика по времени
            time_stats = Booking.objects.filter(
                created_at__gte=start_date
            ).annotate(
                hour=ExtractHour('created_at')
            ).values('hour').annotate(
                count=Count('id')
            ).order_by('hour')
            
            # Статистика по дням недели
            weekday_stats = Booking.objects.filter(
                created_at__gte=start_date
            ).annotate(
                weekday=ExtractWeekDay('created_at')
            ).values('weekday').annotate(
                count=Count('id')
            ).order_by('weekday')
            
            return Response({
                'period': {
                    'days': days,
                    'start_date': start_date.isoformat(),
                    'end_date': timezone.now().isoformat()
                },
                'session_stats': session_stats,
                'search_stats': search_stats,
                'booking_stats': {
                    **booking_stats,
                    'conversion_rate': round(booking_conversion_rate, 2)
                },
                'time_stats': list(time_stats),
                'weekday_stats': list(weekday_stats)
            })
            
        except Exception as e:
            logger.error(f"Failed to get behavioral analytics: {e}")
            return Response(
                {'error': _('Failed to get behavioral analytics')},
                status=status.HTTP_400_BAD_REQUEST
            ) 