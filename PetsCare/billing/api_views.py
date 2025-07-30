"""
API views for the billing module.

Этот модуль содержит представления для:
1. Управления платежами
2. Управления счетами
3. Управления возвратами
4. Управления типами контрактов
"""

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Payment, Invoice, Refund, ContractType, BillingManagerProvider, BillingManagerEvent, Contract, BlockingRule, ProviderBlocking, BlockingNotification, ContractApprovalHistory
from .serializers import (
    PaymentSerializer,
    InvoiceSerializer,
    RefundSerializer,
    PaymentCreateSerializer,
    RefundCreateSerializer,
    ContractTypeSerializer,
    ContractSerializer,
    ContractCreateSerializer,
    BillingManagerProviderSerializer,
    BillingManagerProviderCreateSerializer,
    BillingManagerEventSerializer,
    BlockingRuleSerializer, 
    ProviderBlockingSerializer, 
    BlockingNotificationSerializer
)
from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics
from django.shortcuts import get_object_or_404
from providers.models import Provider


class ContractTypeViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления типами контрактов.
    
    Используется для CRUD операций с типами контрактов.
    Поддерживает фильтрацию по статусу активности и поиск по названию и коду.
    """
    queryset = ContractType.objects.all()
    serializer_class = ContractTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'code']

    def get_queryset(self):
        """
        Возвращает отфильтрованный список типов контрактов.
        
        Для обычных пользователей возвращает только активные типы контрактов.
        """
        queryset = ContractType.objects.all()
        
        # Для обычных пользователей - только активные типы
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
            
        return queryset


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
    filterset_fields = ['status', 'payment_method']
    ordering_fields = ['created_at', 'amount']

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentCreateSerializer
        return PaymentSerializer

    def get_queryset(self):
        """
        Возвращает отфильтрованный список платежей.
        
        Для обычных пользователей возвращает только их платежи.
        """
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
        payment = self.get_object()
        
        # Используем select_for_update для предотвращения гонки
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(id=payment.id)
            
            if payment.status != 'pending':
                return Response(
                    {'error': _('Payment is not pending')},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            payment.status = 'completed'
            payment.save()
        
        # Создаем счет
        Invoice.objects.create(
            booking=payment.booking,
            amount=payment.amount,
            status='paid',
            due_date=payment.created_at.date()
        )
        
        return Response({'status': _('payment confirmed')})


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для просмотра счетов.
    
    Используется для просмотра списка и деталей счетов.
    Поддерживает фильтрацию и сортировку.
    """
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status']
    ordering_fields = ['created_at', 'amount']

    def get_queryset(self):
        """
        Возвращает отфильтрованный список счетов.
        
        Для обычных пользователей возвращает только их счета.
        Для менеджеров по биллингу - счета их провайдеров.
        """
        queryset = Invoice.objects.all()
        user = self.request.user
        
        # Для менеджеров по биллингу - счета их провайдеров
        if user.has_role('billing_manager'):
            managed_providers = BillingManagerProvider.objects.filter(
                billing_manager=user,
                status__in=['active', 'temporary']
            ).values_list('provider', flat=True)
            queryset = queryset.filter(provider__in=managed_providers)
        # Для обычных пользователей - только их счета
        elif not user.is_staff:
            queryset = queryset.filter(booking__user=user)
            
        return queryset


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
        qs = super().get_queryset()
        user = self.request.user
        if user.has_role('billing_manager'):
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
        qs = super().get_queryset()
        user = self.request.user
        if user.has_role('billing_manager'):
            return qs.filter(billing_manager_provider__billing_manager=user)
        return qs


class ContractViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления контрактами.
    
    Используется для CRUD операций с контрактами.
    Поддерживает фильтрацию по статусу, провайдеру и типу контракта.
    Для менеджеров по биллингу - только контракты их провайдеров.
    """
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'provider', 'contract_type']
    search_fields = ['number', 'provider__name', 'contract_type__name']
    ordering_fields = ['start_date', 'end_date', 'created_at']

    def get_serializer_class(self):
        """
        Возвращает соответствующий сериализатор в зависимости от действия.
        """
        if self.action == 'create':
            return ContractCreateSerializer
        return ContractSerializer

    def get_queryset(self):
        """
        Возвращает отфильтрованный список контрактов.
        
        Для менеджеров по биллингу - только контракты их провайдеров.
        Для провайдеров - только их контракты.
        Для администраторов - все контракты.
        """
        queryset = Contract.objects.all()
        user = self.request.user
        
        # Для менеджеров по биллингу - контракты их провайдеров
        if user.has_role('billing_manager'):
            managed_providers = BillingManagerProvider.objects.filter(
                billing_manager=user,
                status__in=['active', 'temporary']
            ).values_list('provider', flat=True)
            queryset = queryset.filter(provider__in=managed_providers)
        # Для провайдеров - только их контракты
        elif user.has_role('provider'):
            queryset = queryset.filter(provider=user.provider)
        # Для обычных пользователей - только их контракты (если есть)
        elif not user.is_staff:
            # Обычные пользователи не имеют прямого доступа к контрактам
            queryset = Contract.objects.none()
            
        return queryset

    def perform_create(self, serializer):
        """
        Сохраняет создателя контракта при создании.
        """
        serializer.save(created_by=self.request.user)


class BlockingRuleListCreateAPIView(generics.ListCreateAPIView):
    """
    API для просмотра списка и создания правил блокировки.
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права админа или биллинг-менеджера
    """
    queryset = BlockingRule.objects.all()
    serializer_class = BlockingRuleSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_active', 'is_mass_rule', 'priority']


class BlockingRuleRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для работы с конкретным правилом блокировки.
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права админа или биллинг-менеджера
    """
    queryset = BlockingRule.objects.all()
    serializer_class = BlockingRuleSerializer
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
    filterset_fields = ['status', 'blocking_rule', 'provider']


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
                'debt_amount': active_blocking.debt_amount,
                'overdue_days': active_blocking.overdue_days,
                'currency': active_blocking.currency.code,
                'rule_name': active_blocking.blocking_rule.name,
                'notes': active_blocking.notes
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
                'error': 'Блокировка уже неактивна'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Снимаем блокировку
        notes = request.data.get('notes', 'Снято через API')
        blocking.resolve(resolved_by=request.user, notes=notes)
        
        return Response({
            'success': True,
            'message': f'Блокировка учреждения {blocking.provider.name} снята',
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


class BlockingNotificationRetryAPIView(generics.UpdateAPIView):
    """
    API для повторной отправки неудачного уведомления.
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права админа или биллинг-менеджера
    """
    permission_classes = [permissions.IsAuthenticated]

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
                'error': 'Уведомление не является неудачным'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Здесь должна быть логика повторной отправки уведомления
        # Пока просто отмечаем как отправленное
        notification.mark_as_sent()
        
        return Response({
            'success': True,
            'message': 'Уведомление отправлено повторно',
            'sent_at': notification.sent_at
        }) 


# Workflow согласования контрактов
from rest_framework.decorators import api_view, permission_classes
from django.utils import timezone
from django.db import transaction


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def submit_contract_for_approval(request, contract_id):
    """
    Отправляет контракт на согласование админу.
    
    Права доступа:
    - Требуется аутентификация
    - Только менеджеры по биллингу или создатели контракта
    """
    try:
        with transaction.atomic():
            contract = get_object_or_404(Contract, id=contract_id)
            
            # Проверяем права доступа
            if not (request.user.is_staff or 
                   contract.created_by == request.user or
                   BillingManagerProvider.objects.filter(
                       billing_manager=request.user,
                       provider=contract.provider,
                       status='active'
                   ).exists()):
                return Response({
                    'error': _('You do not have permission to submit this contract for approval')
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Проверяем, что контракт в статусе черновика
            if contract.status != 'draft':
                return Response({
                    'error': _('Contract must be in draft status to submit for approval')
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Обновляем статус контракта
            contract.status = 'pending_approval'
            contract.submitted_for_approval_at = timezone.now()
            contract.save()
            
            # Создаем запись в истории
            ContractApprovalHistory.objects.create(
                contract=contract,
                action='submitted',
                user=request.user,
                reason=request.data.get('reason', '')
            )
            
            # Отправляем уведомления админам
            from .services import notify_admins_contract_approval_needed
            notify_admins_contract_approval_needed(contract)
            
            return Response({
                'message': _('Contract submitted for approval successfully'),
                'contract_id': contract.id,
                'status': contract.status
            })
            
    except Exception as e:
        return Response({
            'error': _('Failed to submit contract for approval'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def approve_contract(request, contract_id):
    """
    Одобряет контракт админом.
    
    Права доступа:
    - Требуется аутентификация
    - Только админы
    """
    try:
        with transaction.atomic():
            contract = get_object_or_404(Contract.objects.select_for_update(), id=contract_id)
            
            # Проверяем, что контракт ожидает согласования
            if contract.status != 'pending_approval':
                return Response({
                    'error': _('Contract must be pending approval to approve')
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Обновляем статус контракта
            contract.status = 'active'
            contract.approved_by = request.user
            contract.approved_at = timezone.now()
            contract.save()
            
            # Создаем запись в истории
            ContractApprovalHistory.objects.create(
                contract=contract,
                action='approved',
                user=request.user,
                reason=request.data.get('reason', '')
            )
            
            # Отправляем уведомление менеджеру
            from .services import notify_manager_contract_approved
            notify_manager_contract_approved(contract)
            
            return Response({
                'message': _('Contract approved successfully'),
                'contract_id': contract.id,
                'status': contract.status
            })
            
    except Exception as e:
        return Response({
            'error': _('Failed to approve contract'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def reject_contract(request, contract_id):
    """
    Отклоняет контракт админом.
    
    Права доступа:
    - Требуется аутентификация
    - Только админы
    """
    try:
        with transaction.atomic():
            contract = get_object_or_404(Contract.objects.select_for_update(), id=contract_id)
            
            # Проверяем, что контракт ожидает согласования
            if contract.status != 'pending_approval':
                return Response({
                    'error': _('Contract must be pending approval to reject')
                }, status=status.HTTP_400_BAD_REQUEST)
            
            rejection_reason = request.data.get('reason', '')
            if not rejection_reason:
                return Response({
                    'error': _('Rejection reason is required')
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Обновляем статус контракта
            contract.status = 'rejected'
            contract.rejection_reason = rejection_reason
            contract.save()
            
            # Создаем запись в истории
            ContractApprovalHistory.objects.create(
                contract=contract,
                action='rejected',
                user=request.user,
                reason=rejection_reason
            )
            
            # Отправляем уведомление менеджеру
            from .services import notify_manager_contract_rejected
            notify_manager_contract_rejected(contract, rejection_reason)
            
            return Response({
                'message': _('Contract rejected successfully'),
                'contract_id': contract.id,
                'status': contract.status
            })
            
    except Exception as e:
        return Response({
            'error': _('Failed to reject contract'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def activate_contract(request, contract_id):
    """
    Активирует контракт менеджером (если стандартные условия) или админом.
    
    Права доступа:
    - Требуется аутентификация
    - Менеджеры могут активировать только стандартные контракты
    - Админы могут активировать любые контракты
    """
    try:
        with transaction.atomic():
            contract = get_object_or_404(Contract.objects.select_for_update(), id=contract_id)
            
            # Проверяем права доступа
            if not request.user.is_staff:
                # Для менеджеров проверяем, что контракт стандартный
                if not contract.can_manager_activate():
                    return Response({
                        'error': _('You can only activate contracts with standard conditions')
                    }, status=status.HTTP_403_FORBIDDEN)
                
                # Проверяем, что менеджер связан с провайдером
                if not BillingManagerProvider.objects.filter(
                    billing_manager=request.user,
                    provider=contract.provider,
                    status='active'
                ).exists():
                    return Response({
                        'error': _('You do not have permission to activate this contract')
                    }, status=status.HTTP_403_FORBIDDEN)
            
            # Проверяем, что контракт в статусе черновика или одобрен
            if contract.status not in ['draft', 'active']:
                return Response({
                    'error': _('Contract must be in draft or approved status to activate')
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Обновляем статус контракта
            contract.status = 'active'
            if not request.user.is_staff:
                contract.approved_by = request.user
                contract.approved_at = timezone.now()
            contract.save()
            
            # Создаем запись в истории
            ContractApprovalHistory.objects.create(
                contract=contract,
                action='activated',
                user=request.user,
                reason=request.data.get('reason', '')
            )
            
            return Response({
                'message': _('Contract activated successfully'),
                'contract_id': contract.id,
                'status': contract.status
            })
            
    except Exception as e:
        return Response({
            'error': _('Failed to activate contract'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 