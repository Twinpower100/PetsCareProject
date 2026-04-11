"""
API представления для модуля передержки питомцев.

Этот модуль содержит endpoints для:
1. Профиля ситтера
2. Объявлений владельцев
3. Откликов ситтеров
4. Жизненного цикла передержки
5. Отзывов и чатов
6. Геопоиска ситтеров
"""

from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from access.models import PetAccess
from notifications.models import Notification
from pets.models import Pet
from pets.serializers import PetSerializer
from users.email_verification_permissions import require_verified_email_for_owner_action

from .models import Conversation, Message, PetSitting, PetSittingAd, PetSittingRequest, PetSittingResponse, SitterProfile, SitterReview
from .serializers import (
    ConversationDetailSerializer,
    ConversationSerializer,
    MessageSerializer,
    PetSittingAdSerializer,
    PetSittingRequestSerializer,
    PetSittingResponseSerializer,
    PetSittingSerializer,
    SitterProfileSerializer,
    SitterReviewSerializer,
)

User = get_user_model()

CAPACITY_BLOCKING_STATUSES = ('waiting_start', 'active', 'waiting_review')


def _normalize_language_code(raw_value: str | None) -> str:
    """
    Нормализует язык пользователя до поддерживаемого кода.
    """
    if not raw_value:
        return 'en'

    language_code = raw_value.split('-')[0].strip().lower()
    if language_code not in {'en', 'ru', 'me', 'de'}:
        return 'en'
    return language_code


def _build_frontend_url(path: str) -> str:
    """
    Собирает абсолютную ссылку на публичный frontend.
    """
    base_url = settings.FRONTEND_URL.rstrip('/')
    normalized_path = path if path.startswith('/') else f'/{path}'
    return f'{base_url}{normalized_path}'


def _notify_user(
    user,
    *,
    title: str,
    message: str,
    notification_type: str = 'pet_sitting',
    data: dict | None = None,
    pet=None,
) -> Notification:
    """
    Создаёт уведомление и сразу отправляет email/in-app каналами.
    """
    notification_data = dict(data or {})
    language_code = _normalize_language_code(getattr(user, 'preferred_language', None))

    with translation.override(language_code):
        notification = Notification.objects.create(
            user=user,
            pet=pet,
            notification_type=notification_type,
            title=str(title),
            message=str(message),
            channel='all',
            data=notification_data,
        )
    notification.send()
    return notification


def _parse_iso_date(raw_value: str | None, field_name: str) -> date | None:
    """
    Преобразует ISO-дату из запроса и валидирует формат.
    """
    if not raw_value:
        return None

    parsed_value = parse_date(raw_value)
    if parsed_value is None:
        raise ValidationError({field_name: _('Invalid date format. Use YYYY-MM-DD.')})
    return parsed_value


def _resolve_search_coordinates(request) -> tuple[float, float, str]:
    """
    Определяет координаты поиска из запроса или сохранённой геолокации.
    """
    latitude = request.query_params.get('latitude')
    longitude = request.query_params.get('longitude')

    if latitude and longitude:
        try:
            return float(latitude), float(longitude), 'request_coordinates'
        except (TypeError, ValueError) as exc:
            raise ValidationError({'coordinates': _('Invalid coordinates format')}) from exc

    user_location = getattr(request.user, 'user_location', None)
    if user_location and user_location.point:
        return float(user_location.point.y), float(user_location.point.x), 'user_location'

    raise ValidationError({'coordinates': _('Provide search coordinates or save your location first.')})


def _has_matching_pet_type(profile_pet_types: list, requested_pet_types: set[str]) -> bool:
    """
    Проверяет совместимость профиля ситтера с типом питомца.
    """
    if not requested_pet_types:
        return True

    normalized_profile_types = {str(value).strip().lower() for value in (profile_pet_types or []) if str(value).strip()}
    return bool(normalized_profile_types & requested_pet_types)


def _ensure_response_capacity(response: PetSittingResponse) -> int:
    """
    Проверяет вместимость ситтера на даты объявления.
    """
    overlapping_sittings = PetSitting.objects.select_for_update().filter(
        sitter=response.sitter,
        status__in=CAPACITY_BLOCKING_STATUSES,
        start_date__lte=response.ad.end_date,
        end_date__gte=response.ad.start_date,
    )
    current_load = overlapping_sittings.count()

    if current_load >= response.sitter.max_pets:
        raise ValidationError({'max_pets': _('Sitter capacity is exceeded for the selected dates.')})

    return current_load


def _ensure_request_capacity(sitting_request: PetSittingRequest) -> int:
    """
    Проверяет вместимость ситтера на даты прямого запроса.
    """
    overlapping_sittings = PetSitting.objects.select_for_update().filter(
        sitter=sitting_request.sitter,
        status__in=CAPACITY_BLOCKING_STATUSES,
        start_date__lte=sitting_request.end_date,
        end_date__gte=sitting_request.start_date,
    )
    current_load = overlapping_sittings.count()

    if current_load >= sitting_request.sitter.max_pets:
        raise ValidationError({'max_pets': _('Sitter capacity is exceeded for the selected dates.')})

    return current_load


def _get_or_create_conversation(*, owner, sitter_user, ad: PetSittingAd | None = None, sitting: PetSitting | None = None) -> Conversation:
    """
    Возвращает существующий чат между владельцем и ситтером или создаёт новый.
    """
    relation_filter = Q()
    if ad is not None:
        relation_filter &= Q(pet_sitting_ad=ad)
    if sitting is not None:
        relation_filter &= Q(pet_sitting=sitting)

    conversation = Conversation.objects.filter(
        participants=owner,
        is_active=True,
    ).filter(
        participants=sitter_user,
    ).filter(relation_filter).first()

    if conversation is None:
        conversation = Conversation.objects.create(
            pet_sitting_ad=ad,
            pet_sitting=sitting,
        )
        conversation.participants.add(owner, sitter_user)
        return conversation

    updated_fields: list[str] = []
    if ad is not None and conversation.pet_sitting_ad_id is None:
        conversation.pet_sitting_ad = ad
        updated_fields.append('pet_sitting_ad')
    if sitting is not None and conversation.pet_sitting_id is None:
        conversation.pet_sitting = sitting
        updated_fields.append('pet_sitting')
    if updated_fields:
        conversation.save(update_fields=updated_fields + ['updated_at'])
    return conversation


def _attach_request_conversation(
    conversation: Conversation | None,
    *,
    ad: PetSittingAd | None = None,
    sitting: PetSitting | None = None,
) -> Conversation | None:
    """
    Привязывает к уже существующему диалогу служебные сущности прямого запроса.
    """
    if conversation is None:
        return None

    updated_fields: list[str] = []
    if ad is not None and conversation.pet_sitting_ad_id is None:
        conversation.pet_sitting_ad = ad
        updated_fields.append('pet_sitting_ad')
    if sitting is not None and conversation.pet_sitting_id is None:
        conversation.pet_sitting = sitting
        updated_fields.append('pet_sitting')

    if updated_fields:
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=updated_fields + ['updated_at'])
    return conversation


def _upsert_pet_access(sitting: PetSitting, *, allow_write: bool) -> PetAccess:
    """
    Создаёт или обновляет доступ ситтера к карточке питомца.
    """
    end_datetime = timezone.make_aware(datetime.combine(sitting.end_date, time.max))
    existing_access = PetAccess.objects.select_for_update().filter(
        pet=sitting.pet,
        granted_to=sitting.sitter.user,
        granted_by=sitting.ad.owner,
    ).first()

    permissions_payload = {
        'read': True,
        'book': True,
        'write': allow_write,
    }

    if existing_access is None:
        return PetAccess.objects.create(
            pet=sitting.pet,
            granted_to=sitting.sitter.user,
            granted_by=sitting.ad.owner,
            expires_at=end_datetime,
            permissions=permissions_payload,
            is_active=True,
        )

    existing_access.expires_at = end_datetime
    existing_access.permissions = permissions_payload
    existing_access.is_active = True
    existing_access.save(update_fields=['expires_at', 'permissions', 'is_active'])
    return existing_access


def _deactivate_pet_access(sitting: PetSitting) -> int:
    """
    Полностью отключает временный доступ ситтера к питомцу.
    """
    return PetAccess.objects.filter(
        pet=sitting.pet,
        granted_to=sitting.sitter.user,
        granted_by=sitting.ad.owner,
        is_active=True,
    ).update(is_active=False)


class SitterProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet для профилей ситтеров с кабинетом текущего пользователя.
    """

    serializer_class = SitterProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['user__first_name', 'user__last_name', 'description']
    ordering_fields = ['hourly_rate', 'created_at', 'experience_years']

    def get_queryset(self):
        """
        Возвращает профили ситтеров с безопасной областью видимости.
        """
        if getattr(self, 'swagger_fake_view', False):
            return SitterProfile.objects.none()

        queryset = SitterProfile.objects.select_related('user', 'user__user_location').annotate(
            rating_value=Avg('sittings__reviews__rating'),
            reviews_count_value=Count('sittings__reviews', distinct=True),
        )

        if self.action in {'update', 'partial_update', 'destroy', 'me'}:
            return queryset.filter(user=self.request.user).order_by('-updated_at', '-id')

        if self.request.query_params.get('mine') == 'true':
            return queryset.filter(user=self.request.user).order_by('-updated_at', '-id')

        return queryset.filter(Q(is_active=True) | Q(user=self.request.user)).order_by('-updated_at', '-id')

    def perform_create(self, serializer):
        """
        Создаёт профиль ситтера для текущего пользователя.
        """
        if SitterProfile.objects.filter(user=self.request.user).exists():
            raise ValidationError({'detail': _('Sitter profile already exists for this user.')})

        serializer.save(user=self.request.user)
        self.request.user.add_role('pet_sitter')

    @action(detail=False, methods=['get', 'post', 'put', 'patch'])
    def me(self, request):
        """
        Возвращает или обновляет профиль ситтера текущего пользователя.
        """
        profile = SitterProfile.objects.filter(user=request.user).select_related('user', 'user__user_location').first()
        profile_already_exists = profile is not None

        if request.method == 'GET':
            if profile is None:
                return Response({'detail': _('Sitter profile was not found.')}, status=status.HTTP_404_NOT_FOUND)
            serializer = self.get_serializer(profile)
            return Response(serializer.data)

        partial = request.method == 'PATCH'
        serializer = self.get_serializer(instance=profile, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save(user=request.user)
        request.user.add_role('pet_sitter')
        response_status = status.HTTP_200_OK if profile_already_exists else status.HTTP_201_CREATED
        return Response(self.get_serializer(profile).data, status=response_status)


class PetSittingAdViewSet(viewsets.ModelViewSet):
    """
    ViewSet объявлений владельцев о поиске передержки.
    """

    serializer_class = PetSittingAdSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['description', 'pet__name', 'location']
    ordering_fields = ['start_date', 'created_at']

    def get_queryset(self):
        """
        Возвращает объявления владельцев с фильтрацией по роли запроса.
        """
        if getattr(self, 'swagger_fake_view', False):
            return PetSittingAd.objects.none()

        queryset = PetSittingAd.objects.select_related('pet', 'pet__pet_type', 'pet__breed', 'owner', 'structured_address').prefetch_related(
            'pet__chronic_conditions'
        ).annotate(
            responses_count=Count('responses', distinct=True)
        )

        queryset = queryset.filter(visibility='public')

        if self.action in {'update', 'partial_update', 'destroy', 'close'}:
            queryset = queryset.filter(owner=self.request.user)
        elif self.request.query_params.get('mine') == 'true':
            queryset = queryset.filter(owner=self.request.user)
        else:
            queryset = queryset.filter(Q(status='active') | Q(owner=self.request.user))

        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        compensation_type = self.request.query_params.get('compensation_type')
        if compensation_type:
            queryset = queryset.filter(compensation_type=compensation_type)

        return queryset.order_by('-created_at', '-id')

    def perform_create(self, serializer):
        """
        Создаёт объявление от имени текущего пользователя.
        """
        require_verified_email_for_owner_action(self.request.user)
        pet = serializer.validated_data['pet']
        if not pet.owners.filter(id=self.request.user.id).exists():
            raise ValidationError({'pet': _('You can create pet sitting ads only for your own pets')})
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """
        Закрывает объявление владельца.
        """
        require_verified_email_for_owner_action(request.user)
        ad = self.get_object()
        ad.status = 'closed'
        ad.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(ad).data)


class PetSittingResponseViewSet(viewsets.ModelViewSet):
    """
    ViewSet откликов ситтеров на объявления владельцев.
    """

    serializer_class = PetSittingResponseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Возвращает отклики, видимые владельцу или ситтеру.
        """
        if getattr(self, 'swagger_fake_view', False):
            return PetSittingResponse.objects.none()

        queryset = PetSittingResponse.objects.select_related(
            'ad',
            'ad__pet',
            'ad__pet__pet_type',
            'ad__pet__breed',
            'ad__structured_address',
            'ad__owner',
            'sitter',
            'sitter__user',
        ).prefetch_related(
            'ad__pet__chronic_conditions'
        ).filter(
            Q(ad__owner=self.request.user) | Q(sitter__user=self.request.user),
            ad__visibility='public',
        )

        role = self.request.query_params.get('role')
        if role == 'owner':
            queryset = queryset.filter(ad__owner=self.request.user)
        elif role == 'sitter':
            queryset = queryset.filter(sitter__user=self.request.user)

        ad_id = self.request.query_params.get('ad')
        if ad_id:
            queryset = queryset.filter(ad_id=ad_id)

        response_status_value = self.request.query_params.get('status')
        if response_status_value:
            queryset = queryset.filter(status=response_status_value)

        return queryset.order_by('-created_at', '-id')

    def perform_create(self, serializer):
        """
        Создаёт отклик текущего ситтера на объявление владельца.
        """
        sitter_profile = get_object_or_404(SitterProfile, user=self.request.user)
        ad = serializer.validated_data['ad']

        if not sitter_profile.is_active:
            raise ValidationError({'detail': _('Activate your sitter profile before responding to ads.')})
        if ad.owner_id == self.request.user.id:
            raise ValidationError({'detail': _('Owners cannot respond to their own ads.')})
        if ad.status != 'active':
            raise ValidationError({'detail': _('You can respond only to active ads.')})
        if ad.visibility != 'public':
            raise ValidationError({'detail': _('You can respond only to public ads.')})

        duplicate_exists = PetSittingResponse.objects.filter(
            ad=ad,
            sitter=sitter_profile,
        ).exclude(status='rejected').exists()
        if duplicate_exists:
            raise ValidationError({'detail': _('You have already responded to this ad.')})

        response = serializer.save(sitter=sitter_profile)
        _get_or_create_conversation(owner=ad.owner, sitter_user=sitter_profile.user, ad=ad)

        _notify_user(
            ad.owner,
            title=_('New pet sitting response'),
            message=_('%(user)s responded to your ad for %(pet)s. Open PetsCare to review the response and continue the conversation.') % {
                'user': self.request.user.get_full_name() or self.request.user.email,
                'pet': ad.pet.name,
            },
            pet=ad.pet,
            data={
                'ad_id': ad.id,
                'response_id': response.id,
                'action_url': _build_frontend_url(f'/boarding?tab=ownerAds&ad={ad.id}'),
            },
        )

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def accept(self, request, pk=None):
        """
        Принимает отклик и создаёт передержку с проверкой вместимости.
        """
        require_verified_email_for_owner_action(request.user)
        response = get_object_or_404(
            PetSittingResponse.objects.select_for_update().select_related(
                'ad',
                'ad__pet',
                'ad__owner',
                'sitter',
                'sitter__user',
            ),
            pk=pk,
        )

        if response.ad.owner_id != request.user.id:
            raise PermissionDenied(_('Only the owner can accept a pet sitting response.'))
        if response.status != 'pending':
            raise ValidationError({'detail': _('This response has already been processed.')})

        response.sitter = SitterProfile.objects.select_for_update().get(pk=response.sitter_id)
        _ensure_response_capacity(response)

        response.status = 'accepted'
        response.save(update_fields=['status'])

        sitting = PetSitting.objects.create(
            ad=response.ad,
            response=response,
            sitter=response.sitter,
            pet=response.ad.pet,
            start_date=response.ad.start_date,
            end_date=response.ad.end_date,
            status='waiting_start',
        )

        rejected_responses = PetSittingResponse.objects.select_for_update().filter(
            ad=response.ad,
            status='pending',
        ).exclude(pk=response.pk)

        for other_response in rejected_responses:
            other_response.status = 'rejected'
            other_response.save(update_fields=['status'])
            _notify_user(
                other_response.sitter.user,
                title=_('Your pet sitting response was rejected'),
                message=_('Your response to the ad for %(pet)s was not selected.') % {
                    'pet': response.ad.pet.name,
                },
                pet=response.ad.pet,
                data={
                    'ad_id': response.ad.id,
                    'response_id': other_response.id,
                    'action_url': _build_frontend_url(f'/boarding?tab=sitterSearch&ad={response.ad.id}'),
                },
            )

        response.ad.status = 'closed'
        response.ad.save(update_fields=['status', 'updated_at'])

        _get_or_create_conversation(
            owner=response.ad.owner,
            sitter_user=response.sitter.user,
            ad=response.ad,
            sitting=sitting,
        )

        _notify_user(
            response.sitter.user,
            title=_('Your pet sitting response was accepted'),
            message=_('Your response to the ad for %(pet)s was accepted.') % {'pet': response.ad.pet.name},
            pet=response.ad.pet,
            data={
                'ad_id': response.ad.id,
                'response_id': response.id,
                'sitting_id': sitting.id,
                'action_url': _build_frontend_url(f'/boarding?tab=stays&sitting={sitting.id}'),
            },
        )

        serializer = PetSittingSerializer(sitting, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reject(self, request, pk=None):
        """
        Отклоняет отклик ситтера.
        """
        require_verified_email_for_owner_action(request.user)
        response = get_object_or_404(
            PetSittingResponse.objects.select_for_update().select_related('ad', 'ad__owner', 'ad__pet', 'sitter__user'),
            pk=pk,
        )

        if response.ad.owner_id != request.user.id:
            raise PermissionDenied(_('Only the owner can reject a pet sitting response.'))
        if response.status != 'pending':
            raise ValidationError({'detail': _('This response has already been processed.')})

        response.status = 'rejected'
        response.save(update_fields=['status'])

        _notify_user(
            response.sitter.user,
            title=_('Your pet sitting response was rejected'),
            message=_('Your response to the ad for %(pet)s was rejected.') % {'pet': response.ad.pet.name},
            pet=response.ad.pet,
            data={
                'ad_id': response.ad.id,
                'response_id': response.id,
                'action_url': _build_frontend_url(f'/boarding?tab=sitterSearch&ad={response.ad.id}'),
            },
        )

        return Response(self.get_serializer(response).data)


class PetSittingRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet прямых owner -> sitter запросов на передержку.
    """

    serializer_class = PetSittingRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Возвращает прямые запросы, видимые владельцу или ситтеру.
        """
        if getattr(self, 'swagger_fake_view', False):
            return PetSittingRequest.objects.none()

        queryset = PetSittingRequest.objects.select_related(
            'owner',
            'pet',
            'pet__pet_type',
            'pet__breed',
            'sitter',
            'sitter__user',
            'conversation',
            'pet_sitting',
            'structured_address',
        ).prefetch_related(
            'pet__chronic_conditions'
        ).filter(
            Q(owner=self.request.user) | Q(sitter__user=self.request.user)
        )

        role = self.request.query_params.get('role')
        if role == 'owner':
            queryset = queryset.filter(owner=self.request.user)
        elif role == 'sitter':
            queryset = queryset.filter(sitter__user=self.request.user)

        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        conversation_id = self.request.query_params.get('conversation')
        if conversation_id:
            queryset = queryset.filter(conversation_id=conversation_id)

        return queryset.order_by('-created_at', '-id')

    @transaction.atomic
    def perform_create(self, serializer):
        """
        Создаёт прямой запрос владельца к ситтеру.
        """
        require_verified_email_for_owner_action(self.request.user)

        sitter_profile = SitterProfile.objects.select_for_update().select_related('user').get(
            pk=serializer.validated_data['sitter'].pk
        )
        pet = serializer.validated_data['pet']

        if not pet.owners.filter(id=self.request.user.id).exists():
            raise ValidationError({'pet': _('You can create pet sitting requests only for your own pets.')})
        if sitter_profile.user_id == self.request.user.id:
            raise ValidationError({'sitter': _('You cannot create a pet sitting request for yourself.')})
        if not sitter_profile.is_active:
            raise ValidationError({'sitter': _('Activate the sitter profile before sending a direct request.')})

        duplicate_exists = PetSittingRequest.objects.select_for_update().filter(
            owner=self.request.user,
            sitter=sitter_profile,
            pet=pet,
            start_date=serializer.validated_data['start_date'],
            end_date=serializer.validated_data['end_date'],
            status=PetSittingRequest.STATUS_PENDING,
        ).exists()
        if duplicate_exists:
            raise ValidationError({'detail': _('You already have a pending pet sitting request for this pet and sitter.')})

        conversation = None
        conversation_id = self.request.data.get('conversation_id')
        if conversation_id:
            conversation = get_object_or_404(
                Conversation.objects.prefetch_related('participants'),
                pk=conversation_id,
                is_active=True,
                participants=self.request.user,
            )
            if not conversation.participants.filter(id=sitter_profile.user_id).exists():
                raise ValidationError({'conversation_id': _('The selected conversation does not belong to this sitter.')})
        else:
            conversation = _get_or_create_conversation(owner=self.request.user, sitter_user=sitter_profile.user)

        pet_sitting_request = serializer.save(
            owner=self.request.user,
            initiated_by=self.request.user,
            sitter=sitter_profile,
            conversation=conversation,
        )

        _notify_user(
            sitter_profile.user,
            title=_('New pet sitting request'),
            message=_('%(owner)s sent you a pet sitting request for %(pet)s. Open PetsCare to accept or decline it.') % {
                'owner': self.request.user.get_full_name() or self.request.user.email,
                'pet': pet.name,
            },
            pet=pet,
            data={
                'request_id': pet_sitting_request.id,
                'conversation_id': conversation.id if conversation else None,
                'action_url': _build_frontend_url(f'/boarding?tab=requests&request={pet_sitting_request.id}'),
            },
        )

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def accept(self, request, pk=None):
        """
        Принимает прямой запрос и создаёт внутреннюю передержку.
        """
        pet_sitting_request = get_object_or_404(
            PetSittingRequest.objects.select_for_update().select_related(
                'owner',
                'pet',
                'sitter',
                'sitter__user',
            ),
            pk=pk,
        )

        if pet_sitting_request.sitter.user_id != request.user.id:
            raise PermissionDenied(_('Only the sitter can accept a direct pet sitting request.'))
        if pet_sitting_request.status != PetSittingRequest.STATUS_PENDING:
            raise ValidationError({'detail': _('This pet sitting request has already been processed.')})

        pet_sitting_request.sitter = SitterProfile.objects.select_for_update().get(pk=pet_sitting_request.sitter_id)
        _ensure_request_capacity(pet_sitting_request)

        internal_ad = PetSittingAd.objects.create(
            pet=pet_sitting_request.pet,
            owner=pet_sitting_request.owner,
            start_date=pet_sitting_request.start_date,
            end_date=pet_sitting_request.end_date,
            description=pet_sitting_request.message,
            status='closed',
            visibility='internal',
            location=pet_sitting_request.location,
            structured_address=pet_sitting_request.structured_address,
            max_distance_km=pet_sitting_request.sitter.max_distance_km,
            compensation_type=pet_sitting_request.sitter.compensation_type,
        )
        internal_response = PetSittingResponse.objects.create(
            ad=internal_ad,
            sitter=pet_sitting_request.sitter,
            message=pet_sitting_request.message,
            status='accepted',
        )
        sitting = PetSitting.objects.create(
            ad=internal_ad,
            response=internal_response,
            sitter=pet_sitting_request.sitter,
            pet=pet_sitting_request.pet,
            start_date=pet_sitting_request.start_date,
            end_date=pet_sitting_request.end_date,
            status='waiting_start',
        )

        pet_sitting_request.status = PetSittingRequest.STATUS_ACCEPTED
        pet_sitting_request.version += 1
        pet_sitting_request.created_ad = internal_ad
        pet_sitting_request.created_response = internal_response
        pet_sitting_request.pet_sitting = sitting

        conversation = pet_sitting_request.conversation or _get_or_create_conversation(
            owner=pet_sitting_request.owner,
            sitter_user=pet_sitting_request.sitter.user,
        )
        pet_sitting_request.conversation = _attach_request_conversation(
            conversation,
            ad=internal_ad,
            sitting=sitting,
        )
        pet_sitting_request.save(
            update_fields=[
                'status',
                'version',
                'created_ad',
                'created_response',
                'pet_sitting',
                'conversation',
                'updated_at',
            ]
        )

        _notify_user(
            pet_sitting_request.owner,
            title=_('Your pet sitting request was accepted'),
            message=_('%(sitter)s accepted your pet sitting request for %(pet)s. Open PetsCare to review the stay and continue in chat.') % {
                'sitter': pet_sitting_request.sitter.user.get_full_name() or pet_sitting_request.sitter.user.email,
                'pet': pet_sitting_request.pet.name,
            },
            pet=pet_sitting_request.pet,
            data={
                'request_id': pet_sitting_request.id,
                'sitting_id': sitting.id,
                'conversation_id': pet_sitting_request.conversation_id,
                'action_url': _build_frontend_url(f'/boarding?tab=stays&sitting={sitting.id}'),
            },
        )

        serializer = self.get_serializer(pet_sitting_request)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reject(self, request, pk=None):
        """
        Отклоняет прямой запрос владельца.
        """
        pet_sitting_request = get_object_or_404(
            PetSittingRequest.objects.select_for_update().select_related('owner', 'pet', 'sitter__user'),
            pk=pk,
        )

        if pet_sitting_request.sitter.user_id != request.user.id:
            raise PermissionDenied(_('Only the sitter can reject a direct pet sitting request.'))
        if pet_sitting_request.status != PetSittingRequest.STATUS_PENDING:
            raise ValidationError({'detail': _('This pet sitting request has already been processed.')})

        pet_sitting_request.status = PetSittingRequest.STATUS_REJECTED
        pet_sitting_request.version += 1
        pet_sitting_request.save(update_fields=['status', 'version', 'updated_at'])

        _notify_user(
            pet_sitting_request.owner,
            title=_('Your pet sitting request was declined'),
            message=_('%(sitter)s declined your pet sitting request for %(pet)s. Open PetsCare to review the request history or continue the conversation.') % {
                'sitter': pet_sitting_request.sitter.user.get_full_name() or pet_sitting_request.sitter.user.email,
                'pet': pet_sitting_request.pet.name,
            },
            pet=pet_sitting_request.pet,
            data={
                'request_id': pet_sitting_request.id,
                'action_url': _build_frontend_url(f'/boarding?tab=requests&request={pet_sitting_request.id}'),
            },
        )

        return Response(self.get_serializer(pet_sitting_request).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def cancel(self, request, pk=None):
        """
        Отменяет исходящий прямой запрос владельца.
        """
        require_verified_email_for_owner_action(request.user)
        pet_sitting_request = get_object_or_404(
            PetSittingRequest.objects.select_for_update().select_related('owner', 'pet', 'sitter__user'),
            pk=pk,
        )

        if pet_sitting_request.owner_id != request.user.id:
            raise PermissionDenied(_('Only the owner can cancel a direct pet sitting request.'))
        if pet_sitting_request.status != PetSittingRequest.STATUS_PENDING:
            raise ValidationError({'detail': _('Only pending pet sitting requests can be cancelled.')})

        pet_sitting_request.status = PetSittingRequest.STATUS_CANCELLED
        pet_sitting_request.version += 1
        pet_sitting_request.save(update_fields=['status', 'version', 'updated_at'])

        _notify_user(
            pet_sitting_request.sitter.user,
            title=_('A pet sitting request was cancelled'),
            message=_('%(owner)s cancelled the pet sitting request for %(pet)s. Open PetsCare to review the conversation and current status.') % {
                'owner': pet_sitting_request.owner.get_full_name() or pet_sitting_request.owner.email,
                'pet': pet_sitting_request.pet.name,
            },
            pet=pet_sitting_request.pet,
            data={
                'request_id': pet_sitting_request.id,
                'action_url': _build_frontend_url(f'/boarding?tab=requests&request={pet_sitting_request.id}'),
            },
        )

        return Response(self.get_serializer(pet_sitting_request).data)


class SitterReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet отзывов о передержке.
    """

    serializer_class = SitterReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Возвращает отзывы, доступные текущему пользователю.
        """
        if getattr(self, 'swagger_fake_view', False):
            return SitterReview.objects.none()

        queryset = SitterReview.objects.select_related('history', 'history__sitter', 'author')
        sitter_id = self.request.query_params.get('sitter')
        if sitter_id:
            queryset = queryset.filter(history__sitter_id=sitter_id)
        return queryset.order_by('-created_at', '-id')

    def perform_create(self, serializer):
        """
        Сохраняет автора отзыва как текущего пользователя.
        """
        serializer.save(author=self.request.user)


class PetSittingViewSet(viewsets.ModelViewSet):
    """
    ViewSet жизненного цикла передержки питомца.
    """

    serializer_class = PetSittingSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status']

    def get_queryset(self):
        """
        Возвращает передержки текущего владельца или ситтера.
        """
        if getattr(self, 'swagger_fake_view', False):
            return PetSitting.objects.none()

        queryset = PetSitting.objects.select_related(
            'ad',
            'ad__owner',
            'response',
            'pet',
            'pet__pet_type',
            'pet__breed',
            'sitter',
            'sitter__user',
        ).filter(
            Q(sitter__user=self.request.user) | Q(ad__owner=self.request.user)
        )

        role = self.request.query_params.get('role')
        if role == 'owner':
            queryset = queryset.filter(ad__owner=self.request.user)
        elif role == 'sitter':
            queryset = queryset.filter(sitter__user=self.request.user)

        return queryset.order_by('-created_at', '-id')

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def confirm_start(self, request, pk=None):
        """
        Подтверждает начало передержки и активирует доступ после двух подтверждений.
        """
        sitting = get_object_or_404(
            PetSitting.objects.select_for_update().select_related('ad', 'ad__owner', 'pet', 'sitter', 'sitter__user'),
            pk=pk,
        )

        if request.user.id == sitting.ad.owner_id:
            require_verified_email_for_owner_action(request.user)
            if sitting.owner_confirmed_start:
                raise ValidationError({'detail': _('You have already confirmed the start of this pet sitting.')})
            sitting.owner_confirmed_start = True
        elif request.user.id == sitting.sitter.user_id:
            if sitting.sitter_confirmed_start:
                raise ValidationError({'detail': _('You have already confirmed the start of this pet sitting.')})
            sitting.sitter_confirmed_start = True
        else:
            raise PermissionDenied(_('Only participants can confirm the start of pet sitting.'))

        if sitting.status != 'waiting_start':
            raise ValidationError({'detail': _('Pet sitting cannot be started from the current status.')})

        if sitting.owner_confirmed_start and sitting.sitter_confirmed_start:
            sitting.status = 'active'
            _upsert_pet_access(sitting, allow_write=False)
            _get_or_create_conversation(
                owner=sitting.ad.owner,
                sitter_user=sitting.sitter.user,
                ad=sitting.ad,
                sitting=sitting,
            )
            _notify_user(
                sitting.ad.owner,
                title=_('Pet sitting has started'),
                message=_('The pet sitting for %(pet)s is now active.') % {'pet': sitting.pet.name},
                pet=sitting.pet,
                data={'sitting_id': sitting.id},
            )
            _notify_user(
                sitting.sitter.user,
                title=_('Pet sitting has started'),
                message=_('The pet sitting for %(pet)s is now active.') % {'pet': sitting.pet.name},
                pet=sitting.pet,
                data={'sitting_id': sitting.id},
            )
        else:
            counterpart = sitting.sitter.user if request.user.id == sitting.ad.owner_id else sitting.ad.owner
            _notify_user(
                counterpart,
                title=_('Pet sitting start confirmation is waiting for you'),
                message=_('Please confirm the start of pet sitting for %(pet)s.') % {'pet': sitting.pet.name},
                pet=sitting.pet,
                data={'sitting_id': sitting.id},
            )

        sitting.save(
            update_fields=[
                'owner_confirmed_start',
                'sitter_confirmed_start',
                'status',
                'updated_at',
            ]
        )
        return Response(self.get_serializer(sitting).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def confirm_end(self, request, pk=None):
        """
        Подтверждает завершение передержки и переводит её в этап отзыва.
        """
        sitting = get_object_or_404(
            PetSitting.objects.select_for_update().select_related('ad', 'ad__owner', 'pet', 'sitter', 'sitter__user'),
            pk=pk,
        )

        if sitting.status != 'active':
            raise ValidationError({'detail': _('Pet sitting can be finished only while it is active.')})

        if request.user.id == sitting.ad.owner_id:
            require_verified_email_for_owner_action(request.user)
            if sitting.owner_confirmed_end:
                raise ValidationError({'detail': _('You have already confirmed the end of this pet sitting.')})
            sitting.owner_confirmed_end = True
        elif request.user.id == sitting.sitter.user_id:
            if sitting.sitter_confirmed_end:
                raise ValidationError({'detail': _('You have already confirmed the end of this pet sitting.')})
            sitting.sitter_confirmed_end = True
        else:
            raise PermissionDenied(_('Only participants can confirm the end of pet sitting.'))

        if sitting.owner_confirmed_end and sitting.sitter_confirmed_end:
            sitting.status = 'waiting_review'
            _deactivate_pet_access(sitting)
            _notify_user(
                sitting.ad.owner,
                title=_('Please leave a review'),
                message=_('Pet sitting for %(pet)s has ended. Please leave a review.') % {'pet': sitting.pet.name},
                pet=sitting.pet,
                data={'sitting_id': sitting.id},
            )
            _notify_user(
                sitting.sitter.user,
                title=_('Pet sitting has been finished'),
                message=_('Pet sitting for %(pet)s is waiting for the owner review.') % {'pet': sitting.pet.name},
                pet=sitting.pet,
                data={'sitting_id': sitting.id},
            )
        else:
            counterpart = sitting.sitter.user if request.user.id == sitting.ad.owner_id else sitting.ad.owner
            _notify_user(
                counterpart,
                title=_('Pet sitting end confirmation is waiting for you'),
                message=_('Please confirm the end of pet sitting for %(pet)s.') % {'pet': sitting.pet.name},
                pet=sitting.pet,
                data={'sitting_id': sitting.id},
            )

        sitting.save(
            update_fields=[
                'owner_confirmed_end',
                'sitter_confirmed_end',
                'status',
                'updated_at',
            ]
        )
        return Response(self.get_serializer(sitting).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def leave_review(self, request, pk=None):
        """
        Сохраняет обязательный отзыв владельца и завершает передержку.
        """
        sitting = get_object_or_404(
            PetSitting.objects.select_for_update().select_related('ad', 'ad__owner', 'pet', 'sitter', 'sitter__user'),
            pk=pk,
        )

        if request.user.id != sitting.ad.owner_id:
            raise PermissionDenied(_('Only the owner can leave a review for pet sitting.'))
        require_verified_email_for_owner_action(request.user)
        if sitting.status != 'waiting_review':
            raise ValidationError({'detail': _('A review can be left only after both sides confirm the end.')})
        if sitting.review_left:
            raise ValidationError({'detail': _('The review for this pet sitting has already been submitted.')})

        rating = request.data.get('rating')
        text = request.data.get('text', '')
        try:
            rating_value = int(rating)
        except (TypeError, ValueError) as exc:
            raise ValidationError({'rating': _('Rating is required and must be an integer from 1 to 5.')}) from exc

        if rating_value < 1 or rating_value > 5:
            raise ValidationError({'rating': _('Rating must be between 1 and 5.')})

        review = SitterReview.objects.create(
            history=sitting,
            author=request.user,
            rating=rating_value,
            text=text,
        )

        sitting.review_left = True
        sitting.status = 'completed'
        sitting.save(update_fields=['review_left', 'status', 'updated_at'])

        _notify_user(
            sitting.sitter.user,
            title=_('Pet sitting has been completed'),
            message=_('The owner completed pet sitting for %(pet)s and left a review.') % {'pet': sitting.pet.name},
            pet=sitting.pet,
            data={'sitting_id': sitting.id, 'review_id': review.id},
        )

        return Response(
            {
                'status': 'completed',
                'review': SitterReviewSerializer(review, context={'request': request}).data,
                'sitting': self.get_serializer(sitting).data,
            }
        )

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def cancel(self, request, pk=None):
        """
        Отменяет передержку и отзывает временный доступ.
        """
        sitting = get_object_or_404(
            PetSitting.objects.select_for_update().select_related('ad', 'ad__owner', 'pet', 'sitter', 'sitter__user'),
            pk=pk,
        )

        if request.user.id not in {sitting.ad.owner_id, sitting.sitter.user_id}:
            raise PermissionDenied(_('Only participants can cancel pet sitting.'))
        if request.user.id == sitting.ad.owner_id:
            require_verified_email_for_owner_action(request.user)
        if sitting.status in {'completed', 'cancelled'}:
            raise ValidationError({'detail': _('This pet sitting has already been finished.')})

        sitting.status = 'cancelled'
        sitting.save(update_fields=['status', 'updated_at'])
        _deactivate_pet_access(sitting)

        for participant in (sitting.ad.owner, sitting.sitter.user):
            _notify_user(
                participant,
                title=_('Pet sitting was cancelled'),
                message=_('Pet sitting for %(pet)s has been cancelled.') % {'pet': sitting.pet.name},
                pet=sitting.pet,
                data={'sitting_id': sitting.id},
            )

        return Response(self.get_serializer(sitting).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def grant_access(self, request, pk=None):
        """
        Выдаёт ситтеру расширенный write-доступ к питомцу.
        """
        sitting = get_object_or_404(
            PetSitting.objects.select_for_update().select_related('ad', 'ad__owner', 'pet', 'sitter', 'sitter__user'),
            pk=pk,
        )

        if request.user.id != sitting.ad.owner_id:
            raise PermissionDenied(_('Only the owner can grant additional access.'))
        if sitting.status != 'active':
            raise ValidationError({'detail': _('Additional access can be granted only while pet sitting is active.')})

        _upsert_pet_access(sitting, allow_write=True)
        _notify_user(
            sitting.sitter.user,
            title=_('Extended pet access granted'),
            message=_('You have been granted extended access to %(pet)s.') % {'pet': sitting.pet.name},
            pet=sitting.pet,
            data={'sitting_id': sitting.id},
        )
        return Response(self.get_serializer(sitting).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def revoke_access(self, request, pk=None):
        """
        Отключает только расширенный write-доступ, сохраняя базовый доступ до конца передержки.
        """
        sitting = get_object_or_404(
            PetSitting.objects.select_for_update().select_related('ad', 'ad__owner', 'pet', 'sitter', 'sitter__user'),
            pk=pk,
        )

        if request.user.id != sitting.ad.owner_id:
            raise PermissionDenied(_('Only the owner can revoke additional access.'))
        if sitting.status != 'active':
            raise ValidationError({'detail': _('Additional access can be revoked only while pet sitting is active.')})

        _upsert_pet_access(sitting, allow_write=False)
        _notify_user(
            sitting.sitter.user,
            title=_('Extended pet access revoked'),
            message=_('Your extended access to %(pet)s has been revoked.') % {'pet': sitting.pet.name},
            pet=sitting.pet,
            data={'sitting_id': sitting.id},
        )
        return Response(self.get_serializer(sitting).data)

    @action(detail=False, methods=['post'], url_path='remind')
    def remind(self, request):
        """
        Отправляет email/in-app напоминания о зависших шагах передержки.
        """
        today = timezone.now().date()
        reminders_sent = 0

        waiting_start_sittings = PetSitting.objects.select_related('ad', 'pet', 'sitter__user').filter(
            status='waiting_start',
            start_date__lte=today + timedelta(days=1),
        )
        for sitting in waiting_start_sittings:
            if not sitting.owner_confirmed_start:
                _notify_user(
                    sitting.ad.owner,
                    title=_('Confirm the start of pet sitting'),
                    message=_('Please confirm the start of pet sitting for %(pet)s.') % {'pet': sitting.pet.name},
                    pet=sitting.pet,
                    data={'sitting_id': sitting.id},
                )
                reminders_sent += 1
            if not sitting.sitter_confirmed_start:
                _notify_user(
                    sitting.sitter.user,
                    title=_('Confirm the start of pet sitting'),
                    message=_('Please confirm the start of pet sitting for %(pet)s.') % {'pet': sitting.pet.name},
                    pet=sitting.pet,
                    data={'sitting_id': sitting.id},
                )
                reminders_sent += 1

        waiting_end_sittings = PetSitting.objects.select_related('ad', 'pet', 'sitter__user').filter(
            status='active',
            end_date__lte=today,
        )
        for sitting in waiting_end_sittings:
            if not sitting.owner_confirmed_end:
                _notify_user(
                    sitting.ad.owner,
                    title=_('Confirm the end of pet sitting'),
                    message=_('Please confirm the end of pet sitting for %(pet)s.') % {'pet': sitting.pet.name},
                    pet=sitting.pet,
                    data={'sitting_id': sitting.id},
                )
                reminders_sent += 1
            if not sitting.sitter_confirmed_end:
                _notify_user(
                    sitting.sitter.user,
                    title=_('Confirm the end of pet sitting'),
                    message=_('Please confirm the end of pet sitting for %(pet)s.') % {'pet': sitting.pet.name},
                    pet=sitting.pet,
                    data={'sitting_id': sitting.id},
                )
                reminders_sent += 1

        review_sittings = PetSitting.objects.select_related('ad', 'pet').filter(
            status='waiting_review',
            review_left=False,
        )
        for sitting in review_sittings:
            _notify_user(
                sitting.ad.owner,
                title=_('Leave a pet sitting review'),
                message=_('Please leave a review for pet sitting of %(pet)s.') % {'pet': sitting.pet.name},
                pet=sitting.pet,
                data={'sitting_id': sitting.id},
            )
            reminders_sent += 1

        return Response({'reminders_sent': reminders_sent})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def search_sitters(request):
    """
    Выполняет геопоиск ситтеров с фильтрами по дате, типу питомца и ставке.
    """
    search_lat, search_lon, location_source = _resolve_search_coordinates(request)

    try:
        radius = float(request.query_params.get('radius', 10))
    except (TypeError, ValueError) as exc:
        raise ValidationError({'radius': _('Radius must be a number between 0.1 and 100.')}) from exc

    if not (0.1 <= radius <= 100):
        raise ValidationError({'radius': _('Radius must be a number between 0.1 and 100.')})

    available_from = _parse_iso_date(request.query_params.get('available_from'), 'available_from')
    available_to = _parse_iso_date(request.query_params.get('available_to'), 'available_to')
    if available_from and available_to and available_from > available_to:
        raise ValidationError({'available_to': _('End date must be after start date')})

    requested_pet_types = {
        value.strip().lower()
        for value in request.query_params.get('pet_type', '').split(',')
        if value.strip()
    }
    compensation_type = request.query_params.get('compensation_type')
    price_min = request.query_params.get('price_min')
    price_max = request.query_params.get('price_max')
    rating_min = request.query_params.get('rating_min')

    sitters = SitterProfile.objects.select_related('user', 'user__user_location').annotate(
        rating_value=Avg('sittings__reviews__rating'),
        reviews_count_value=Count('sittings__reviews', distinct=True),
    ).filter(is_active=True)

    matched_sitters: list[SitterProfile] = []
    for sitter in sitters:
        user_location = getattr(sitter.user, 'user_location', None)
        if user_location is None or not user_location.point:
            continue

        distance_km = user_location.distance_to(search_lat, search_lon)
        if distance_km is None or distance_km > radius:
            continue

        if not _has_matching_pet_type(sitter.pet_types, requested_pet_types):
            continue

        if compensation_type and sitter.compensation_type != compensation_type:
            continue

        sitter_rate = float(sitter.hourly_rate) if sitter.hourly_rate is not None else None
        if price_min and (sitter_rate is None or sitter_rate < float(price_min)):
            continue
        if price_max and sitter_rate is not None and sitter_rate > float(price_max):
            continue

        sitter_rating = float(getattr(sitter, 'rating_value', 0) or 0)
        if rating_min and sitter_rating < float(rating_min):
            continue

        if available_from and sitter.available_from and sitter.available_from > available_from:
            continue
        if available_to and sitter.available_to and sitter.available_to < available_to:
            continue

        current_load = 0
        if available_from and available_to:
            current_load = PetSitting.objects.filter(
                sitter=sitter,
                status__in=CAPACITY_BLOCKING_STATUSES,
                start_date__lte=available_to,
                end_date__gte=available_from,
            ).count()
            if current_load >= sitter.max_pets:
                continue

        sitter.distance_km = round(float(distance_km), 2)
        sitter.current_load = current_load
        matched_sitters.append(sitter)

    matched_sitters.sort(key=lambda profile: getattr(profile, 'distance_km', 0))
    serializer = SitterProfileSerializer(matched_sitters, many=True, context={'request': request})
    serialized_data = serializer.data

    for payload, sitter in zip(serialized_data, matched_sitters, strict=False):
        payload['distance_km'] = getattr(sitter, 'distance_km', None)
        payload['current_load'] = getattr(sitter, 'current_load', 0)

    return Response(
        {
            'results': serialized_data,
            'search': {
                'latitude': search_lat,
                'longitude': search_lon,
                'radius_km': radius,
                'location_source': location_source,
                'total_found': len(serialized_data),
            },
        }
    )


class ConversationViewSet(viewsets.ModelViewSet):
    """
    ViewSet диалогов между владельцами и ситтерами.
    """

    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Возвращает активные диалоги текущего пользователя.
        """
        if getattr(self, 'swagger_fake_view', False):
            return Conversation.objects.none()

        return Conversation.objects.filter(participants=self.request.user, is_active=True).prefetch_related(
            'participants',
            'messages',
        ).order_by('-updated_at', '-id')

    def get_serializer_class(self):
        """
        Подбирает сериализатор в зависимости от действия.
        """
        if self.action == 'retrieve':
            return ConversationDetailSerializer
        return ConversationSerializer

    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """
        Отправляет сообщение в диалог между участниками.
        """
        conversation = self.get_object()
        text = str(request.data.get('text', '')).strip()
        if not text:
            raise ValidationError({'text': _('Message text is required.')})

        other_participant = conversation.get_other_participant(request.user)
        if other_participant is None:
            raise ValidationError({'detail': _('No other participant found for this conversation.')})

        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            recipient=other_participant,
            text=text,
        )

        _notify_user(
            other_participant,
            title=_('New boarding chat message'),
            message=_('%(sender)s sent you a new PetsCare boarding message. Open the chat to read and reply.') % {
                'sender': request.user.get_full_name() or request.user.email,
            },
            notification_type='system',
            data={
                'conversation_id': conversation.id,
                'message_id': message.id,
                'action_url': _build_frontend_url(f'/boarding?tab=chat&conversation={conversation.id}'),
            },
        )

        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])
        return Response(MessageSerializer(message, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """
        Отмечает непрочитанные сообщения как прочитанные.
        """
        conversation = self.get_object()
        updated_count = conversation.messages.filter(
            is_read=False,
            recipient=request.user,
        ).update(is_read=True)
        return Response({'marked_as_read': updated_count})

    @action(detail=False, methods=['post'])
    def create_or_get(self, request):
        """
        Создаёт новый диалог или возвращает уже существующий.
        """
        other_user_id = request.data.get('other_user_id')
        ad_id = request.data.get('ad_id')
        sitting_id = request.data.get('sitting_id')

        if not other_user_id:
            raise ValidationError({'other_user_id': _('other_user_id is required.')})
        if int(other_user_id) == request.user.id:
            raise ValidationError({'other_user_id': _('You cannot create a conversation with yourself.')})

        other_user = get_object_or_404(User, pk=other_user_id)
        ad = get_object_or_404(PetSittingAd, pk=ad_id) if ad_id else None
        sitting = get_object_or_404(PetSitting, pk=sitting_id) if sitting_id else None

        conversation = _get_or_create_conversation(
            owner=request.user if ad is None or ad.owner_id == request.user.id else other_user,
            sitter_user=other_user if ad is None or ad.owner_id == request.user.id else request.user,
            ad=ad,
            sitting=sitting,
        )
        serializer = ConversationDetailSerializer(conversation, context={'request': request})
        return Response(serializer.data)


class PetFilterForSittingAPIView(generics.ListAPIView):
    """
    Возвращает питомцев текущего пользователя для формы объявления.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """
        Возвращает сериализатор питомца для Swagger и runtime.
        """
        return PetSerializer

    def get_queryset(self):
        """
        Возвращает только питомцев текущего пользователя с фильтрами.
        """
        if getattr(self, 'swagger_fake_view', False):
            return Pet.objects.none()

        queryset = Pet.objects.filter(owners=self.request.user).distinct()

        pet_type = self.request.query_params.get('pet_type')
        if pet_type:
            queryset = queryset.filter(pet_type__code=pet_type)

        breed = self.request.query_params.get('breed')
        if breed:
            queryset = queryset.filter(breed__code=breed)

        age_min = self.request.query_params.get('age_min')
        age_max = self.request.query_params.get('age_max')
        if age_min:
            max_birth_date = timezone.now().date() - timedelta(days=int(age_min) * 365)
            queryset = queryset.filter(birth_date__lte=max_birth_date)
        if age_max:
            min_birth_date = timezone.now().date() - timedelta(days=(int(age_max) + 1) * 365)
            queryset = queryset.filter(birth_date__gt=min_birth_date)

        weight_min = self.request.query_params.get('weight_min')
        weight_max = self.request.query_params.get('weight_max')
        if weight_min:
            queryset = queryset.filter(weight__gte=float(weight_min))
        if weight_max:
            queryset = queryset.filter(weight__lte=float(weight_max))

        has_medical_conditions = self.request.query_params.get('has_medical_conditions')
        if has_medical_conditions is not None:
            if has_medical_conditions.lower() == 'true':
                queryset = queryset.filter(~Q(medical_conditions={}) & ~Q(medical_conditions__isnull=True))
            else:
                queryset = queryset.filter(Q(medical_conditions={}) | Q(medical_conditions__isnull=True))

        has_special_needs = self.request.query_params.get('has_special_needs')
        if has_special_needs is not None:
            if has_special_needs.lower() == 'true':
                queryset = queryset.filter(~Q(special_needs={}) & ~Q(special_needs__isnull=True))
            else:
                queryset = queryset.filter(Q(special_needs={}) | Q(special_needs__isnull=True))

        ordering = self.request.query_params.get('ordering', 'name')
        if ordering in ['birth_date', '-birth_date', 'weight', '-weight', 'name', '-name']:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by('name')

        return queryset

    def list(self, request, *args, **kwargs):
        """
        Возвращает список питомцев с метаданными фильтрации.
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                'results': serializer.data,
                'meta': {
                    'total_count': queryset.count(),
                    'ordering': request.query_params.get('ordering', 'name'),
                },
            }
        )
