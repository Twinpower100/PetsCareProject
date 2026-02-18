from rest_framework import generics, status, permissions, serializers
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
import re
from .serializers import (
    UserSerializer, 
    UserRegistrationSerializer,
    GoogleAuthSerializer,
    UserRoleAssignmentSerializer,
    ProviderFormSerializer,
    ProviderFormApprovalSerializer,
    ProviderAdminRegistrationSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    AccountDeactivationSerializer
)
from google.oauth2 import id_token
from google.auth.transport import requests
from django.conf import settings
from .models import UserType, ProviderForm, EmployeeSpecialization, PasswordResetToken
from providers.models import ManagerTransferInvite, EmployeeProvider
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from providers.models import Provider, Employee
from rest_framework.exceptions import PermissionDenied
from sitters.models import PetSitting
from pets.models import Pet
from rest_framework.viewsets import ModelViewSet
from django.utils import timezone
from .models import RoleInvite
from .serializers import (
    RoleInviteSerializer,
    RoleInviteCreateSerializer,
    RoleInviteAcceptSerializer,
    RoleInviteDeclineSerializer,
    RoleTerminationSerializer
)
from rest_framework.serializers import ValidationError
from django.db.models import Q
from geolocation.utils import filter_by_distance, validate_coordinates
import logging
logger = logging.getLogger(__name__)
# from audit.models import AuditLog  # временно отключено - приложение audit отключено

User = get_user_model()


class UserRegistrationAPIView(generics.CreateAPIView):
    """
    Класс для регистрации новых пользователей.
    Позволяет создать пользователя с email, username и паролем.
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        """
        Создает пользователя и возвращает токены вместе с профилем.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)


class UserLoginAPIView(TokenObtainPairView):
    """
    Класс для аутентификации пользователя и получения JWT-токенов.
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, *args, **kwargs):
        """
        Возвращает токены вместе с профилем пользователя.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        data['user'] = UserSerializer(serializer.user).data
        return Response(data, status=status.HTTP_200_OK)


class UserProfileAPIView(generics.RetrieveUpdateAPIView):
    """
    Класс для просмотра и редактирования профиля текущего пользователя.
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # Возвращаем текущего пользователя без дополнительных проверок роли
        if getattr(self, 'swagger_fake_view', False):
            from users.models import User
            return User.objects.none().first()  # Возвращаем None для схемы
        return self.request.user


class GoogleAuthAPIView(generics.CreateAPIView):
    """
    Класс для аутентификации через Google OAuth2.
    Создаёт пользователя, если он не существует, и возвращает JWT-токены.
    """
    serializer_class = GoogleAuthSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        """
        Обрабатывает аутентификацию через Google и выдаёт токены.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            # Получаем данные пользователя из сериализатора
            google_data = serializer.validated_data['google_user_data']
            email = google_data['email']
            
            # Получение или создание пользователя
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                # Username генерируется автоматически в UserManager
                # Получаем телефон от Google, если есть
                google_phone = google_data.get('phone')
                phone_number = google_phone if google_phone else ''
                
                user = User.objects.create_user(
                    email=email,
                    first_name=google_data.get('name', '').split(' ')[0] if google_data.get('name') else '',
                    last_name=' '.join(google_data.get('name', '').split(' ')[1:]) if google_data.get('name') and len(google_data.get('name', '').split(' ')) > 1 else '',
                    phone_number=phone_number,  # Пустая строка, если Google не предоставил телефон
                    password=None  # Пароль не нужен для социальной аутентификации
                )
            
            # Генерация JWT токенов
            refresh = RefreshToken.for_user(user)
            user_data = UserSerializer(user).data
            
            # Проверяем, нужен ли телефон для завершения регистрации
            needs_phone = not user.phone_number
            
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': user_data,
                'needs_phone': needs_phone
            })
            
        except Exception as e:
            return Response(
                {'error': _(str(e))},
                status=status.HTTP_400_BAD_REQUEST
            ) 

class IsSystemAdmin(permissions.BasePermission):
    """
    Кастомное разрешение: доступ только для системного администратора.
    """
    def has_permission(self, request, view):
        """
        Проверяет, является ли пользователь системным администратором.
        """
        return request.user.is_system_admin()

class UserRoleAssignmentAPIView(APIView):
    """
    Класс для назначения ролей пользователям.
    Доступно только системному администратору.
    """
    permission_classes = [IsSystemAdmin]
    
    def post(self, request):
        """
        Назначение ролей пользователям.
        Доступно только системному администратору.
        """
        serializer = UserRoleAssignmentSerializer(data=request.data)
        if serializer.is_valid():
            user = User.objects.get(id=serializer.validated_data['user_id'])
            role = serializer.validated_data['role']
            
            if role == 'provider_admin':
                # Проверка формы учреждения
                if not ProviderForm.objects.filter(
                    created_by=user,
                    status='approved'
                ).exists():
                    return Response(
                        {'error': _('Provider form not approved')},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            user_type = UserType.objects.get(name=role)
            user.user_types.add(user_type)
            user.save()
            return Response({'status': 'success'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProviderFormListCreateAPIView(generics.ListCreateAPIView):
    """
    API для просмотра и создания заявок учреждений.

    - GET: Возвращает список заявок. Системный администратор видит все заявки, обычный пользователь — только свои.
    - POST: Создаёт новую заявку учреждения от текущего пользователя.
    """
    serializer_class = ProviderFormSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = []  # Отключаем django_filters для совместимости со Swagger
    
    def get_queryset(self):
        """
        Возвращает queryset заявок в зависимости от роли пользователя.
        Системный администратор видит все заявки, обычный пользователь — только свои.
        """
        if getattr(self, 'swagger_fake_view', False):
            return ProviderForm.objects.none()
        if self.request.user.is_system_admin():
            return ProviderForm.objects.all()
        return ProviderForm.objects.filter(created_by=self.request.user)
    
    def perform_create(self, serializer):
        """
        Сохраняет заявку учреждения с указанием текущего пользователя как создателя.
        """
        serializer.save(created_by=self.request.user)

class ProviderFormApprovalAPIView(APIView):
    """
    API для одобрения или отклонения заявок учреждений.

    Доступно только системному администратору.
    - POST: Одобряет или отклоняет заявку учреждения по её ID и действию ('approve' или 'reject').
    """
    permission_classes = [IsSystemAdmin]
    
    def post(self, request):
        """
        Обрабатывает одобрение или отклонение заявки учреждения.
        """
        serializer = ProviderFormApprovalSerializer(data=request.data)
        if serializer.is_valid():
            form = ProviderForm.objects.get(id=serializer.validated_data['form_id'])
            action = serializer.validated_data['action']
            
            try:
                if action == 'approve':
                    form.approve(request.user)
                else:
                    form.reject(request.user)
                return Response({'status': 'success'})
            except ValueError as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserDeactivationAPIView(APIView):
    permission_classes = [IsSystemAdmin]
    
    def post(self, request, user_id):
        """
        Деактивация пользователя.
        Доступно только системному администратору.
        """
        try:
            user = User.objects.get(id=user_id)
            user.is_active = False
            user.save()
            return Response({'status': 'success'})
        except User.DoesNotExist:
            return Response(
                {'error': _('User not found')},
                status=status.HTTP_404_NOT_FOUND
            )

class EmployeeDeactivationAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, employee_id):
        """
        Деактивация сотрудника учреждения.
        Доступно системному администратору или администратору учреждения.
        """
        try:
            employee = Employee.objects.get(id=employee_id)
            
            # Проверка прав на деактивацию
            if not (request.user.is_system_admin() or 
                   (request.user.is_provider_admin() and 
                    employee.providers.filter(
                        admins__user=request.user,
                        admins__is_active=True
                    ).exists())):
                return Response(
                    {'error': _('Permission denied')},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            employee.is_active = False
            employee.save()
            return Response({'status': 'success'})
        except Employee.DoesNotExist:
            return Response(
                {'error': _('Employee not found')},
                status=status.HTTP_404_NOT_FOUND
            )


class RoleInviteViewSet(APIView):
    """
    ViewSet для управления инвайтами на роли.
    
    Поддерживает:
    - Создание инвайтов (только менеджеры и системные админы)
    - Просмотр списка инвайтов
    - Детали инвайта
    - Отмена инвайта
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Получает список инвайтов."""
        if getattr(self, 'swagger_fake_view', False):
            return Response([])
        try:
            user = request.user
            
            if user.has_role('system_admin') or user.is_superuser:
                invites = RoleInvite.objects.all()
            elif user.has_role('employee'):
                try:
                    from providers.models import Employee, EmployeeProvider
                    employee = Employee.objects.get(user=user)
                    managed_providers = EmployeeProvider.objects.filter(
                        employee=employee,
                        is_manager=True,
                        status='active'
                    ).values_list('provider_id', flat=True)
                    invites = RoleInvite.objects.filter(provider_id__in=managed_providers)
                except Employee.DoesNotExist:
                    invites = RoleInvite.objects.none()
            else:
                invites = RoleInvite.objects.filter(email=user.email)
            
            serializer = RoleInviteSerializer(invites, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {'error': _('Failed to get role invites')},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def post(self, request):
        """Создает новый инвайт."""
        if getattr(self, 'swagger_fake_view', False):
            return Response({})
        try:
            serializer = RoleInviteSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(created_by=request.user)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': 'Failed to create role invite'},
                status=status.HTTP_400_BAD_REQUEST
            )


class RoleInviteDetailView(APIView):
    """API для детального управления инвайтом на роль."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, pk):
        """Получает детали инвайта."""
        if getattr(self, 'swagger_fake_view', False):
            return Response({})
        try:
            invite = RoleInvite.objects.get(pk=pk)
            serializer = RoleInviteSerializer(invite)
            return Response(serializer.data)
        except RoleInvite.DoesNotExist:
            return Response(
                {'error': _('Role invite not found')},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': 'Failed to get role invite'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def put(self, request, pk):
        """Обновляет инвайт."""
        if getattr(self, 'swagger_fake_view', False):
            return Response({})
        try:
            invite = RoleInvite.objects.get(pk=pk)
            serializer = RoleInviteSerializer(invite, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except RoleInvite.DoesNotExist:
            return Response(
                {'error': _('Role invite not found')},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': 'Failed to update role invite'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def delete(self, request, pk):
        """Удаляет инвайт."""
        if getattr(self, 'swagger_fake_view', False):
            return Response({})
        try:
            invite = RoleInvite.objects.get(pk=pk)
            invite.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except RoleInvite.DoesNotExist:
            return Response(
                {'error': _('Role invite not found')},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': 'Failed to delete role invite'},
                status=status.HTTP_400_BAD_REQUEST
            )


class RoleInviteAcceptAPIView(APIView):
    """
    API для принятия инвайта на роль.
    
    Поддерживает:
    - Принятие инвайта по токену
    - Автоматическое назначение роли
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Принимает инвайт на роль.
        """
        serializer = RoleInviteAcceptSerializer(data=request.data)
        if serializer.is_valid():
            try:
                invite = serializer.accept_invite(request.user)
                return Response({
                    'message': _('Role invite accepted successfully'),
                    'invite': RoleInviteSerializer(invite).data
                }, status=status.HTTP_200_OK)
            except ValidationError as e:
                return Response({
                    'error': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RoleInviteDeclineAPIView(APIView):
    """
    API для отклонения инвайта на роль.
    
    Поддерживает:
    - Отклонение инвайта по токену
    - Уведомление создателя инвайта
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Отклоняет инвайт на роль.
        """
        serializer = RoleInviteDeclineSerializer(data=request.data)
        if serializer.is_valid():
            try:
                invite = serializer.decline_invite(request.user)
                return Response({
                    'message': _('Role invite declined successfully'),
                    'invite': RoleInviteSerializer(invite).data
                }, status=status.HTTP_200_OK)
            except ValidationError as e:
                return Response({
                    'error': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RoleInviteByTokenAPIView(APIView):
    """
    API для получения информации об инвайте по токену.
    
    Поддерживает:
    - Получение деталей инвайта по токену
    - Проверку валидности токена
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, token):
        """
        Получает информацию об инвайте по токену.
        """
        try:
            invite = RoleInvite.objects.get(token=token)
            serializer = RoleInviteSerializer(invite)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except RoleInvite.DoesNotExist:
            return Response({
                'error': _('Invalid invite token')
            }, status=status.HTTP_404_NOT_FOUND)


class RoleInviteQRCodeAPIView(APIView):
    """
    API для получения QR-кода инвайта.
    
    Поддерживает:
    - Генерацию QR-кода для мобильного приложения
    - Сканирование QR-кода
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, invite_id):
        """
        Получает QR-код для инвайта.
        """
        try:
            invite = RoleInvite.objects.get(id=invite_id)
            
            # Проверяем права доступа
            if not self._can_access_invite(request.user, invite):
                return Response({
                    'error': _('Access denied')
                }, status=status.HTTP_403_FORBIDDEN)
            
            return Response({
                'qr_code': invite.qr_code,
                'token': invite.token,
                'expires_at': invite.expires_at
            }, status=status.HTTP_200_OK)
        except RoleInvite.DoesNotExist:
            return Response({
                'error': _('Invite not found')
            }, status=status.HTTP_404_NOT_FOUND)
    
    def _can_access_invite(self, user, invite):
        """
        Проверяет права доступа к инвайту.
        """
        # Создатель инвайта
        if invite.created_by == user:
            return True
        
        # Получатель инвайта
        if invite.email == user.email:
            return True
        
        # Системный админ
        if user.is_system_admin():
            return True
        
        # Менеджер учреждения
        if user.is_employee() and user.employee_profile.employeeprovider_set.filter(
            provider=invite.provider, is_manager=True, is_confirmed=True
        ).exists():
            return True
        
        return False


class RoleTerminationAPIView(APIView):
    """
    API для увольнения пользователя с роли.
    
    Поддерживает:
    - Увольнение сотрудника (менеджером учреждения)
    - Увольнение менеджера по биллингу (системным админом)
    - Уведомления об увольнении
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Увольняет пользователя с роли.
        """
        serializer = RoleTerminationSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            try:
                self._terminate_role(serializer.validated_data)
                return Response({
                    'message': _('User role terminated successfully')
                }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({
                    'error': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def _terminate_role(self, data):
        """
        Выполняет увольнение пользователя с роли.
        """
        user_id = data['user_id']
        role = data['role']
        provider_id = data['provider_id']
        reason = data.get('reason', '')
        
        target_user = User.objects.get(id=user_id)
        provider = Provider.objects.get(id=provider_id)
        
        if role == 'employee':
            self._terminate_employee(target_user, provider, reason)
        elif role == 'billing_manager':
            self._terminate_billing_manager(target_user, provider, reason)
    
    def _terminate_employee(self, user, provider, reason):
        """
        Увольняет сотрудника.
        """
        from providers.models import EmployeeProvider
        
        # Находим активную связь сотрудника с учреждением
        employee_provider = EmployeeProvider.objects.get(
            employee__user=user,
            provider=provider,
            end_date__isnull=True
        )
        
        # Устанавливаем дату окончания
        employee_provider.end_date = timezone.now().date()
        employee_provider.save()
        
        # Отправляем уведомление
        self._send_termination_notification(user, 'employee', provider, reason)
    
    def _terminate_billing_manager(self, user, provider, reason):
        """
        Увольняет менеджера по биллингу.
        """
        from billing.models import BillingManagerProvider
        
        # Находим активную связь менеджера с провайдером
        billing_manager_provider = BillingManagerProvider.objects.get(
            billing_manager=user,
            provider=provider,
            status__in=['active', 'vacation']
        )
        
        # Завершаем управление
        billing_manager_provider.terminate(reason)
        
        # Отправляем уведомление
        self._send_termination_notification(user, 'billing_manager', provider, reason)
    
    def _send_termination_notification(self, user, role, provider, reason):
        """
        Отправляет уведомление об увольнении.
        """
        # TODO: Реализовать отправку уведомления пользователю
        pass


class RoleInvitePendingAPIView(APIView):
    """
    API для получения активных инвайтов пользователя.
    
    Поддерживает:
    - Получение списка активных инвайтов для текущего пользователя
    - Фильтрацию по ролям
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Получает активные инвайты для текущего пользователя.
        """
        role = request.query_params.get('role')
        
        queryset = RoleInvite.get_pending_for_email(request.user.email)
        
        if role:
            queryset = queryset.filter(role=role)
        
        serializer = RoleInviteSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RoleInviteCleanupAPIView(APIView):
    """
    API для очистки истекших инвайтов.
    
    Поддерживает:
    - Автоматическую очистку истекших инвайтов
    - Отчет о количестве очищенных инвайтов
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Очищает истекшие инвайты.
        """
        if not request.user.is_system_admin():
            return Response({
                'error': _('Only system administrators can cleanup invites')
            }, status=status.HTTP_403_FORBIDDEN)
        
        cleaned_count = RoleInvite.cleanup_expired()
        
        return Response({
            'message': _('Expired invites cleaned successfully'),
            'cleaned_count': cleaned_count
        }, status=status.HTTP_200_OK)


class UserSearchByDistanceAPIView(generics.ListAPIView):
    """
    API для поиска пользователей по расстоянию от указанной точки.
    
    Основные возможности:
    - Поиск пользователей в указанном радиусе
    - Фильтрация по ролям (ситтеры, владельцы питомцев)
    - Сортировка по расстоянию
    - Возвращает расстояние до каждого пользователя
    
    Параметры запроса:
    - latitude: Широта центральной точки
    - longitude: Долгота центральной точки
    - radius: Радиус поиска в километрах (по умолчанию 10)
    - user_type: Тип пользователя для фильтрации (sitter, pet_owner)
    - limit: Максимальное количество результатов (по умолчанию 20)
    
    Права доступа:
    - Требуется аутентификация
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Возвращает пользователей в указанном радиусе.
        """
        # Получаем параметры запроса
        latitude = self.request.query_params.get('latitude')
        longitude = self.request.query_params.get('longitude')
        radius = float(self.request.query_params.get('radius', 10))
        user_type = self.request.query_params.get('user_type')
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
        
        # Базовый queryset
        queryset = User.objects.filter(is_active=True)
        
        # Фильтрация по типу пользователя
        if user_type:
            if user_type == 'sitter':
                queryset = queryset.filter(user_types__name='sitter')
            elif user_type == 'pet_owner':
                queryset = queryset.filter(user_types__name='pet_owner')
        
        # В модели User нет геокоординат для поиска по расстоянию
        return User.objects.none()
    
    def get_serializer_context(self):
        """
        Добавляет контекст для расчета расстояний в сериализатор.
        """
        context = super().get_serializer_context()
        context['latitude'] = self.request.query_params.get('latitude')
        context['longitude'] = self.request.query_params.get('longitude')
        return context


class SitterSearchByDistanceAPIView(generics.ListAPIView):
    """
    API для поиска ситтеров по расстоянию от указанной точки.
    
    Основные возможности:
    - Поиск ситтеров в указанном радиусе
    - Фильтрация по доступности и рейтингу
    - Сортировка по расстоянию и рейтингу
    - Возвращает расстояние до каждого ситтера
    
    Параметры запроса:
    - latitude: Широта центральной точки
    - longitude: Долгота центральной точки
    - radius: Радиус поиска в километрах (по умолчанию 10)
    - min_rating: Минимальный рейтинг ситтера
    - available: Только доступные ситтеры (true/false)
    - limit: Максимальное количество результатов (по умолчанию 20)
    
    Права доступа:
    - Требуется аутентификация
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Возвращает ситтеров в указанном радиусе.
        """
        from geolocation.utils import filter_by_distance, validate_coordinates
        from sitters.models import PetSitting
        
        # Получаем параметры запроса
        latitude = self.request.query_params.get('latitude')
        longitude = self.request.query_params.get('longitude')
        radius = float(self.request.query_params.get('radius', 10))
        min_rating = self.request.query_params.get('min_rating')
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
        
        # В модели User нет геокоординат и рейтинга для ситтеров
        return User.objects.none()
    
    def get_serializer_context(self):
        """
        Добавляет контекст для расчета расстояний в сериализатор.
        """
        context = super().get_serializer_context()
        context['latitude'] = self.request.query_params.get('latitude')
        context['longitude'] = self.request.query_params.get('longitude')
        return context


class BulkRoleAssignmentAPIView(APIView):
    """
    API для массового назначения ролей пользователям.
    """
    permission_classes = [IsSystemAdmin]

    def post(self, request):
        """Массово назначает роли пользователям."""
        try:
            assignments = request.data.get('assignments', [])
            results = {
                'success': [],
                'failed': []
            }

            for assignment in assignments:
                user_id = assignment.get('user_id')
                role = assignment.get('role')
                reason = assignment.get('reason', '')

                try:
                    user = User.objects.get(id=user_id)
                    
                    # Проверяем, что роль существует
                    from .models import UserType
                    if not UserType.objects.filter(name=role).exists():
                        results['failed'].append({
                            'user_id': user_id,
                            'error': _('Invalid role: {role}').format(role=role)
                        })
                        continue

                    # Назначаем роль
                    user.add_role(role)
                    
                    # Логируем действие (временно отключено)
                    # AuditLog.objects.create(
                    #     user=request.user,
                    #     action='role_assigned',
                    #     resource_type='user',
                    #     resource_id=user.id,
                    #     resource_name=user.email,
                    #     details={
                    #         'assigned_role': role,
                    #         'reason': reason,
                    #         'assigned_by': request.user.email
                    #     },
                    #     ip_address=request.META.get('REMOTE_ADDR'),
                    #     user_agent=request.META.get('HTTP_USER_AGENT')
                    # )

                    results['success'].append({
                        'user_id': user_id,
                        'user_email': user.email,
                        'role': role
                    })

                except User.DoesNotExist:
                    results['failed'].append({
                        'user_id': user_id,
                        'error': _('User not found')
                    })
                except Exception as e:
                    results['failed'].append({
                        'user_id': user_id,
                        'error': str(e)
                    })

            return Response({
                'message': f'Bulk role assignment completed. Success: {len(results["success"])}, Failed: {len(results["failed"])}',
                'results': results
            })

        except Exception as e:
            logger.error(f"Bulk role assignment failed: {e}")
            return Response(
                {'error': _('Failed to perform bulk role assignment')},
                status=status.HTTP_400_BAD_REQUEST
            )


class BulkUserDeactivationAPIView(APIView):
    """
    API для массовой деактивации пользователей.
    """
    permission_classes = [IsSystemAdmin]

    def post(self, request):
        """Массово деактивирует пользователей."""
        try:
            user_ids = request.data.get('user_ids', [])
            reason = request.data.get('reason', 'Bulk deactivation')
            results = {
                'success': [],
                'failed': []
            }

            for user_id in user_ids:
                try:
                    user = User.objects.get(id=user_id)
                    
                    # Деактивируем пользователя
                    user.is_active = False
                    user.save()
                    
                    # Логируем действие (временно отключено)
                    # AuditLog.objects.create(
                    #     user=request.user,
                    #     action='user_deactivated',
                    #     resource_type='user',
                    #     resource_id=user.id,
                    #     resource_name=user.email,
                    #     details={
                    #         'reason': reason,
                    #         'deactivated_by': request.user.email
                    #     },
                    #     ip_address=request.META.get('REMOTE_ADDR'),
                    #     user_agent=request.META.get('HTTP_USER_AGENT')
                    # )

                    results['success'].append({
                        'user_id': user_id,
                        'user_email': user.email
                    })

                except User.DoesNotExist:
                    results['failed'].append({
                        'user_id': user_id,
                        'error': 'User not found'
                    })
                except Exception as e:
                    results['failed'].append({
                        'user_id': user_id,
                        'error': str(e)
                    })

            return Response({
                'message': f'Bulk user deactivation completed. Success: {len(results["success"])}, Failed: {len(results["failed"])}',
                'results': results
            })

        except Exception as e:
            logger.error(f"Bulk user deactivation failed: {e}")
            return Response(
                {'error': _('Failed to perform bulk user deactivation')},
                status=status.HTTP_400_BAD_REQUEST
            )


class BulkUserActivationAPIView(APIView):
    """
    API для массовой активации пользователей.
    """
    permission_classes = [IsSystemAdmin]

    def post(self, request):
        """Массово активирует пользователей."""
        try:
            user_ids = request.data.get('user_ids', [])
            reason = request.data.get('reason', 'Bulk activation')
            results = {
                'success': [],
                'failed': []
            }

            for user_id in user_ids:
                try:
                    user = User.objects.get(id=user_id)
                    
                    # Активируем пользователя
                    user.is_active = True
                    user.save()
                    
                    # Логируем действие (временно отключено)
                    # AuditLog.objects.create(
                    #     user=request.user,
                    #     action='user_activated',
                    #     resource_type='user',
                    #     resource_id=user.id,
                    #     resource_name=user.email,
                    #     details={
                    #         'reason': reason,
                    #         'activated_by': request.user.email
                    #     },
                    #     ip_address=request.META.get('REMOTE_ADDR'),
                    #     user_agent=request.META.get('HTTP_USER_AGENT')
                    # )

                    results['success'].append({
                        'user_id': user_id,
                        'user_email': user.email
                    })

                except User.DoesNotExist:
                    results['failed'].append({
                        'user_id': user_id,
                        'error': 'User not found'
                    })
                except Exception as e:
                    results['failed'].append({
                        'user_id': user_id,
                        'error': str(e)
                    })

            return Response({
                'message': f'Bulk user activation completed. Success: {len(results["success"])}, Failed: {len(results["failed"])}',
                'results': results
            })

        except Exception as e:
            logger.error(f"Bulk user activation failed: {e}")
            return Response(
                {'error': _('Failed to perform bulk user activation')},
                status=status.HTTP_400_BAD_REQUEST
            )


class CheckEmailAPIView(APIView):
    """
    API для проверки уникальности email.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """
        Проверяет уникальность email.
        """
        email = request.query_params.get('email')
        
        if not email:
            return Response(
                {'error': _('Email parameter is required')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Валидация формата email
        try:
            validate_email(email)
            valid = True
        except DjangoValidationError:
            valid = False
        
        # Проверка уникальности
        exists = User.objects.filter(email=email).exists()
        
        return Response({
            'email': email,
            'exists': exists,
            'valid': valid
        })


class CheckPhoneAPIView(APIView):
    """
    API для проверки уникальности номера телефона.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """
        Проверяет уникальность номера телефона.
        """
        phone = request.query_params.get('phone')
        
        if not phone:
            return Response(
                {'error': _('Phone parameter is required')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Валидация формата телефона
        phone_regex = r'^\+?[1-9]\d{1,14}$'
        valid = bool(re.match(phone_regex, phone))
        
        # Проверка уникальности
        exists = User.objects.filter(phone_number=phone).exists()
        
        return Response({
            'phone': phone,
            'exists': exists,
            'valid': valid
        })


class CheckProviderNameAPIView(APIView):
    """
    API для проверки уникальности названия провайдера.
    
    Проверяет, существует ли уже организация с таким названием
    в ProviderForm или Provider.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        Проверяет уникальность названия провайдера.
        
        Query параметры:
        - provider_name: название организации для проверки
        
        Returns:
        - exists: True, если организация с таким названием уже существует
        """
        provider_name = request.query_params.get('provider_name')
        
        if not provider_name:
            return Response(
                {'error': _('Provider name parameter is required')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Проверяем уникальность в ProviderForm (заявки) и Provider (одобренные организации)
        exists_in_forms = ProviderForm.objects.filter(provider_name__iexact=provider_name.strip()).exists()
        exists_in_providers = Provider.objects.filter(name__iexact=provider_name.strip()).exists()
        exists = exists_in_forms or exists_in_providers
        
        return Response({
            'provider_name': provider_name,
            'exists': exists
        })


class CheckProviderEmailAPIView(APIView):
    """
    API для проверки уникальности email провайдера.
    
    Проверяет, существует ли уже организация с таким email
    в ProviderForm или Provider.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        Проверяет уникальность email провайдера.
        
        Query параметры:
        - provider_email: email организации для проверки
        
        Returns:
        - exists: True, если организация с таким email уже существует
        - valid: True, если email имеет правильный формат
        """
        provider_email = request.query_params.get('provider_email')
        
        if not provider_email:
            return Response(
                {'error': _('Provider email parameter is required')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Валидация формата email
        try:
            validate_email(provider_email)
            valid = True
        except DjangoValidationError:
            valid = False
        
        # Проверяем уникальность в ProviderForm (заявки) и Provider (одобренные организации)
        exists_in_forms = ProviderForm.objects.filter(provider_email__iexact=provider_email.strip()).exists()
        exists_in_providers = Provider.objects.filter(email__iexact=provider_email.strip()).exists()
        exists = exists_in_forms or exists_in_providers
        
        return Response({
            'provider_email': provider_email,
            'exists': exists,
            'valid': valid
        })


class CheckProviderPhoneAPIView(APIView):
    """
    API для проверки уникальности телефона провайдера.
    
    Проверяет, существует ли уже организация с таким телефоном
    в ProviderForm или Provider.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        Проверяет уникальность телефона провайдера.
        
        Query параметры:
        - provider_phone: телефон организации для проверки
        
        Returns:
        - exists: True, если организация с таким телефоном уже существует
        - valid: True, если телефон имеет правильный формат
        """
        provider_phone = request.query_params.get('provider_phone')
        
        if not provider_phone:
            return Response(
                {'error': _('Provider phone parameter is required')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Валидация формата телефона (базовая проверка)
        phone_cleaned = provider_phone.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        valid = len(phone_cleaned) >= 10 and phone_cleaned.replace('+', '').isdigit()
        
        # Проверяем уникальность в ProviderForm (заявки) и Provider (одобренные организации)
        # Для ProviderForm используем provider_phone, для Provider - phone_number
        exists_in_forms = ProviderForm.objects.filter(provider_phone__iexact=provider_phone.strip()).exists()
        exists_in_providers = Provider.objects.filter(phone_number__iexact=provider_phone.strip()).exists()
        exists = exists_in_forms or exists_in_providers
        
        return Response({
            'provider_phone': provider_phone,
            'exists': exists,
            'valid': valid
        })


class ForgotPasswordAPIView(generics.CreateAPIView):
    """
    API для запроса восстановления пароля.
    
    Отправляет email с токеном восстановления пароля.
    Защищен от enumeration атак.
    """
    serializer_class = ForgotPasswordSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        """
        Обрабатывает запрос восстановления пароля.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        
        try:
            # Получаем пользователя
            user = User.objects.get(email=email)
            
            # Проверяем rate limiting
            if self._is_rate_limited(user):
                return Response({
                    'message': _('Too many password reset attempts. Please try again later.'),
                    'success': False
                }, status=429)
            
            # Создаем токен восстановления
            from .models import PasswordResetToken
            reset_token = PasswordResetToken.create_for_user(
                user=user,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # Отправляем email
            self._send_password_reset_email(user, reset_token)
            
            # Логируем попытку
            logger.info(f"Password reset requested for user {user.email} from IP {self._get_client_ip(request)}")
            
        except User.DoesNotExist:
            # Не раскрываем существование email для безопасности
            pass
        
        # Всегда возвращаем успешный ответ для безопасности
        return Response({
            'message': _('If an account with this email exists, a password reset link has been sent.'),
            'success': True
        })
    
    def _is_rate_limited(self, user):
        """
        Проверяет rate limiting для пользователя.
        """
        from django.conf import settings
        from django.utils import timezone
        from datetime import timedelta
        
        max_attempts = getattr(settings, 'PASSWORD_RESET_MAX_ATTEMPTS', 3)
        cooldown = getattr(settings, 'PASSWORD_RESET_COOLDOWN', 3600)
        
        # Проверяем количество попыток за последний час
        since = timezone.now() - timedelta(seconds=cooldown)
        attempts = PasswordResetToken.objects.filter(
            user=user,
            created_at__gte=since
        ).count()
        
        return attempts >= max_attempts
    
    def _get_client_ip(self, request):
        """
        Получает IP адрес клиента.
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _send_password_reset_email(self, user, reset_token):
        """
        Отправляет email с токеном восстановления пароля.
        """
        from django.core.mail import send_mail
        from django.conf import settings
        from django.urls import reverse
        
        # Создаем ссылку для сброса пароля
        reset_url = f"{settings.FRONTEND_URL}/reset-password/{reset_token.token}"
        
        subject = _('Password Reset Request - PetsCare')
        message = f"""
        Hello {user.first_name or user.email},
        
        You have requested to reset your password for your PetsCare account.
        
        To reset your password, please click the link below:
        {reset_url}
        
        This link will expire in 30 minutes for security reasons.
        
        If you did not request this password reset, please ignore this email.
        
        Best regards,
        PetsCare Team
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )


class ResetPasswordAPIView(generics.CreateAPIView):
    """
    API для сброса пароля по токену.
    
    Позволяет установить новый пароль используя токен восстановления.
    """
    serializer_class = ResetPasswordSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        """
        Обрабатывает сброс пароля.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        reset_token = serializer.validated_data['reset_token']
        new_password = serializer.validated_data['new_password']
        
        # Устанавливаем новый пароль
        user.set_password(new_password)
        user.save()
        
        # Отмечаем токен как использованный
        reset_token.mark_as_used()
        
        # Логируем успешный сброс
        logger.info(f"Password reset successful for user {user.email} from IP {self._get_client_ip(request)}")
        
        return Response({
            'message': _('Password has been reset successfully. You can now log in with your new password.'),
            'success': True
        })
    
    def _get_client_ip(self, request):
        """
        Получает IP адрес клиента.
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip 


class AccountDeactivationView(APIView):
    """
    API view для деактивации аккаунта пользователя.
    Обрабатывает запросы на деактивацию с проверкой прав и ролей.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Деактивирует аккаунт пользователя.
        """
        serializer = AccountDeactivationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        
        # Проверяем, можно ли деактивировать аккаунт
        deactivation_check = self._check_deactivation_permissions(user)
        if not deactivation_check['can_deactivate']:
            return Response({
                'error': deactivation_check['reason']
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            with transaction.atomic():
                # Деактивируем аккаунт
                self._deactivate_user_account(user)
                
                # Логируем действие
                logger.info(f'User {user.id} deactivated their account')
                
                return Response({
                    'message': _('Account successfully deactivated'),
                    'success': True
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f'Error deactivating account for user {user.id}: {str(e)}', exc_info=True)
            return Response({
                'error': _('Failed to deactivate account. Please try again.')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _check_deactivation_permissions(self, user):
        """
        Проверяет, можно ли деактивировать аккаунт пользователя.
        """
        # Получаем роли пользователя
        user_roles = [role.name for role in user.user_types.all()]
        
        # Проверяем служебные роли
        service_roles = ['system_admin', 'billing_manager', 'booking_manager', 'employee']
        if any(role in user_roles for role in service_roles):
            return {
                'can_deactivate': False,
                'reason': _('Users with service roles cannot deactivate their accounts')
            }
        
        # Проверяем администратора учреждения
        if 'provider_admin' in user_roles:
            return {
                'can_deactivate': False,
                'reason': _('Institution administrators cannot deactivate their accounts. Please transfer your rights or contact support.')
            }
        
        # Если только basic_user - можно деактивировать сразу
        if user_roles == ['basic_user']:
            return {'can_deactivate': True}
        
        # Проверяем активные услуги для других ролей
        active_services = self._check_active_services(user)
        if active_services:
            return {
                'can_deactivate': False,
                'reason': _('You have active services. Please complete them before deactivating your account.')
            }
        
        return {'can_deactivate': True}
    
    def _check_active_services(self, user):
        """
        Проверяет наличие активных услуг у пользователя.
        """
        # Проверяем активные передержки через SitterProfile
        try:
            from sitters.models import SitterProfile
            sitter_profile = SitterProfile.objects.get(user=user)
            active_sittings = PetSitting.objects.filter(
                sitter=sitter_profile,
                status__in=['waiting_start', 'active', 'waiting_end', 'waiting_review']
            ).exists()
            
            if active_sittings:
                return True
        except SitterProfile.DoesNotExist:
            # У пользователя нет профиля ситтера
            pass
        
        # Проверяем активные бронирования (если есть такая модель)
        # TODO: Добавить проверку активных бронирований когда модель будет готова
        
        return False
    
    def _deactivate_user_account(self, user):
        """
        Деактивирует аккаунт пользователя с обработкой всех связанных данных.
        """
        with transaction.atomic():
            logger.info(f'Deactivating user account {user.id}')
            
            try:
                # Отменяем будущие услуги
                logger.info(f'Step 1: Cancelling future services for user {user.id}')
                self._cancel_future_services(user)
                
                # Обрабатываем питомцев пользователя
                logger.info(f'Step 2: Handling user pets for user {user.id}')
                self._handle_user_pets(user)
                
                # Обрабатываем роли пользователя
                logger.info(f'Step 3: Handling user roles for user {user.id}')
                self._handle_user_roles(user)
                
                # Анонимизируем данные пользователя
                logger.info(f'Step 4: Anonymizing user data for user {user.id}')
                self._anonymize_user_data(user)
                
                # Деактивируем пользователя
                logger.info(f'Step 5: Deactivating user {user.id}')
                user.is_active = False
                user.save()
                
                # Отправляем уведомления
                logger.info(f'Step 6: Sending notifications for user {user.id}')
                self._send_deactivation_notifications(user)
                
                logger.info(f'User {user.id} account deactivated successfully')
            except Exception as e:
                logger.error(f'Error during deactivation of user {user.id}: {e}')
                raise
    
    def _cancel_future_services(self, user):
        """
        Отменяет все будущие услуги пользователя и уведомляет заинтересованных лиц.
        """
        # Отменяем будущие передержки через SitterProfile
        try:
            from sitters.models import SitterProfile
            sitter_profile = SitterProfile.objects.get(user=user)
            future_sittings = PetSitting.objects.filter(
                sitter=sitter_profile,
                status__in=['pending', 'confirmed', 'waiting_start']
            )
            
            for sitting in future_sittings:
                # Отменяем передержку
                sitting.status = 'cancelled'
                sitting.save()
                
                # Уведомляем владельца питомца об отмене
                self._notify_pet_owner_cancellation(sitting)
        except SitterProfile.DoesNotExist:
            # У пользователя нет профиля ситтера
            pass
    
    def _handle_user_pets(self, user):
        """
        Обрабатывает питомцев пользователя при деактивации.
        """
        # Получаем питомцев, где пользователь основной владелец
        owned_pets = Pet.objects.filter(main_owner=user)
        
        for pet in owned_pets:
            # Сохраняем совладельцев для уведомлений
            co_owners = list(pet.owners.all())
            
            # Питомец остается как есть - это не личная информация владельца
            
            # Деактивируем питомца
            pet.is_active = False
            pet.save()
            
            # Оставляем всех владельцев для истории, но деактивируем питомца
            # Совладельцы остаются в owners для возможности восстановления
            # pet.owners остается как есть - все владельцы сохраняются
            # pet.main_owner остается как есть - для истории
    
    def _check_co_owner_roles(self, co_owner):
        """
        Проверяет и обновляет роли совладельца после удаления из питомцев.
        """
        # Проверяем, есть ли у совладельца другие питомцы
        other_pets = Pet.objects.filter(
            owners=co_owner,
            is_active=True
        ).exists()
        
        if not other_pets:
            # У совладельца не осталось питомцев - понижаем роль
            from .models import UserType
            try:
                basic_user_role = UserType.objects.get(name='basic_user')
                pet_owner_role = UserType.objects.get(name='pet_owner')
                
                co_owner.user_types.remove(pet_owner_role)
                if not co_owner.user_types.filter(name='basic_user').exists():
                    co_owner.user_types.add(basic_user_role)
            except UserType.DoesNotExist as e:
                logger.error(f'UserType not found: {e}')
                # Продолжаем выполнение без изменения ролей
    
    def _handle_user_roles(self, user):
        """
        Обрабатывает роли пользователя при деактивации.
        """
        from .models import UserType
        
        try:
            # Удаляем роли pet_owner и pet_sitter
            pet_owner_role = UserType.objects.get(name='pet_owner')
            pet_sitter_role = UserType.objects.get(name='pet_sitter')
            
            user.user_types.remove(pet_owner_role, pet_sitter_role)
            
            # Оставляем только basic_user
            basic_user_role = UserType.objects.get(name='basic_user')
            if not user.user_types.filter(name='basic_user').exists():
                user.user_types.add(basic_user_role)
        except UserType.DoesNotExist as e:
            logger.error(f'UserType not found: {e}')
            # Продолжаем выполнение без изменения ролей
    
    
    def _anonymize_user_data(self, user):
        """
        Анонимизирует данные пользователя.
        """
        # Анонимизируем email
        user.email = f'deactivated_{user.id}@anonymized.local'
        
        # Генерируем уникальный номер телефона
        user.phone_number = self._generate_unique_phone_number()
        
        # Генерируем уникальное имя пользователя для деактивированного пользователя
        user.username = self._generate_deactivated_username()
        
        # Анонимизируем имя
        user.first_name = 'Deactivated'
        user.last_name = 'User'
        
        user.save()
    
    def _generate_unique_phone_number(self):
        """
        Генерирует уникальный анонимный номер телефона.
        """
        import random
        
        # Генерируем уникальный номер
        while True:
            phone_number = f'+0000000{random.randint(1000, 9999)}'
            if not User.objects.filter(phone_number=phone_number).exists():
                return phone_number
    
    def _generate_deactivated_username(self):
        """
        Генерирует уникальное анонимное имя пользователя для деактивированного аккаунта.
        """
        import random
        import string
        
        # Генерируем уникальное имя пользователя для деактивированного аккаунта
        while True:
            random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            username = f'deactivated_{random_suffix}'
            if not User.objects.filter(username=username).exists():
                return username
    
    def _notify_pet_owner_cancellation(self, sitting):
        """
        Уведомляет владельца питомца об отмене передержки.
        """
        # TODO: Реализовать отправку уведомления владельцу питомца
        logger.info(f'Pet owner {sitting.pet.main_owner.id} should be notified about sitting {sitting.id} cancellation')
    
    def _send_deactivation_notifications(self, user):
        """
        Отправляет уведомления о деактивации аккаунта.
        """
        # TODO: Реализовать отправку уведомлений
        logger.info(f'Deactivation notifications should be sent for user {user.id}')


class UserRolesView(APIView):
    """
    API view для получения ролей пользователя.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Возвращает роли текущего пользователя.
        """
        user = request.user
        user_roles = [role.name for role in user.user_types.all()]
        
        return Response({
            'roles': user_roles
        })


class UserSittingsView(APIView):
    """
    API view для получения информации о передержках пользователя.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Возвращает информацию о передержках пользователя.
        """
        user = request.user
        
        try:
            from sitters.models import SitterProfile
            sitter_profile = SitterProfile.objects.get(user=user)
            
            # Проверяем активные передержки
            active_sittings = PetSitting.objects.filter(
                sitter=sitter_profile,
                status__in=['waiting_start', 'active', 'waiting_end', 'waiting_review']
            ).count()
            
            # Проверяем запланированные передержки
            future_sittings = PetSitting.objects.filter(
                sitter=sitter_profile,
                status__in=['pending', 'confirmed', 'waiting_start']
            ).count()
            
            return Response({
                'has_active_sittings': active_sittings > 0,
                'has_future_sittings': future_sittings > 0,
                'active_count': active_sittings,
                'future_count': future_sittings
            })
            
        except SitterProfile.DoesNotExist:
            return Response({
                'has_active_sittings': False,
                'has_future_sittings': False,
                'active_count': 0,
                'future_count': 0
            })


class UserPetsView(APIView):
    """
    API view для получения информации о питомцах пользователя.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Возвращает информацию о питомцах пользователя.
        """
        user = request.user
        
        # Проверяем, является ли пользователь основным владельцем
        owned_pets = Pet.objects.filter(main_owner=user).count()
        
        # Проверяем, является ли пользователь совладельцем
        co_owned_pets = Pet.objects.filter(owners=user).count()
        
        return Response({
            'has_owned_pets': owned_pets > 0,
            'has_co_owned_pets': co_owned_pets > 0,
            'owned_count': owned_pets,
            'co_owned_count': co_owned_pets
        })


class RemoveUserRoleView(APIView):
    """
    API view для удаления роли у пользователя.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Удаляет роль у пользователя.
        """
        role_name = request.data.get('role_name')
        if not role_name:
            return Response({'error': _('Role name is required')}, status=400)
        
        user = request.user
        
        try:
            from .models import UserType
            role = UserType.objects.get(name=role_name)
            
            # Специальная логика для pet_owner согласно UserDeactivation.md
            if role_name == 'pet_owner':
                self._handle_pet_owner_removal(user)
            
            user.user_types.remove(role)
            
            return Response({
                'message': _('Role {role_name} removed successfully').format(role_name=role_name),
                'success': True
            })
            
        except UserType.DoesNotExist:
            return Response({'error': _('Role not found')}, status=404)
        except Exception as e:
            logger.error(f'Error removing role {role_name}: {e}')
            return Response({'error': _('Failed to remove role')}, status=500)
    
    def _handle_pet_owner_removal(self, user):
        """
        Обрабатывает удаление роли pet_owner согласно UserDeactivation.md
        """
        from pets.models import Pet
        
        # 8.2.1.2.1. Для каждого питомца, у которого пользователь основной владелец
        owned_pets = Pet.objects.filter(main_owner=user)
        
        for pet in owned_pets:
            # 8.2.1.2.1.1. Для каждого совладельца: рассылка уведомлений
            co_owners = pet.owners.exclude(id=user.id)
            for co_owner in co_owners:
                self._notify_co_owner_removal(co_owner, pet, user)
            
            # 8.2.1.2.1.3. Деактивация питомца
            pet.is_active = False
            pet.save()
            
            # 8.2.1.2.1.4. Проверка наличия иных питомцев у совладельцев
            for co_owner in co_owners:
                self._check_co_owner_remaining_pets(co_owner)
        
        # 8.2.2.2.1. Для каждого питомца, у которого пользователь совладелец
        co_owned_pets = Pet.objects.filter(owners=user).exclude(main_owner=user)
        
        for pet in co_owned_pets:
            # 8.2.2.2.1.1. Сообщение основному владельцу
            if pet.main_owner:
                self._notify_main_owner_co_owner_removal(pet.main_owner, pet, user)
            
            # 8.2.2.2.1.2. Удалить пользователя из состава совладельцев
            pet.owners.remove(user)
    
    def _notify_co_owner_removal(self, co_owner, pet, removed_user):
        """
        Уведомляет совладельца об удалении из питомца
        """
        # TODO: Реализовать отправку уведомления
        logger.info(f'Co-owner {co_owner.id} should be notified about removal from pet {pet.id} by user {removed_user.id}')
    
    def _notify_main_owner_co_owner_removal(self, main_owner, pet, removed_user):
        """
        Уведомляет основного владельца об удалении совладельца
        """
        # TODO: Реализовать отправку уведомления
        logger.info(f'Main owner {main_owner.id} should be notified about co-owner {removed_user.id} removal from pet {pet.id}')
    
    def _check_co_owner_remaining_pets(self, co_owner):
        """
        Проверяет оставшиеся питомцы у совладельца и удаляет pet_owner роль если нет
        """
        from pets.models import Pet
        
        # Проверяем, есть ли у совладельца еще питомцы
        remaining_pets = Pet.objects.filter(
            owners=co_owner,
            is_active=True
        ).count()
        
        # Если питомцев нет, удаляем роль pet_owner
        if remaining_pets == 0:
            try:
                from .models import UserType
                pet_owner_role = UserType.objects.get(name='pet_owner')
                co_owner.user_types.remove(pet_owner_role)
                logger.info(f'Removed pet_owner role from user {co_owner.id} - no remaining pets')
            except UserType.DoesNotExist:
                logger.error('pet_owner role not found')
            except Exception as e:
                logger.error(f'Error removing pet_owner role from user {co_owner.id}: {e}')