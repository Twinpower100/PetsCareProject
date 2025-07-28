"""
API представления для модуля передержки питомцев.

Этот модуль содержит представления для:
1. Управления профилями передержки
2. Поиска передержек
3. Получения профиля текущего пользователя
"""

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import SitterProfile, PetSittingAd, PetSittingResponse, Review, PetSitting
from .serializers import SitterProfileSerializer, PetSittingAdSerializer, PetSittingResponseSerializer, ReviewSerializer, PetSittingSerializer
from django.shortcuts import get_object_or_404
from django.db import models
from django.db.models import Avg
from notifications.models import Notification
from notifications.tasks import send_notification
from django.utils.translation import gettext_lazy as _
from geolocation.services import DeviceLocationService
from access.models import PetAccess
from .models import Conversation, Message
from .serializers import ConversationSerializer, ConversationDetailSerializer, MessageSerializer
from django.contrib.auth import get_user_model

User = get_user_model()


class SitterProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления профилями передержки.
    
    Предоставляет следующие endpoints:
    - GET /sitters/profiles/ - список всех профилей
    - POST /sitters/profiles/ - создание нового профиля
    - GET /sitters/profiles/{id}/ - детали конкретного профиля
    - PUT /sitters/profiles/{id}/ - обновление профиля
    - DELETE /sitters/profiles/{id}/ - удаление профиля
    
    Поддерживаемые фильтры:
    - is_active - фильтрация по активности
    - min_price - минимальная цена
    - max_price - максимальная цена
    
    Поля для поиска:
    - name - название услуги
    - description - описание услуги
    
    Поля для сортировки:
    - name - по названию
    - price - по цене
    - rating - по рейтингу
    """
    queryset = SitterProfile.objects.all()
    serializer_class = SitterProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'price', 'rating']

    def get_queryset(self):
        """
        Возвращает отфильтрованный список профилей.
        
        Поддерживает фильтрацию по:
        - Минимальной цене (min_price)
        - Максимальной цене (max_price)
        
        Returns:
            QuerySet: Отфильтрованный список профилей
        """
        queryset = SitterProfile.objects.all()
        
        # Фильтрация по ценовому диапазону
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)
            
        return queryset 


class PetSittingAdViewSet(viewsets.ModelViewSet):
    """
    ViewSet для объявлений о передержке питомцев.
    Позволяет создавать, просматривать, фильтровать и закрывать объявления.
    Поддерживает фильтрацию по дате, компенсации, статусу, питомцу, поиск по описанию и сортировку по дате, рейтингу.
    """
    serializer_class = PetSittingAdSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['start_date', 'end_date', 'compensation_type', 'status', 'pet']
    search_fields = ['description', 'pet__name']
    ordering_fields = ['start_date', 'created_at', 'rating']

    def get_queryset(self):
        """
        Возвращает queryset с аннотированным рейтингом для сортировки.
        """
        queryset = PetSittingAd.objects.all()
        # Аннотируем рейтинг ситтера, связанного с объявлением
        queryset = queryset.annotate(
            rating=Avg('responses__sitter__user__sitter_rating')
        )
        return queryset

    def perform_create(self, serializer):
        """
        Устанавливает владельца объявления текущим пользователем.
        """
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def close(self, request, pk=None):
        """
        Закрывает объявление (статус closed).
        """
        ad = self.get_object()
        ad.status = 'closed'
        ad.save()
        return Response({'status': 'closed'})


class PetSittingResponseViewSet(viewsets.ModelViewSet):
    """
    ViewSet для откликов на объявления о передержке.
    Позволяет ситтеру откликнуться, владельцу принять/отклонить отклик.
    """
    queryset = PetSittingResponse.objects.all()
    serializer_class = PetSittingResponseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        """
        Устанавливает ситтера текущим пользователем и уведомляет владельца объявления о новом отклике.
        """
        sitter_profile = get_object_or_404(SitterProfile, user=self.request.user)
        response = serializer.save(sitter=sitter_profile)
        # Уведомление владельцу объявления
        notification = Notification.objects.create(
            user=response.ad.owner,
            title='New response to your pet sitting ad',
            message=f'{self.request.user.get_full_name()} responded to your ad for {response.ad.pet}.',
            notification_type='system',
            channel='both',
            data={'ad_id': response.ad.id, 'response_id': response.id}
        )
        send_notification.delay(notification.id)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def accept(self, request, pk=None):
        """
        Принимает отклик на заявку о передержке (статус accepted), создает запись в истории передержек. 
        """
        response = self.get_object()
        if response.status != 'pending':
            return Response({'error': _('Already processed')}, status=status.HTTP_400_BAD_REQUEST)
        response.status = 'accepted'
        response.save()
        # Создать запись о передержке
        PetSitting.objects.create(
            ad=response.ad,
            response=response,
            sitter=response.sitter,
            pet=response.ad.pet,
            start_date=response.ad.start_date,
            end_date=response.ad.end_date,
            status='waiting_start',
        )
        # Уведомление ситтеру о принятии отклика
        notification = Notification.objects.create(
            user=response.sitter.user,
            title='Your response was accepted',
            message=f'Your response to the ad for {response.ad.pet} was accepted.',
            notification_type='system',
            channel='both',
            data={'ad_id': response.ad.id, 'response_id': response.id}
        )
        send_notification.delay(notification.id)
        # После response.save()
        other_responses = PetSittingResponse.objects.filter(
            ad=response.ad,
            status='pending'
        ).exclude(id=response.id)

        for other in other_responses:
            other.status = 'rejected'
            other.save()
            # Уведомление ситтеру об отклонении отклика
            notification = Notification.objects.create(
                user=other.sitter.user,
                title=_('Your response was rejected'),
                message=_('Your response to the ad for {pet} was rejected.').format(pet=other.ad.pet),
                notification_type='system',
                channel='both',
                data={'ad_id': other.ad.id, 'response_id': other.id}
            )
            send_notification.delay(notification.id)
        return Response({'status': 'accepted'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def reject(self, request, pk=None):
        """
        Отклоняет отклик на заявку о передержке до принятия какого-то отклика по какой-то причине, например, плохая оценка ситтера (статус rejected).
        """
        response = self.get_object()
        if response.status != 'pending':
            return Response({'error': _('Already processed')}, status=status.HTTP_400_BAD_REQUEST)
        response.status = 'rejected'
        response.save()
        # Уведомление ситтеру об отклонении отклика
        notification = Notification.objects.create(
            user=response.sitter.user,
            title='Your response was rejected',
            message=f'Your response to the ad for {response.ad.pet} was rejected.',
            notification_type='system',
            channel='both',
            data={'ad_id': response.ad.id, 'response_id': response.id}
        )
        send_notification.delay(notification.id)
        return Response({'status': 'rejected'})


class ReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet для отзывов о передержке.
    Позволяет оставлять и просматривать отзывы.
    """
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        """
        Устанавливает автора текущим пользователем.
        """
        serializer.save(author=self.request.user)


class PetSittingViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления процессом передержки (PetSitting).
    Позволяет подтверждать передачу/возврат, отменять, завершать с обязательной оценкой, отправлять напоминания.
    """
    queryset = PetSitting.objects.all()
    serializer_class = PetSittingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Фильтрует передержки по текущему пользователю (как владелец или ситтер).
        """
        user = self.request.user
        return PetSitting.objects.filter(
            models.Q(sitter__user=user) | models.Q(ad__owner=user)
        )

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def confirm_start(self, request, pk=None):
        """
        Подтверждение передачи питомца (обе стороны должны подтвердить).
        """
        sitting = self.get_object()
        user = request.user
        if user == sitting.ad.owner:
            sitting.owner_confirmed_start = True
        elif user == sitting.sitter.user:
            sitting.sitter_confirmed_start = True
        else:
            return Response({'error': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)
        sitting.save()
        # Уведомления о подтверждении передачи
        if user == sitting.ad.owner:
            notification = Notification.objects.create(
                user=sitting.sitter.user,
                title='Owner confirmed pet transfer',
                message=f'{user.get_full_name()} confirmed pet transfer for {sitting.pet}.',
                notification_type='system',
                channel='both',
                data={'sitting_id': sitting.id}
            )
            send_notification.delay(notification.id)
        else:
            notification = Notification.objects.create(
                user=sitting.ad.owner,
                title='Sitter confirmed pet transfer',
                message=f'{user.get_full_name()} confirmed pet transfer for {sitting.pet}.',
                notification_type='system',
                channel='both',
                data={'sitting_id': sitting.id}
            )
            send_notification.delay(notification.id)
        # Если обе стороны подтвердили — статус active, создать PetAccess и уведомить обеих
        if sitting.owner_confirmed_start and sitting.sitter_confirmed_start:
            sitting.status = 'active'
            sitting.save()
            
            # Создаем временный доступ для ситтера к питомцу
            from datetime import datetime, time
            start_datetime = datetime.combine(sitting.start_date, time.min)
            end_datetime = datetime.combine(sitting.end_date, time.max)
            
            PetAccess.objects.create(
                pet=sitting.pet,
                granted_to=sitting.sitter.user,
                granted_by=sitting.ad.owner,
                expires_at=end_datetime,
                permissions={
                    'read': True,
                    'book': True,  # Ситтер может записывать питомца на услуги
                    'write': False  # Но не может изменять данные питомца
                }
            )
            
            for notify_user in [sitting.ad.owner, sitting.sitter.user]:
                notification = Notification.objects.create(
                    user=notify_user,
                    title=_('Pet sitting started'),
                    message=_('Pet sitting for {pet} has started.').format(pet=sitting.pet),
                    notification_type='system',
                    channel='both',
                    data={'sitting_id': sitting.id}
                )
                send_notification.delay(notification.id)
        return Response(PetSittingSerializer(sitting).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def confirm_end(self, request, pk=None):
        """
        Подтверждение возврата питомца (обе стороны должны подтвердить).
        """
        sitting = self.get_object()
        user = request.user
        if user == sitting.ad.owner:
            sitting.owner_confirmed_end = True
        elif user == sitting.sitter.user:
            sitting.sitter_confirmed_end = True
        else:
            return Response({'error': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)
        sitting.save()
        # Уведомления о подтверждении возврата
        if user == sitting.ad.owner:
            notification = Notification.objects.create(
                user=sitting.sitter.user,
                title='Owner confirmed pet return',
                message=f'{user.get_full_name()} confirmed pet return for {sitting.pet}.',
                notification_type='system',
                channel='both',
                data={'sitting_id': sitting.id}
            )
            send_notification.delay(notification.id)
        else:
            notification = Notification.objects.create(
                user=sitting.ad.owner,
                title='Sitter confirmed pet return',
                message=f'{user.get_full_name()} confirmed pet return for {sitting.pet}.',
                notification_type='system',
                channel='both',
                data={'sitting_id': sitting.id}
            )
            send_notification.delay(notification.id)
        # Если обе стороны подтвердили — статус waiting_review, отозвать PetAccess и уведомить владельца
        if sitting.owner_confirmed_end and sitting.sitter_confirmed_end:
            sitting.status = 'waiting_review'
            sitting.save()
            
            # Отзываем временный доступ ситтера к питомцу
            PetAccess.objects.filter(
                pet=sitting.pet,
                granted_to=sitting.sitter.user,
                granted_by=sitting.ad.owner,
                is_active=True
            ).update(is_active=False)
            
            notification = Notification.objects.create(
                user=sitting.ad.owner,
                title=_('Leave a review for pet sitting'),
                message=_('Please leave a review for pet sitting of {pet}.').format(pet=sitting.pet),
                notification_type='system',
                channel='both',
                data={'sitting_id': sitting.id}
            )
            send_notification.delay(notification.id)
        return Response(PetSittingSerializer(sitting).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def leave_review(self, request, pk=None):
        """
        Оставить обязательный отзыв после завершения передержки (только владелец).
        """
        sitting = self.get_object()
        user = request.user
        if user != sitting.ad.owner:
            return Response({'error': 'Only owner can leave review'}, status=status.HTTP_403_FORBIDDEN)
        if sitting.status != 'waiting_review':
            return Response({'error': 'Not allowed at this stage'}, status=status.HTTP_400_BAD_REQUEST)
        # Оценка обязательна
        rating = request.data.get('rating')
        text = request.data.get('text', '')
        if not rating:
            return Response({'error': 'Rating is required'}, status=status.HTTP_400_BAD_REQUEST)
        from .models import Review
        review = Review.objects.create(
            history=sitting,
            author=user,
            rating=rating,
            text=text
        )
        sitting.review_left = True
        sitting.status = 'completed'
        sitting.save()
        # Уведомление ситтеру о завершении и отзыве
        notification = Notification.objects.create(
            user=sitting.sitter.user,
            title='Pet sitting completed and reviewed',
            message=f'Pet sitting for {sitting.pet} has been completed and reviewed.',
            notification_type='system',
            channel='both',
            data={'sitting_id': sitting.id, 'review_id': review.id}
        )
        send_notification.delay(notification.id)
        return Response({'review_id': review.id, 'status': 'completed'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def cancel(self, request, pk=None):
        """
        Отмена передержки (до передачи или по force majeure).
        """
        sitting = self.get_object()
        user = request.user
        if sitting.status in ['completed', 'cancelled']:
            return Response({'error': 'Already finished'}, status=status.HTTP_400_BAD_REQUEST)
        # Только владелец или ситтер могут отменить
        if user != sitting.ad.owner and user != sitting.sitter.user:
            return Response({'error': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)
        sitting.status = 'cancelled'
        sitting.save()
        # Уведомления обеим сторонам об отмене
        for notify_user in [sitting.ad.owner, sitting.sitter.user]:
            notification = Notification.objects.create(
                user=notify_user,
                title='Pet sitting cancelled',
                message=f'Pet sitting for {sitting.pet} has been cancelled.',
                notification_type='system',
                channel='both',
                data={'sitting_id': sitting.id}
            )
            send_notification.delay(notification.id)
        return Response({'status': 'cancelled'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def grant_access(self, request, pk=None):
        """
        Предоставить ситтеру дополнительный доступ к питомцу (опционально).
        """
        sitting = self.get_object()
        
        # Проверяем, что запрос от владельца питомца
        if request.user != sitting.ad.owner:
            return Response({'error': _('Only pet owner can grant access')}, status=status.HTTP_403_FORBIDDEN)
        
        # Проверяем, что передержка активна
        if sitting.status != 'active':
            return Response({'error': _('Pet sitting must be active to grant access')}, status=status.HTTP_400_BAD_REQUEST)
        
        # Создаем или обновляем PetAccess с расширенными правами
        from datetime import datetime, time
        end_datetime = datetime.combine(sitting.end_date, time.max)
        
        pet_access, created = PetAccess.objects.get_or_create(
            pet=sitting.pet,
            granted_to=sitting.sitter.user,
            granted_by=sitting.ad.owner,
            defaults={
                'expires_at': end_datetime,
                'permissions': {
                    'read': True,
                    'book': True,
                    'write': True  # Расширенные права
                }
            }
        )
        
        if not created:
            # Обновляем существующий доступ
            pet_access.permissions['write'] = True
            pet_access.expires_at = end_datetime
            pet_access.is_active = True
            pet_access.save()
        
        notification = Notification.objects.create(
            user=sitting.sitter.user,
            title=_('Extended access granted'),
            message=_('You have been granted extended access to {pet}.').format(pet=sitting.pet),
            notification_type='system',
            channel='both',
            data={'sitting_id': sitting.id}
        )
        send_notification.delay(notification.id)
        
        return Response({'status': 'access_granted'})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def revoke_access(self, request, pk=None):
        """
        Отозвать дополнительный доступ ситтера к питомцу.
        """
        sitting = self.get_object()
        
        # Проверяем, что запрос от владельца питомца
        if request.user != sitting.ad.owner:
            return Response({'error': _('Only pet owner can revoke access')}, status=status.HTTP_403_FORBIDDEN)
        
        # Отзываем доступ
        PetAccess.objects.filter(
            pet=sitting.pet,
            granted_to=sitting.sitter.user,
            granted_by=sitting.ad.owner,
            is_active=True
        ).update(is_active=False)
        
        notification = Notification.objects.create(
            user=sitting.sitter.user,
            title=_('Access revoked'),
            message=_('Your extended access to {pet} has been revoked.').format(pet=sitting.pet),
            notification_type='system',
            channel='both',
            data={'sitting_id': sitting.id}
        )
        send_notification.delay(notification.id)
        
        return Response({'status': 'access_revoked'})

    @action(detail=False, methods=['get'], url_path='remind')
    def remind(self, request):
        """
        Напоминания о необходимости подтверждения передачи/возврата или оставления отзыва.
        Может вызываться по расписанию (например, Celery beat).
        """
        # Найти все зависшие процессы и отправить напоминания
        count = 0
        for sitting in PetSitting.objects.filter(status__in=['waiting_start', 'waiting_end', 'waiting_review']):
            if sitting.status == 'waiting_start':
                for notify_user, role in [(sitting.ad.owner, 'owner'), (sitting.sitter.user, 'sitter')]:
                    if (role == 'owner' and not sitting.owner_confirmed_start) or (role == 'sitter' and not sitting.sitter_confirmed_start):
                        notification = Notification.objects.create(
                            user=notify_user,
                            title='Confirm pet transfer',
                            message=f'Please confirm pet transfer for {sitting.pet}.',
                            notification_type='system',
                            channel='both',
                            data={'sitting_id': sitting.id}
                        )
                        send_notification.delay(notification.id)
                        count += 1
            elif sitting.status == 'waiting_end':
                for notify_user, role in [(sitting.ad.owner, 'owner'), (sitting.sitter.user, 'sitter')]:
                    if (role == 'owner' and not sitting.owner_confirmed_end) or (role == 'sitter' and not sitting.sitter_confirmed_end):
                        notification = Notification.objects.create(
                            user=notify_user,
                            title='Confirm pet return',
                            message=f'Please confirm pet return for {sitting.pet}.',
                            notification_type='system',
                            channel='both',
                            data={'sitting_id': sitting.id}
                        )
                        send_notification.delay(notification.id)
                        count += 1
            elif sitting.status == 'waiting_review' and not sitting.review_left:
                notification = Notification.objects.create(
                    user=sitting.ad.owner,
                    title='Leave a review for pet sitting',
                    message=f'Please leave a review for pet sitting of {sitting.pet}.',
                    notification_type='system',
                    channel='both',
                    data={'sitting_id': sitting.id}
                )
                send_notification.delay(notification.id)
                count += 1
        return Response({'reminders_sent': count})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def search_sitters(request):
    """
    Поиск ситтеров по геолокации с учетом ролей пользователей.
    
    Логика определения местоположения по ролям:
    1. Обычный пользователь: адрес НЕ обязателен, используется геолокация устройства
    2. Ситтер: адрес ОБЯЗАТЕЛЕН (где оказывает услуги)
    3. Учреждение: адрес ОБЯЗАТЕЛЕН (где находится учреждение)
    
    Параметры:
    - latitude, longitude: Координаты (опционально)
    - radius: Радиус поиска в км (по умолчанию 10)
    - service_type: Тип услуги (опционально)
    - price_min, price_max: Диапазон цен (опционально)
    - rating_min: Минимальный рейтинг (опционально)
    - available_from, available_to: Период доступности (опционально)
    """
    try:
        # Получаем параметры поиска
        latitude = request.GET.get('latitude')
        longitude = request.GET.get('longitude')
        radius = float(request.GET.get('radius', 10))
        service_type = request.GET.get('service_type')
        price_min = request.GET.get('price_min')
        price_max = request.GET.get('price_max')
        rating_min = request.GET.get('rating_min')
        available_from = request.GET.get('available_from')
        available_to = request.GET.get('available_to')
        
        # Проверяем требования к адресу для пользователя
        device_service = DeviceLocationService()
        address_check = device_service.check_address_requirement(request.user)
        
        # Определяем местоположение для поиска
        search_lat = None
        search_lon = None
        location_source = None
        
        if latitude and longitude:
            # Используем переданные координаты
            try:
                search_lat = float(latitude)
                search_lon = float(longitude)
                location_source = 'request_coordinates'
            except ValueError:
                return Response({
                    'success': False,
                    'error': _('Invalid coordinates format')
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Проверяем роль пользователя
            if address_check['address_required'] and address_check['missing_address']:
                # Адрес обязателен, но отсутствует
                return Response({
                    'success': False,
                    'error': _('Address required'),
                    'message': address_check['message'],
                    'role': address_check['role'],
                    'requires_address': True
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Если адрес не обязателен или есть адрес, используем местоположение пользователя
            user_location = device_service.get_user_location(request.user)
            
            if user_location:
                search_lat = float(user_location['latitude'])
                search_lon = float(user_location['longitude'])
                location_source = 'user_location'
            else:
                # Местоположение не определено
                if address_check['address_required']:
                    # Для ситтеров и учреждений адрес обязателен
                    return Response({
                        'success': False,
                        'error': _('Address required'),
                        'message': address_check['message'],
                        'role': address_check['role'],
                        'requires_address': True
                    }, status=status.HTTP_400_BAD_REQUEST)
                else:
                    # Для обычных пользователей требуем включить геолокацию
                    return Response({
                        'success': False,
                        'error': _('Location not available'),
                        'message': _('Please enable device location or select area on map'),
                        'requires_location': True
                    }, status=status.HTTP_400_BAD_REQUEST)
        
        # Валидируем параметры поиска
        if not (-90 <= search_lat <= 90) or not (-180 <= search_lon <= 180):
            return Response({
                'success': False,
                'error': _('Invalid coordinates')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not (0.1 <= radius <= 100):
            return Response({
                'success': False,
                'error': _('Invalid search radius (0.1-100 km)')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Выполняем поиск ситтеров
        sitters = SitterProfile.objects.filter(is_active=True)
        
        # Фильтрация по расстоянию
        sitters_with_distance = []
        for sitter in sitters:
            # Проверяем, есть ли у ситтера адрес (обязательно для ситтеров)
            if not sitter.user.address:
                continue  # Пропускаем ситтеров без адреса
            
            if sitter.user.address.latitude and sitter.user.address.longitude:
                distance = sitter.user.address.distance_to(search_lat, search_lon)
                if distance <= radius:
                    sitters_with_distance.append({
                        'sitter': sitter,
                        'distance': distance
                    })
        
        # Сортировка по расстоянию
        sitters_with_distance.sort(key=lambda x: x['distance'])
        
        # Применяем дополнительные фильтры
        filtered_sitters = []
        for item in sitters_with_distance:
            sitter = item['sitter']
            
            # Фильтр по типу услуги
            if service_type and service_type not in sitter.services.all().values_list('name', flat=True):
                continue
            
            # Фильтр по цене
            if price_min and sitter.hourly_rate < float(price_min):
                continue
            if price_max and sitter.hourly_rate > float(price_max):
                continue
            
            # Фильтр по рейтингу
            if rating_min and sitter.rating < float(rating_min):
                continue
            
            # Фильтр по доступности
            if available_from and available_to:
                # Здесь должна быть логика проверки доступности
                # Пока пропускаем этот фильтр
                pass
            
            filtered_sitters.append(item)
        
        # Формируем ответ
        result = []
        for item in filtered_sitters:
            sitter = item['sitter']
            result.append({
                'id': sitter.id,
                'name': f"{sitter.user.first_name} {sitter.user.last_name}",
                'rating': sitter.rating,
                'hourly_rate': sitter.hourly_rate,
                'services': list(sitter.services.all().values_list('name', flat=True)),
                'experience_years': sitter.experience_years,
                'bio': sitter.bio,
                'distance_km': round(item['distance'], 2),
                'location': {
                    'latitude': float(sitter.user.address.latitude),
                    'longitude': float(sitter.user.address.longitude),
                    'address': sitter.user.address.formatted_address
                }
            })
        
        return Response({
            'success': True,
            'sitters': result,
            'search_params': {
                'latitude': search_lat,
                'longitude': search_lon,
                'radius_km': radius,
                'location_source': location_source,
                'total_found': len(result)
            },
            'user_role_info': {
                'role': address_check['role'],
                'address_required': address_check['address_required'],
                'has_address': address_check['has_address']
            }
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': _('Error searching sitters'),
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 


class ConversationViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления диалогами между владельцами и ситтерами.
    """
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает диалоги текущего пользователя"""
        return Conversation.objects.filter(
            participants=self.request.user,
            is_active=True
        )

    def get_serializer_class(self):
        """Выбирает сериализатор в зависимости от действия"""
        if self.action == 'retrieve':
            return ConversationDetailSerializer
        return ConversationSerializer

    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """
        Отправка сообщения в диалог.
        """
        conversation = self.get_object()
        text = request.data.get('text', '').strip()
        
        if not text:
            return Response({'error': _('Message text is required')}, status=status.HTTP_400_BAD_REQUEST)
        
        # Создаем сообщение
        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            text=text
        )
        
        # Отправляем уведомление другому участнику
        other_participant = conversation.get_other_participant(request.user)
        if other_participant:
            notification = Notification.objects.create(
                user=other_participant,
                title=_('New message'),
                message=_('You have a new message from {sender}').format(sender=request.user.get_full_name()),
                notification_type='chat',
                channel='both',
                data={
                    'conversation_id': conversation.id,
                    'message_id': message.id
                }
            )
            send_notification.delay(notification.id)
        
        return Response(MessageSerializer(message).data)

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """
        Отмечает все сообщения в диалоге как прочитанные.
        """
        conversation = self.get_object()
        user = request.user
        
        # Отмечаем все непрочитанные сообщения от других участников
        conversation.messages.filter(
            is_read=False
        ).exclude(
            sender=user
        ).update(is_read=True)
        
        return Response({'status': 'marked_as_read'})

    @action(detail=False, methods=['post'])
    def create_or_get(self, request):
        """
        Создает новый диалог или возвращает существующий.
        """
        other_user_id = request.data.get('other_user_id')
        ad_id = request.data.get('ad_id')
        sitting_id = request.data.get('sitting_id')
        
        if not other_user_id:
            return Response({'error': _('other_user_id is required')}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            other_user = User.objects.get(id=other_user_id)
        except User.DoesNotExist:
            return Response({'error': _('User not found')}, status=status.HTTP_404_NOT_FOUND)
        
        # Ищем существующий диалог
        conversation = Conversation.objects.filter(
            participants=request.user
        ).filter(
            participants=other_user
        ).filter(
            is_active=True
        ).first()
        
        if not conversation:
            # Создаем новый диалог
            conversation = Conversation.objects.create()
            conversation.participants.add(request.user, other_user)
            
            # Привязываем к объявлению или передержке
            if ad_id:
                try:
                    ad = PetSittingAd.objects.get(id=ad_id)
                    conversation.pet_sitting_ad = ad
                    conversation.save()
                except PetSittingAd.DoesNotExist:
                    pass
            elif sitting_id:
                try:
                    sitting = PetSitting.objects.get(id=sitting_id)
                    conversation.pet_sitting = sitting
                    conversation.save()
                except PetSitting.DoesNotExist:
                    pass
        
        return Response(ConversationDetailSerializer(conversation, context={'request': request}).data) 