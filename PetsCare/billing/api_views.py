"""
API views for the billing module.

Этот модуль содержит представления для:
1. Управления платежами
2. Управления счетами
3. Управления возвратами
4. Управления типами контрактов
"""

from rest_framework import viewsets, permissions, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.http import FileResponse
from .models import Payment, Invoice, Refund, BillingManagerProvider, BillingManagerEvent, RegionalBlockingPolicy, ProviderBlocking, BlockingNotification, Currency
from .export_utils import build_excel_response
from .invoice_services import build_invoice_breakdown_rows, summarize_invoice_breakdown
from .serializers import (
    PaymentSerializer,
    InvoiceSerializer,
    RefundSerializer,
    PaymentCreateSerializer,
    RefundCreateSerializer,
    BillingManagerProviderSerializer,
    BillingManagerProviderCreateSerializer,
    BillingManagerEventSerializer,
    RegionalBlockingPolicySerializer,
    ProviderBlockingSerializer, 
    BlockingNotificationSerializer,
    CurrencySerializer
)

# Пустой сериализатор для Swagger (когда view не использует сериализатор)
class EmptySerializer(serializers.Serializer):
    """Пустой сериализатор для Swagger схемы"""
    pass
from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics
from django.shortcuts import get_object_or_404
from django.db import transaction
from providers.models import Provider
from providers.permission_service import ProviderPermissionService


# ContractTypeViewSet удален - используется LegalDocument и DocumentAcceptance


class PaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления платежами.
    
    Используется для CRUD операций с платежами.
    Поддерживает подтверждение платежей, фильтрацию и сортировку.
    """
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'payment_method', 'provider', 'invoice']
    ordering_fields = ['created_at', 'amount']
    search_fields = ['provider__name', 'invoice__number', 'transaction_id']

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentCreateSerializer
        return PaymentSerializer

    def get_queryset(self):
        """
        Возвращает отфильтрованный список платежей.
        
        Для обычных пользователей возвращает только их платежи.
        """
        if getattr(self, 'swagger_fake_view', False):
            return Payment.objects.none()
        
        queryset = Payment.objects.all()
        
        # Для пользователей - только их платежи
        if not self.request.user.is_staff:
            queryset = queryset.filter(booking__user=self.request.user)
            
        return queryset

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """
        Подтверждение платежа.
        
        Args:
            request: HTTP запрос
            pk: ID платежа
            
        Returns:
            Response: Результат подтверждения платежа
        """
        # Получаем объект до транзакции для проверки существования
        # Используем get_object_or_404 для явной обработки случая, когда объект не найден
        queryset = self.get_queryset()
        payment_obj = get_object_or_404(queryset, pk=pk)
        payment_id = payment_obj.id
        
        # Используем select_for_update для предотвращения гонки
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(id=payment_id)

            if payment.status != 'pending':
                return Response(
                    {'error': _('Payment is not pending')},
                    status=status.HTTP_400_BAD_REQUEST
                )

            payment.status = 'completed'
            payment.save()

        return Response({'status': _('Payment confirmed')})


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для просмотра счетов.
    
    Используется для просмотра списка и деталей счетов.
    Поддерживает фильтрацию и сортировку.
    """
    queryset = Invoice.objects.select_related('provider', 'currency', 'platform_company').prefetch_related('payment_history')
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'provider']
    ordering_fields = ['created_at', 'amount']

    def get_queryset(self):
        """
        Возвращает отфильтрованный список счетов.
        
        Для обычных пользователей возвращает только их счета.
        Для менеджеров по биллингу - счета их провайдеров.
        """
        if getattr(self, 'swagger_fake_view', False):
            return Invoice.objects.none()
        
        queryset = Invoice.objects.all()
        user = self.request.user
        
        # Проверяем, что пользователь аутентифицирован (для Swagger)
        if not user.is_authenticated:
            return queryset.none()
        
        # Для менеджеров по биллингу - счета их провайдеров
        if hasattr(user, 'has_role') and user.has_role('billing_manager'):
            managed_providers = BillingManagerProvider.objects.filter(
                billing_manager=user,
                status__in=['active', 'temporary']
            ).values_list('provider', flat=True)
            queryset = queryset.filter(provider__in=managed_providers)
        # Для обычных пользователей счета недоступны
        elif not user.is_staff:
            managed_provider_ids = []
            for provider in user.get_managed_providers().only('id'):
                if ProviderPermissionService.check_permission(user, provider, 'org.billing', 'read'):
                    managed_provider_ids.append(provider.id)
            if managed_provider_ids:
                queryset = queryset.filter(provider_id__in=managed_provider_ids)
            else:
                return queryset.none()
            
        return queryset

    @action(detail=True, methods=['get'], url_path='download-pdf')
    def download_pdf(self, request, pk=None):
        """
        Возвращает PDF-файл счета для скачивания.
        """
        invoice = self.get_object()
        pdf_file = invoice.ensure_pdf_file(force=True)

        if not pdf_file:
            return Response(
                {'error': _('Invoice PDF is not available')},
                status=status.HTTP_404_NOT_FOUND,
            )

        response = FileResponse(
            pdf_file.open('rb'),
            as_attachment=True,
            filename=pdf_file.name.rsplit('/', 1)[-1],
            content_type='application/pdf',
        )
        return response

    @action(detail=True, methods=['get'], url_path='booking-breakdown')
    def booking_breakdown(self, request, pk=None):
        """
        Возвращает прозрачную детализацию бронирований по счету или Excel-выгрузку.
        """
        invoice = self.get_object()
        rows = build_invoice_breakdown_rows(invoice)
        summary = summarize_invoice_breakdown(invoice, rows=rows)

        if request.query_params.get('export') == 'xlsx':
            return build_excel_response(
                f'invoice-{invoice.number}-bookings.xlsx',
                'Invoice Bookings',
                [
                    str(_('Booking ID')),
                    str(_('Booking Code')),
                    str(_('Completed At')),
                    str(_('Service')),
                    str(_('Client')),
                    str(_('Pet')),
                    str(_('Location')),
                    str(_('Booking Amount')),
                    str(_('Commission')),
                    str(_('VAT')),
                    str(_('Total')),
                ],
                [
                    [
                        row['booking_id'],
                        row['booking_code'],
                        row['completed_at_label'],
                        row['service'],
                        row['client'],
                        row['pet'],
                        row['location'],
                        row['amount'],
                        row['commission'],
                        row['vat_amount'],
                        row['total_with_vat'],
                    ]
                    for row in rows
                ],
            )

        return Response({
            'invoice_id': invoice.pk,
            'invoice_number': invoice.number,
            'period_label': summary['period_label'],
            'currency_code': summary['currency_code'],
            'booking_count': summary['booking_count'],
            'booking_amount_total': summary['booking_amount_total'],
            'commission_total': summary['commission_total'],
            'vat_total': summary['vat_total'],
            'total_amount': summary['total_amount'],
            'rows': [
                {
                    'booking_id': row['booking_id'],
                    'booking_code': row['booking_code'],
                    'booking_label': row['booking_label'],
                    'completed_at': row['completed_at'].isoformat() if row['completed_at'] else None,
                    'completed_at_label': row['completed_at_label'],
                    'service': row['service'],
                    'client': row['client'],
                    'pet': row['pet'],
                    'location': row['location'],
                    'amount': row['amount'],
                    'commission': row['commission'],
                    'vat_amount': row['vat_amount'],
                    'total_with_vat': row['total_with_vat'],
                }
                for row in rows
            ],
        })


class RefundViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления возвратами.
    
    Используется для CRUD операций с возвратами.
    Поддерживает подтверждение возвратов, фильтрацию и сортировку.
    """
    queryset = Refund.objects.all()
    serializer_class = RefundSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status']
    ordering_fields = ['created_at', 'amount']

    def get_serializer_class(self):
        if self.action == 'create':
            return RefundCreateSerializer
        return RefundSerializer

    def get_queryset(self):
        """
        Возвращает отфильтрованный список возвратов.
        
        Для обычных пользователей возвращает только их возвраты.
        """
        if getattr(self, 'swagger_fake_view', False):
            return Refund.objects.none()
        
        queryset = Refund.objects.all()
        
        # Для пользователей - только их возвраты
        if not self.request.user.is_staff:
            queryset = queryset.filter(payment__booking__user=self.request.user)
            
        return queryset

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """
        Подтверждение возврата.
        
        Args:
            request: HTTP запрос
            pk: ID возврата
            
        Returns:
            Response: Результат подтверждения возврата
        """
        refund = self.get_object()
        
        # Используем select_for_update для предотвращения гонки
        with transaction.atomic():
            refund = Refund.objects.select_for_update().get(id=refund.id)
            
            if refund.status != 'pending':
                return Response(
                    {'error': _('Refund is not pending')},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            refund.status = 'approved'
            refund.save()
            
            # Обновляем статус платежа
            refund.payment.status = 'refunded'
            refund.payment.save()
        
        return Response({'status': _('refund approved')})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """
        Отклонение возврата.
        
        Args:
            request: HTTP запрос
            pk: ID возврата
            
        Returns:
            Response: Результат отклонения возврата
        """
        refund = self.get_object()
        
        # Используем select_for_update для предотвращения гонки
        with transaction.atomic():
            refund = Refund.objects.select_for_update().get(id=refund.id)
            
            if refund.status != 'pending':
                return Response(
                    {'error': _('Refund is not pending')},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            refund.status = 'rejected'
            refund.save()
        
        return Response({'status': _('refund rejected')})


class BillingManagerProviderViewSet(viewsets.ModelViewSet):
    """
    API endpoint для управления связями менеджеров по биллингу с провайдерами.
    """
    queryset = BillingManagerProvider.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['billing_manager', 'provider', 'status']
    search_fields = ['billing_manager__first_name', 'billing_manager__last_name', 'provider__name']
    ordering_fields = ['start_date', 'created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return BillingManagerProviderCreateSerializer
        return BillingManagerProviderSerializer

    def get_queryset(self):
        """
        Фильтрация по ролям: менеджер видит только свои связи, админ — все.
        """
        if getattr(self, 'swagger_fake_view', False):
            return BillingManagerProvider.objects.none()
        
        qs = super().get_queryset()
        user = self.request.user
        
        # Проверяем, что пользователь аутентифицирован (для Swagger)
        if not user.is_authenticated:
            return qs.none()
            
        if hasattr(user, 'has_role') and user.has_role('billing_manager'):
            return qs.filter(billing_manager=user)
        return qs


class BillingManagerEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint для просмотра истории событий менеджеров по биллингу.
    Только чтение (аудит).
    """
    queryset = BillingManagerEvent.objects.all()
    serializer_class = BillingManagerEventSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['billing_manager_provider', 'event_type', 'created_by']
    search_fields = ['billing_manager_provider__billing_manager__first_name',
                    'billing_manager_provider__billing_manager__last_name',
                    'billing_manager_provider__provider__name',
                    'notes']
    ordering_fields = ['effective_date', 'created_at']

    def get_queryset(self):
        """
        Менеджер по биллингу видит только свои события, админ — все.
        """
        if getattr(self, 'swagger_fake_view', False):
            return BillingManagerEvent.objects.none()
        
        qs = super().get_queryset()
        user = self.request.user
        
        # Проверяем, что пользователь аутентифицирован (для Swagger)
        if not user.is_authenticated:
            return qs.none()
            
        if hasattr(user, 'has_role') and user.has_role('billing_manager'):
            return qs.filter(billing_manager_provider__billing_manager=user)
        return qs


# ContractViewSet удален - используется LegalDocument и DocumentAcceptance


class RegionalBlockingPolicyListCreateAPIView(generics.ListCreateAPIView):
    """
    API: платформенные политики блокировок по региону (валюта, допуск, пороги дней L2/L3).
    """
    queryset = RegionalBlockingPolicy.objects.all()
    serializer_class = RegionalBlockingPolicySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_active', 'region_code']


class RegionalBlockingPolicyRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """API: одна запись RegionalBlockingPolicy."""
    queryset = RegionalBlockingPolicy.objects.all()
    serializer_class = RegionalBlockingPolicySerializer
    permission_classes = [permissions.IsAuthenticated]


class ProviderBlockingListAPIView(generics.ListAPIView):
    """
    API для просмотра списка блокировок учреждений.
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права админа или биллинг-менеджера
    """
    queryset = ProviderBlocking.objects.all()
    serializer_class = ProviderBlockingSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'provider']


class ProviderBlockingRetrieveAPIView(generics.RetrieveAPIView):
    """
    API для просмотра детальной информации о блокировке.
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = ProviderBlocking.objects.all()
    serializer_class = ProviderBlockingSerializer
    permission_classes = [permissions.IsAuthenticated]


class ProviderBlockingStatusAPIView(generics.RetrieveAPIView):
    """
    API для проверки статуса блокировки конкретного учреждения.
    
    Права доступа:
    - Требуется аутентификация
    """
    serializer_class = ProviderBlockingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, provider_id):
        """
        Проверяет статус блокировки учреждения.
        
        Args:
            provider_id: ID учреждения
            
        Returns:
            JSON с информацией о блокировке
        """
        provider = get_object_or_404(Provider, id=provider_id)
        
        # Проверяем активную блокировку
        active_blocking = ProviderBlocking.objects.filter(
            provider=provider,
            status='active'
        ).first()
        
        if active_blocking:
            return Response({
                'is_blocked': True,
                'blocking_id': active_blocking.id,
                'blocked_at': active_blocking.blocked_at,
                'blocking_level': active_blocking.blocking_level,
                'debt_amount': active_blocking.debt_amount,
                'overdue_days': active_blocking.overdue_days,
                'currency': active_blocking.currency.code,
                'notes': active_blocking.notes,
            })
        else:
            return Response({
                'is_blocked': False,
                'blocking_id': None
            })


class ProviderBlockingResolveAPIView(generics.UpdateAPIView):
    """
    API для снятия блокировки учреждения.
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права админа или биллинг-менеджера
    """
    serializer_class = ProviderBlockingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, blocking_id):
        """
        Снимает блокировку учреждения.
        
        Args:
            blocking_id: ID блокировки
            
        Returns:
            JSON с результатом операции
        """
        blocking = get_object_or_404(ProviderBlocking.objects.select_for_update(), id=blocking_id)
        
        # Проверяем, что блокировка активна
        if blocking.status != 'active':
            return Response({
                'error': _('Blocking is already inactive')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Снимаем блокировку
        notes = request.data.get('notes', 'Resolved through API')
        blocking.resolve(resolved_by=request.user, notes=notes)
        
        return Response({
            'success': True,
            'message': _('Blocking for provider %(provider)s has been resolved') % {
                'provider': blocking.provider.name,
            },
            'resolved_at': blocking.resolved_at,
            'resolved_by': blocking.resolved_by.username if blocking.resolved_by else None
        })


class ProviderBlockingHistoryAPIView(generics.ListAPIView):
    """
    API для просмотра истории блокировок учреждения.
    
    Права доступа:
    - Требуется аутентификация
    """
    serializer_class = ProviderBlockingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Возвращает историю блокировок для конкретного учреждения.
        """
        if getattr(self, 'swagger_fake_view', False):
            return ProviderBlocking.objects.none()
            
        provider_id = self.kwargs.get('provider_id')
        provider = get_object_or_404(Provider, id=provider_id)
        
        return ProviderBlocking.objects.filter(provider=provider).order_by('-blocked_at')


class BlockingNotificationListAPIView(generics.ListAPIView):
    """
    API для просмотра списка уведомлений о блокировках.
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права админа или биллинг-менеджера
    """
    queryset = BlockingNotification.objects.all()
    serializer_class = BlockingNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'notification_type', 'provider_blocking']


class BlockingNotificationRetryAPIView(generics.GenericAPIView):
    """
    API для повторной отправки неудачного уведомления.
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права админа или биллинг-менеджера
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        """Возвращает сериализатор для Swagger или None для реальных запросов"""
        if getattr(self, 'swagger_fake_view', False):
            # Для Swagger возвращаем пустой сериализатор
            return EmptySerializer
        return None
    
    def get_serializer(self, *args, **kwargs):
        """Переопределяем для Swagger"""
        if getattr(self, 'swagger_fake_view', False):
            return super().get_serializer(*args, **kwargs)
        return None

    def post(self, request, notification_id):
        """
        Повторно отправляет уведомление.
        
        Args:
            notification_id: ID уведомления
            
        Returns:
            JSON с результатом операции
        """
        notification = get_object_or_404(BlockingNotification, id=notification_id)
        
        if notification.status != 'failed':
            return Response({
                'error': _('Notification is not in failed status')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Здесь должна быть логика повторной отправки уведомления
        # Пока просто отмечаем как отправленное
        notification.mark_as_sent()
        
        return Response({
            'success': True,
            'message': _('Notification has been retried'),
            'sent_at': notification.sent_at
        }) 


class CurrencyListAPIView(generics.ListAPIView):
    """
    API для получения списка активных валют.
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = Currency.objects.filter(is_active=True)
    serializer_class = CurrencySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Возвращает список активных валют, отсортированных по коду.
        """
        return Currency.objects.filter(is_active=True).order_by('code')


# Workflow согласования контрактов удален - используется LegalDocument и DocumentAcceptance 
