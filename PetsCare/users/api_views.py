from rest_framework import generics, status, permissions, serializers
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .serializers import (
    UserSerializer, 
    UserRegistrationSerializer,
    GoogleAuthSerializer,
    UserRoleAssignmentSerializer,
    ProviderFormSerializer,
    ProviderFormApprovalSerializer,
    ProviderAdminRegistrationSerializer
)
from google.oauth2 import id_token
from google.auth.transport import requests
from django.conf import settings
from .models import UserType, ProviderForm, EmployeeSpecialization
from rest_framework.views import APIView
from pets.models import Pet
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from providers.models import Provider, Employee, EmployeeProvider, ManagerTransferInvite
from rest_framework.exceptions import PermissionDenied
from sitters.models import PetSitting
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
from django.utils.log import logger
from .models import AuditLog

User = get_user_model()


class UserRegistrationAPIView(generics.CreateAPIView):
    """
    Класс для регистрации новых пользователей.
    Позволяет создать пользователя с email, username и паролем.
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]


class UserLoginAPIView(TokenObtainPairView):
    """
    Класс для аутентификации пользователя и получения JWT-токенов.
    """
    permission_classes = [permissions.AllowAny]


class UserProfileAPIView(generics.RetrieveUpdateAPIView):
    """
    Класс для просмотра и редактирования профиля текущего пользователя.
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        if not self.request.user.has_role('pet_owner'):
            raise PermissionDenied(_('Only pet owners can access this view'))
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
            # Валидация Google токена
            idinfo = id_token.verify_oauth2_token(
                serializer.validated_data['token'],
                requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )
            
            # Получение или создание пользователя
            email = idinfo['email']
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                user = User.objects.create_user(
                    email=email,
                    first_name=idinfo.get('given_name', ''),
                    last_name=idinfo.get('family_name', ''),
                    password=None  # Пароль не нужен для социальной аутентификации
                )
            
            # Генерация JWT токенов
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data
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
    
    def get_queryset(self):
        """
        Возвращает queryset заявок в зависимости от роли пользователя.
        Системный администратор видит все заявки, обычный пользователь — только свои.
        """
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

def can_delete_user(user):
    """
    Проверяет, может ли пользователь быть удалён с учётом ролей менеджера, сотрудника, ситтера и основного владельца питомца.
    Возвращает (True, None) если можно, иначе (False, сообщение).
    """
    # Проверка: менеджер учреждения
    manager_links = EmployeeProvider.objects.filter(
        employee__user=user,
        is_manager=True,
        end_date=None
    )
    for link in manager_links:
        # Считаем других подтверждённых менеджеров в учреждении
        other_managers = EmployeeProvider.objects.filter(
            provider=link.provider,
            is_manager=True,
            end_date=None
        ).exclude(employee__user=user)
        if not other_managers.exists():
            return False, _('Cannot delete account: you are the last manager for provider "%(provider)s". Please transfer manager rights first.') % {'provider': link.provider.name}
        # Проверка: есть ли неподтверждённые приглашения на передачу прав
        if ManagerTransferInvite.objects.filter(
            from_manager=link.employee,
            provider=link.provider,
            is_accepted=False,
            is_declined=False
        ).exists():
            return False, _('Cannot delete account: manager rights transfer is pending confirmation for provider "%(provider)s".') % {'provider': link.provider.name}

    # Проверка: сотрудник учреждения (не менеджер)
    if Employee.objects.filter(user=user).exists():
        return False, _('Cannot delete account: user is an employee')

    # Проверка: активные заявки у ситтера
    ACTIVE_STATUSES = ['waiting_start', 'active', 'waiting_end', 'waiting_review']
    if PetSitting.objects.filter(sitter=user, status__in=ACTIVE_STATUSES).exists():
        return False, _('Cannot delete account: you have active pet sitting requests.')

    # Проверка: основной владелец питомца без других владельцев
    pets_as_main_owner = Pet.objects.filter(main_owner=user)
    for pet in pets_as_main_owner:
        if pet.owners.count() <= 1:
            return False, _('Cannot delete account: user is the only owner of a pet')

    return True, None

class UserSelfDeleteAPIView(APIView):
    """
    API endpoint для самостоятельного удаления учетной записи пользователя.
    Пользователь не может удалить себя, если он менеджер (единственный или с незавершённой передачей прав), сотрудник учреждения, основной владелец питомца без других владельцев, или ситтер с активными заявками.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def delete(self, request):
        """
        Удаляет пользователя, если это разрешено бизнес-правилами.
        """
        user = request.user

        can_delete, error = can_delete_user(user)
        if not can_delete:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class RoleInviteViewSet(ModelViewSet):
    """
    ViewSet для управления инвайтами на роли.
    
    Поддерживает:
    - Создание инвайтов (только менеджеры и системные админы)
    - Просмотр списка инвайтов
    - Детали инвайта
    - Отмена инвайта
    """
    serializer_class = RoleInviteSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Возвращает queryset в зависимости от роли пользователя.
        """
        user = self.request.user
        
        if user.is_system_admin():
            # Системный админ видит все инвайты
            return RoleInvite.objects.all()
        elif user.is_employee():
            # Менеджер учреждения видит инвайты для своего учреждения
            managed_providers = user.employee_profile.employeeprovider_set.filter(
                is_manager=True, is_confirmed=True
            ).values_list('provider_id', flat=True)
            return RoleInvite.objects.filter(provider_id__in=managed_providers)
        else:
            # Обычные пользователи видят только свои инвайты
            return RoleInvite.objects.filter(email=user.email)
    
    def get_serializer_class(self):
        """
        Возвращает соответствующий сериализатор.
        """
        if self.action == 'create':
            return RoleInviteCreateSerializer
        return RoleInviteSerializer
    
    def perform_create(self, serializer):
        """
        Создает инвайт и отправляет уведомление.
        """
        invite = serializer.save()
        
        # Отправляем email уведомление
        self._send_invite_email(invite)
        
        return invite
    
    def _send_invite_email(self, invite):
        """
        Отправляет email с инвайтом.
        """
        # TODO: Реализовать отправку email с токеном и QR-кодом
        pass


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
        
        # Фильтруем пользователей с адресами
        queryset = queryset.filter(
            Q(address__isnull=False) | 
            Q(provider_address__isnull=False)
        ).distinct()
        
        # Получаем пользователей в радиусе
        users_with_distance = filter_by_distance(
            queryset, lat, lon, radius, 'address__point'
        )
        
        # Если пользователь не найден по основному адресу, ищем по адресу провайдера
        if not users_with_distance:
            users_with_distance = filter_by_distance(
                queryset, lat, lon, radius, 'provider_address__point'
            )
        
        # Возвращаем только объекты пользователей (расстояния будут в сериализаторе)
        return [user for user, distance in users_with_distance[:limit]]
    
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
        
        # Фильтрация по рейтингу
        if min_rating:
            try:
                min_rating = float(min_rating)
                queryset = queryset.filter(rating__gte=min_rating)
            except (ValueError, TypeError):
                pass
        
        # Фильтрация по доступности
        if available == 'true':
            # Исключаем ситтеров с активными заявками
            active_sittings = PetSitting.objects.filter(
                status__in=['pending', 'confirmed', 'in_progress']
            ).values_list('sitter_id', flat=True)
            queryset = queryset.exclude(id__in=active_sittings)
        
        # Фильтруем ситтеров с адресами
        queryset = queryset.filter(
            Q(address__isnull=False) | 
            Q(provider_address__isnull=False)
        ).distinct()
        
        # Получаем ситтеров в радиусе
        sitters_with_distance = filter_by_distance(
            queryset, lat, lon, radius, 'address__point'
        )
        
        # Если ситтер не найден по основному адресу, ищем по адресу провайдера
        if not sitters_with_distance:
            sitters_with_distance = filter_by_distance(
                queryset, lat, lon, radius, 'provider_address__point'
            )
        
        # Сортируем по расстоянию и рейтингу
        sitters_with_distance.sort(key=lambda x: (x[1], -x[0].rating))
        
        # Возвращаем только объекты пользователей
        return [sitter for sitter, distance in sitters_with_distance[:limit]]
    
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
                    if role not in dict(User.ROLE_CHOICES):
                        results['failed'].append({
                            'user_id': user_id,
                            'error': f'Invalid role: {role}'
                        })
                        continue

                    # Назначаем роль
                    user.add_role(role)
                    
                    # Логируем действие
                    AuditLog.objects.create(
                        user=request.user,
                        action='role_assigned',
                        resource_type='user',
                        resource_id=user.id,
                        resource_name=user.email,
                        details={
                            'assigned_role': role,
                            'reason': reason,
                            'assigned_by': request.user.email
                        },
                        ip_address=request.META.get('REMOTE_ADDR'),
                        user_agent=request.META.get('HTTP_USER_AGENT')
                    )

                    results['success'].append({
                        'user_id': user_id,
                        'user_email': user.email,
                        'role': role
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
                    
                    # Логируем действие
                    AuditLog.objects.create(
                        user=request.user,
                        action='user_deactivated',
                        resource_type='user',
                        resource_id=user.id,
                        resource_name=user.email,
                        details={
                            'reason': reason,
                            'deactivated_by': request.user.email
                        },
                        ip_address=request.META.get('REMOTE_ADDR'),
                        user_agent=request.META.get('HTTP_USER_AGENT')
                    )

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
                    
                    # Логируем действие
                    AuditLog.objects.create(
                        user=request.user,
                        action='user_activated',
                        resource_type='user',
                        resource_id=user.id,
                        resource_name=user.email,
                        details={
                            'reason': reason,
                            'activated_by': request.user.email
                        },
                        ip_address=request.META.get('REMOTE_ADDR'),
                        user_agent=request.META.get('HTTP_USER_AGENT')
                    )

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