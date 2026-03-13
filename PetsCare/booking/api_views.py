"""
API views для модуля бронирования.

Этот модуль содержит представления для:
1. Управления временными слотами
2. Управления бронированиями
3. Поиска доступных слотов
4. Фильтрации бронирований
"""

from rest_framework import viewsets, permissions, status, serializers
from rest_framework.views import APIView
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db.models import Prefetch, Q
from datetime import datetime
from .models import Booking, BookingCancellationReason, BookingPayment, BookingReview, TimeSlot, BookingServiceIssue
from .serializers import (
    BookingCreateSerializer,
    BookingCancellationActionSerializer,
    BookingCompletionActionSerializer,
    BookingVisitRecordUpsertSerializer,
    BookingUpdateSerializer,
    BookingListSerializer,
    BookingPaymentSerializer,
    BookingPaymentCreateSerializer,
    BookingReviewSerializer,
    BookingReviewCreateSerializer,
    BookingSerializer,
    BookingStatusUpdateSerializer,
    TimeSlotSearchSerializer,
    TimeSlotSerializer,
    BookingServiceIssueSerializer,
    BookingServiceIssueCreateSerializer,
    BookingServiceIssueResolveSerializer,
)
from .utils import (
    check_booking_availability,
    calculate_booking_price,
    update_booking_status,
    get_available_time_slots
)
from .services import (
    BookingAvailabilityService,
    BookingCompletionService,
    BookingDomainError,
    BookingTransactionService,
    EmployeeAutoBookingService,
)
from .constants import (
    BOOKING_STATUS_COMPLETED,
    CANCELLED_BY_CLIENT,
    CANCELLED_BY_PROVIDER,
    CANCELLATION_REASON_CLIENT_NO_SHOW,
    ISSUE_STATUS_ACKNOWLEDGED,
    ISSUE_STATUS_OPEN,
    RESOLUTION_OUTCOME_PROVIDER_CANCELLED,
    RESOLUTION_OUTCOME_COMPLETED,
    RESOLUTION_OUTCOME_CLIENT_CANCELLED,
    RESOLUTION_OUTCOME_CLAIM_REJECTED,
    REPORTED_BY_CLIENT,
    RESOLVED_BY_PROVIDER,
    RESOLVED_BY_SUPPORT,
)
from pets.models import Pet, PetDocument, PetHealthNote, PetOwner, VisitRecord
from pets.serializers import VisitRecordAddendumSerializer
from providers.models import Provider, Service
from users.models import User
from rest_framework.permissions import IsAuthenticated


def scope_bookings_for_user(queryset, user):
    if user.is_superuser or user.is_system_admin():
        return queryset

    if user.is_client():
        return queryset.filter(user=user)

    if user.is_employee():
        return queryset.filter(employee__user=user)

    if user.is_provider_admin():
        managed_providers = user.get_managed_providers()
        return queryset.filter(
            Q(provider__in=managed_providers) |
            Q(provider_location__provider__in=managed_providers)
        )

    return queryset.none()


def with_booking_list_related(queryset):
    return queryset.select_related(
        'user',
        'pet',
        'pet__pet_type',
        'pet__breed',
        'provider',
        'provider__structured_address',
        'provider_location',
        'provider_location__structured_address',
        'employee',
        'employee__user',
        'service',
        'service__parent',
        'service__parent__parent',
        'status',
        'cancelled_by_user',
        'completed_by_user',
        'cancellation_reason',
    ).prefetch_related(
        Prefetch('service_issues', queryset=BookingServiceIssue.objects.order_by('-created_at')),
    )


def with_booking_detail_related(queryset):
    return queryset.select_related(
        'user',
        'escort_owner',
        'pet',
        'pet__pet_type',
        'pet__breed',
        'provider',
        'provider__structured_address',
        'provider_location',
        'provider_location__structured_address',
        'employee',
        'employee__user',
        'service',
        'service__parent',
        'service__parent__parent',
        'status',
        'cancelled_by_user',
        'completed_by_user',
        'cancellation_reason',
        'payment',
        'review',
        'visit_record',
        'visit_record__provider_location',
        'visit_record__service',
        'visit_record__employee__user',
    ).prefetch_related(
        Prefetch('service_issues', queryset=BookingServiceIssue.objects.order_by('-created_at')),
        'pet__chronic_conditions',
        Prefetch('pet__petowner_set', queryset=PetOwner.objects.select_related('user').order_by('id')),
        Prefetch('pet__health_notes', queryset=PetHealthNote.objects.order_by('-date', '-created_at')),
        Prefetch(
            'pet__documents',
            queryset=PetDocument.objects.select_related(
                'document_type',
                'visit_record',
                'health_note',
                'uploaded_by',
            ).order_by('-uploaded_at', '-created_at'),
        ),
        Prefetch(
            'visit_record__documents',
            queryset=PetDocument.objects.select_related(
                'document_type',
                'visit_record',
                'health_note',
                'uploaded_by',
            ).order_by('-uploaded_at', '-created_at'),
        ),
        'visit_record__addenda',
        'visit_record__addenda__author',
        'visit_record__source_bookings',
        Prefetch(
            'pet__records',
            queryset=VisitRecord.objects.select_related(
                'provider_location',
                'service',
                'employee__user',
                'provider',
            ).prefetch_related(
                'documents',
                'documents__document_type',
                'documents__uploaded_by',
                'addenda',
                'addenda__author',
                'source_bookings',
            ).order_by('-date', '-created_at'),
        ),
    )


class TimeSlotViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления временными слотами.
    
    Особенности:
    - CRUD операции
    - Поиск слотов
    - Фильтрация и сортировка
    """
    queryset = TimeSlot.objects.all()
    serializer_class = TimeSlotSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['employee', 'provider', 'is_available']
    ordering_fields = ['start_time', 'end_time']

    def get_queryset(self):
        """Возвращает отфильтрованный список слотов"""
        if getattr(self, 'swagger_fake_view', False):
            return TimeSlot.objects.none()
        
        queryset = TimeSlot.objects.filter(
            start_time__gte=timezone.now()
        )
        
        # Для специалистов - только их слоты
        if self.request.user.is_employee():
            queryset = queryset.filter(employee=self.request.user)
        
        # Для админов учреждений - слоты их учреждения
        elif self.request.user.is_provider_admin():
            managed_providers = self.request.user.get_managed_providers()
            queryset = queryset.filter(
                Q(provider__in=managed_providers) |
                Q(provider_location__provider__in=managed_providers)
            )
            
        return queryset

    @action(detail=False, methods=['post'])
    def search(self, request):
        """Поиск доступных слотов"""
        serializer = TimeSlotSearchSerializer(data=request.data)
        if serializer.is_valid():
            queryset = self.get_queryset()
            
            if serializer.validated_data.get('start_date'):
                queryset = queryset.filter(
                    start_time__gte=serializer.validated_data['start_date']
                )
            
            if serializer.validated_data.get('end_date'):
                queryset = queryset.filter(
                    end_time__lte=serializer.validated_data['end_date']
                )
            
            if serializer.validated_data.get('employee'):
                queryset = queryset.filter(
                    employee=serializer.validated_data['employee']
                )
            
            if serializer.validated_data.get('provider'):
                queryset = queryset.filter(
                    provider=serializer.validated_data['provider']
                )
            
            # Только доступные слоты
            queryset = queryset.filter(is_available=True)
            
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BookingViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления бронированиями.
    
    Особенности:
    - CRUD операции
    - Подтверждение и отмена
    - Фильтрация и сортировка
    """
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'provider', 'employee', 'service']
    ordering_fields = ['start_time', 'created_at']
    
    def get_queryset(self):
        """
        Возвращает список бронирований для текущего пользователя.
        """
        if getattr(self, 'swagger_fake_view', False):
            return Booking.objects.none()

        queryset = scope_bookings_for_user(Booking.objects.all(), self.request.user)

        if self.action == 'list':
            return with_booking_list_related(queryset)

        if self.action in {
            'retrieve',
            'cancel_by_client',
            'cancel_by_provider',
            'complete',
            'visit_record',
            'visit_record_addenda',
            'mark_no_show_by_client',
        }:
            return with_booking_detail_related(queryset)

        return queryset

    def _user_can_manage_provider(self, user, booking):
        """
        Проверяет, может ли админ учреждения управлять бронированием.
        """
        if not user.is_provider_admin():
            return False
        provider = booking.provider
        if not provider and booking.provider_location:
            provider = booking.provider_location.provider
        if not provider:
            return False
        return user.get_managed_providers().filter(id=provider.id).exists()

    def _get_booking_for_service_issue_action(self, pk):
        if self.request.user.is_superuser or self.request.user.is_system_admin():
            return get_object_or_404(Booking.objects.all(), pk=pk)
        return self.get_object()

    def _get_service_issue_resolution_actor(self, user, booking):
        if user.is_superuser or user.is_system_admin():
            return RESOLVED_BY_SUPPORT
        if user.is_employee():
            if booking.employee and booking.employee.user == user:
                return RESOLVED_BY_PROVIDER
            return None
        if user.is_provider_admin() and self._user_can_manage_provider(user, booking):
            return RESOLVED_BY_PROVIDER
        return None

    def _user_can_edit_visit_record(self, user, booking):
        if user.is_superuser or user.is_system_admin():
            return True
        if user.is_employee():
            return booking.employee and booking.employee.user == user
        if user.is_provider_admin():
            return self._user_can_manage_provider(user, booking)
        return False

    def _build_booking_detail_response(self, booking_id, *, status_code=status.HTTP_200_OK):
        booking = self.get_queryset().get(pk=booking_id)
        return Response(self.get_serializer(booking).data, status=status_code)
    
    def get_serializer_class(self):
        """
        Выбирает сериализатор в зависимости от действия.
        """
        if self.action == 'create':
            return BookingCreateSerializer
        elif self.action == 'list':
            return BookingListSerializer
        elif self.action in ['update', 'partial_update']:
            return BookingUpdateSerializer
        elif self.action == 'update_status':
            return BookingStatusUpdateSerializer
        return BookingSerializer
    
    def perform_create(self, serializer):
        """
        Создает новое бронирование.
        """
        provider_location = serializer.validated_data.get('provider_location')
        provider = serializer.validated_data.get('provider')
        if provider_location is not None and provider is None:
            provider = provider_location.provider

        try:
            booking = BookingTransactionService.create_booking(
                user=self.request.user,
                pet=serializer.validated_data['pet'],
                provider=provider,
                provider_location=provider_location,
                employee=serializer.validated_data['employee'],
                service=serializer.validated_data['service'],
                start_time=serializer.validated_data['start_time'],
                escort_owner=serializer.validated_data.get('escort_owner'),
                notes=serializer.validated_data.get('notes', ''),
            )
        except BookingDomainError as exc:
            raise serializers.ValidationError(exc.to_dict())

        serializer.instance = booking

    def _cancel_booking(self, request, booking, cancelled_by):
        serializer = BookingCancellationActionSerializer(
            data=request.data,
            context={'cancelled_by': cancelled_by},
        )
        serializer.is_valid(raise_exception=True)
        try:
            booking.cancel_booking(
                cancelled_by=cancelled_by,
                cancelled_by_user=request.user,
                cancellation_reason=serializer.validated_data['cancellation_reason'],
                cancellation_reason_text=serializer.validated_data.get('cancellation_reason_text', ''),
                client_attendance=serializer.validated_data.get('client_attendance'),
            )
        except ValueError as exc:
            raise serializers.ValidationError({'error': str(exc)})
        return self._build_booking_detail_response(booking.id)

    def _complete_booking(self, request, booking):
        serializer = BookingCompletionActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            BookingCompletionService.complete_booking(
                booking,
                request.user,
                pet_record_data=serializer.validated_data.get('visit_record'),
            )
        except BookingDomainError as exc:
            raise serializers.ValidationError(exc.to_dict())
        except ValueError as exc:
            raise serializers.ValidationError({'error': str(exc)})
        return self._build_booking_detail_response(booking.id)

    def _save_visit_record(self, request, booking):
        serializer = BookingVisitRecordUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            BookingCompletionService.save_visit_record(
                booking,
                request.user,
                pet_record_data=serializer.validated_data,
            )
        except BookingDomainError as exc:
            raise serializers.ValidationError(exc.to_dict())
        except ValueError as exc:
            raise serializers.ValidationError({'error': str(exc)})
        return self._build_booking_detail_response(booking.id)
    
    @action(detail=True, methods=['post'])
    def cancel_by_client(self, request, pk=None):
        """
        Отмена бронирования клиентом.
        """
        booking = self.get_object()
        
        # Проверяем права
        if booking.user != request.user:
            return Response(
                {'error': _('You can only cancel your own bookings')},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            return self._cancel_booking(request, booking, CANCELLED_BY_CLIENT)
        except serializers.ValidationError as exc:
            return Response(
                exc.detail,
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def cancel_by_provider(self, request, pk=None):
        """
        Отмена бронирования провайдером.
        """
        booking = self.get_object()
        
        # Проверяем права
        if not (request.user.is_employee() or request.user.is_provider_admin()):
            return Response(
                {'error': _('Only employees and provider admins can cancel bookings')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Проверяем принадлежность к учреждению
        if request.user.is_employee():
            if booking.employee.user != request.user:
                return Response(
                    {'error': _('You can only cancel your own bookings')},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:  # provider admin
            if not self._user_can_manage_provider(request.user, booking):
                return Response(
                    {'error': _('You can only cancel bookings of your provider')},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        try:
            return self._cancel_booking(request, booking, CANCELLED_BY_PROVIDER)
        except serializers.ValidationError as exc:
            return Response(
                exc.detail,
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """
        Завершение услуги.
        """
        booking = self.get_object()
        
        # Проверяем права
        if not (request.user.is_employee() or request.user.is_provider_admin()):
            return Response(
                {'error': _('Only employees and provider admins can complete bookings')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Проверяем принадлежность к учреждению
        if request.user.is_employee():
            if booking.employee.user != request.user:
                return Response(
                    {'error': _('You can only complete your own bookings')},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:  # provider admin
            if not self._user_can_manage_provider(request.user, booking):
                return Response(
                    {'error': _('You can only complete bookings of your provider')},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        try:
            return self._complete_booking(request, booking)
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['patch'])
    def visit_record(self, request, pk=None):
        """
        Создание или обновление протокола уже завершённого визита.
        """
        booking = self.get_object()

        if booking.status.name != BOOKING_STATUS_COMPLETED:
            return Response(
                {
                    'code': 'visit_record_unavailable',
                    'error': _('Visit protocol can only be saved for completed bookings'),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not self._user_can_edit_visit_record(request.user, booking):
            return Response(
                {
                    'code': 'visit_record_forbidden',
                    'error': _('You do not have permission to edit this visit protocol'),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            return self._save_visit_record(request, booking)
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get', 'post'], url_path='visit-record-addenda')
    def visit_record_addenda(self, request, pk=None):
        booking = self.get_object()

        if booking.visit_record_id is None:
            return Response(
                {
                    'code': 'visit_record_missing',
                    'error': _('Addenda are available only after a visit protocol is created'),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.method.lower() == 'get':
            queryset = booking.visit_record.addenda.select_related('author').order_by('created_at')
            serializer = VisitRecordAddendumSerializer(queryset, many=True, context=self.get_serializer_context())
            return Response(serializer.data)

        if not self._user_can_edit_visit_record(request.user, booking):
            return Response(
                {
                    'code': 'visit_record_forbidden',
                    'error': _('You do not have permission to add a post-visit update'),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = VisitRecordAddendumSerializer(
            data=request.data,
            context=self.get_serializer_context(),
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        addendum = serializer.save(
            visit_record=booking.visit_record,
            author=request.user,
        )
        return Response(
            VisitRecordAddendumSerializer(addendum, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def mark_no_show_by_client(self, request, pk=None):
        """
        Отметка о неявке клиента.
        """
        booking = self.get_object()
        
        # Проверяем права
        if not (request.user.is_employee() or request.user.is_provider_admin()):
            return Response(
                {'error': _('Only employees and provider admins can mark no-shows')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Проверяем принадлежность к учреждению
        if request.user.is_employee():
            if booking.employee.user != request.user:
                return Response(
                    {'error': _('You can only mark no-shows for your own bookings')},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:  # provider admin
            if not self._user_can_manage_provider(request.user, booking):
                return Response(
                    {'error': _('You can only mark no-shows for bookings of your provider')},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        no_show_reason = BookingCancellationReason.objects.filter(
            code=CANCELLATION_REASON_CLIENT_NO_SHOW,
            is_active=True,
        ).first()
        payload = {
            'reason_code': CANCELLATION_REASON_CLIENT_NO_SHOW,
            'client_attendance': 'no_show',
        }
        if 'reason_text' in request.data:
            payload['reason_text'] = request.data.get('reason_text')
        if no_show_reason is None:
            return Response(
                {'error': _('No-show reason is not configured')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        serializer = BookingCancellationActionSerializer(
            data=payload,
            context={'cancelled_by': CANCELLED_BY_PROVIDER},
        )
        serializer.is_valid(raise_exception=True)
        try:
            booking.cancel_booking(
                cancelled_by=CANCELLED_BY_PROVIDER,
                cancelled_by_user=request.user,
                cancellation_reason=no_show_reason,
                cancellation_reason_text=serializer.validated_data.get('cancellation_reason_text', ''),
                client_attendance='no_show',
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self._build_booking_detail_response(booking.id)

    @action(detail=True, methods=['post'])
    def report_service_issue(self, request, pk=None):
        """
        Сообщить о неоказании услуги клиентом.
        """
        booking = self._get_booking_for_service_issue_action(pk)

        # Проверяем права
        if booking.user != request.user:
            return Response(
                {'error': _('You can only report issues for your own bookings')},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = BookingServiceIssueCreateSerializer(
            data=request.data,
            context={'booking': booking},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        issue = BookingServiceIssue.objects.create(
            booking=booking,
            issue_type=serializer.validated_data['issue_type'],
            reported_by_user=request.user,
            reported_by_side=REPORTED_BY_CLIENT,
            client_attendance_snapshot=serializer.validated_data.get('client_attendance_snapshot', 'unknown'),
            description=serializer.validated_data.get('description', ''),
        )
        return Response(
            BookingServiceIssueSerializer(issue, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get'])
    def service_issues(self, request, pk=None):
        """Получить все споры/проблемы по бронированию"""
        booking = self._get_booking_for_service_issue_action(pk)
        issues = BookingServiceIssue.objects.filter(booking=booking)
        return Response(BookingServiceIssueSerializer(issues, many=True, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'], url_path='service-issues/(?P<issue_id>[^/.]+)/resolve')
    def resolve_service_issue(self, request, pk=None, issue_id=None):
        """Отрезолвить спор по бронированию (провайдер/суппорт)"""
        booking = self._get_booking_for_service_issue_action(pk)
        try:
            issue = BookingServiceIssue.objects.get(id=issue_id, booking=booking)
        except BookingServiceIssue.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if issue.status not in (ISSUE_STATUS_OPEN, ISSUE_STATUS_ACKNOWLEDGED):
            return Response({'error': _('Issue is already resolved or not open')}, status=status.HTTP_400_BAD_REQUEST)

        resolution_actor = self._get_service_issue_resolution_actor(request.user, booking)
        if resolution_actor is None:
            return Response(
                {'error': _('Only assigned provider staff or support can resolve issues')},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = BookingServiceIssueResolveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        outcome = serializer.validated_data['resolution_outcome']
        note = serializer.validated_data.get('resolution_note', '')
        cancellation_reason = serializer.validated_data.get('cancellation_reason_obj')

        try:
            if outcome == RESOLUTION_OUTCOME_PROVIDER_CANCELLED:
                booking.cancel_booking(
                    cancelled_by=CANCELLED_BY_PROVIDER,
                    cancelled_by_user=request.user,
                    cancellation_reason=cancellation_reason,
                    cancellation_reason_text=f'Resolved issue #{issue.id} in favor of client',
                    client_attendance='arrived',
                )
            elif outcome == RESOLUTION_OUTCOME_COMPLETED:
                BookingCompletionService.complete_booking(booking, request.user)
            elif outcome == RESOLUTION_OUTCOME_CLIENT_CANCELLED:
                booking.cancel_booking(
                    cancelled_by=CANCELLED_BY_CLIENT,
                    cancelled_by_user=request.user,
                    cancellation_reason=cancellation_reason,
                    cancellation_reason_text=f'Resolved issue #{issue.id}',
                    client_attendance='arrived',
                )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        issue.status = 'resolved' if outcome != RESOLUTION_OUTCOME_CLAIM_REJECTED else 'rejected'
        issue.resolution_outcome = outcome
        issue.resolved_by_user = request.user
        issue.resolved_by_actor = resolution_actor
        issue.resolved_at = timezone.now()
        issue.resolution_note = note
        issue.save()

        return Response(BookingServiceIssueSerializer(issue, context=self.get_serializer_context()).data)


class BookingPaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления платежами.
    """
    serializer_class = BookingPaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Возвращает список платежей для бронирований текущего пользователя.
        """
        if getattr(self, 'swagger_fake_view', False):
            return BookingPayment.objects.none()
        return BookingPayment.objects.filter(booking__pet__owner=self.request.user)


class BookingReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления отзывами.
    """
    serializer_class = BookingReviewSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Возвращает список отзывов для бронирований текущего пользователя.
        """
        if getattr(self, 'swagger_fake_view', False):
            return BookingReview.objects.none()
        return BookingReview.objects.filter(booking__pet__owner=self.request.user)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def auto_book_employee(request):
    """
    Автоматическое бронирование работника для услуги.
    
    Система автоматически выбирает свободного работника и создает бронирование.
    """
    try:
        # Получаем данные из запроса
        pet_id = request.data.get('pet_id')
        provider_id = request.data.get('provider_id')
        service_id = request.data.get('service_id')
        start_time_str = request.data.get('start_time')
        end_time_str = request.data.get('end_time')
        price = request.data.get('price')
        notes = request.data.get('notes', '')
        
        # Валидация обязательных полей
        if not all([pet_id, provider_id, service_id, start_time_str, end_time_str, price]):
            return Response({
                'error': _('All required fields must be filled')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Получаем объекты
        try:
            pet = Pet.objects.get(id=pet_id, owners=request.user)
            provider = Provider.objects.get(id=provider_id, is_active=True)
            service = Service.objects.get(id=service_id, is_active=True)
        except (Pet.DoesNotExist, Provider.DoesNotExist, Service.DoesNotExist):
            return Response({
                'error': _('Pet, institution or service not found')
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Парсим время
        try:
            start_time = timezone.datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            end_time = timezone.datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
        except ValueError:
            return Response({
                'error': _('Invalid time format')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Проверяем, что время в будущем
        if start_time <= timezone.now():
            return Response({
                'error': _('Booking time must be in the future')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Проверяем, что end_time > start_time
        if end_time <= start_time:
            return Response({
                'error': _('End time must be later than start time')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Автоматически выбираем и бронируем работника
        booking = EmployeeAutoBookingService.auto_book_employee(
            user=request.user,
            pet=pet,
            provider=provider,
            service=service,
            start_time=start_time,
            end_time=end_time,
            price=float(price),
            notes=notes
        )
        
        if not booking:
            return Response({
                'error': _('No available workers for selected time')
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Возвращаем информацию о созданном бронировании
        return Response({
            'success': True,
            'message': _('Booking successfully created'),
            'booking': {
                'id': booking.id,
                'employee_name': f"{booking.employee.user.first_name} {booking.employee.user.last_name}",
                'service_name': booking.service.name,
                'start_time': booking.start_time.isoformat(),
                'end_time': booking.end_time.isoformat(),
                'price': booking.price,
                'status': booking.status.name
            }
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'error': _('Error creating booking'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_available_employees(request):
    """
    Получение списка доступных работников с их свободными слотами.
    """
    try:
        provider_id = request.GET.get('provider_id')
        service_id = request.GET.get('service_id')
        date_str = request.GET.get('date')
        
        # Валидация параметров
        if not all([provider_id, service_id, date_str]):
            return Response({
                'error': _('Must specify provider_id, service_id and date')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Получаем объекты
        try:
            provider = Provider.objects.get(id=provider_id, is_active=True)
            service = Service.objects.get(id=service_id, is_active=True)
        except (Provider.DoesNotExist, Service.DoesNotExist):
            return Response({
                'error': _('Institution or service not found')
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Парсим дату
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({
                'error': _('Invalid date format. Use YYYY-MM-DD')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Получаем доступных работников с их слотами
        available_employees = EmployeeAutoBookingService.get_available_employees_with_slots(
            provider=provider,
            service=service,
            date=date
        )
        
        # Формируем ответ
        result = []
        for item in available_employees:
            employee = item['employee']
            result.append({
                'employee_id': employee.id,
                'employee_name': f"{employee.user.first_name} {employee.user.last_name}",
                'workload_hours': item['workload'],
                'rating': item['rating'],
                'available_slots': [
                    {
                        'start_time': slot['start_time'].isoformat(),
                        'end_time': slot['end_time'].isoformat(),
                        'duration_minutes': slot['duration_minutes']
                    }
                    for slot in item['available_slots']
                ]
            })
        
        return Response({
            'success': True,
            'available_employees': result
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': _('Error getting workers list'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CancelBookingAPIView(APIView):
    """API для отмены бронирования."""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, booking_id):
        """Отменяет бронирование."""
        if getattr(self, 'swagger_fake_view', False):
            return Response({})
        try:
            booking_queryset = with_booking_detail_related(
                scope_bookings_for_user(Booking.objects.all(), request.user)
            )
            booking = booking_queryset.get(id=booking_id)
            cancelled_by = (
                CANCELLED_BY_PROVIDER
                if request.user.has_role('provider_admin') or request.user.has_role('employee')
                else CANCELLED_BY_CLIENT
            )
            serializer = BookingCancellationActionSerializer(
                data=request.data,
                context={'cancelled_by': cancelled_by},
            )
            serializer.is_valid(raise_exception=True)
            booking.cancel_booking(
                cancelled_by=cancelled_by,
                cancelled_by_user=request.user,
                cancellation_reason=serializer.validated_data['cancellation_reason'],
                cancellation_reason_text=serializer.validated_data.get('cancellation_reason_text', ''),
                client_attendance=serializer.validated_data.get('client_attendance'),
            )
            refreshed_booking = with_booking_detail_related(
                scope_bookings_for_user(Booking.objects.all(), request.user)
            ).get(id=booking.id)
            return Response(BookingSerializer(refreshed_booking).data)
        except Booking.DoesNotExist:
            return Response({'error': _('Booking not found')}, status=status.HTTP_404_NOT_FOUND)
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

class CompleteBookingAPIView(APIView):
    """API для завершения бронирования."""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, booking_id):
        """Завершает бронирование."""
        if getattr(self, 'swagger_fake_view', False):
            return Response({})
        try:
            booking_queryset = with_booking_detail_related(
                scope_bookings_for_user(Booking.objects.all(), request.user)
            )
            booking = booking_queryset.get(id=booking_id)
            BookingCompletionService.complete_booking(booking, request.user)
            refreshed_booking = with_booking_detail_related(
                scope_bookings_for_user(Booking.objects.all(), request.user)
            ).get(id=booking.id)
            return Response(BookingSerializer(refreshed_booking).data)
        except Booking.DoesNotExist:
            return Response({'error': _('Booking not found')}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class MarkNoShowAPIView(APIView):
    """API для отметки о неявке."""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, booking_id):
        """Legacy compatibility endpoint for client no-show."""
        if getattr(self, 'swagger_fake_view', False):
            return Response({})
        try:
            booking_queryset = with_booking_detail_related(
                scope_bookings_for_user(Booking.objects.all(), request.user)
            )
            booking = booking_queryset.get(id=booking_id)
            if not (request.user.has_role('provider_admin') or request.user.has_role('employee')):
                return Response(
                    {'error': _('Only provider staff can record no-shows')},
                    status=status.HTTP_403_FORBIDDEN,
                )
            no_show_reason = BookingCancellationReason.objects.filter(
                code=CANCELLATION_REASON_CLIENT_NO_SHOW,
                is_active=True,
            ).first()
            if no_show_reason is None:
                return Response(
                    {'error': _('No-show reason is not configured')},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            booking.cancel_booking(
                cancelled_by=CANCELLED_BY_PROVIDER,
                cancelled_by_user=request.user,
                cancellation_reason=no_show_reason,
                cancellation_reason_text=request.data.get('reason_text', ''),
                client_attendance='no_show',
            )
            refreshed_booking = with_booking_detail_related(
                scope_bookings_for_user(Booking.objects.all(), request.user)
            ).get(id=booking.id)
            return Response(BookingSerializer(refreshed_booking).data)
        except Booking.DoesNotExist:
            return Response({'error': _('Booking not found')}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class GetAvailableTimeSlotsAPIView(APIView):
    """API для получения доступных временных слотов."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, booking_id):
        """Получает доступные временные слоты для бронирования."""
        if getattr(self, 'swagger_fake_view', False):
            return Response([])
        try:
            booking = Booking.objects.get(id=booking_id)
            if not booking.provider_location:
                return Response(
                    {'error': _('Provider location not found for booking')},
                    status=status.HTTP_400_BAD_REQUEST
                )

            slots_by_date = BookingAvailabilityService.get_available_slots(
                provider_location=booking.provider_location,
                service=booking.service,
                pet=booking.pet,
                requester=request.user,
                date_start=booking.start_time.date(),
                date_end=booking.start_time.date(),
            )
            return Response(slots_by_date.get(booking.start_time.date().isoformat(), []))
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST) 
