"""Сервисы operational dashboard для provider admin приложения."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from booking.constants import (
    BOOKING_STATUS_ACTIVE,
    BOOKING_STATUS_CANCELLED,
    BOOKING_STATUS_COMPLETED,
    CANCELLATION_REASON_CLIENT_NO_SHOW,
    CANCELLATION_REASON_PROVIDER_EMERGENCY_PREEMPTION,
    ISSUE_STATUS_OPEN,
)
from booking.models import Booking, BookingServiceIssue
from notifications.models import Notification

from .models import EmployeeLocationRole, EmployeeProvider, Provider, ProviderLocation, Schedule
from .permission_service import ProviderPermissionService


@dataclass(frozen=True)
class ProviderDashboardScope:
    """Разрешённый scope dashboard для текущего пользователя."""

    provider: Provider
    scope_type: str
    location_ids: list[int]
    location_names: list[str]
    can_view_financials: bool
    financial_location_ids: list[int]


class ProviderDashboardService:
    """Собирает realtime-агрегаты для dashboard провайдера."""

    @classmethod
    def build_dashboard(cls, *, user, provider_id: int | None = None, alerts_minutes: int = 30) -> dict:
        """Возвращает payload operational dashboard для пользователя."""
        scope = cls.resolve_scope(user=user, provider_id=provider_id)
        now = timezone.localtime(timezone.now())
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timezone.timedelta(days=1)
        month_start = day_start.replace(day=1)
        alerts_cutoff = now - timezone.timedelta(minutes=alerts_minutes)

        day_bookings = cls._get_scoped_bookings(scope=scope).filter(
            start_time__gte=day_start,
            start_time__lt=day_end,
        )

        completed_count = day_bookings.filter(status__name=BOOKING_STATUS_COMPLETED).count()
        total_count = day_bookings.filter(
            status__name__in=(BOOKING_STATUS_ACTIVE, BOOKING_STATUS_COMPLETED),
        ).count()

        displaced_count = day_bookings.filter(
            status__name=BOOKING_STATUS_CANCELLED,
            cancellation_reason__code=CANCELLATION_REASON_PROVIDER_EMERGENCY_PREEMPTION,
        ).count()
        open_disputes_count = BookingServiceIssue.objects.filter(
            booking__in=day_bookings,
            status=ISSUE_STATUS_OPEN,
        ).count()
        late_count = day_bookings.filter(
            status__name=BOOKING_STATUS_ACTIVE,
            start_time__lt=now,
        ).count()

        shift_staff = cls._get_shift_staff_count(scope=scope, now=now)
        busy_staff = cls._get_busy_staff_count(scope=scope, now=now)

        payload = {
            'timestamp': now,
            'scope': {
                'provider_id': scope.provider.id,
                'provider_name': scope.provider.name,
                'scope_type': scope.scope_type,
                'location_ids': scope.location_ids,
                'location_names': scope.location_names,
                'can_view_financials': scope.can_view_financials,
            },
            'appointments': {
                'completed': completed_count,
                'total': total_count,
                'has_overload': cls._has_overload(day_bookings=day_bookings, displaced_count=displaced_count),
            },
            'staff': {
                'total': shift_staff,
                'busy': busy_staff,
                'available': max(shift_staff - busy_staff, 0),
            },
            'incidents': [
                {'code': 'displaced_bookings', 'count': displaced_count},
                {'code': 'open_disputes', 'count': open_disputes_count},
                {'code': 'late_bookings', 'count': late_count},
            ],
            'system_alerts': cls._build_alerts(scope=scope, alerts_cutoff=alerts_cutoff),
        }

        if scope.can_view_financials:
            payload['financials'] = cls._build_financials(
                scope=scope,
                day_start=day_start,
                day_end=day_end,
                month_start=month_start,
                month_end=day_end,
            )

        return payload

    @classmethod
    def resolve_scope(cls, *, user, provider_id: int | None = None) -> ProviderDashboardScope:
        """Определяет доступный scope dashboard с учётом RBAC."""
        candidate_providers = cls._get_candidate_providers(user=user)
        if provider_id is not None:
            provider = candidate_providers.filter(id=provider_id).first()
        else:
            provider = candidate_providers.order_by('name').first()

        if provider is None:
            raise PermissionError(str(_('You do not have access to this provider dashboard.')))

        dashboard_permission = ProviderPermissionService.get_user_permissions(user, provider).get('dashboard')
        if not dashboard_permission or not dashboard_permission.get('can_read'):
            raise PermissionError(str(_('You do not have access to this provider dashboard.')))

        member_location_qs = cls._get_member_locations(user=user, provider=provider)
        managed_location_qs = cls._get_managed_locations(user=user, provider=provider)
        financial_permission = ProviderPermissionService.get_user_permissions(user, provider).get('reports.financial')
        can_view_all_financials = bool(financial_permission and financial_permission.get('can_read') and financial_permission.get('scope') == 'all')

        if dashboard_permission.get('scope') == 'all':
            return ProviderDashboardScope(
                provider=provider,
                scope_type='provider',
                location_ids=[],
                location_names=[],
                can_view_financials=can_view_all_financials,
                financial_location_ids=[],
            )

        member_locations = list(member_location_qs.order_by('name').values_list('id', 'name'))
        managed_location_ids = list(managed_location_qs.order_by('name').values_list('id', flat=True))

        if member_locations:
            return ProviderDashboardScope(
                provider=provider,
                scope_type='location',
                location_ids=[location_id for location_id, _ in member_locations],
                location_names=[name for _, name in member_locations],
                can_view_financials=bool(financial_permission and financial_permission.get('can_read') and managed_location_ids),
                financial_location_ids=managed_location_ids,
            )

        return ProviderDashboardScope(
            provider=provider,
            scope_type='provider',
            location_ids=[],
            location_names=[],
            can_view_financials=False,
            financial_location_ids=[],
        )

    @classmethod
    def _get_candidate_providers(cls, *, user):
        """Возвращает доступные провайдеры для dashboard."""
        if ProviderPermissionService._is_system_like(user):
            return Provider.objects.filter(is_active=True)

        managed_providers = user.get_managed_providers()
        location_providers = Provider.objects.filter(
            locations__in=cls._get_member_locations(user=user),
        )
        candidate_qs = Provider.objects.filter(
            Q(id__in=managed_providers.values('id'))
            | Q(id__in=location_providers.values('id'))
        ).distinct()
        accessible_ids = []
        for provider in candidate_qs.only('id'):
            permission = ProviderPermissionService.get_user_permissions(user, provider).get('dashboard')
            if permission and permission.get('can_read'):
                accessible_ids.append(provider.id)
        return candidate_qs.filter(id__in=accessible_ids)

    @classmethod
    def _get_member_locations(cls, *, user, provider: Provider | None = None):
        """Возвращает локации, к которым пользователь реально привязан."""
        if provider is None:
            queryset = ProviderLocation.objects.filter(is_active=True)
            if ProviderPermissionService._is_system_like(user):
                return queryset
            now = timezone.now()
            return queryset.filter(
                Q(manager=user)
                | (
                    Q(employee_roles__employee__user=user)
                    & Q(employee_roles__employee__is_active=True)
                    & Q(employee_roles__is_active=True)
                    & (Q(employee_roles__end_date__isnull=True) | Q(employee_roles__end_date__gte=now))
                )
            ).distinct()
        return ProviderPermissionService.get_user_member_locations(user, provider)

    @classmethod
    def _get_managed_locations(cls, *, user, provider: Provider | None = None):
        """Возвращает локации, которыми пользователь управляет на уровне филиала."""
        if provider is None:
            queryset = ProviderLocation.objects.filter(is_active=True)
            if ProviderPermissionService._is_system_like(user):
                return queryset
            now = timezone.now()
            return queryset.filter(
                Q(manager=user)
                | (
                    Q(employee_roles__employee__user=user)
                    & Q(employee_roles__employee__is_active=True)
                    & Q(employee_roles__is_active=True)
                    & (Q(employee_roles__end_date__isnull=True) | Q(employee_roles__end_date__gte=now))
                    & Q(employee_roles__role=EmployeeLocationRole.ROLE_BRANCH_MANAGER)
                )
            ).distinct()
        return ProviderPermissionService.get_user_branch_locations(user, provider)

    @classmethod
    def _get_scoped_bookings(cls, *, scope: ProviderDashboardScope):
        """Возвращает bookings в пределах scope."""
        queryset = Booking.objects.filter(
            provider_location__provider=scope.provider,
            provider_location__is_active=True,
        )
        if scope.scope_type == 'location' and scope.location_ids:
            queryset = queryset.filter(provider_location_id__in=scope.location_ids)
        return queryset

    @classmethod
    def _get_financial_bookings(cls, *, scope: ProviderDashboardScope):
        """Возвращает bookings в финансовом scope пользователя."""
        queryset = Booking.objects.filter(
            provider_location__provider=scope.provider,
            provider_location__is_active=True,
        )
        if scope.financial_location_ids:
            queryset = queryset.filter(provider_location_id__in=scope.financial_location_ids)
        return queryset

    @classmethod
    def _get_shift_staff_count(cls, *, scope: ProviderDashboardScope, now) -> int:
        """Считает сотрудников, которые должны работать в текущую минуту."""
        current_time = now.timetz().replace(tzinfo=None)
        today = now.date()
        schedules = Schedule.objects.filter(
            provider_location__provider=scope.provider,
            provider_location__is_active=True,
            day_of_week=now.weekday(),
            is_working=True,
            start_time__lte=current_time,
            end_time__gt=current_time,
            employee__is_active=True,
            employee__employeeprovider_set__provider=scope.provider,
        ).filter(
            Q(employee__employeeprovider_set__end_date__isnull=True)
            | Q(employee__employeeprovider_set__end_date__gte=today)
        )
        if scope.scope_type == 'location' and scope.location_ids:
            schedules = schedules.filter(provider_location_id__in=scope.location_ids)
        return schedules.values('employee_id').distinct().count()

    @classmethod
    def _get_busy_staff_count(cls, *, scope: ProviderDashboardScope, now) -> int:
        """Считает сотрудников с активным визитом в текущую минуту."""
        bookings = cls._get_scoped_bookings(scope=scope).filter(
            status__name=BOOKING_STATUS_ACTIVE,
            start_time__lte=now,
            end_time__gt=now,
        )
        return bookings.values('employee_id').distinct().count()

    @classmethod
    def _has_overload(cls, *, day_bookings, displaced_count: int) -> bool:
        """Проверяет перегруз по экстренным ручным записям."""
        return displaced_count > 0 or day_bookings.filter(
            source=Booking.BookingSource.MANUAL_ENTRY,
            notes__contains='"is_emergency":true',
        ).exists()

    @classmethod
    def _build_financials(cls, *, scope: ProviderDashboardScope, day_start, day_end, month_start, month_end) -> dict:
        """Собирает финансовые KPI в допустимом scope."""
        bookings = cls._get_financial_bookings(scope=scope)
        expected_today = bookings.filter(
            start_time__gte=day_start,
            start_time__lt=day_end,
        ).filter(
            Q(status__name__in=(BOOKING_STATUS_ACTIVE, BOOKING_STATUS_COMPLETED))
            | Q(
                status__name=BOOKING_STATUS_CANCELLED,
                client_attendance='no_show',
            )
            | Q(
                status__name=BOOKING_STATUS_CANCELLED,
                cancellation_reason__code=CANCELLATION_REASON_CLIENT_NO_SHOW,
            )
        ).aggregate(
            total=Coalesce(Sum('price'), Value(Decimal('0.00'))),
        )['total']

        month_actual = bookings.filter(
            status__name=BOOKING_STATUS_COMPLETED,
            completed_at__gte=month_start,
            completed_at__lt=month_end,
        ).aggregate(
            total=Coalesce(Sum('price'), Value(Decimal('0.00'))),
        )['total']

        currency = getattr(scope.provider.invoice_currency, 'code', None) if getattr(scope.provider, 'invoice_currency', None) else None

        return {
            'expected_revenue_today': expected_today,
            'month_actual_revenue': month_actual,
            'currency_code': currency,
        }

    @classmethod
    def _build_alerts(cls, *, scope: ProviderDashboardScope, alerts_cutoff) -> list[dict]:
        """Собирает последние события dashboard."""
        alerts: list[dict] = []

        booking_events = cls._get_scoped_bookings(scope=scope).filter(
            created_at__gte=alerts_cutoff,
        ).select_related('pet', 'service', 'provider_location').order_by('-created_at')[:10]
        for booking in booking_events:
            alerts.append(
                {
                    'id': f'booking-{booking.id}',
                    'event_type': 'booking_created',
                    'severity': 'warning' if booking.source == Booking.BookingSource.MANUAL_ENTRY else 'success',
                    'created_at': booking.created_at,
                    'booking_id': booking.id,
                    'booking_code': booking.code,
                    'pet_name': booking.pet.name if booking.pet_id else None,
                    'service_name': booking.service.name if booking.service_id else None,
                    'location_name': booking.provider_location.name if booking.provider_location_id else None,
                    'source': booking.source,
                }
            )

        cancellation_events = cls._get_scoped_bookings(scope=scope).filter(
            cancelled_at__gte=alerts_cutoff,
            cancelled_by='client',
        ).select_related('pet', 'service', 'provider_location').order_by('-cancelled_at')[:10]
        for booking in cancellation_events:
            alerts.append(
                {
                    'id': f'cancellation-{booking.id}',
                    'event_type': 'cancellation_request',
                    'severity': 'warning',
                    'created_at': booking.cancelled_at,
                    'booking_id': booking.id,
                    'booking_code': booking.code,
                    'pet_name': booking.pet.name if booking.pet_id else None,
                    'service_name': booking.service.name if booking.service_id else None,
                    'location_name': booking.provider_location.name if booking.provider_location_id else None,
                    'cancelled_by': booking.cancelled_by,
                }
            )

        system_notifications = Notification.objects.filter(
            notification_type='system',
            created_at__gte=alerts_cutoff,
            user_id__in=cls._get_alert_recipient_ids(scope=scope),
        ).order_by('-created_at')[:10]
        for notification in system_notifications:
            alerts.append(
                {
                    'id': f'system-{notification.id}',
                    'event_type': 'system',
                    'severity': 'error' if notification.priority == 'high' else 'warning',
                    'created_at': notification.created_at,
                    'title': notification.title,
                    'message': notification.message,
                }
            )

        alerts.sort(key=lambda item: item['created_at'], reverse=True)
        return alerts[:20]

    @classmethod
    def _get_alert_recipient_ids(cls, *, scope: ProviderDashboardScope) -> list[int]:
        """Возвращает пользователей, чьи system notifications релевантны текущему scope."""
        user_ids = set(
            EmployeeProvider.get_active_admin_links(scope.provider).values_list(
                'employee__user_id',
                flat=True,
            )
        )
        if scope.scope_type == 'location' and scope.location_ids:
            user_ids.update(
                ProviderLocation.objects.filter(id__in=scope.location_ids).exclude(
                    manager_id__isnull=True,
                ).values_list('manager_id', flat=True)
            )
        return list(user_ids)
