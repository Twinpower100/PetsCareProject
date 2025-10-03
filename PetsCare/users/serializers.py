from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, UserType, ProviderForm, EmployeeSpecialization, RoleInvite
from django.utils.translation import gettext_lazy as _
from providers.models import Provider  # noqa: F401
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
        from geolocation.utils import calculate_distance  # noqa: F401
        
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
        # Сначала проверяем основной адрес используя PostGIS
        if hasattr(obj, 'address') and obj.address and obj.address.point:
            from django.contrib.gis.geos import Point
            search_point = Point(search_lon, search_lat)
            distance = obj.address.point.distance(search_point) * 111.32  # Convert to km
            return round(distance, 2) if distance is not None else None
        
        # Если нет основного адреса, проверяем адрес провайдера
        if hasattr(obj, 'provider_address') and obj.provider_address and obj.provider_address.point:
            from django.contrib.gis.geos import Point
            search_point = Point(search_lon, search_lat)
            distance = obj.provider_address.point.distance(search_point) * 111.32  # Convert to km
            return round(distance, 2) if distance is not None else None
        
        return None

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'phone_number', 'user_types', 'is_active', 'distance']
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
        fields = ['email', 'password', 'first_name', 'last_name', 'phone_number', 'token']
    
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
        Username генерируется автоматически.
        """
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone_number=validated_data.get('phone_number', ''),
        )
        return user


class GoogleAuthSerializer(serializers.Serializer):
    """
    Сериализатор для аутентификации через Google.
    Обрабатывает authorization code от Google OAuth 2.0.
    """
    token = serializers.CharField()  # Это authorization code от Google OAuth 2.0
    
    def validate(self, attrs):
        """
        Обменивает authorization code на access token и получает данные пользователя.
        """
        code = attrs.get('token')  # Это authorization code
        try:
            import requests
            from django.conf import settings
            
            # Обмениваем authorization code на access token
            token_url = 'https://oauth2.googleapis.com/token'
            token_data = {
                'client_id': settings.GOOGLE_CLIENT_ID,
                'client_secret': settings.GOOGLE_CLIENT_SECRET,
                'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': 'postmessage'  # Для OAuth 2.0 с authorization code
            }
            
            token_response = requests.post(token_url, data=token_data, timeout=10)
            token_response.raise_for_status()
            token_info = token_response.json()
            
            access_token = token_info.get('access_token')
            if not access_token:
                raise ValueError('No access token received')
            
            # Получаем данные пользователя
            user_info_url = 'https://www.googleapis.com/oauth2/v2/userinfo'
            headers = {'Authorization': f'Bearer {access_token}'}
            user_response = requests.get(user_info_url, headers=headers, timeout=10)
            user_response.raise_for_status()
            user_info = user_response.json()
            
            # Пытаемся получить номер телефона через People API
            phone = None
            try:
                people_url = 'https://people.googleapis.com/v1/people/me?personFields=phoneNumbers'
                people_response = requests.get(people_url, headers=headers, timeout=10)
                if people_response.status_code == 200:
                    people_data = people_response.json()
                    phone_numbers = people_data.get('phoneNumbers', [])
                    if phone_numbers:
                        phone = phone_numbers[0].get('value')
            except Exception as e:
                pass  # Игнорируем ошибки при получении номера телефона
            
            # Сохраняем данные пользователя для использования в API view
            attrs['google_user_data'] = {
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'picture': user_info.get('picture'),
                'google_id': user_info.get('id'),
                'phone': phone  # Может быть None
            }
            
        except requests.RequestException as e:
            print(f"GoogleAuthSerializer: Google API error: {str(e)}")
            raise serializers.ValidationError(f'Google API error: {str(e)}')
        except ValueError as e:
            print(f"GoogleAuthSerializer: Invalid Google response: {str(e)}")
            raise serializers.ValidationError(f'Invalid Google response: {str(e)}')
        except Exception as e:
            print(f"GoogleAuthSerializer: Token exchange error: {str(e)}")
            raise serializers.ValidationError(f'Token exchange error: {str(e)}')
        
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
    
    def validate(self, data):
        """
        Валидация данных регистрации учреждения.
        Проверяет необходимость документов на основе планируемых услуг.
        """
        # В MVP версии документы не обязательны
        # В будущем здесь будет логика проверки на основе выбранных услуг
        # from catalog.models import Service
        # Если учреждение планирует предоставлять услуги с requires_license=True,
        # то документы обязательны
        
        return data 


class RoleInviteSerializer(serializers.ModelSerializer):
    """
    Сериализатор для инвайтов на роли.
    """
    # Упрощенная версия без проблемных полей для Swagger
    class Meta:
        model = RoleInvite
        fields = [
            'id', 'email', 'role', 'provider', 'position', 'comment', 'status',
            'created_by', 'created_at', 'expires_at', 'accepted_at', 'declined_at'
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


class ForgotPasswordSerializer(serializers.Serializer):
    """
    Сериализатор для запроса восстановления пароля.
    """
    email = serializers.EmailField(
        max_length=254,
        help_text=_('Email address to send password reset link')
    )
    
    def validate_email(self, value):
        """
        Валидирует email и проверяет существование пользователя.
        """
        try:
            user = User.objects.get(email=value)
            if not user.is_active:
                raise serializers.ValidationError(
                    _('Account is inactive. Please contact support.')
                )
        except User.DoesNotExist:
            # Не раскрываем существование email для безопасности
            pass
        
        return value


class ResetPasswordSerializer(serializers.Serializer):
    """
    Сериализатор для сброса пароля.
    """
    token = serializers.CharField(
        max_length=64,
        help_text=_('Password reset token')
    )
    new_password = serializers.CharField(
        min_length=8,
        max_length=128,
        help_text=_('New password (minimum 8 characters)')
    )
    confirm_password = serializers.CharField(
        max_length=128,
        help_text=_('Confirm new password')
    )
    
    def validate(self, attrs):
        """
        Валидирует пароли и токен.
        """
        new_password = attrs.get('new_password')
        confirm_password = attrs.get('confirm_password')
        token = attrs.get('token')
        
        # Проверяем совпадение паролей
        if new_password != confirm_password:
            raise serializers.ValidationError(
                _('Passwords do not match')
            )
        
        # Проверяем токен
        from .models import PasswordResetToken
        reset_token = PasswordResetToken.get_valid_token(token)
        if not reset_token:
            raise serializers.ValidationError(
                _('Invalid or expired reset token')
            )
        
        # Сохраняем пользователя для использования в view
        attrs['user'] = reset_token.user
        attrs['reset_token'] = reset_token
        
        return attrs
    
    def validate_new_password(self, value):
        """
        Валидирует новый пароль.
        """
        if len(value) < 8:
            raise serializers.ValidationError(
                _('Password must be at least 8 characters long')
            )
        
        # Проверяем сложность пароля
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError(
                _('Password must contain at least one uppercase letter')
            )
        
        if not any(c.islower() for c in value):
            raise serializers.ValidationError(
                _('Password must contain at least one lowercase letter')
            )
        
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError(
                _('Password must contain at least one digit')
            )
        
        return value 