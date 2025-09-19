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
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import datetime
from .models import TimeSlot, Booking, BookingStatus, BookingPayment, BookingReview
from .serializers import (
    TimeSlotSerializer,
    TimeSlotSearchSerializer,
    BookingSerializer,
    BookingCreateSerializer,
    BookingUpdateSerializer,
    BookingPaymentSerializer,
    BookingPaymentCreateSerializer,
    BookingReviewSerializer,
    BookingReviewCreateSerializer,
    BookingStatusUpdateSerializer
)
from .utils import (
    check_booking_availability,
    calculate_booking_price,
    update_booking_status,
    get_available_time_slots
)
from .services import EmployeeAutoBookingService, BookingTransactionService
from pets.models import Pet
from providers.models import Provider, Service
from users.models import User
from rest_framework.permissions import IsAuthenticated


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
            queryset = queryset.filter(provider__admin=self.request.user)
            
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
        
        queryset = Booking.objects.all()
        
        # Для клиентов - только их бронирования
        if self.request.user.is_client():
            queryset = queryset.filter(user=self.request.user)
        
        # Для работников - бронирования с ними
        elif self.request.user.is_employee():
            queryset = queryset.filter(employee__user=self.request.user)
        
        # Для админов учреждений - бронирования их учреждения
        elif self.request.user.is_provider_admin():
            queryset = queryset.filter(provider__admin=self.request.user)
            
        return queryset
    
    def get_serializer_class(self):
        """
        Выбирает сериализатор в зависимости от действия.
        """
        if self.action == 'create':
            return BookingCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return BookingUpdateSerializer
        elif self.action == 'update_status':
            return BookingStatusUpdateSerializer
        return BookingSerializer
    
    def perform_create(self, serializer):
        """
        Создает новое бронирование.
        """
        # Проверяем доступность временного слота
        if not check_booking_availability(
            serializer.validated_data['provider'],
            serializer.validated_data['employee'],
            serializer.validated_data['start_time'],
            serializer.validated_data['end_time']
        ):
            raise serializers.ValidationError(
                _('Selected time slot is not available.')
            )
        
        # Рассчитываем стоимость
        price = calculate_booking_price(
            serializer.validated_data['service'],
            serializer.validated_data['start_time'],
            serializer.validated_data['end_time']
        )
        
        # Создаем бронирование
        booking = serializer.save(
            user=self.request.user,
            price=price,
            status=BookingStatus.objects.get(name='active')
        )
    
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
        
        # Проверяем время
        if booking.start_time <= timezone.now():
            return Response(
                {'error': _('Cannot cancel past bookings')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.cancel_by_client(request.data.get('reason', ''))
        return Response({'status': 'success'})
    
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
            if booking.provider.admin != request.user:
                return Response(
                    {'error': _('You can only cancel bookings of your provider')},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        booking.cancel_by_provider(request.data.get('reason', ''))
        return Response({'status': 'success'})
    
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
            if booking.provider.admin != request.user:
                return Response(
                    {'error': _('You can only complete bookings of your provider')},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        booking.complete(request.data.get('employee_comment', ''))
        return Response({'status': 'success'})
    
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
            if booking.provider.admin != request.user:
                return Response(
                    {'error': _('You can only mark no-shows for bookings of your provider')},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        booking.mark_no_show_by_client()
        return Response({'status': 'success'})
    
    @action(detail=True, methods=['post'])
    def mark_no_show_by_provider(self, request, pk=None):
        """
        Отметка о неявке провайдера.
        """
        booking = self.get_object()
        
        # Проверяем права
        if booking.user != request.user:
            return Response(
                {'error': _('You can only mark no-shows for your own bookings')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        booking.mark_no_show_by_provider()
        return Response({'status': 'success'})


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
            booking = Booking.objects.get(id=booking_id)
            booking.status = BookingStatus.CANCELLED
            booking.save()
            return Response({'message': 'Booking cancelled successfully'})
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CompleteBookingAPIView(APIView):
    """API для завершения бронирования."""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, booking_id):
        """Завершает бронирование."""
        if getattr(self, 'swagger_fake_view', False):
            return Response({})
        try:
            booking = Booking.objects.get(id=booking_id)
            booking.status = BookingStatus.COMPLETED
            booking.save()
            return Response({'message': 'Booking completed successfully'})
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class MarkNoShowAPIView(APIView):
    """API для отметки о неявке."""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, booking_id):
        """Отмечает неявку."""
        if getattr(self, 'swagger_fake_view', False):
            return Response({})
        try:
            booking = Booking.objects.get(id=booking_id)
            booking.status = BookingStatus.NO_SHOW
            booking.save()
            return Response({'message': 'Booking marked as no-show'})
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)
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
            # Логика получения доступных слотов
            available_slots = TimeSlot.objects.filter(
                provider=booking.provider,
                is_available=True
            ).values('id', 'start_time', 'end_time')
            return Response(list(available_slots))
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST) 