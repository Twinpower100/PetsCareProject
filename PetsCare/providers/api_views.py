"""
API представления для модуля providers.

Этот модуль содержит классы представлений для работы с API провайдеров услуг.

Основные компоненты:
1. Управление провайдерами (создание, просмотр, обновление, удаление)
2. Управление сотрудниками (регистрация, деактивация, подтверждение)
3. Управление расписанием (провайдеров и сотрудников)
4. Управление услугами (добавление, изменение цен)
5. Управление заявками на вступление
6. Массовые операции с рабочими слотами

Особенности реализации:
- Разграничение прав доступа
- Фильтрация и поиск
- Уведомления по email
- Валидация данных
"""

from rest_framework import generics, status, permissions, filters, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _
from django.utils import translation
from django_filters.rest_framework import DjangoFilterBackend

from users.serializers import UserSerializer
from .models import Provider, Employee, EmployeeProvider, Schedule, LocationSchedule, EmployeeWorkSlot, SchedulePattern, ProviderLocation, ProviderLocationService, EmployeeLocationService, EmployeeLocationRole
from catalog.models import Service
from django.db.models import Q, Count, Case, When, Value
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from booking.models import Booking
from .serializers import (
    ProviderSerializer, EmployeeSerializer, EmployeeProviderSerializer,
    ScheduleSerializer,
    EmployeeRegistrationSerializer,
    EmployeeProviderUpdateSerializer,
    EmployeeWorkSlotSerializer,
    ProviderBriefSerializer, ProviderDetailLiteSerializer,
    ProviderLocationSerializer, ProviderLocationListSerializer, ProviderLocationServiceSerializer,
    LocationScheduleSerializer, HolidayShiftSerializer,
    LocationServicePricesUpdateSerializer,
    ProviderAdminListSerializer,
)
# from users.permissions import IsProviderAdmin  # Класс определен ниже в этом файле
from users.models import User

from django.utils import translation


def _user_has_role(user, role_name):
    """
    Безопасная проверка роли пользователя.
    
    Используется для защиты от ошибок при генерации Swagger схемы,
    когда request.user может быть AnonymousUser.
    
    Args:
        user: Объект пользователя (может быть AnonymousUser)
        role_name: Название роли для проверки
        
    Returns:
        bool: True если пользователь аутентифицирован и имеет роль, иначе False
    """
    if not hasattr(user, 'is_authenticated') or not user.is_authenticated:
        return False
    if not hasattr(user, 'has_role'):
        return False
    try:
        return user.has_role(role_name)
    except (AttributeError, TypeError):
        return False


def _get_provider_full_address(provider):
    """
    Возвращает форматированный адрес провайдера, если он доступен.
    """
    if provider.structured_address:
        return provider.structured_address.formatted_address or str(provider.structured_address)
    return None


def _get_provider_rating_map(providers):
    """
    Возвращает карту рейтингов провайдеров по их ID.
    """
    provider_ids = [provider.id for provider in providers]
    if not provider_ids:
        return {}
    provider_content_type = ContentType.objects.get_for_model(Provider)
    ratings = Rating.objects.filter(
        content_type=provider_content_type,
        object_id__in=provider_ids
    )
    return {rating.object_id: float(rating.current_rating) for rating in ratings}


def _get_employee(user):
    """Возвращает Employee для user (get_or_create)."""
    return Employee.objects.get_or_create(user=user)[0]


def _active_employee_provider_q():
    """Q-объект для активных записей EmployeeProvider (end_date пусто или >= сегодня)."""
    from django.utils import timezone
    today = timezone.now().date()
    return Q(end_date__isnull=True) | Q(end_date__gte=today)


def _user_is_owner_for_provider(user, provider):
    """
    Проверяет, является ли пользователь владельцем данного провайдера.
    Используется для ограничения «Пригласить менеджера» и «Я сам себе менеджер» только владельцу.
    """
    if not user or not user.is_authenticated:
        return False
    return EmployeeProvider.objects.filter(
        provider=provider,
        employee__user=user,
        is_owner=True,
    ).filter(_active_employee_provider_q()).exists()


class IsProviderAdmin(permissions.BasePermission):
    """
    Проверка доступа в приложение «Админка провайдеров».
    
    Доступ разрешён, если пользователь привязан хотя бы к одному провайдеру через EmployeeProvider.
    Уровень доступа внутри приложения определяется ролью (owner, provider_manager, и т.д.).
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.get_managed_providers().exists()


class RequisitesValidationRulesAPIView(APIView):
    """
    Возвращает правила/подсказки для реквизитов провайдера (шаг 3) с учетом языка UI.

    Query params:
    - country: ISO2 (DE/RU/UA/ME...)
    - language (optional): en/ru/de/me; если не указан — берется из LocaleMiddleware
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        country = (request.query_params.get('country') or '').upper().strip()
        language = (request.query_params.get('language') or getattr(request, 'LANGUAGE_CODE', None) or translation.get_language() or 'en')
        language = (language or 'en').split('-')[0]
        if language not in ('en', 'ru', 'de', 'me'):
            language = 'en'

        from .validation_rules import get_validation_rules, get_format_description, ORGANIZATION_NAME_HINTS

        rules = get_validation_rules(country) if country else {}

        # Нормализуем структуру для фронта: format_description всегда строка в нужном языке
        normalized = {}
        for field_name, field_rules in rules.items():
            if not isinstance(field_rules, dict):
                continue
            normalized[field_name] = {
                'required': bool(field_rules.get('required', False)),
                'conditional': field_rules.get('conditional') or None,
                'format_description': get_format_description(field_name, country, language=language),
            }

        return Response({
            'country': country,
            'language': language,
            'organization_name_hint': ORGANIZATION_NAME_HINTS.get(language, ORGANIZATION_NAME_HINTS['en']),
            'fields': normalized,
        })
from django.core.mail import send_mail
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from .permissions import IsEmployee
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta
from geolocation.utils import filter_by_distance, validate_coordinates, calculate_distance
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Q
from django.contrib.contenttypes.models import ContentType
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
import logging
from ratings.models import Rating

logger = logging.getLogger(__name__)


def _is_brief_mode(request):
    """
    Облегчённый ответ для админки: исключаем тяжелые вложенные поля.
    Поддерживаем ?brief=1 и ?compact=1.
    """
    v = (request.query_params.get('brief') or request.query_params.get('compact') or '').strip().lower()
    return v in ('1', 'true', 'yes')


class ProviderListCreateAPIView(generics.ListCreateAPIView):
    """
    API для просмотра списка и создания провайдеров услуг.
    
    Основные возможности:
    - Получение списка активных провайдеров
    - Создание нового провайдера
    - Фильтрация по статусу активности
    - Поиск по названию, описанию и адресу
    - Сортировка по названию и рейтингу
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = Provider.objects.filter(is_active=True)
    serializer_class = ProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description', 'structured_address__formatted_address']
    ordering_fields = ['name']

    def get_serializer_class(self):
        if self.request.method == 'GET' and _is_brief_mode(self.request):
            return ProviderBriefSerializer
        return ProviderSerializer
    
    def get_queryset(self):
        """Возвращает queryset с проверкой swagger_fake_view. Для provider_admin — только управляемые организации."""
        if getattr(self, 'swagger_fake_view', False):
            return Provider.objects.none()
        queryset = self.queryset
        if self.request.method == 'GET' and _is_brief_mode(self.request):
            queryset = queryset.select_related('structured_address')
        if self.request.user.get_managed_providers().exists():
            queryset = queryset.filter(id__in=self.request.user.get_managed_providers())
        return queryset


class ProviderRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для работы с конкретным провайдером услуг.
    
    Основные возможности:
    - Получение детальной информации
    - Обновление данных
    - Удаление провайдера
    
    Права доступа:
    - Требуется аутентификация
    - provider_admin видит только свои управляемые организации
    """
    queryset = Provider.objects.all()
    serializer_class = ProviderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'GET' and _is_brief_mode(self.request):
            return ProviderDetailLiteSerializer
        return ProviderSerializer

    def get_queryset(self):
        """Для provider_admin — только управляемые организации."""
        queryset = self.queryset
        if self.request.method == 'GET' and _is_brief_mode(self.request):
            queryset = queryset.select_related('structured_address')
        if self.request.user.get_managed_providers().exists():
            queryset = queryset.filter(id__in=self.request.user.get_managed_providers())
        return queryset


class ProviderAdminListAPIView(generics.ListAPIView):
    """
    Список админов провайдера с полем role (owner / provider_manager / provider_admin).
    Для страницы персонала: отображение владельца учреждения и админов. Источник — EmployeeProvider.
    Доступ: только админ или владелец данного провайдера.
    """
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]
    serializer_class = ProviderAdminListSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return EmployeeProvider.objects.none()
        provider_id = self.kwargs.get('provider_id')
        managed = self.request.user.get_managed_providers()
        if not managed.filter(pk=provider_id).exists():
            return EmployeeProvider.objects.none()
        role_q = Q(is_owner=True) | Q(is_provider_manager=True) | Q(is_provider_admin=True)
        return EmployeeProvider.objects.filter(
            provider_id=provider_id,
        ).filter(role_q).filter(_active_employee_provider_q()).select_related(
            'employee', 'employee__user', 'provider'
        ).order_by('-is_owner', '-is_provider_manager', '-is_provider_admin', 'created_at')


class ProviderAdminAssignSelfAPIView(APIView):
    """
    Назначить себя менеджером провайдера (без инвайта). Владелец через этот API назначить нельзя.
    POST providers/<provider_id>/admins/assign-self/
    Body: { "role": "provider_manager" }. role=owner возвращает 400.
    """
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]

    def post(self, request, provider_id):
        from django.utils import timezone
        provider = get_object_or_404(Provider, pk=provider_id)
        managed = request.user.get_managed_providers()
        if not managed.filter(pk=provider_id).exists():
            raise PermissionDenied(_('You do not manage this provider.'))
        if not _user_is_owner_for_provider(request.user, provider):
            raise PermissionDenied(_('Only the owner can assign themselves as manager.'))
        role = request.data.get('role')
        if role not in (EmployeeProvider.ROLE_OWNER, EmployeeProvider.ROLE_PROVIDER_MANAGER):
            return Response(
                {'role': [_('Must be "owner" or "provider_manager".')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if role == EmployeeProvider.ROLE_OWNER:
            return Response(
                {'role': [_('Owner cannot be self-assigned. Can only be changed via support.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        employee = _get_employee(request.user)
        role_filter = Q(is_provider_manager=True)
        if EmployeeProvider.objects.filter(
            provider=provider, employee=employee,
        ).filter(role_filter).filter(_active_employee_provider_q()).exists():
            return Response(
                {'detail': _('You already have this role for this provider.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        today = timezone.now().date()
        is_owner = False
        is_provider_manager = role == EmployeeProvider.ROLE_PROVIDER_MANAGER
        from django.db import transaction
        from invites.services import maybe_remove_role
        with transaction.atomic():
            # Менеджер у организации один: снимаем роль менеджера со всех остальных, затем назначаем себя.
            old_manager_eps = []
            if is_provider_manager:
                old_manager_eps = list(
                    EmployeeProvider.objects.filter(
                        provider=provider,
                    ).filter(_active_employee_provider_q()).filter(
                        is_provider_manager=True,
                    ).exclude(employee=employee).select_related('employee__user')
                )
                EmployeeProvider.objects.filter(
                    provider=provider,
                ).filter(_active_employee_provider_q()).filter(
                    is_provider_manager=True,
                ).exclude(employee=employee).update(is_provider_manager=False, is_manager=False)
            existing = EmployeeProvider.objects.filter(
                employee=employee, provider=provider,
            ).filter(_active_employee_provider_q()).first()
            if existing:
                if is_owner:
                    existing.is_owner = True
                if is_provider_manager:
                    existing.is_provider_manager = True
                    existing.is_manager = True
                existing.save(update_fields=['is_owner', 'is_provider_manager', 'is_manager'])
                ep = existing
            else:
                ep = EmployeeProvider.objects.create(
                    employee=employee,
                    provider=provider,
                    start_date=today,
                    end_date=None,
                    role=role,
                    is_owner=is_owner,
                    is_provider_manager=is_provider_manager,
                    is_provider_admin=False,
                    is_manager=is_provider_manager,
                )
            # Синхронизация UserType с EmployeeProvider: владельцу добавляем provider_manager, бывшим менеджерам снимаем.
            if is_provider_manager:
                request.user.add_role('provider_manager')
                for old_ep in old_manager_eps:
                    old_user = old_ep.employee.user
                    if old_user.pk != request.user.pk:
                        maybe_remove_role(old_user, 'provider_manager')
        serializer = ProviderAdminListSerializer(ep)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProviderAdminRevokeAPIView(APIView):
    """
    Снять пользователя с роли админа провайдера. Только владелец.
    POST providers/<provider_id>/admins/revoke/
    Body: { "user_id": <id> }
    """
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]

    def post(self, request, provider_id):
        from django.db import transaction
        from invites.services import maybe_remove_role

        provider = get_object_or_404(Provider, pk=provider_id)
        if not _user_is_owner_for_provider(request.user, provider):
            raise PermissionDenied(_('Only the owner can revoke an organization admin.'))
        user_id = request.data.get('user_id')
        if user_id is None:
            return Response(
                {'user_id': [_('This field is required.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            target_user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response(
                {'detail': _('User not found.')},
                status=status.HTTP_404_NOT_FOUND,
            )
        ep = EmployeeProvider.objects.filter(
            provider=provider,
            employee__user=target_user,
        ).filter(_active_employee_provider_q()).first()
        if not ep:
            return Response(
                {'detail': _('This user is not linked to this provider.')},
                status=status.HTTP_404_NOT_FOUND,
            )
        if ep.is_owner:
            return Response(
                {'detail': _('Cannot revoke the owner. Owner role can only be changed via support.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not ep.is_provider_admin:
            return Response(
                {'detail': _('This user is not an organization admin.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            ep.is_provider_admin = False
            if ep.role == EmployeeProvider.ROLE_PROVIDER_ADMIN:
                ep.role = EmployeeProvider.ROLE_SERVICE_WORKER
            ep.save(update_fields=['is_provider_admin', 'role', 'updated_at'])
            maybe_remove_role(target_user, 'provider_admin')
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployeeListCreateAPIView(generics.ListCreateAPIView):
    """
    API для просмотра списка и создания сотрудников.
    
    Основные возможности:
    - Получение списка активных сотрудников
    - Создание нового сотрудника
    - Фильтрация по статусу и должности
    - Поиск по имени, фамилии, должности и биографии
    - Сортировка по имени, фамилии и должности
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = Employee.objects.filter(is_active=True)
    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['user__first_name', 'user__last_name']
    ordering_fields = ['user__first_name', 'user__last_name']
    
    def get_queryset(self):
        """Возвращает queryset с проверкой swagger_fake_view."""
        if getattr(self, 'swagger_fake_view', False):
            return Employee.objects.none()
        return self.queryset


class EmployeeRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для работы с конкретным сотрудником.
    
    Основные возможности:
    - Получение детальной информации
    - Обновление данных
    - Удаление сотрудника
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated]


class EmployeeProviderListCreateAPIView(generics.ListCreateAPIView):
    """
    API для просмотра списка и создания связей сотрудник-провайдер.
    
    Основные возможности:
    - Получение списка связей
    - Создание новой связи
    - Фильтрация по сотруднику, провайдеру и статусу менеджера
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = EmployeeProvider.objects.all()
    serializer_class = EmployeeProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['employee', 'provider', 'is_manager']


class EmployeeProviderRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для работы с конкретной связью сотрудник-провайдер.
    
    Основные возможности:
    - Получение детальной информации
    - Обновление данных
    - Удаление связи
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = EmployeeProvider.objects.all()
    serializer_class = EmployeeProviderSerializer
    permission_classes = [permissions.IsAuthenticated]


class ScheduleListCreateAPIView(generics.ListCreateAPIView):
    """
    API для просмотра списка и создания расписаний.
    
    Основные возможности:
    - Получение списка расписаний
    - Создание нового расписания
    - Фильтрация по сотруднику, дню недели и статусу рабочего дня
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = Schedule.objects.all()
    serializer_class = ScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['employee', 'day_of_week', 'is_working']
    
    def get_queryset(self):
        """Возвращает queryset с проверкой swagger_fake_view."""
        if getattr(self, 'swagger_fake_view', False):
            return Schedule.objects.none()
        return self.queryset


class ScheduleRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для работы с конкретным расписанием.
    
    Основные возможности:
    - Получение детальной информации
    - Обновление данных
    - Удаление расписания
    
    Права доступа:
    - Требуется аутентификация
    """
    queryset = Schedule.objects.all()
    serializer_class = ScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]


# ProviderService API views удалены - используйте ProviderLocationService API views

class ProviderSearchAPIView(generics.ListAPIView):
    """
    API для поиска провайдеров услуг.
    
    Основные возможности:
    - Поиск по названию организации, названию локации и адресу локации
    - Фильтрация по конкретной услуге
    - Возвращает только активных провайдеров с активными локациями
    - Исключает заблокированные учреждения
    
    Права доступа:
    - Требуется аутентификация
    """
    serializer_class = ProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'locations__name', 'locations__structured_address__formatted_address']

    def get_queryset(self):
        """
        Возвращает queryset с исключением заблокированных учреждений.
        """
        if getattr(self, 'swagger_fake_view', False):
            return Provider.objects.none()
        
        from billing.models import ProviderBlocking
        
        # Получаем базовый queryset активных провайдеров с активными локациями
        queryset = Provider.objects.filter(
            is_active=True,
            locations__is_active=True
        ).distinct()
        
        # Исключаем заблокированные учреждения
        blocked_provider_ids = ProviderBlocking.objects.filter(
            status='active'
        ).values_list('provider_id', flat=True)
        
        return queryset.exclude(id__in=blocked_provider_ids)


class EmployeeProviderUpdateAPIView(generics.UpdateAPIView):
    """
    API для обновления данных о работе сотрудника в учреждении.
    
    Основные возможности:
    - Обновление данных о работе сотрудника
    - Доступно только администратору учреждения
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права администратора провайдера
    """
    serializer_class = EmployeeProviderUpdateSerializer
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]
    lookup_url_kwarg = 'employee_id'


class LocationStaffDeactivateAPIView(APIView):
    """
    API для деактивации сотрудника (soft delete) в конкретном филиале.
    
    Если нет resolution_action (dry run):
    - При наличии будущих бронирований вернет 409 Conflict со списком бронирований.
    - Иначе деактивирует (soft-delete).
    
    С resolution_action ('reassign' или 'cancel'):
    - При 'reassign' переназначает брони на target_employee_id.
    - При 'cancel' отменяет бронирования.
    - Затем деактивирует.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, location_pk, employee_id):
        from rest_framework import status
        from rest_framework.response import Response
        from booking.reassignment_service import BookingReassignmentService

        location = get_object_or_404(_location_manager_queryset(request), pk=location_pk)
        employee = get_object_or_404(Employee, pk=employee_id)

        # Get future bookings
        future_bookings = BookingReassignmentService.get_future_bookings(
            employee_id=employee_id,
            location_id=location_pk
        )

        # Поддержка обоих вариантов имён из ТЗ: resolution/resolution_action, cancel_reason/cancellation_reason
        resolution_action = request.data.get('resolution_action') or request.data.get('resolution')
        cancellation_reason = request.data.get('cancellation_reason') or request.data.get('cancel_reason', '')
        target_employee_id = request.data.get('target_employee_id')

        future_count = future_bookings.count()
        # Определяем, нужен ли resolution (есть будущие записи и не передан способ решения)
        if future_count and not resolution_action:
            bookings_payload = BookingReassignmentService.serialize_bookings_for_response(future_bookings)
            return Response({
                'error': 'has_future_bookings',
                'future_bookings_count': future_count,
                'message': _(
                    'Employee has future bookings. Please choose an action: cancel them or reassign to another specialist.'
                ),
                'bookings': bookings_payload,
                # Совместимость с текущим фронтом
                'conflict_type': 'future_bookings',
                'bookings_count': future_count,
            }, status=status.HTTP_409_CONFLICT)

        try:
            result = BookingReassignmentService.deactivate_staff(
                provider_location=location,
                employee=employee,
                resolution=resolution_action or 'cancel',
                target_employee_id=target_employee_id,
                reason=cancellation_reason,
                performed_by=request.user
            )
            return Response({'detail': _('Employee successfully deactivated at this location.'), 'result': result})
        
        except ValidationError as e:
            return Response({
                'detail': e.message if hasattr(e, 'message') else str(e),
                'conflicts': e.error_dict if hasattr(e, 'error_dict') else (getattr(e, 'params', {}) or {}).get('conflicts', [])
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error("Deactivation failed: %s", e)
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class LocationStaffReactivateAPIView(APIView):
    """
    API для реактивации (восстановления) сотрудника в филиале.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, location_pk, employee_id):
        from rest_framework import status
        from rest_framework.response import Response
        
        location = get_object_or_404(_location_manager_queryset(request), pk=location_pk)
        employee = get_object_or_404(Employee, pk=employee_id)

        try:
            role_obj = EmployeeLocationRole.objects.get(
                employee=employee,
                provider_location=location,
            )
            role_obj.is_active = True
            role_obj.end_date = None
            role_obj.save(update_fields=['is_active', 'end_date'])
            return Response({'detail': _('Employee successfully reactivated at this location.')})
        except EmployeeLocationRole.DoesNotExist:
            return Response(
                {'detail': _('Employee role not found at this location.')},
                status=status.HTTP_404_NOT_FOUND
            )



class EmployeeWorkSlotViewSet(viewsets.ModelViewSet):
    """
    API для управления рабочими слотами сотрудников.
    
    Основные возможности:
    - CRUD операции с рабочими слотами
    - Автоматическая фильтрация по провайдеру администратора
    
    Права доступа:
    - Требуется аутентификация
    - Требуются права администратора провайдера
    """
    queryset = EmployeeWorkSlot.objects.all()
    serializer_class = EmployeeWorkSlotSerializer
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]


class EmployeeAccountDeleteNotifyAPIView(APIView):
    """
    API для уведомления админа учреждения при попытке удаления аккаунта сотрудником.
    """
    permission_classes = [permissions.IsAuthenticated]


class EmployeeProviderViewSet(viewsets.ModelViewSet):
    """
    API для управления связями сотрудник-учреждение
    """
    queryset = EmployeeProvider.objects.all()
    serializer_class = EmployeeProviderSerializer
    permission_classes = [IsAuthenticated]


class EmployeeWorkSlotBulkAPIView(APIView):
    """
    API для массового создания/обновления рабочих слотов
    """
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]


class SchedulePatternApplyAPIView(APIView):
    """
    API для применения шаблона расписания
    """
    permission_classes = [permissions.IsAuthenticated, IsProviderAdmin]


class ProviderSearchByDistanceAPIView(generics.ListAPIView):
    """
    API для поиска провайдеров по расстоянию от указанной точки.
    
    Основные возможности:
    - Поиск провайдеров в указанном радиусе
    - Фильтрация по услугам, рейтингу, цене и доступности
    - Сортировка по расстоянию, рейтингу и цене
    - Возвращает расстояние до каждого провайдера
    - Исключает заблокированные учреждения
    
    Параметры запроса:
    - latitude: Широта центральной точки
    - longitude: Долгота центральной точки
    - radius: Радиус поиска в километрах (по умолчанию 10)
    - service_id: ID конкретной услуги для фильтрации
    - min_rating: Минимальный рейтинг провайдера
    - price_min: Минимальная цена услуги
    - price_max: Максимальная цена услуги
    - available_date: Дата для проверки доступности (YYYY-MM-DD)
    - available_time: Время для проверки доступности (HH:MM)
    - available: Только доступные учреждения (true/false)
    - sort_by: Сортировка (distance, rating, price_asc, price_desc)
    - limit: Максимальное количество результатов (по умолчанию 20)
    
    Права доступа:
    - Требуется аутентификация
    """
    serializer_class = ProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Возвращает провайдеров в указанном радиусе с фильтрацией по цене и доступности.
        """
        if getattr(self, 'swagger_fake_view', False):
            return Provider.objects.none()
        
        from billing.models import ProviderBlocking
        from booking.models import Booking
        from datetime import datetime, timedelta
        
        # Получаем параметры запроса
        latitude = self.request.query_params.get('latitude')
        longitude = self.request.query_params.get('longitude')
        radius = float(self.request.query_params.get('radius', 10))
        service_id = self.request.query_params.get('service_id')
        min_rating = self.request.query_params.get('min_rating')
        price_min = self.request.query_params.get('price_min')
        price_max = self.request.query_params.get('price_max')
        available_date = self.request.query_params.get('available_date')
        available_time = self.request.query_params.get('available_time')
        available_only = self.request.query_params.get('available', '').lower() == 'true'
        sort_by = self.request.query_params.get('sort_by', 'distance')
        limit = int(self.request.query_params.get('limit', 20))
        
        # Валидируем координаты
        if not latitude or not longitude:
            return Provider.objects.none()
        
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (ValueError, TypeError):
            return Provider.objects.none()
        
        if not validate_coordinates(lat, lon):
            return Provider.objects.none()
        
        # Базовый queryset активных провайдеров
        queryset = Provider.objects.filter(is_active=True)
        
        # Исключаем заблокированные учреждения
        blocked_provider_ids = ProviderBlocking.objects.filter(
            status='active'
        ).values_list('provider_id', flat=True)
        queryset = queryset.exclude(id__in=blocked_provider_ids)
        
        # Фильтрация по услуге через локации
        if service_id:
            try:
                service_id = int(service_id)
                # Фильтруем провайдеров, у которых есть активные локации с этой услугой
                queryset = queryset.filter(
                    locations__is_active=True,
                    locations__available_services__service_id=service_id,
                    locations__available_services__is_active=True
                ).distinct()
            except (ValueError, TypeError):
                pass
        
        # Фильтрация по цене через локации
        if service_id and (price_min or price_max):
            try:
                service_id = int(service_id)
                from providers.models import ProviderLocationService
                
                # Фильтруем локации с услугами в указанном диапазоне цен
                location_services_filter = ProviderLocationService.objects.filter(
                    location__provider__in=queryset,
                    location__is_active=True,
                    service_id=service_id,
                    is_active=True
                )
                
                if price_min:
                    try:
                        price_min_val = float(price_min)
                        location_services_filter = location_services_filter.filter(price__gte=price_min_val)
                    except (ValueError, TypeError):
                        pass
                
                if price_max:
                    try:
                        price_max_val = float(price_max)
                        location_services_filter = location_services_filter.filter(price__lte=price_max_val)
                    except (ValueError, TypeError):
                        pass
                
                # Получаем ID провайдеров, у которых есть локации с подходящими ценами
                provider_ids = location_services_filter.values_list('location__provider_id', flat=True).distinct()
                queryset = queryset.filter(id__in=provider_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтрация по доступности
        if available_only and available_date and available_time:
            try:
                # Парсим дату и время
                date_obj = datetime.strptime(available_date, '%Y-%m-%d').date()
                time_obj = datetime.strptime(available_time, '%H:%M').time()
                datetime_obj = datetime.combine(date_obj, time_obj)
                
                # Получаем день недели (0 = понедельник)
                weekday = date_obj.weekday()
                
                # Проверяем доступность слотов
                available_provider_ids = []
                
                for provider in queryset:
                    # Проверяем расписание учреждения
                    provider_schedule = provider.schedules.filter(weekday=weekday).first()
                    if not provider_schedule or provider_schedule.is_closed:
                        continue
                    
                    # Проверяем время работы
                    if (provider_schedule.open_time and provider_schedule.close_time and
                        (time_obj < provider_schedule.open_time or time_obj > provider_schedule.close_time)):
                        continue
                    
                    # Проверяем свободные слоты сотрудников
                    if service_id:
                        # Ищем сотрудников с этой услугой
                        employees = provider.employees.filter(
                            services__id=service_id,
                            is_active=True
                        )
                        
                        # Проверяем доступность хотя бы одного сотрудника
                        has_available_employee = False
                        for employee in employees:
                            # Проверяем расписание сотрудника
                            employee_schedule = employee.schedules.filter(day_of_week=weekday).first()
                            if not employee_schedule or not employee_schedule.is_working:
                                continue
                            
                            # Проверяем время работы сотрудника
                            if (employee_schedule.start_time and employee_schedule.end_time and
                                (time_obj < employee_schedule.start_time or time_obj > employee_schedule.end_time)):
                                continue
                            
                            # Проверяем, нет ли уже бронирования в это время
                            slot_end_time = datetime_obj + timedelta(minutes=30)  # Предполагаем 30 минут
                            conflicting_booking = Booking.objects.filter(
                                employee=employee,
                                scheduled_date=date_obj,
                                scheduled_time__lt=slot_end_time.time(),
                                scheduled_time__gt=datetime_obj.time(),
                                status__in=['confirmed', 'pending']
                            ).exists()
                            
                            if not conflicting_booking:
                                has_available_employee = True
                                break
                        
                        if has_available_employee:
                            available_provider_ids.append(provider.id)
                    else:
                        # Если услуга не указана, считаем доступным если есть работающие сотрудники
                        if provider.employees.filter(is_active=True).exists():
                            available_provider_ids.append(provider.id)
                
                # Фильтруем только доступные учреждения
                if available_provider_ids:
                    queryset = queryset.filter(id__in=available_provider_ids)
                else:
                    return Provider.objects.none()
                    
            except (ValueError, TypeError):
                pass
        
        # Фильтруем провайдеров с активными локациями, у которых есть адреса
        queryset = queryset.filter(
            locations__is_active=True,
            locations__structured_address__isnull=False,
            locations__structured_address__point__isnull=False
        ).distinct()
        
        # Получаем локации в радиусе (вместо провайдеров)
        # Сначала получаем все локации провайдеров
        from providers.models import ProviderLocation
        locations = ProviderLocation.objects.filter(
            provider__in=queryset,
            is_active=True,
            structured_address__isnull=False,
            structured_address__point__isnull=False
        )
        
        # Фильтруем локации по расстоянию
        locations_with_distance = filter_by_distance(
            locations, lat, lon, radius, 'structured_address__point'
        )
        
        # Группируем локации по провайдерам и выбираем ближайшую локацию для каждого провайдера
        providers_with_distance = []
        provider_distances = {}  # {provider_id: min_distance}
        
        for location, distance in locations_with_distance:
            provider_id = location.provider_id
            if provider_id not in provider_distances or distance < provider_distances[provider_id]:
                provider_distances[provider_id] = distance
        
        # Создаем список (provider, distance) для сортировки
        for provider_id, distance in provider_distances.items():
            try:
                provider = Provider.objects.get(id=provider_id)
                providers_with_distance.append((provider, distance))
            except Provider.DoesNotExist:
                pass
        
        rating_map = _get_provider_rating_map([provider for provider, _ in providers_with_distance])
        get_rating = lambda provider: rating_map.get(provider.id, 0)
        
        # Сортировка
        if sort_by == 'rating':
            providers_with_distance.sort(key=lambda x: (-get_rating(x[0]), x[1]))
        elif sort_by == 'price_asc' and service_id:
            # Сортировка по возрастанию цены (минимальная цена из всех локаций)
            def get_min_price(provider):
                from providers.models import ProviderLocationService
                location_service = ProviderLocationService.objects.filter(
                    location__provider=provider,
                    location__is_active=True,
                    service_id=service_id,
                    is_active=True
                ).order_by('price').first()
                return location_service.price if location_service else float('inf')
            
            providers_with_distance.sort(key=lambda x: (get_min_price(x[0]), x[1]))
        elif sort_by == 'price_desc' and service_id:
            # Сортировка по убыванию цены (максимальная цена из всех локаций)
            def get_max_price(provider):
                from providers.models import ProviderLocationService
                location_service = ProviderLocationService.objects.filter(
                    location__provider=provider,
                    location__is_active=True,
                    service_id=service_id,
                    is_active=True
                ).order_by('-price').first()
                return location_service.price if location_service else float('-inf')
            
            providers_with_distance.sort(key=lambda x: (-get_max_price(x[0]), x[1]))
        else:
            # Сортировка по расстоянию (по умолчанию)
            providers_with_distance.sort(key=lambda x: (x[1], -get_rating(x[0])))
        
        # Возвращаем только объекты провайдеров
        return [provider for provider, distance in providers_with_distance[:limit]]
    
    def get_serializer_context(self):
        """
        Добавляет контекст для расчета расстояний и информации о ценах/доступности в сериализатор.
        """
        context = super().get_serializer_context()
        if getattr(self, 'swagger_fake_view', False):
            return context
        context['latitude'] = self.request.query_params.get('latitude')
        context['longitude'] = self.request.query_params.get('longitude')
        context['service_id'] = self.request.query_params.get('service_id')
        context['available_date'] = self.request.query_params.get('available_date')
        context['available_time'] = self.request.query_params.get('available_time')
        return context


class SitterAdvancedSearchByDistanceAPIView(generics.ListAPIView):
    """
    API для расширенного поиска ситтеров по расстоянию с дополнительными фильтрами.
    
    Основные возможности:
    - Поиск ситтеров в указанном радиусе
    - Фильтрация по услугам, расписанию, цене
    - Фильтрация по рейтингу и доступности
    - Сортировка по расстоянию, рейтингу и цене
    - Возвращает расстояние до каждого ситтера
    
    Параметры запроса:
    - latitude: Широта центральной точки
    - longitude: Долгота центральной точки
    - radius: Радиус поиска в километрах (по умолчанию 10)
    - service_id: ID конкретной услуги для фильтрации
    - min_rating: Минимальный рейтинг ситтера
    - max_price: Максимальная цена за услугу
    - available_date: Дата для проверки доступности (YYYY-MM-DD)
    - available_time: Время для проверки доступности (HH:MM)
    - available: Только доступные ситтеры (true/false)
    - limit: Максимальное количество результатов (по умолчанию 20)
    
    Права доступа:
    - Требуется аутентификация
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Возвращает ситтеров в указанном радиусе с расширенными фильтрами.
        """
        if getattr(self, 'swagger_fake_view', False):
            from users.models import User
            return User.objects.none()
        
        from geolocation.utils import filter_by_distance, validate_coordinates
        from sitters.models import PetSitting
        from datetime import datetime, time
        from django.utils import timezone
        
        # Получаем параметры запроса
        latitude = self.request.query_params.get('latitude')
        longitude = self.request.query_params.get('longitude')
        radius = float(self.request.query_params.get('radius', 10))
        service_id = self.request.query_params.get('service_id')
        min_rating = self.request.query_params.get('min_rating')
        max_price = self.request.query_params.get('max_price')
        available_date = self.request.query_params.get('available_date')
        available_time = self.request.query_params.get('available_time')
        available = self.request.query_params.get('available')
        limit = int(self.request.query_params.get('limit', 20))
        
        # Валидируем координаты
        if not latitude or not longitude:
            return User.objects.none()
        
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (ValueError, TypeError):
            return User.objects.none()
        
        if not validate_coordinates(lat, lon):
            return User.objects.none()
        
        # Базовый queryset ситтеров
        queryset = User.objects.filter(
            is_active=True,
            user_types__name='sitter'
        )
        
        # В модели User нет геокоординат/рейтинга для поиска ситтеров по расстоянию
        return User.objects.none()
    
    def get_serializer_context(self):
        """
        Добавляет контекст для расчета расстояний в сериализатор.
        """
        context = super().get_serializer_context()
        if getattr(self, 'swagger_fake_view', False):
            return context
        context['latitude'] = self.request.query_params.get('latitude')
        context['longitude'] = self.request.query_params.get('longitude')
        return context 


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def check_provider_availability(request, provider_id):
    """
    Проверяет доступность учреждения в указанное время.
    
    Args:
        request: HTTP запрос
        provider_id: ID учреждения
    
    Параметры запроса:
    - date: Дата для проверки (YYYY-MM-DD)
    - time: Время для проверки (HH:MM)
    - service_id: ID услуги (опционально)
    - duration_minutes: Продолжительность услуги в минутах (по умолчанию 30)
    
    Returns:
        JSON ответ с информацией о доступности
    """
    try:
        from datetime import datetime, timedelta
        from booking.models import Booking
        
        # Получаем параметры
        date_str = request.GET.get('date')
        time_str = request.GET.get('time')
        service_id = request.GET.get('service_id')
        duration_minutes = int(request.GET.get('duration_minutes', 30))
        
        if not date_str or not time_str:
            return Response({
                'success': False,
                'message': _('Date and time must be specified')
            }, status=400)
        
        # Получаем учреждение
        try:
            provider = Provider.objects.get(id=provider_id, is_active=True)
        except Provider.DoesNotExist:
            return Response({
                'success': False,
                'message': _('Institution not found')
            }, status=404)
        
        # Парсим дату и время
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            time_obj = datetime.strptime(time_str, '%H:%M').time()
            datetime_obj = datetime.combine(date_obj, time_obj)
        except ValueError:
            return Response({
                'success': False,
                'message': _('Invalid date or time format')
            }, status=400)
        
        # Получаем день недели
        weekday = date_obj.weekday()
        
        # Проверяем расписание учреждения
        provider_schedule = provider.schedules.filter(weekday=weekday).first()
        if not provider_schedule or provider_schedule.is_closed:
            return Response({
                'success': True,
                'provider_id': provider_id,
                'available': False,
                'reason': 'provider_closed',
                'message': _('Institution is closed on this day')
            })
        
        # Проверяем время работы
        if (provider_schedule.open_time and provider_schedule.close_time and
            (time_obj < provider_schedule.open_time or time_obj > provider_schedule.close_time)):
            return Response({
                'success': True,
                'provider_id': provider_id,
                'available': False,
                'reason': 'outside_hours',
                'message': _('Institution works from {} to {}').format(provider_schedule.open_time, provider_schedule.close_time)
            })
        
        # Проверяем доступность сотрудников (по услугам в локациях провайдера)
        if service_id:
            try:
                service_id = int(service_id)
                employees = Employee.objects.filter(
                    location_services__provider_location__provider=provider,
                    location_services__service_id=service_id,
                    is_active=True,
                ).distinct()
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid service ID')
                }, status=400)
        else:
            employees = provider.employees.filter(is_active=True)
        
        available_employees = []
        for employee in employees:
            # Проверяем расписание сотрудника
            employee_schedule = employee.schedules.filter(day_of_week=weekday).first()
            if not employee_schedule or not employee_schedule.is_working:
                continue
            
            # Проверяем время работы сотрудника
            if (employee_schedule.start_time and employee_schedule.end_time and
                (time_obj < employee_schedule.start_time or time_obj > employee_schedule.end_time)):
                continue
            
            # Проверяем, нет ли уже бронирования в это время
            slot_end_time = datetime_obj + timedelta(minutes=duration_minutes)
            conflicting_booking = Booking.objects.filter(
                employee=employee,
                scheduled_date=date_obj,
                scheduled_time__lt=slot_end_time.time(),
                scheduled_time__gt=datetime_obj.time(),
                status__in=['confirmed', 'pending']
            ).exists()
            
            if not conflicting_booking:
                services_list = list(
                    EmployeeLocationService.objects.filter(
                        employee=employee,
                        provider_location__provider=provider,
                    ).values_list('service_id', 'service__name').distinct()
                )
                available_employees.append({
                    'id': employee.id,
                    'name': f"{employee.user.first_name} {employee.user.last_name}",
                    'services': [(sid, name) for sid, name in services_list]
                })
        
        if available_employees:
            return Response({
                'success': True,
                'provider_id': provider_id,
                'available': True,
                'available_employees': available_employees,
                'message': _('{} employees available').format(len(available_employees))
            })
        else:
            return Response({
                'success': True,
                'provider_id': provider_id,
                'available': False,
                'reason': 'no_available_employees',
                'message': _('No available employees at this time')
            })
            
    except Exception as e:
        logger.error(f"Error checking provider availability: {e}")
        return Response({
            'success': False,
            'message': _('Error checking availability')
        }, status=500)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_provider_prices(request, provider_id):
    """
    Получает информацию о ценах на услуги в учреждении.
    
    Args:
        request: HTTP запрос
        provider_id: ID учреждения
    
    Параметры запроса:
    - service_id: ID конкретной услуги (опционально)
    
    Returns:
        JSON ответ с информацией о ценах
    """
    try:
        # Получаем учреждение
        try:
            provider = Provider.objects.get(id=provider_id, is_active=True)
        except Provider.DoesNotExist:
            return Response({
                'success': False,
                'message': _('Institution not found')
            }, status=404)
        
        # Получаем параметры
        service_id = request.GET.get('service_id')
        
        # Получаем услуги из всех активных локаций провайдера
        from .serializers import ProviderLocationServiceSerializer
        
        location_services = ProviderLocationService.objects.filter(
            location__provider=provider,
            location__is_active=True,
            is_active=True
        ).select_related('location', 'service')
        
        if service_id:
            try:
                service_id = int(service_id)
                location_services = location_services.filter(service_id=service_id)
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid service ID')
                }, status=400)
        
        # Сериализуем данные
        serializer = ProviderLocationServiceSerializer(location_services, many=True)
        
        return Response({
            'success': True,
            'provider_id': provider_id,
            'services': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Error getting provider prices: {e}")
        return Response({
            'success': False,
            'message': _('Error getting price information')
        }, status=500) 


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_provider_available_slots(request, provider_id):
    """
    Gets available time slots for a specific service at an institution.
    
    Args:
        request: HTTP request
        provider_id: Institution ID
    
    Query parameters:
    - service_id: Service ID (required)
    - date: Date for checking availability (YYYY-MM-DD, optional)
    - time: Time for checking availability (HH:MM, optional)
    - duration_minutes: Service duration in minutes (optional, default from service)
    - horizon_days: Search horizon in days (optional, default 7)
    
    Returns:
        JSON response with available slots information
    """
    try:
        # Get institution
        try:
            provider = Provider.objects.get(id=provider_id, is_active=True)
        except Provider.DoesNotExist:
            return Response({
                'success': False,
                'message': _('Institution not found')
            }, status=404)
        
        # Get parameters
        service_id = request.GET.get('service_id')
        date_str = request.GET.get('date')
        time_str = request.GET.get('time')
        duration_minutes = request.GET.get('duration_minutes')
        horizon_days = int(request.GET.get('horizon_days', 7))
        
        # Validate required parameters
        if not service_id:
            return Response({
                'success': False,
                'message': _('Service ID is required')
            }, status=400)
        
        try:
            service_id = int(service_id)
        except ValueError:
            return Response({
                'success': False,
                'message': _('Invalid service ID')
            }, status=400)
        
        # Get service information from provider locations
        # Используем первую найденную локацию с этой услугой
        location_service = ProviderLocationService.objects.filter(
            location__provider=provider,
            location__is_active=True,
            service_id=service_id,
            is_active=True
        ).first()
        
        if not location_service:
            return Response({
                'success': False,
                'message': _('Service not found at any active location of this institution')
            }, status=404)
        
        # Use service duration if not specified
        if not duration_minutes:
            duration_minutes = location_service.duration_minutes
        else:
            try:
                duration_minutes = int(duration_minutes)
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid duration format')
                }, status=400)
        
        # Parse date and time if provided
        requested_date = None
        requested_time = None
        requested_datetime = None
        
        if date_str:
            try:
                requested_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid date format')
                }, status=400)
        
        if time_str:
            try:
                requested_time = datetime.strptime(time_str, '%H:%M').time()
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid time format')
                }, status=400)
        
        if requested_date and requested_time:
            requested_datetime = datetime.combine(requested_date, requested_time)
        
        # Get available slots
        available_slots = []
        next_available_slot = None
        requested_slot_info = None
        
        # Determine search start date
        if requested_date:
            search_start_date = requested_date
        else:
            search_start_date = timezone.now().date()
        
        # Search for available slots
        current_date = search_start_date
        end_date = current_date + timedelta(days=horizon_days)
        
        while current_date <= end_date:
            weekday = current_date.weekday()
            
            # Check institution schedule
            provider_schedule = provider.schedules.filter(weekday=weekday).first()
            if not provider_schedule or provider_schedule.is_closed:
                current_date += timedelta(days=1)
                continue
            
            # Get working hours
            open_time = provider_schedule.open_time
            close_time = provider_schedule.close_time
            
            if not open_time or not close_time:
                current_date += timedelta(days=1)
                continue
            
            # Get employees for this service
            employees = provider.employees.filter(
                services__id=service_id,
                is_active=True
            )
            
            if not employees.exists():
                current_date += timedelta(days=1)
                continue
            
            # Generate time slots for this day
            current_time = open_time
            slot_end_time = (datetime.combine(current_date, current_time) + 
                           timedelta(minutes=duration_minutes)).time()
            
            while slot_end_time <= close_time:
                # Check if this slot is available
                slot_available = True
                available_employees = []
                
                for employee in employees:
                    # Check employee schedule
                    employee_schedule = employee.schedules.filter(day_of_week=weekday).first()
                    if not employee_schedule or not employee_schedule.is_working:
                        continue
                    
                    # Check employee working hours
                    if (employee_schedule.start_time and employee_schedule.end_time and
                        (current_time < employee_schedule.start_time or 
                         slot_end_time > employee_schedule.end_time)):
                        continue
                    
                    # Check for booking conflicts
                    slot_start_datetime = datetime.combine(current_date, current_time)
                    slot_end_datetime = datetime.combine(current_date, slot_end_time)
                    
                    conflicting_booking = Booking.objects.filter(
                        employee=employee,
                        scheduled_date=current_date,
                        scheduled_time__lt=slot_end_datetime.time(),
                        scheduled_time__gt=slot_start_datetime.time(),
                        status__in=['confirmed', 'pending']
                    ).exists()
                    
                    if not conflicting_booking:
                        available_employees.append({
                            'id': employee.id,
                            'name': f"{employee.user.first_name} {employee.user.last_name}",
                        })
                
                if available_employees:
                    # Получаем цену из первой доступной локации провайдера с этой услугой
                    location_service = ProviderLocationService.objects.filter(
                        location__provider=provider,
                        location__is_active=True,
                        service_id=service_id,
                        is_active=True
                    ).first()
                    price = float(location_service.price) if location_service else 0.0
                    
                    slot_info = {
                        'date': current_date.strftime('%Y-%m-%d'),
                        'time': current_time.strftime('%H:%M'),
                        'end_time': slot_end_time.strftime('%H:%M'),
                        'duration_minutes': duration_minutes,
                        'available_employees': available_employees,
                        'price': price
                    }
                    
                    available_slots.append(slot_info)
                    
                    # Check if this is the requested slot
                    if (requested_datetime and 
                        current_date == requested_date and 
                        current_time == requested_time):
                        requested_slot_info = {
                            'date': current_date.strftime('%Y-%m-%d'),
                            'time': current_time.strftime('%H:%M'),
                            'available': True,
                            'available_employees': available_employees
                        }
                    
                    # Find next available slot
                    if not next_available_slot:
                        next_available_slot = slot_info
                
                # Move to next slot (30-minute intervals)
                current_time = (datetime.combine(current_date, current_time) + 
                              timedelta(minutes=30)).time()
                slot_end_time = (datetime.combine(current_date, current_time) + 
                               timedelta(minutes=duration_minutes)).time()
            
            current_date += timedelta(days=1)
        
        # If requested slot was not found, mark it as unavailable
        if requested_datetime and not requested_slot_info:
            requested_slot_info = {
                'date': requested_date.strftime('%Y-%m-%d'),
                'time': requested_time.strftime('%H:%M'),
                'available': False,
                'reason': 'slot_unavailable'
            }
        
        # Sort available slots by date, time, and price
        available_slots.sort(key=lambda x: (x['date'], x['time'], x['price']))
        
        return Response({
            'success': True,
            'provider_id': provider_id,
            'service_id': service_id,
            'requested_slot': requested_slot_info,
            'next_available_slot': next_available_slot,
            'available_slots': available_slots,
            'total_slots_found': len(available_slots)
        })
        
    except Exception as e:
        logger.error(f'Error getting provider available slots: {e}')
        return Response({
            'success': False,
            'message': _('Error getting available slots')
        }, status=500) 


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def search_providers_map_availability(request):
    """
    Search for institutions on map with nearest available slots for selected service and time.
    
    Args:
        request: HTTP request
    
    Query parameters:
    - latitude: User latitude (required)
    - longitude: User longitude (required)
    - service_id: Service ID (required)
    - date: Date for checking availability (YYYY-MM-DD, optional)
    - time: Time for checking availability (HH:MM, optional)
    - radius: Search radius in kilometers (optional, default 10)
    - min_rating: Minimum institution rating (optional)
    - price_min: Minimum service price (optional)
    - price_max: Maximum service price (optional)
    - sort_by: Sort order (distance, rating, price_asc, price_desc, availability)
    - limit: Maximum results (optional, default 20)
    
    Returns:
        JSON response with institutions and their availability information
    """
    try:
        # Get and validate coordinates
        latitude = request.GET.get('latitude')
        longitude = request.GET.get('longitude')
        
        if not latitude or not longitude:
            return Response({
                'success': False,
                'message': _('Latitude and longitude are required')
            }, status=400)
        
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except ValueError:
            return Response({
                'success': False,
                'message': _('Invalid coordinates format')
            }, status=400)
        
        if not validate_coordinates(latitude, longitude):
            return Response({
                'success': False,
                'message': _('Invalid coordinates')
            }, status=400)
        
        # Get and validate service_id
        service_id = request.GET.get('service_id')
        if not service_id:
            return Response({
                'success': False,
                'message': _('Service ID is required')
            }, status=400)
        
        try:
            service_id = int(service_id)
        except ValueError:
            return Response({
                'success': False,
                'message': _('Invalid service ID')
            }, status=400)
        
        # Get other parameters
        radius = float(request.GET.get('radius', 10))
        min_rating = request.GET.get('min_rating')
        price_min = request.GET.get('price_min')
        price_max = request.GET.get('price_max')
        sort_by = request.GET.get('sort_by', 'distance')
        limit = int(request.GET.get('limit', 20))
        
        date_str = request.GET.get('date')
        time_str = request.GET.get('time')
        
        # Parse date and time if provided
        requested_date = None
        requested_time = None
        requested_datetime = None
        
        if date_str:
            try:
                requested_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid date format')
                }, status=400)
        
        if time_str:
            try:
                requested_time = datetime.strptime(time_str, '%H:%M').time()
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid time format')
                }, status=400)
        
        if requested_date and requested_time:
            requested_datetime = datetime.combine(requested_date, requested_time)
        
        # Get providers in radius
        providers = Provider.objects.filter(is_active=True)
        
        # Получаем локации в радиусе (вместо провайдеров)
        from providers.models import ProviderLocation
        locations = ProviderLocation.objects.filter(
            provider__in=providers,
            is_active=True,
            structured_address__isnull=False,
            structured_address__point__isnull=False
        )
        
        # Фильтруем локации по расстоянию
        locations_with_distance = filter_by_distance(
            locations, latitude, longitude, radius, 'structured_address__point'
        )
        
        # Получаем уникальных провайдеров из локаций
        provider_ids = set()
        location_distances = {}  # {provider_id: min_distance}
        
        for location, distance in locations_with_distance:
            provider_id = location.provider_id
            provider_ids.add(provider_id)
            if provider_id not in location_distances or distance < location_distances[provider_id]:
                location_distances[provider_id] = distance
        
        providers = Provider.objects.filter(id__in=provider_ids)
        
        # Filter by price (через локации)
        if price_min or price_max:
            # Фильтруем провайдеров, у которых есть локации с услугами в указанном диапазоне цен
            from providers.models import ProviderLocationService
            
            location_services_filter = ProviderLocationService.objects.filter(
                location__provider__in=providers,
                location__is_active=True,
                is_active=True
            )
            
            if service_id:
                location_services_filter = location_services_filter.filter(service_id=service_id)
            
            if price_min:
                try:
                    price_min = float(price_min)
                    location_services_filter = location_services_filter.filter(price__gte=price_min)
                except ValueError:
                    return Response({
                        'success': False,
                        'message': _('Invalid minimum price format')
                    }, status=400)
            
            if price_max:
                try:
                    price_max = float(price_max)
                    location_services_filter = location_services_filter.filter(price__lte=price_max)
                except ValueError:
                    return Response({
                        'success': False,
                        'message': _('Invalid maximum price format')
                    }, status=400)
            
            # Получаем ID провайдеров, у которых есть локации с подходящими ценами
            provider_ids = location_services_filter.values_list('location__provider_id', flat=True).distinct()
            providers = providers.filter(id__in=provider_ids)
        
        providers = list(providers)
        rating_map = _get_provider_rating_map(providers)
        
        # Filter by rating (по данным Rating)
        if min_rating:
            try:
                min_rating = float(min_rating)
                providers = [provider for provider in providers if rating_map.get(provider.id, 0) >= min_rating]
            except ValueError:
                return Response({
                    'success': False,
                    'message': _('Invalid rating format')
                }, status=400)
        
        # Limit results
        providers = providers[:limit]
        
        # Get availability information for each provider
        providers_with_availability = []
        
        for provider in providers:
            # Calculate distance using PostGIS (берем расстояние до ближайшей локации)
            distance = location_distances.get(provider.id)
            if distance is not None:
                distance = round(distance, 2)
            else:
                # Fallback: ищем ближайшую локацию
                from providers.models import ProviderLocation
                from django.contrib.gis.geos import Point
                user_point = Point(longitude, latitude, srid=4326)
                nearest_location = ProviderLocation.objects.filter(
                    provider=provider,
                    is_active=True,
                    structured_address__point__isnull=False
                ).annotate(
                    distance=Distance('structured_address__point', user_point)
                ).order_by('distance').first()
                
                if nearest_location:
                    distance = round(nearest_location.distance * 111.32, 2)  # Convert to km
                else:
                    distance = None
            
            # Get service price from first available location
            try:
                location_service = ProviderLocationService.objects.filter(
                    location__provider=provider,
                    location__is_active=True,
                    service_id=service_id,
                    is_active=True
                ).first()
                
                if not location_service:
                    continue
                    
                price = float(location_service.price)
                duration_minutes = location_service.duration_minutes
            except (ProviderLocationService.DoesNotExist, AttributeError):
                continue
            
            # Check availability
            availability_info = check_provider_slot_availability(
                provider, service_id, requested_date, requested_time, duration_minutes
            )
            
            provider_info = {
                'id': provider.id,
                'name': provider.name,
                'address': _get_provider_full_address(provider),
                'rating': rating_map.get(provider.id, 0),
                'distance': distance,
                'price': price,
                'duration_minutes': duration_minutes,
                'requested_slot_available': availability_info['requested_slot_available'],
                'next_available_slot': availability_info['next_available_slot'],
                'availability_reason': availability_info['reason']
            }
            
            providers_with_availability.append(provider_info)
        
        # Sort results
        if sort_by == 'distance':
            providers_with_availability.sort(key=lambda x: (x['distance'] or float('inf')))
        elif sort_by == 'rating':
            providers_with_availability.sort(key=lambda x: (x['rating'] or 0), reverse=True)
        elif sort_by == 'price_asc':
            providers_with_availability.sort(key=lambda x: x['price'])
        elif sort_by == 'price_desc':
            providers_with_availability.sort(key=lambda x: x['price'], reverse=True)
        elif sort_by == 'availability':
            # Sort by availability first, then by distance
            providers_with_availability.sort(key=lambda x: (
                not x['requested_slot_available'],
                x['distance'] or float('inf')
            ))
        
        return Response({
            'success': True,
            'search_params': {
                'latitude': latitude,
                'longitude': longitude,
                'service_id': service_id,
                'radius': radius,
                'requested_date': date_str,
                'requested_time': time_str
            },
            'providers': providers_with_availability,
            'total_found': len(providers_with_availability)
        })
        
    except Exception as e:
        logger.error(f'Error searching providers map availability: {e}')
        return Response({
            'success': False,
            'message': _('Error searching institutions')
        }, status=500)


def check_provider_slot_availability(provider, service_id, requested_date, requested_time, duration_minutes):
    """
    Helper function to check slot availability for a provider.
    
    Args:
        provider: Provider instance
        service_id: Service ID
        requested_date: Requested date (optional)
        requested_time: Requested time (optional)
        duration_minutes: Service duration in minutes
    
    Returns:
        Dictionary with availability information
    """
    try:
        # If no date/time specified, find nearest available slot
        if not requested_date:
            requested_date = timezone.now().date()
        
        # Check if requested slot is available
        requested_slot_available = False
        next_available_slot = None
        reason = 'available'
        
        if requested_time:
            # Check specific time slot
            weekday = requested_date.weekday()
            
            # Check provider schedule
            provider_schedule = provider.schedules.filter(weekday=weekday).first()
            if not provider_schedule or provider_schedule.is_closed:
                reason = 'institution_closed'
            else:
                # Check working hours
                if (provider_schedule.open_time and provider_schedule.close_time and
                    (requested_time < provider_schedule.open_time or 
                     requested_time > provider_schedule.close_time)):
                    reason = 'outside_hours'
                else:
                    # Check employee availability
                    employees = provider.employees.filter(
                        services__id=service_id,
                        is_active=True
                    )
                    
                    if not employees.exists():
                        reason = 'no_employees'
                    else:
                        slot_end_time = (datetime.combine(requested_date, requested_time) + 
                                       timedelta(minutes=duration_minutes)).time()
                        
                        available_employees = []
                        for employee in employees:
                            # Check employee schedule
                            employee_schedule = employee.schedules.filter(day_of_week=weekday).first()
                            if not employee_schedule or not employee_schedule.is_working:
                                continue
                            
                            # Check employee working hours
                            if (employee_schedule.start_time and employee_schedule.end_time and
                                (requested_time < employee_schedule.start_time or 
                                 slot_end_time > employee_schedule.end_time)):
                                continue
                            
                            # Check for booking conflicts
                            conflicting_booking = Booking.objects.filter(
                                employee=employee,
                                scheduled_date=requested_date,
                                scheduled_time__lt=slot_end_time,
                                scheduled_time__gt=requested_time,
                                status__in=['confirmed', 'pending']
                            ).exists()
                            
                            if not conflicting_booking:
                                available_employees.append(employee.id)
                        
                        if available_employees:
                            requested_slot_available = True
                            reason = 'available'
                        else:
                            reason = 'slot_occupied'
        
        # Find next available slot if requested slot is not available
        if not requested_slot_available:
            next_available_slot = find_next_available_slot(
                provider, service_id, requested_date, duration_minutes
            )
        
        return {
            'requested_slot_available': requested_slot_available,
            'next_available_slot': next_available_slot,
            'reason': reason
        }
        
    except Exception as e:
        logger.error(f'Error checking provider slot availability: {e}')
        return {
            'requested_slot_available': False,
            'next_available_slot': None,
            'reason': 'error'
        }


def find_next_available_slot(provider, service_id, start_date, duration_minutes):
    """
    Helper function to find next available slot for a provider.
    
    Args:
        provider: Provider instance
        service_id: Service ID
        start_date: Start date for search
        duration_minutes: Service duration in minutes
    
    Returns:
        Dictionary with next available slot info or None
    """
    try:
        current_date = start_date
        end_date = current_date + timedelta(days=7)  # Search for 7 days
        
        while current_date <= end_date:
            weekday = current_date.weekday()
            
            # Check provider schedule
            provider_schedule = provider.schedules.filter(weekday=weekday).first()
            if not provider_schedule or provider_schedule.is_closed:
                current_date += timedelta(days=1)
                continue
            
            # Get working hours
            open_time = provider_schedule.open_time
            close_time = provider_schedule.close_time
            
            if not open_time or not close_time:
                current_date += timedelta(days=1)
                continue
            
            # Get employees
            employees = provider.employees.filter(
                services__id=service_id,
                is_active=True
            )
            
            if not employees.exists():
                current_date += timedelta(days=1)
                continue
            
            # Check time slots
            current_time = open_time
            slot_end_time = (datetime.combine(current_date, current_time) + 
                           timedelta(minutes=duration_minutes)).time()
            
            while slot_end_time <= close_time:
                # Check if slot is available
                for employee in employees:
                    # Check employee schedule
                    employee_schedule = employee.schedules.filter(day_of_week=weekday).first()
                    if not employee_schedule or not employee_schedule.is_working:
                        continue
                    
                    # Check employee working hours
                    if (employee_schedule.start_time and employee_schedule.end_time and
                        (current_time < employee_schedule.start_time or 
                         slot_end_time > employee_schedule.end_time)):
                        continue
                    
                    # Check for booking conflicts
                    conflicting_booking = Booking.objects.filter(
                        employee=employee,
                        scheduled_date=current_date,
                        scheduled_time__lt=slot_end_time,
                        scheduled_time__gt=current_time,
                        status__in=['confirmed', 'pending']
                    ).exists()
                    
                    if not conflicting_booking:
                        return {
                            'date': current_date.strftime('%Y-%m-%d'),
                            'time': current_time.strftime('%H:%M'),
                            'employee_id': employee.id,
                            'employee_name': f"{employee.user.first_name} {employee.user.last_name}"
                        }
                
                # Move to next slot (30-minute intervals)
                current_time = (datetime.combine(current_date, current_time) + 
                              timedelta(minutes=30)).time()
                slot_end_time = (datetime.combine(current_date, current_time) + 
                               timedelta(minutes=duration_minutes)).time()
            
            current_date += timedelta(days=1)
        
        return None
        
    except Exception as e:
        logger.error(f'Error finding next available slot: {e}')
        return None


class ProviderLocationListCreateAPIView(generics.ListCreateAPIView):
    """
    API для просмотра списка и создания локаций провайдера.
    
    Основные возможности:
    - Получение списка локаций провайдера
    - Создание новой локации
    - Фильтрация по провайдеру и статусу активности
    
    Права доступа:
    - Требуется аутентификация
    - Provider admin может управлять только локациями своей организации
    """
    serializer_class = ProviderLocationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['provider', 'is_active']
    search_fields = ['name', 'phone_number', 'email']
    ordering_fields = ['name', 'created_at']

    def get_serializer_class(self):
        # Для списка используем облегчённый сериализатор без тяжёлых массивов услуг/цен.
        if self.request.method == 'GET':
            return ProviderLocationListSerializer
        return ProviderLocationSerializer
    
    def get_queryset(self):
        """
        Возвращает queryset локаций с учетом прав доступа.
        """
        queryset = ProviderLocation.objects.select_related(
            'provider', 'provider__invoice_currency', 'structured_address', 'manager'
        )
        if self.request.method == 'GET':
            queryset = queryset.prefetch_related(
                'served_pet_types',
                'employees', 'schedules', 'location_schedules', 'location_services'
            )
        else:
            queryset = queryset.prefetch_related('served_pet_types')
        
        # Provider admin видит только локации своей организации
        if self.request.user.get_managed_providers().exists():
            managed_providers = self.request.user.get_managed_providers()
            queryset = queryset.filter(provider__in=managed_providers)
        
        return queryset
    
    def perform_create(self, serializer):
        """
        Создает локацию с проверкой прав доступа.
        """
        # Проверяем права доступа - только provider_admin и system_admin могут создавать локации
        if not (self.request.user.get_managed_providers().exists() or _user_has_role(self.request.user, 'system_admin')):
            raise PermissionDenied(
                _('You do not have permission to create locations.')
            )
        
        provider = serializer.validated_data.get('provider')
        
        # Проверяем права доступа для provider_admin
        if self.request.user.get_managed_providers().exists():
            managed_providers = self.request.user.get_managed_providers()
            if provider not in managed_providers:
                raise PermissionDenied(
                    _('You can only create locations for your own organization.')
                )
        # Автоматически назначаем владельца организации менеджером филиала
        from providers.models import EmployeeProvider
        owner_ep = EmployeeProvider.objects.filter(
            provider=provider,
            is_owner=True
        ).first()
        
        manager = None
        if owner_ep and owner_ep.employee and hasattr(owner_ep.employee, 'user'):
            manager = owner_ep.employee.user
            if not manager.has_role('branch_manager'):
                manager.add_role('branch_manager')
                
        serializer.save(manager=manager)


class ProviderLocationRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для просмотра, обновления и удаления локации провайдера.
    
    Права доступа:
    - Требуется аутентификация
    - Provider admin может управлять только локациями своей организации
    """
    serializer_class = ProviderLocationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Возвращает queryset локаций с учетом прав доступа.
        """
        queryset = ProviderLocation.objects.select_related(
            'provider', 'provider__invoice_currency', 'structured_address', 'manager'
        ).prefetch_related(
            'available_services', 'served_pet_types',
            'employees', 'schedules', 'location_schedules', 'location_services',
            'location_services__service', 'location_services__pet_type'
        )
        
        # Provider admin видит только локации своей организации
        if self.request.user.get_managed_providers().exists():
            managed_providers = self.request.user.get_managed_providers()
            queryset = queryset.filter(provider__in=managed_providers)
        
        return queryset
    
    def perform_update(self, serializer):
        """
        Обновляет локацию с проверкой прав доступа.
        """
        provider = serializer.validated_data.get('provider', serializer.instance.provider)
        
        # Проверяем права доступа
        if self.request.user.get_managed_providers().exists():
            managed_providers = self.request.user.get_managed_providers()
            if provider not in managed_providers:
                raise PermissionDenied(
                    _('You can only update locations of your own organization.')
                )
        
        serializer.save()
    
    def perform_destroy(self, instance):
        """
        Удаляет локацию с проверкой прав доступа.
        """
        # Проверяем права доступа
        if self.request.user.get_managed_providers().exists():
            managed_providers = self.request.user.get_managed_providers()
            if instance.provider not in managed_providers:
                raise PermissionDenied(
                    _('You can only delete locations of your own organization.')
                )
        
        instance.delete()


def _location_manager_queryset(request):
    """Queryset локаций, которыми может управлять текущий пользователь (для установки/снятия руководителя)."""
    qs = ProviderLocation.objects.select_related('provider', 'manager')
    if request.user.get_managed_providers().exists():
        managed = request.user.get_managed_providers()
        qs = qs.filter(provider__in=managed)
    else:
        qs = qs.none()
    return qs


class SetLocationManagerAPIView(APIView):
    """
    Установка руководителя точки по email.
    Если админ ввёл свой email — руководитель назначается сразу.
    Если чужой email — создаётся инвайт, отправляется письмо с кодом; руководитель назначается после принятия инвайта.
    POST body: { "email": "user@example.com" }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        location = get_object_or_404(_location_manager_queryset(request), pk=pk)
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response(
                {'email': [_('This field is required.')]},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {'email': [_('No user with this email address was found.')]},
                status=status.HTTP_404_NOT_FOUND
            )
        old_manager = location.manager
        if user.id == request.user.id:
            location.manager = user
            location.save(update_fields=['manager'])
            user.add_role('branch_manager')
            if old_manager and old_manager.pk != user.pk:
                from invites.services import maybe_remove_role
                maybe_remove_role(old_manager, 'branch_manager')
            ser = ProviderLocationSerializer(location)
            return Response(ser.data)
        from invites.models import Invite
        from invites.email import send_invite_email
        from django.utils import timezone
        # Отменяем старые pending инвайты руководителя этой локации
        Invite.objects.filter(
            provider_location=location,
            invite_type=Invite.TYPE_BRANCH_MANAGER,
            status=Invite.STATUS_PENDING,
        ).update(status=Invite.STATUS_CANCELLED)
        try:
            token = Invite.generate_token()
        except Exception:
            return Response(
                {'detail': _('Could not generate a unique activation code. Please try again.')},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        expires_at = timezone.now() + timezone.timedelta(days=7)
        invite = Invite.objects.create(
            invite_type=Invite.TYPE_BRANCH_MANAGER,
            email=user.email,
            token=token,
            expires_at=expires_at,
            created_by=request.user,
            provider_location=location,
            provider=location.provider,
        )
        # We do not modify location.manager here so that the location always has a manager
        # It will be updated when the invite is accepted.
        lang = (request.data.get('language') or '').strip().lower() or 'en'
        if lang not in ('en', 'ru', 'de', 'me'):
            lang = translation.get_language() or getattr(request, 'LANGUAGE_CODE', 'en')
        try:
            send_invite_email(invite, lang)
        except Exception:
            invite.delete()
            return Response(
                {'detail': _('Failed to send invitation email.')},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        ser = ProviderLocationSerializer(location)
        return Response(ser.data)

class CancelLocationManagerInviteAPIView(APIView):
    """
    Отмена отправленного приглашения руководителю точки.
    DELETE provider-locations/<pk>/manager-invite/
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        from invites.models import Invite
        location = get_object_or_404(_location_manager_queryset(request), pk=pk)
        Invite.objects.filter(
            provider_location=location,
            invite_type=Invite.TYPE_BRANCH_MANAGER,
            status=Invite.STATUS_PENDING,
        ).update(status=Invite.STATUS_CANCELLED)
        return Response(status=status.HTTP_204_NO_CONTENT)





class LocationStaffListAPIView(APIView):
    """
    Список персонала филиала: сотрудники (принявшие инвайт) и ожидающие инвайты.
    GET provider-locations/<pk>/staff/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        from invites.models import Invite
        location = get_object_or_404(_location_manager_queryset(request), pk=pk)
        provider = location.provider
        
        # Determine location-specific active status via EmployeeLocationRole
        from providers.models import EmployeeLocationRole
        location_roles = {
            r.employee_id: r
            for r in EmployeeLocationRole.objects.filter(provider_location=location)
        }

        employees = []
        for ep in EmployeeProvider.objects.filter(
            provider=provider,
            employee__locations=location,
            end_date__isnull=True,
        ).select_related('employee', 'employee__user').distinct():
            
            # Default to active if role record doesn't exist
            role_obj = location_roles.get(ep.employee_id)
            is_active_loc = role_obj.is_active if role_obj else True
            
            employees.append({
                'type': 'employee',
                'id': ep.employee_id,
                'email': ep.employee.user.email,
                'first_name': ep.employee.user.first_name,
                'last_name': ep.employee.user.last_name,
                'is_owner': ep.is_owner,
                'is_provider_manager': ep.is_provider_manager,
                'is_provider_admin': ep.is_provider_admin,
                'is_manager': ep.is_manager,
                'is_active': is_active_loc,
            })
        invites = []
        for inv in Invite.objects.filter(
            provider_location=location,
            invite_type=Invite.TYPE_SPECIALIST,
            status=Invite.STATUS_PENDING,
            expires_at__gt=timezone.now(),
        ).order_by('-created_at'):
            invites.append({
                'type': 'invite',
                'id': inv.id,
                'email': inv.email,
                'created_at': inv.created_at,
                'expires_at': inv.expires_at,
            })
        return Response({
            'employees': employees,
            'invites': invites,
        })


def _get_location_and_staff_employee(request, location_pk, employee_id):
    """
    Возвращает (location, employee) если пользователь может управлять локацией
    и сотрудник привязан к этой локации. Иначе raises 404 или PermissionDenied.
    """
    location = get_object_or_404(_location_manager_queryset(request), pk=location_pk)
    employee = get_object_or_404(Employee, pk=employee_id)
    if not employee.locations.filter(pk=location.pk).exists():
        raise PermissionDenied(_('This employee is not assigned to this location.'))
    return location, employee


class LocationStaffServicesAPIView(APIView):
    """
    Услуги сотрудника в контексте филиала: список и установка.
    GET provider-locations/<location_pk>/staff/<employee_id>/services/
    PATCH provider-locations/<location_pk>/staff/<employee_id>/services/
    Body PATCH: { "service_ids": [1, 2, 3] } — только ID из доступных в локации.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, location_pk, employee_id):
        location, employee = _get_location_and_staff_employee(request, location_pk, employee_id)
        employee_service_ids = list(
            EmployeeLocationService.objects.filter(
                employee=employee, provider_location=location
            ).values_list('service_id', flat=True)
        )
        return Response({'service_ids': employee_service_ids})

    def patch(self, request, location_pk, employee_id):
        from django.db import transaction
        location, employee = _get_location_and_staff_employee(request, location_pk, employee_id)
        # Услуги филиала (из прайса)
        allowed_ids = set(
            ProviderLocationService.objects.filter(
                location=location, is_active=True
            ).values_list('service_id', flat=True).distinct()
        )
        # Технические услуги (is_client_facing=False) из глобального каталога — разрешены для назначения любому сотруднику
        tech_root_ids = set(
            Service.objects.filter(parent__isnull=True, is_active=True, is_client_facing=False)
            .values_list('id', flat=True)
        )
        tech_all_ids = set(tech_root_ids)
        tech_frontier = set(tech_root_ids)
        while tech_frontier:
            tech_children = set(
                Service.objects.filter(parent_id__in=tech_frontier, is_active=True)
                .values_list('id', flat=True)
            ) - tech_all_ids
            if not tech_children:
                break
            tech_all_ids.update(tech_children)
            tech_frontier = tech_children
        # Добавляем все технические услуги (включая подкатегории)
        allowed_ids |= tech_all_ids
        service_ids = request.data.get('service_ids')
        if not isinstance(service_ids, list):
            return Response(
                {'service_ids': [_('Must be a list of service IDs.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ids = [int(x) for x in service_ids]
        except (ValueError, TypeError):
            return Response(
                {'service_ids': [_('All items must be integers.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invalid = set(ids) - allowed_ids
        if invalid:
            return Response(
                {'service_ids': [_('Some service IDs are not available at this location.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            EmployeeLocationService.objects.filter(
                employee=employee, provider_location=location
            ).delete()
            EmployeeLocationService.objects.bulk_create([
                EmployeeLocationService(employee=employee, provider_location=location, service_id=sid)
                for sid in ids
            ])
        return Response({'service_ids': ids})


class LocationStaffServicesAddByCategoryAPIView(APIView):
    """
    Добавление услуг сотруднику по категории (все листовые услуги категории, доступные в локации).
    POST provider-locations/<location_pk>/staff/<employee_id>/services/add-by-category/
    Body: { "category_id": <id> }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, location_pk, employee_id):
        from django.db import transaction
        location, employee = _get_location_and_staff_employee(request, location_pk, employee_id)
        category_id = request.data.get('category_id')
        if category_id is None:
            return Response(
                {'category_id': [_('This field is required.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            category_id = int(category_id)
        except (ValueError, TypeError):
            return Response(
                {'category_id': [_('Must be an integer.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        location_service_ids = set(
            ProviderLocationService.objects.filter(
                location=location, is_active=True
            ).values_list('service_id', flat=True).distinct()
        )
        # Листовые услуги: все потомки категории без своих детей, входящие в location_service_ids
        descendants = set()
        frontier = {category_id}
        while frontier:
            children = set(
                Service.objects.filter(parent_id__in=frontier, is_active=True).values_list('id', flat=True)
            )
            if not children:
                break
            descendants.update(children)
            frontier = children
        parent_ids = set(Service.objects.filter(parent_id__in=descendants).values_list('parent_id', flat=True))
        leaf_ids = descendants - parent_ids
        if category_id in location_service_ids:
            leaf_ids.add(category_id)
        to_add = leaf_ids & location_service_ids
        if not to_add:
            return Response(
                {'category_id': [_('No leaf services found for this category at this location.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            current = set(
                EmployeeLocationService.objects.filter(
                    employee=employee, provider_location=location
                ).values_list('service_id', flat=True)
            )
            to_create = to_add - current
            if to_create:
                EmployeeLocationService.objects.bulk_create([
                    EmployeeLocationService(employee=employee, provider_location=location, service_id=sid)
                    for sid in to_create
                ])
        new_list = list(
            EmployeeLocationService.objects.filter(
                employee=employee, provider_location=location
            ).values_list('service_id', flat=True)
        )
        return Response({'service_ids': new_list, 'added_count': len(to_create)})


class LocationStaffSchedulePatternAPIView(APIView):
    """
    Паттерн рабочего расписания сотрудника в филиале (7 дней).
    GET provider-locations/<location_pk>/staff/<employee_id>/schedules/
    PUT provider-locations/<location_pk>/staff/<employee_id>/schedules/
    Body PUT: { "days": [ { "day_of_week": 0, "start_time": "09:00", "end_time": "18:00",
      "break_start": null, "break_end": null, "is_working": true }, ... ] }
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, location_pk, employee_id):
        location, employee = _get_location_and_staff_employee(request, location_pk, employee_id)
        schedules = Schedule.objects.filter(
            employee=employee,
            provider_location=location,
        ).order_by('day_of_week')
        out = []
        for s in schedules:
            out.append({
                'id': s.id,
                'day_of_week': s.day_of_week,
                'start_time': s.start_time.strftime('%H:%M') if s.start_time else None,
                'end_time': s.end_time.strftime('%H:%M') if s.end_time else None,
                'break_start': s.break_start.strftime('%H:%M') if s.break_start else None,
                'break_end': s.break_end.strftime('%H:%M') if s.break_end else None,
                'is_working': s.is_working,
            })
        # Расписание филиала: по умолчанию и границы для графика работника (паттерн и смены в праздники — на фронте из location schedules + holiday-shifts).
        location_schedules = LocationSchedule.objects.filter(
            provider_location=location
        ).order_by('weekday')
        loc_days = []
        for dow in range(7):
            ls = next((x for x in location_schedules if x.weekday == dow), None)
            if ls:
                loc_days.append({
                    'day_of_week': dow,
                    'open_time': ls.open_time.strftime('%H:%M') if ls.open_time else None,
                    'close_time': ls.close_time.strftime('%H:%M') if ls.close_time else None,
                    'is_closed': ls.is_closed,
                })
            else:
                loc_days.append({
                    'day_of_week': dow,
                    'open_time': None,
                    'close_time': None,
                    'is_closed': True,
                })
        return Response({'days': out, 'location_schedule': {'days': loc_days}})

    def put(self, request, location_pk, employee_id):
        from django.db import transaction
        from datetime import time as dt_time
        location, employee = _get_location_and_staff_employee(request, location_pk, employee_id)
        days = request.data.get('days')
        if not isinstance(days, list) or len(days) != 7:
            return Response(
                {'days': [_('Must be an array of exactly 7 items (one per weekday).')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        def parse_time(s):
            if s is None or s == '':
                return None
            if isinstance(s, dt_time):
                return s
            parts = str(s).strip().split(':')
            if len(parts) >= 2:
                try:
                    return dt_time(int(parts[0]) % 24, int(parts[1]) % 60)
                except ValueError:
                    pass
            return None
        # График работника не должен выходить за рамки графика филиала; в выходной филиала смена запрещена.
        location_schedules_map = {
            ls.weekday: ls
            for ls in LocationSchedule.objects.filter(provider_location=location)
        }
        for day_data in days:
            dow = day_data.get('day_of_week')
            if dow not in range(7):
                continue
            loc_day = location_schedules_map.get(dow)
            is_closed = loc_day.is_closed if loc_day else True
            loc_open = loc_day.open_time if loc_day and not loc_day.is_closed else None
            loc_close = loc_day.close_time if loc_day and not loc_day.is_closed else None
            is_working = bool(day_data.get('is_working', True))
            if is_closed and is_working:
                return Response(
                    {'days': [_('The branch is closed on this day. Employee cannot be set as working.')]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if is_working and (loc_open is not None or loc_close is not None):
                start_time = parse_time(day_data.get('start_time')) or dt_time(9, 0)
                end_time = parse_time(day_data.get('end_time')) or dt_time(18, 0)
                if loc_open is not None and start_time < loc_open:
                    return Response(
                        {'days': [_('Employee start time must not be before the branch opening time for this day.')]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if loc_close is not None and end_time > loc_close:
                    return Response(
                        {'days': [_('Employee end time must not be after the branch closing time for this day.')]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        with transaction.atomic():
            for day_data in days:
                dow = day_data.get('day_of_week')
                if dow not in range(7):
                    return Response(
                        {'days': [_('Each day_of_week must be 0-6.')]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                is_working = bool(day_data.get('is_working', True))
                start_time = parse_time(day_data.get('start_time')) or dt_time(9, 0)
                end_time = parse_time(day_data.get('end_time')) or dt_time(18, 0)
                break_start = parse_time(day_data.get('break_start'))
                break_end = parse_time(day_data.get('break_end'))
                if not is_working:
                    start_time = None
                    end_time = None
                    break_start = None
                    break_end = None
                try:
                    Schedule.objects.update_or_create(
                        employee=employee,
                        provider_location=location,
                        day_of_week=dow,
                        defaults={
                            'start_time': start_time,
                            'end_time': end_time,
                            'break_start': break_start,
                            'break_end': break_end,
                            'is_working': is_working,
                        },
                    )
                except ValidationError as e:
                    return Response(
                        {'days': e.messages if hasattr(e, 'messages') else [str(e)]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        schedules = Schedule.objects.filter(
            employee=employee,
            provider_location=location,
        ).order_by('day_of_week')
        out = []
        for s in schedules:
            out.append({
                'id': s.id,
                'day_of_week': s.day_of_week,
                'start_time': s.start_time.strftime('%H:%M') if s.start_time else None,
                'end_time': s.end_time.strftime('%H:%M') if s.end_time else None,
                'break_start': s.break_start.strftime('%H:%M') if s.break_start else None,
                'break_end': s.break_end.strftime('%H:%M') if s.break_end else None,
                'is_working': s.is_working,
            })
        return Response({'days': out})


class LocationScheduleListCreateAPIView(generics.ListCreateAPIView):
    """
    API расписания работы локации: список и создание записей по дням недели.
    URL: provider-locations/<location_pk>/schedules/
    """
    serializer_class = LocationScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        location_pk = self.kwargs.get('location_pk')
        queryset = LocationSchedule.objects.filter(provider_location_id=location_pk).order_by('weekday')
        if self.request.user.get_managed_providers().exists():
            managed = self.request.user.get_managed_providers()
            queryset = queryset.filter(provider_location__provider__in=managed)
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['location_pk'] = self.kwargs.get('location_pk')
        return context

    def perform_create(self, serializer):
        location_pk = self.kwargs.get('location_pk')
        location = get_object_or_404(ProviderLocation.objects.filter(pk=location_pk))
        if self.request.user.get_managed_providers().exists():
            managed = self.request.user.get_managed_providers()
            if location.provider not in managed:
                raise PermissionDenied(_('You can only manage schedules of your organization locations.'))
        serializer.save(provider_location=location)


class LocationScheduleRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API одной записи расписания локации: просмотр, обновление, удаление.
    URL: provider-locations/<location_pk>/schedules/<pk>/
    """
    serializer_class = LocationScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        location_pk = self.kwargs.get('location_pk')
        queryset = LocationSchedule.objects.filter(provider_location_id=location_pk)
        if self.request.user.get_managed_providers().exists():
            managed = self.request.user.get_managed_providers()
            queryset = queryset.filter(provider_location__provider__in=managed)
        return queryset


class HolidayShiftListCreateAPIView(generics.ListCreateAPIView):
    """
    API смен в праздничные дни: список и создание для локации.
    URL: provider-locations/<location_pk>/holiday-shifts/
    """
    serializer_class = HolidayShiftSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from .models import HolidayShift
        location_pk = self.kwargs.get('location_pk')
        queryset = HolidayShift.objects.filter(provider_location_id=location_pk).order_by('date')
        if self.request.user.get_managed_providers().exists():
            managed = self.request.user.get_managed_providers()
            queryset = queryset.filter(provider_location__provider__in=managed)
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['location_pk'] = self.kwargs.get('location_pk')
        return context

    def perform_create(self, serializer):
        location_pk = self.kwargs.get('location_pk')
        location = get_object_or_404(ProviderLocation.objects.filter(pk=location_pk))
        if self.request.user.get_managed_providers().exists():
            managed = self.request.user.get_managed_providers()
            if location.provider not in managed:
                raise PermissionDenied(_('You can only manage holiday shifts of your organization locations.'))
        serializer.save(provider_location=location)


class HolidayShiftRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API одной смены в праздник: просмотр, обновление, удаление.
    URL: provider-locations/<location_pk>/holiday-shifts/<pk>/
    """
    serializer_class = HolidayShiftSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from .models import HolidayShift
        location_pk = self.kwargs.get('location_pk')
        queryset = HolidayShift.objects.filter(provider_location_id=location_pk)
        if self.request.user.get_managed_providers().exists():
            managed = self.request.user.get_managed_providers()
            queryset = queryset.filter(provider_location__provider__in=managed)
        return queryset


class ProviderLocationServiceListCreateAPIView(generics.ListCreateAPIView):
    """
    API для просмотра списка и создания услуг в локации провайдера.
    
    Основные возможности:
    - Получение списка услуг локации
    - Создание новой услуги в локации
    - Фильтрация по локации и статусу активности
    
    Пагинация отключена, чтобы админка провайдера получала все услуги филиала за один запрос
    (иначе при PAGE_SIZE=20 часть услуг не отображается и не скрывается из справочника «Добавить»).
    
    Права доступа:
    - Требуется аутентификация
    - Provider admin может управлять только услугами локаций своей организации
    """
    serializer_class = ProviderLocationServiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['location', 'service', 'pet_type', 'size_code', 'is_active']
    ordering_fields = ['price', 'duration_minutes', 'created_at']

    def get_queryset(self):
        """
        Возвращает queryset записей услуг локаций (локация + услуга + тип + размер) с учётом прав.
        """
        queryset = ProviderLocationService.objects.select_related(
            'location', 'location__provider', 'service', 'pet_type'
        )
        
        # Provider admin видит только услуги локаций своей организации
        if self.request.user.get_managed_providers().exists():
            managed_providers = self.request.user.get_managed_providers()
            queryset = queryset.filter(location__provider__in=managed_providers)
        
        return queryset
    
    def perform_create(self, serializer):
        """
        Создаёт одну запись услуги локации (location + service + pet_type + size_code) с проверкой прав.
        """
        location = serializer.validated_data.get('location')
        if self.request.user.get_managed_providers().exists():
            managed_providers = self.request.user.get_managed_providers()
            if location.provider not in managed_providers:
                raise PermissionDenied(
                    _('You can only create services for locations of your own organization.')
                )
        service = serializer.validated_data.get('service')
        if service and not service.is_client_facing:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'service': [_('Cannot add technical (non-client-facing) services to the location price matrix.')]})
        serializer.save()


class ProviderLocationServiceRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API для просмотра, обновления и удаления услуги в локации провайдера.
    
    Права доступа:
    - Требуется аутентификация
    - Provider admin может управлять только услугами локаций своей организации
    """
    serializer_class = ProviderLocationServiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Возвращает queryset услуг локаций с учетом прав доступа.
        """
        queryset = ProviderLocationService.objects.select_related(
            'location', 'location__provider', 'service', 'pet_type'
        )
        
        # Provider admin видит только услуги локаций своей организации
        if self.request.user.get_managed_providers().exists():
            managed_providers = self.request.user.get_managed_providers()
            queryset = queryset.filter(location__provider__in=managed_providers)
        
        return queryset
    
    def perform_update(self, serializer):
        """
        Обновляет услугу локации с проверкой прав доступа.
        """
        location = serializer.validated_data.get('location', serializer.instance.location)
        
        # Проверяем права доступа
        if self.request.user.get_managed_providers().exists():
            managed_providers = self.request.user.get_managed_providers()
            if location.provider not in managed_providers:
                raise PermissionDenied(
                    _('You can only update services of locations of your own organization.')
                )
        
        serializer.save()
    
    def perform_destroy(self, instance):
        """
        Удаляет одну запись услуги локации (одна комбинация тип+размер) с проверкой прав.
        """
        if self.request.user.get_managed_providers().exists():
            managed_providers = self.request.user.get_managed_providers()
            if instance.location.provider not in managed_providers:
                raise PermissionDenied(
                    _('You can only delete services of locations of your own organization.')
                )
        instance.delete()


class LocationPriceMatrixAPIView(APIView):
    """
    GET: матрица цен по услугам локации (по типам животных и размерам).
    Только услуги, добавленные в локацию; только типы из served_pet_types.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        location = get_object_or_404(ProviderLocation.objects.prefetch_related('served_pet_types'), pk=pk)
        if request.user.get_managed_providers().exists():
            managed = request.user.get_managed_providers()
            if location.provider not in managed:
                raise PermissionDenied(_('You can only view locations of your own organization.'))
        # Определяем язык из Accept-Language (как в каталоге)
        lang = translation.get_language() or 'en'
        accept_lang = request.headers.get('Accept-Language', '')
        if accept_lang:
            lang = accept_lang.split(',')[0].split('-')[0].strip()
        lang = 'me' if lang == 'cnr' else lang
        served_ids = set(location.served_pet_types.values_list('id', flat=True))
        rows = ProviderLocationService.objects.filter(
            location=location
        ).select_related('service', 'pet_type').order_by('service__name', 'pet_type__code', 'size_code')
        # Группируем по (service_id) -> по pet_type_id -> variants (size_code, price, duration)
        by_service = {}
        for row in rows:
            if row.pet_type_id not in served_ids:
                continue
            if row.service_id not in by_service:
                by_service[row.service_id] = {
                    'location_service_id': row.id,
                    'service_id': row.service_id,
                    'service_name': row.service.get_localized_name(lang) if hasattr(row.service, 'get_localized_name') else (getattr(row.service, 'name', '') or ''),
                    'prices': {},
                }
            s = by_service[row.service_id]
            if row.pet_type_id not in s['prices']:
                s['prices'][row.pet_type_id] = {
                    'pet_type_id': row.pet_type_id,
                    'pet_type_code': row.pet_type.code,
                    'pet_type_name': row.pet_type.get_localized_name(lang) if hasattr(row.pet_type, 'get_localized_name') else (getattr(row.pet_type, 'name', None) or row.pet_type.code),
                    'base_price': str(row.price),
                    'base_duration_minutes': row.duration_minutes,
                    'variants': [],
                }
            s['prices'][row.pet_type_id]['variants'].append({
                'size_code': row.size_code,
                'price': str(row.price),
                'duration_minutes': row.duration_minutes,
            })
        result = []
        for sid, s in by_service.items():
            result.append({
                'location_service_id': s['location_service_id'],
                'service_id': s['service_id'],
                'service_name': s['service_name'],
                'prices': list(s['prices'].values()),
            })
        return Response(result)


class LocationServicePricesUpdateAPIView(APIView):
    """
    PUT: полная замена матрицы цен по одной услуге локации (по типам животных и размерам).
    Тело: { "prices": [ { "pet_type_id", "base_price", "base_duration_minutes", "variants": [ { "size_code", "price", "duration_minutes" } ] } ] }.
    pet_type_id должны быть из location.served_pet_types.
    """
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, location_pk, location_service_id):
        from django.db import transaction
        location = get_object_or_404(
            ProviderLocation.objects.prefetch_related('served_pet_types'),
            pk=location_pk
        )
        if request.user.get_managed_providers().exists():
            managed = request.user.get_managed_providers()
            if location.provider not in managed:
                raise PermissionDenied(_('You can only edit locations of your own organization.'))
        location_service = get_object_or_404(
            ProviderLocationService.objects.select_related('service'),
            pk=location_service_id,
            location=location,
        )
        if not location_service.service.is_client_facing:
            return Response(
                {'detail': [_('Cannot update technical (non-client-facing) services in the location price matrix.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        served_ids = set(location.served_pet_types.values_list('id', flat=True))
        ser = LocationServicePricesUpdateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        for item in ser.validated_data['prices']:
            if item['pet_type_id'] not in served_ids:
                return Response(
                    {'prices': [_('Each pet_type_id must be one of the location\'s served pet types.')]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        with transaction.atomic():
            ProviderLocationService.objects.filter(
                location=location,
                service=location_service.service,
            ).delete()
            for item in ser.validated_data['prices']:
                pet_type_id = item['pet_type_id']
                base_price = item['base_price']
                base_duration = item['base_duration_minutes']
                for v in item.get('variants', []):
                    ProviderLocationService.objects.create(
                        location=location,
                        service=location_service.service,
                        pet_type_id=pet_type_id,
                        size_code=v['size_code'],
                        price=v.get('price', base_price),
                        duration_minutes=v.get('duration_minutes', base_duration),
                    )
        return Response(status=status.HTTP_204_NO_CONTENT)


class LocationCatalogServicePricesUpdateAPIView(APIView):
    """
    POST/PUT: полная замена матрицы цен по одной услуге из глобального каталога (по service_id).
    Тело: { "prices": [ { "pet_type_id", "base_price", "base_duration_minutes", "variants": [ { "size_code", "price", "duration_minutes" } ] } ] }.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, location_pk, service_id):
        return self._update(request, location_pk, service_id)
        
    def put(self, request, location_pk, service_id):
        return self._update(request, location_pk, service_id)

    def _update(self, request, location_pk, service_id):
        from django.db import transaction
        from catalog.models import Service
        location = get_object_or_404(
            ProviderLocation.objects.prefetch_related('served_pet_types'),
            pk=location_pk
        )
        if request.user.get_managed_providers().exists():
            managed = request.user.get_managed_providers()
            if location.provider not in managed:
                raise PermissionDenied(_('You can only edit locations of your own organization.'))
        service = get_object_or_404(Service, pk=service_id)
        if not service.is_client_facing:
            return Response(
                {'detail': [_('Cannot add technical (non-client-facing) services to the location price matrix.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        served_ids = set(location.served_pet_types.values_list('id', flat=True))
        ser = LocationServicePricesUpdateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
            
        if not ser.validated_data['prices']:
            return Response(
                {'prices': [_('At least one price row (pet type and size) is required.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for item in ser.validated_data['prices']:
            if item['pet_type_id'] not in served_ids:
                return Response(
                    {'prices': [_('Each pet_type_id must be one of the location\'s served pet types.')]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
                
        with transaction.atomic():
            ProviderLocationService.objects.filter(
                location=location,
                service=service,
            ).delete()
            for item in ser.validated_data['prices']:
                pet_type_id = item['pet_type_id']
                base_price = item['base_price']
                base_duration = item['base_duration_minutes']
                for v in item.get('variants', []):
                    ProviderLocationService.objects.create(
                        location=location,
                        service=service,
                        pet_type_id=pet_type_id,
                        size_code=v['size_code'],
                        price=v.get('price', base_price),
                        duration_minutes=v.get('duration_minutes', base_duration),
                    )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProviderAvailableCatalogServicesAPIView(APIView):
    """
    Список услуг каталога, доступных для выбора провайдером (ветви из available_category_levels).
    Для вкладки «Услуги и цены»: быстрый поиск и выбор только из разрешённых для организации услуг.
    Если передан location_id — возвращаются только услуги, доступные хотя бы одному типу животных филиала
    (услуга без allowed_pet_types или с пересечением allowed_pet_types с location.served_pet_types).
    Если передан include_technical=1 — включаются также технические услуги (is_client_facing=False),
    которые не добавляются в прайс филиала, но могут назначаться сотрудникам.
    GET /api/v1/providers/<provider_id>/available-catalog-services/?q=...&location_id=...&include_technical=1
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, provider_id):
        provider = get_object_or_404(Provider, pk=provider_id)
        if request.user.get_managed_providers().exists():
            managed = request.user.get_managed_providers()
            if provider not in managed:
                raise PermissionDenied(_('You can only view services for your own organization.'))
        root_ids = list(
            provider.available_category_levels.filter(level=0, parent__isnull=True)
            .values_list('id', flat=True)
        )
        # Собираем все дочерние узлы рекурсивно: уровень вложенности не ограничен.
        allowed_ids = set(root_ids)
        frontier_ids = set(root_ids)
        while frontier_ids:
            child_ids = set(
                Service.objects.filter(parent_id__in=frontier_ids, is_active=True)
                .values_list('id', flat=True)
            ) - allowed_ids
            if not child_ids:
                break
            allowed_ids.update(child_ids)
            frontier_ids = child_ids

        # Если include_technical — добавляем все технические услуги из глобального каталога
        # (они общие для всех организаций и не привязаны к available_category_levels)
        include_technical = request.query_params.get('include_technical') in ('1', 'true')
        if include_technical:
            tech_root_ids = set(
                Service.objects.filter(parent__isnull=True, is_active=True, is_client_facing=False)
                .values_list('id', flat=True)
            )
            # Также собираем потомков технических корней
            tech_all_ids = set(tech_root_ids)
            tech_frontier = set(tech_root_ids)
            while tech_frontier:
                tech_children = set(
                    Service.objects.filter(parent_id__in=tech_frontier, is_active=True)
                    .values_list('id', flat=True)
                ) - tech_all_ids
                if not tech_children:
                    break
                tech_all_ids.update(tech_children)
                tech_frontier = tech_children
            if tech_all_ids:
                allowed_ids.update(tech_all_ids)
                
        if not allowed_ids:
            return Response([])

        qs = Service.objects.filter(id__in=allowed_ids, is_active=True).order_by('hierarchy_order', 'name')
        # Фильтр по типам животных филиала: только услуги без ограничения или с пересечением с served_pet_types
        location_id_param = request.query_params.get('location_id')
        if location_id_param:
            try:
                loc = ProviderLocation.objects.prefetch_related('served_pet_types').get(pk=location_id_param)
            except (ProviderLocation.DoesNotExist, ValueError):
                return Response([])
            if loc.provider_id != provider.id:
                raise PermissionDenied(_('Location does not belong to this organization.'))
            served_ids = list(loc.served_pet_types.values_list('id', flat=True))
            if not served_ids:
                return Response([])
            if include_technical:
                # Клиентские услуги фильтруем по типам животных, технические — включаем все
                qs = qs.annotate(_n_apt=Count('allowed_pet_types')).filter(
                    Q(is_client_facing=False) |
                    Q(_n_apt=0) | Q(allowed_pet_types__in=served_ids)
                ).distinct().order_by('hierarchy_order', 'name')
            else:
                qs = qs.annotate(_n_apt=Count('allowed_pet_types')).filter(
                    Q(_n_apt=0) | Q(allowed_pet_types__in=served_ids)
                ).distinct().order_by('hierarchy_order', 'name')
        q = (request.query_params.get('q') or '').strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(name_en__icontains=q) | Q(name_ru__icontains=q) |
                Q(name_de__icontains=q) | Q(name_me__icontains=q)
            )
        lang = request.query_params.get('lang') or translation.get_language() or 'en'
        lang = 'me' if lang == 'cnr' else (lang.split('-')[0] if lang else 'en')
        parent_ids = set(qs.exclude(parent_id__isnull=True).values_list('parent_id', flat=True))
        out = []
        for s in qs:
            name = s.get_localized_name(lang) if hasattr(s, 'get_localized_name') else s.name
            out.append({
                'id': s.id,
                'name': name,
                'parent_id': s.parent_id,
                'level': s.level,
                'has_children': s.id in parent_ids,
                'is_client_facing': s.is_client_facing,
            })
        return Response(out) 