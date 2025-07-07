from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, UserType, ProviderForm, EmployeeSpecialization, RoleInvite
from django.utils.translation import gettext_lazy as _
from providers.models import Provider, Employee
from django.utils import timezone


class UserTypeSerializer(serializers.ModelSerializer):
    """
    Сериализатор для типа пользователя (UserType).
    Преобразует объекты UserType в JSON и обратно.
    """
    class Meta:
        model = UserType
        fields = ['id', 'name']


class UserSerializer(serializers.ModelSerializer):
    """
    Сериализатор для пользователя.
    Сериализует основные поля пользователя и список его ролей.
    """
    user_types = serializers.SerializerMethodField()
    distance = serializers.SerializerMethodField()
    
    def get_user_types(self, obj):
        """
        Возвращает список ролей пользователя.
        """
        return [role.name for role in obj.user_types.all()]
    
    def get_distance(self, obj):
        """
        Возвращает расстояние до пользователя, если указаны координаты поиска.
        """
        from geolocation.utils import calculate_distance
        
        # Получаем координаты поиска из контекста
        context = self.context
        search_lat = context.get('latitude')
        search_lon = context.get('longitude')
        
        if not search_lat or not search_lon:
            return None
        
        try:
            search_lat = float(search_lat)
            search_lon = float(search_lon)
        except (ValueError, TypeError):
            return None
        
        # Пытаемся получить координаты пользователя
        user_lat = None
        user_lon = None
        
        # Сначала проверяем основной адрес
        if hasattr(obj, 'address') and obj.address:
            user_lat = obj.address.latitude
            user_lon = obj.address.longitude
        
        # Если нет основного адреса, проверяем адрес провайдера
        if (user_lat is None or user_lon is None) and hasattr(obj, 'provider_address') and obj.provider_address:
            user_lat = obj.provider_address.latitude
            user_lon = obj.provider_address.longitude
        
        if user_lat is not None and user_lon is not None:
            distance = calculate_distance(search_lat, search_lon, user_lat, user_lon)
            return round(distance, 2) if distance is not None else None
        
        return None

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'user_types', 'is_active', 'distance']
        read_only_fields = ['email', 'user_types', 'distance']


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для регистрации пользователя.
    Проверяет и создает нового пользователя.
    """
    password = serializers.CharField(write_only=True)
    token = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['email', 'password', 'first_name', 'last_name', 'token']
    
    def get_token(self, user):
        """
        Генерирует JWT-токен для пользователя.
        """
        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
    
    def create(self, validated_data):
        """
        Создает нового пользователя с указанными данными.
        """
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        return user


class GoogleAuthSerializer(serializers.Serializer):
    """
    Сериализатор для аутентификации через Google.
    Проверяет токен Google и возвращает пользователя.
    """
    token = serializers.CharField()
    
    def validate(self, attrs):
        """
        Валидирует Google токен и возвращает данные пользователя.
        """
        token = attrs.get('token')
        try:
            # Здесь будет логика валидации Google токена
            # и создания/получения пользователя
            pass
        except Exception as e:
            raise serializers.ValidationError(_(str(e)))
        return attrs 


class ProviderFormSerializer(serializers.ModelSerializer):
    """
    Сериализатор для формы учреждения (провайдера).
    """
    class Meta:
        model = ProviderForm
        fields = [
            'id', 'provider_name', 'provider_address', 
            'provider_phone', 'documents', 'status',
            'created_at', 'updated_at', 'approved_at'
        ]
        read_only_fields = ['status', 'created_at', 'updated_at', 'approved_at']


class UserRoleAssignmentSerializer(serializers.Serializer):
    """
    Сериализатор для назначения роли пользователю.
    """
    user_id = serializers.IntegerField()
    role = serializers.CharField()

    def validate_user_id(self, value):
        """
        Проверяет существование пользователя по ID.
        """
        try:
            User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(_("User does not exist"))
        return value

    def validate_role(self, value):
        """
        Проверяет существование роли.
        """
        try:
            UserType.objects.get(name=value)
        except UserType.DoesNotExist:
            raise serializers.ValidationError(_("Role does not exist"))
        return value


class ProviderFormApprovalSerializer(serializers.Serializer):
    """
    Сериализатор для одобрения или отклонения формы учреждения.
    """
    form_id = serializers.IntegerField()
    action = serializers.ChoiceField(choices=['approve', 'reject'])

    def validate_form_id(self, value):
        """
        Проверяет существование формы учреждения по ID.
        """
        try:
            ProviderForm.objects.get(id=value)
        except ProviderForm.DoesNotExist:
            raise serializers.ValidationError(_("Form does not exist"))
        return value


class ProviderAdminRegistrationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для регистрации администратора учреждения.
    """
    class Meta:
        model = ProviderForm
        fields = [
            'provider_name', 'provider_address', 
            'provider_phone', 'documents'
        ] 


class RoleInviteSerializer(serializers.ModelSerializer):
    """
    Сериализатор для инвайтов на роли.
    """
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    provider_name = serializers.CharField(source='provider.name', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    can_be_accepted = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = 'users.RoleInvite'
        fields = [
            'id', 'email', 'role', 'role_display', 'provider', 'provider_name',
            'position', 'comment', 'status', 'status_display', 'created_by',
            'created_by_name', 'created_at', 'expires_at', 'is_expired',
            'can_be_accepted', 'accepted_at', 'declined_at'
        ]
        read_only_fields = [
            'id', 'token', 'qr_code', 'status', 'created_at', 'expires_at',
            'accepted_at', 'declined_at', 'accepted_by'
        ]


class RoleInviteCreateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания инвайтов на роли.
    """
    class Meta:
        model = 'users.RoleInvite'
        fields = ['email', 'role', 'provider', 'position', 'comment']
    
    def validate(self, data):
        """
        Валидация данных инвайта.
        """
        from .models import RoleInvite
        
        user = self.context['request'].user
        email = data['email']
        role = data['role']
        provider = data['provider']
        
        # Проверяем права на создание инвайта
        if role == 'employee':
            # Только менеджер учреждения может приглашать сотрудников
            if not user.is_employee() or not user.employee_profile.employeeprovider_set.filter(
                provider=provider, is_manager=True, is_confirmed=True
            ).exists():
                raise serializers.ValidationError(
                    _("Only confirmed managers can invite employees")
                )
        elif role == 'billing_manager':
            # Только системный админ может приглашать менеджеров по биллингу
            if not user.is_system_admin():
                raise serializers.ValidationError(
                    _("Only system administrators can invite billing managers")
                )
        
        # Проверяем, что пользователь с таким email существует
        if not User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                _("User with this email does not exist")
            )
        
        # Проверяем, что нет активных инвайтов для этого email и роли
        if RoleInvite.objects.filter(
            email=email,
            role=role,
            provider=provider,
            status='pending',
            expires_at__gt=timezone.now()
        ).exists():
            raise serializers.ValidationError(
                _("Active invite already exists for this user and role")
            )
        
        # Проверяем, что пользователь еще не имеет эту роль
        target_user = User.objects.get(email=email)
        if role == 'employee':
            if target_user.is_employee() and target_user.employee_profile.employeeprovider_set.filter(
                provider=provider, end_date__isnull=True
            ).exists():
                raise serializers.ValidationError(
                    _("User is already an employee at this provider")
                )
        elif role == 'billing_manager':
            if target_user.has_role('billing_manager') and target_user.managed_providers.filter(
                provider=provider, status__in=['active', 'vacation']
            ).exists():
                raise serializers.ValidationError(
                    _("User is already a billing manager for this provider")
                )
        
        return data
    
    def create(self, validated_data):
        """
        Создает инвайт на роль.
        """
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class RoleInviteAcceptSerializer(serializers.Serializer):
    """
    Сериализатор для принятия инвайта на роль.
    """
    token = serializers.CharField(max_length=64)
    
    def validate_token(self, value):
        """
        Валидирует токен инвайта.
        """
        try:
            invite = RoleInvite.objects.get(token=value)
            if not invite.can_be_accepted():
                raise serializers.ValidationError(_("Invite cannot be accepted"))
            return value
        except RoleInvite.DoesNotExist:
            raise serializers.ValidationError(_("Invalid invite token"))
    
    def accept_invite(self, user):
        """
        Принимает инвайт пользователем.
        """
        token = self.validated_data['token']
        invite = RoleInvite.objects.get(token=token)
        
        try:
            invite.accept(user)
            return invite
        except ValueError as e:
            raise serializers.ValidationError(str(e))


class RoleInviteDeclineSerializer(serializers.Serializer):
    """
    Сериализатор для отклонения инвайта на роль.
    """
    token = serializers.CharField(max_length=64)
    
    def validate_token(self, value):
        """
        Валидирует токен инвайта.
        """
        try:
            invite = RoleInvite.objects.get(token=value)
            if invite.status != 'pending':
                raise serializers.ValidationError(_("Invite cannot be declined"))
            return value
        except RoleInvite.DoesNotExist:
            raise serializers.ValidationError(_("Invalid invite token"))
    
    def decline_invite(self, user):
        """
        Отклоняет инвайт пользователем.
        """
        token = self.validated_data['token']
        invite = RoleInvite.objects.get(token=token)
        
        try:
            invite.decline(user)
            return invite
        except ValueError as e:
            raise serializers.ValidationError(str(e))


class RoleTerminationSerializer(serializers.Serializer):
    """
    Сериализатор для увольнения пользователя с роли.
    """
    user_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=[('employee', 'Employee'), ('billing_manager', 'Billing Manager')])
    provider_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=500, required=False)
    
    def validate(self, data):
        """
        Валидация данных увольнения.
        """
        user = self.context['request'].user
        target_user_id = data['user_id']
        role = data['role']
        provider_id = data['provider_id']
        
        try:
            target_user = User.objects.get(id=target_user_id)
            provider = Provider.objects.get(id=provider_id)
        except (User.DoesNotExist, Provider.DoesNotExist):
            raise serializers.ValidationError(_("Invalid user or provider"))
        
        # Проверяем права на увольнение
        if role == 'employee':
            # Только менеджер учреждения может увольнять сотрудников
            if not user.is_employee() or not user.employee_profile.employeeprovider_set.filter(
                provider=provider, is_manager=True, is_confirmed=True
            ).exists():
                raise serializers.ValidationError(
                    _("Only confirmed managers can terminate employees")
                )
            
            # Проверяем, что пользователь действительно сотрудник
            if not target_user.is_employee() or not target_user.employee_profile.employeeprovider_set.filter(
                provider=provider, end_date__isnull=True
            ).exists():
                raise serializers.ValidationError(
                    _("User is not an employee at this provider")
                )
        
        elif role == 'billing_manager':
            # Только системный админ может увольнять менеджеров по биллингу
            if not user.is_system_admin():
                raise serializers.ValidationError(
                    _("Only system administrators can terminate billing managers")
                )
            
            # Проверяем, что пользователь действительно менеджер по биллингу
            if not target_user.has_role('billing_manager') or not target_user.managed_providers.filter(
                provider=provider, status__in=['active', 'vacation']
            ).exists():
                raise serializers.ValidationError(
                    _("User is not a billing manager for this provider")
                )
        
        return data 