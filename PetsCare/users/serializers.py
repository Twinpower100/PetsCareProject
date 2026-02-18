from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, UserType, ProviderForm, EmployeeSpecialization, RoleInvite
from .requisite_normalize import (
    normalize_tax_id,
    normalize_registration_number,
    normalize_vat_number,
    normalize_iban,
)
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
        
        # У пользователя нет привязанного PointField для расчетов расстояния
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
        Использует SocialApp из БД для получения credentials (единый подход).
        """
        code = attrs.get('token')  # Это authorization code
        try:
            import requests
            from allauth.socialaccount.models import SocialApp
            
            # Получаем SocialApp для фронтенда из БД (единый подход с django-allauth)
            try:
                social_app = SocialApp.objects.get(
                    provider='google',
                    name='PetsCare Frontend'
                )
                client_id = social_app.client_id
                client_secret = social_app.secret
            except SocialApp.DoesNotExist:
                raise serializers.ValidationError(
                    _('SocialApp "PetsCare Frontend" not found in database. Please configure it in Django admin.')
                )
            
            # Обмениваем authorization code на access token
            token_url = 'https://oauth2.googleapis.com/token'
            token_data = {
                'client_id': client_id,
                'client_secret': client_secret,
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
            raise serializers.ValidationError(
                _('Google API error: {error}').format(error=str(e))
            )
        except ValueError as e:
            print(f"GoogleAuthSerializer: Invalid Google response: {str(e)}")
            raise serializers.ValidationError(
                _('Invalid Google response: {error}').format(error=str(e))
            )
        except Exception as e:
            print(f"GoogleAuthSerializer: Token exchange error: {str(e)}")
            raise serializers.ValidationError(
                _('Token exchange error: {error}').format(error=str(e))
            )
        
        return attrs 


class ProviderFormSerializer(serializers.ModelSerializer):
    """
    Сериализатор для формы учреждения (провайдера).
    """
    selected_categories = serializers.SerializerMethodField()
    offer_accepted_ip = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    def get_selected_categories(self, obj):
        """Возвращает ID выбранных категорий"""
        if hasattr(obj, 'selected_categories'):
            return list(obj.selected_categories.values_list('id', flat=True))
        return []
    
    def to_internal_value(self, data):
        """Обрабатывает входящие данные для selected_categories"""
        # Сохраняем selected_categories из входящих данных
        if 'selected_categories' in data:
            if hasattr(data, 'getlist'):
                self._selected_categories_data = data.getlist('selected_categories')
            else:
                selected = data.get('selected_categories')
                if isinstance(selected, str):
                    self._selected_categories_data = [item.strip() for item in selected.split(',') if item.strip()]
                else:
                    self._selected_categories_data = selected
        return super().to_internal_value(data)
    
    def _validate_vat_rate_for_country(self, country):
        """
        Проверяет, есть ли ставка НДС для выбранной страны.
        """
        if not country:
            return
        
        # Проверяем наличие ставки НДС в таблице VAT Rates
        from billing.models import VATRate
        country_code = getattr(country, 'code', str(country))
        if VATRate.get_rate_for_country(country_code) is None:
            raise serializers.ValidationError({
                'country': _(
                    'VAT rate for the selected country is not configured. '
                    'Please contact support to request onboarding for this country.'
                )
            })
    
    def create(self, validated_data):
        """Создает объект с выбранными категориями"""
        selected_categories = getattr(self, '_selected_categories_data', [])
        validated_data.pop('selected_categories', None)  # Убираем из validated_data
        
        # Валидация выбранных категорий
        if not selected_categories:
            raise serializers.ValidationError({
                'selected_categories': _('At least one service category must be selected.')
            })
        
        # Проверяем, что все категории существуют и имеют уровень 0
        from catalog.models import Service
        try:
            categories = Service.objects.filter(id__in=selected_categories, level=0)
            if categories.count() != len(selected_categories):
                invalid_ids = set(selected_categories) - set(categories.values_list('id', flat=True))
                raise serializers.ValidationError({
                    'selected_categories': _('Invalid category IDs: {ids}. Only level 0 categories are allowed.').format(ids=list(invalid_ids))
                })
        except Exception as e:
            raise serializers.ValidationError({
                'selected_categories': _('Error validating categories: {error}').format(error=str(e))
            })
        
        # Проверяем, что страна поддерживается (есть VAT Rate)
        self._validate_vat_rate_for_country(validated_data.get('country'))
        
        # Проверяем уникальность email провайдера
        provider_email = validated_data.get('provider_email')
        if provider_email:
            from providers.models import Provider
            if Provider.objects.filter(email=provider_email).exists():
                raise serializers.ValidationError({
                    'provider_email': _('A provider with this email already exists.')
                })
        
        # Проверяем уникальность телефона провайдера
        provider_phone = validated_data.get('provider_phone')
        if provider_phone:
            from providers.models import Provider
            if Provider.objects.filter(phone_number=str(provider_phone)).exists():
                raise serializers.ValidationError({
                    'provider_phone': _('A provider with this phone number already exists.')
                })
        
        # Валидируем адрес через Google Maps API и сохраняем нормализованный адрес
        provider_address = validated_data.get('provider_address')
        if provider_address:
            try:
                from geolocation.services import GoogleMapsService
                maps_service = GoogleMapsService()
                geocode_result = maps_service.geocode_address(provider_address.strip())
                
                if geocode_result:
                    # Сохраняем нормализованный адрес от Google Maps API
                    formatted_address = geocode_result.get('formatted_address')
                    if formatted_address:
                        validated_data['provider_address'] = formatted_address
            except Exception:
                # Если валидация не удалась, оставляем исходный адрес
                # (не прерываем создание формы, так как адрес может быть валидирован позже)
                pass
        
        instance = super().create(validated_data)
        
        # Устанавливаем выбранные категории
        instance.selected_categories.set(categories)
        
        return instance
    
    def update(self, instance, validated_data):
        """Обновляет объект с выбранными категориями"""
        selected_categories = getattr(self, '_selected_categories_data', [])
        validated_data.pop('selected_categories', None)  # Убираем из validated_data
        
        # Проверяем, что страна поддерживается (есть VAT Rate)
        country = validated_data.get('country', instance.country)
        self._validate_vat_rate_for_country(country)
        
        # Валидируем адрес через Google Maps API и сохраняем нормализованный адрес
        provider_address = validated_data.get('provider_address')
        if provider_address:
            try:
                from geolocation.services import GoogleMapsService
                maps_service = GoogleMapsService()
                geocode_result = maps_service.geocode_address(provider_address.strip())
                
                if geocode_result:
                    # Сохраняем нормализованный адрес от Google Maps API
                    formatted_address = geocode_result.get('formatted_address')
                    if formatted_address:
                        validated_data['provider_address'] = formatted_address
            except Exception:
                # Если валидация не удалась, оставляем исходный адрес
                pass
        
        # Проверяем уникальность email провайдера (исключая текущий экземпляр)
        provider_email = validated_data.get('provider_email')
        if provider_email and provider_email != instance.provider_email:
            from providers.models import Provider
            if Provider.objects.filter(email=provider_email).exists():
                raise serializers.ValidationError({
                    'provider_email': _('A provider with this email already exists.')
                })
        
        # Проверяем уникальность телефона провайдера (исключая текущий экземпляр)
        provider_phone = validated_data.get('provider_phone')
        if provider_phone and str(provider_phone) != str(instance.provider_phone):
            from providers.models import Provider
            if Provider.objects.filter(phone_number=str(provider_phone)).exists():
                raise serializers.ValidationError({
                    'provider_phone': _('A provider with this phone number already exists.')
                })
        
        instance = super().update(instance, validated_data)
        
        # Обновляем выбранные категории
        if selected_categories is not None:
            from catalog.models import Service
            categories = Service.objects.filter(id__in=selected_categories, level=0)
            instance.selected_categories.set(categories)
        
        return instance
    
    class Meta:
        model = ProviderForm
        fields = [
            'id', 'provider_name', 'provider_address',
            'provider_phone', 'provider_email', 'admin_email', 'documents', 'status',
            'selected_categories', 'created_at', 'updated_at', 'approved_at',
            'country', 'organization_type', 'director_name',
            'registration_number', 'tax_id', 'kpp',
            'is_vat_payer', 'vat_number', 'invoice_currency',
            'iban', 'swift_bic', 'bank_name',
            'offer_accepted', 'offer_accepted_at', 'offer_accepted_ip',
            'offer_accepted_user_agent'
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


class AccountDeactivationSerializer(serializers.Serializer):
    """
    Сериализатор для деактивации аккаунта пользователя.
    Обрабатывает запрос на деактивацию с подтверждением.
    """
    confirm_deactivation = serializers.BooleanField(
        required=True,
        help_text=_('Confirmation that user wants to deactivate account')
    )
    
    def validate_confirm_deactivation(self, value):
        """
        Проверяет, что пользователь подтвердил деактивацию.
        """
        if not value:
            raise serializers.ValidationError(
                _('You must confirm account deactivation')
            )
        return value


# ============================================================================
# Сериализаторы для мастера регистрации провайдера (пошаговые)
# ============================================================================

class ProviderRegistrationStep1Serializer(serializers.Serializer):
    """
    Шаг 1: Выбор страны регистрации
    """
    country = serializers.CharField(
        max_length=2,
        required=True,
        help_text=_('Country code (ISO 3166-1 alpha-2)')
    )
    
    def validate_country(self, value):
        """Проверяет наличие VATRate для страны"""
        from billing.models import VATRate
        if not VATRate.objects.filter(country=value, is_active=True).exists():
            raise serializers.ValidationError(
                _('We do not currently work in this country. Please contact support to request adding your country.')
            )
        return value


class ProviderRegistrationStep2Serializer(serializers.Serializer):
    """
    Шаг 2: Заполнение базовых данных организации
    """
    provider_name = serializers.CharField(max_length=100, required=True)
    provider_address = serializers.CharField(max_length=200, required=True)
    provider_phone = serializers.CharField(required=True)
    provider_email = serializers.EmailField(required=True)
    admin_email = serializers.EmailField(required=True)
    selected_categories = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        min_length=1
    )
    documents = serializers.ListField(
        child=serializers.FileField(allow_empty_file=False),
        required=False,
        allow_empty=True,
    )
    # Компоненты адреса из Google Places Autocomplete (опционально)
    address_components = serializers.JSONField(required=False, allow_null=True)

    def validate_provider_name(self, value):
        """Проверка уникальности названия организации (таблица валидаций: onblur, Далее, Завершение)"""
        from providers.models import Provider
        name_clean = (value or '').strip()
        if not name_clean:
            return value
        if Provider.objects.filter(name__iexact=name_clean).exists():
            raise serializers.ValidationError(_('An organization with this name already exists.'))
        if ProviderForm.objects.filter(provider_name__iexact=name_clean, status__in=['pending', 'approved']).exists():
            raise serializers.ValidationError(_('An organization with this name already exists.'))
        return value

    def validate_provider_email(self, value):
        """Проверка уникальности email организации"""
        from providers.models import Provider
        if Provider.objects.filter(email=value).exists():
            raise serializers.ValidationError(_('Provider with this email already exists'))
        if ProviderForm.objects.filter(provider_email=value, status__in=['pending', 'approved']).exists():
            raise serializers.ValidationError(_('Provider form with this email already exists'))
        return value
    
    def validate_provider_phone(self, value):
        """Проверка уникальности телефона организации"""
        from providers.models import Provider
        if Provider.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError(_('Provider with this phone already exists'))
        if ProviderForm.objects.filter(provider_phone=value, status__in=['pending', 'approved']).exists():
            raise serializers.ValidationError(_('Provider form with this phone already exists'))
        return value
    
    def validate_admin_email(self, value):
        """Проверка существования пользователя-администратора"""
        # Если admin_email указан, проверяем существование пользователя
        if value:
            if not User.objects.filter(email=value, is_active=True).exists():
                raise serializers.ValidationError(
                    _('User with this email is not registered in the system. Please specify an existing user email or ask the user to register.')
                )
        # Если не указан, будет использован email создателя заявки (в модели save())
        return value
    
    def validate_selected_categories(self, value):
        """Проверка категорий услуг уровня 0"""
        from catalog.models import Service
        categories = Service.objects.filter(id__in=value, level=0)
        if categories.count() != len(value):
            raise serializers.ValidationError(_('All categories must be level 0'))
        if categories.count() < 1:
            raise serializers.ValidationError(_('At least one category is required'))
        return value


class ProviderRegistrationStep3Serializer(serializers.Serializer):
    """
    Шаг 3: Заполнение юридических реквизитов
    """
    tax_id = serializers.CharField(max_length=50, required=True)
    registration_number = serializers.CharField(max_length=100, required=True)
    invoice_currency = serializers.IntegerField(required=True)
    organization_type = serializers.CharField(max_length=50, required=True, allow_blank=False)
    is_vat_payer = serializers.BooleanField(required=True)
    vat_number = serializers.CharField(max_length=50, required=False, allow_blank=True)
    kpp = serializers.CharField(max_length=20, required=False, allow_blank=True)
    iban = serializers.CharField(max_length=50, required=False, allow_blank=True)
    swift_bic = serializers.CharField(max_length=20, required=False, allow_blank=True)
    bank_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    director_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    
    def validate_invoice_currency(self, value):
        """Проверка существования валюты"""
        from billing.models import Currency
        if not Currency.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError(_('Invalid currency'))
        return value


class ProviderRegistrationStep4Serializer(serializers.Serializer):
    """
    Шаг 4: Принятие юридических документов
    """
    offer_accepted = serializers.BooleanField(required=True)
    offer_accepted_ip = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    offer_accepted_user_agent = serializers.CharField(required=False, allow_blank=True)
    scroll_position = serializers.FloatField(required=False)
    reading_time_seconds = serializers.IntegerField(required=False)
    
    def validate_offer_accepted(self, value):
        """Проверка, что оферта принята"""
        if not value:
            raise serializers.ValidationError(_('You must accept the offer to continue'))
        return value


class ProviderRegistrationWizardSerializer(serializers.Serializer):
    """
    Полный сериализатор для всех шагов мастера регистрации
    Объединяет все шаги для финального сохранения
    """
    # Шаг 1
    country = serializers.CharField(max_length=2, required=True)
    language = serializers.CharField(max_length=10, required=False, default='en', allow_blank=True)

    # Шаг 2
    provider_name = serializers.CharField(max_length=100, required=True)
    provider_address = serializers.CharField(max_length=200, required=True)
    provider_phone = serializers.CharField(required=True)
    provider_email = serializers.EmailField(required=True)
    admin_email = serializers.EmailField(required=False, allow_blank=True)
    selected_categories = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        min_length=1
    )
    documents = serializers.ListField(
        child=serializers.FileField(allow_empty_file=False),
        required=False,
        allow_empty=True,
    )
    address_components = serializers.JSONField(required=False, allow_null=True)

    # Шаг 3
    tax_id = serializers.CharField(max_length=50, required=True)
    registration_number = serializers.CharField(max_length=100, required=True)
    invoice_currency = serializers.IntegerField(required=True)
    organization_type = serializers.CharField(max_length=50, required=True, allow_blank=False)
    is_vat_payer = serializers.BooleanField(required=True)
    vat_number = serializers.CharField(max_length=50, required=False, allow_blank=True)
    kpp = serializers.CharField(max_length=20, required=False, allow_blank=True)
    iban = serializers.CharField(max_length=34, required=False, allow_blank=True)
    swift_bic = serializers.CharField(max_length=11, required=False, allow_blank=True)
    bank_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    director_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    
    # Шаг 4
    offer_accepted = serializers.BooleanField(required=True)
    offer_accepted_ip = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    offer_accepted_user_agent = serializers.CharField(required=False, allow_blank=True)

    # Нормализация selected_categories для multipart выполняется во view (ProviderRegistrationWizardAPIView._normalize_wizard_data),
    # чтобы сериализатор всегда получал обычный dict и не требовалось менять to_internal_value (избегаем "expected dictionary" и порчи полей).

    def validate_documents(self, value):
        """Проверка типов загруженных файлов (те же расширения, что в ProviderForm.clean_documents)."""
        if not value:
            return value
        allowed_extensions = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png']
        import os
        for f in value:
            ext = os.path.splitext(getattr(f, 'name', '') or '')[1].lower()
            if ext not in allowed_extensions:
                raise serializers.ValidationError(
                    _('File type not supported. Allowed: %(allowed)s') % {'allowed': ', '.join(allowed_extensions)}
                )
        return value

    def validate_tax_id(self, value):
        """Валидация Tax ID по формату для выбранной страны"""
        country = self.initial_data.get('country')
        if not country:
            return value
        
        from providers.validation_rules import validate_requisite_field
        
        is_vat_payer = self.initial_data.get('is_vat_payer', False)
        organization_type = self.initial_data.get('organization_type', '')
        
        is_valid, error_message = validate_requisite_field(
            'tax_id',
            value,
            country,
            is_vat_payer=is_vat_payer,
            organization_type=organization_type
        )
        
        if not is_valid:
            raise serializers.ValidationError(error_message)
        
        return normalize_tax_id(value)
    
    def validate_vat_number(self, value):
        """Валидация VAT Number по формату и через VIES API"""
        country = self.initial_data.get('country')
        is_vat_payer = self.initial_data.get('is_vat_payer', False)
        
        # Если неплательщик НДС, VAT Number не требуется
        if not is_vat_payer:
            return value
        
        # Если плательщик НДС, но VAT Number не указан
        if not value or not value.strip():
            # Проверяем, требуется ли VAT Number для этой страны
            from providers.validation_rules import get_validation_rules
            rules = get_validation_rules(country)
            if rules.get('vat_number', {}).get('required', False):
                raise serializers.ValidationError(_('VAT Number is required for VAT payers'))
            return value
        
        # Проверка формата
        from providers.validation_rules import validate_requisite_field
        
        is_valid, error_message = validate_requisite_field(
            'vat_number',
            value,
            country,
            is_vat_payer=is_vat_payer
        )
        
        if not is_valid:
            raise serializers.ValidationError(error_message)
        
        # Проверка через VIES API (только для стран ЕС)
        eu_countries = ['AT', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI', 'FR', 'GR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU', 'LV', 'MT', 'NL', 'PL', 'PT', 'RO', 'SE', 'SI', 'SK']
        if country in eu_countries:
            from providers.vat_validation_service import validate_vat_id_vies
            
            # Извлекаем VAT ID без префикса страны для VIES API
            vat_clean = value.upper().strip()
            if vat_clean.startswith(country.upper()):
                vat_clean = vat_clean[len(country.upper()):]
            
            vies_result = validate_vat_id_vies(country, vat_clean)
            
            # Сохраняем результат проверки в validated_data для использования в create()
            self.context['vat_verification_result'] = vies_result
            
            # Не блокируем регистрацию при непройденной проверке VIES
            # Статус проверки сохраняется и может быть проверен вручную через админку позже
            # if vies_result['is_valid']:
            #     # VAT ID валидный - все хорошо
            #     pass
            # elif vies_result['error'] and 'timeout' not in vies_result['error'].lower() and 'unavailable' not in vies_result['error'].lower():
            #     # VAT ID невалидный (не найден в реестре) - НЕ блокируем регистрацию
            #     # Статус будет 'invalid', можно проверить вручную через админку
            #     pass
            # else:
            #     # API недоступен - разрешаем регистрацию, но статус будет 'failed'
            #     # Это обрабатывается в create() методе
            #     pass
        
        return normalize_vat_number(value) if value and value.strip() else value
    
    def validate_iban(self, value):
        """Валидация IBAN по формату"""
        country = self.initial_data.get('country')
        is_vat_payer = self.initial_data.get('is_vat_payer', False)
        
        # Если поле пустое, проверяем обязательность
        if not value or not value.strip():
            from providers.validation_rules import get_validation_rules
            rules = get_validation_rules(country)
            iban_rules = rules.get('iban', {})
            
            if iban_rules.get('required', False):
                conditional = iban_rules.get('conditional', {})
                if conditional.get('is_vat_payer') == is_vat_payer:
                    raise serializers.ValidationError(_('IBAN is required'))
            return value
        
        # Проверка формата
        from providers.validation_rules import validate_requisite_field
        
        is_valid, error_message = validate_requisite_field(
            'iban',
            value,
            country,
            is_vat_payer=is_vat_payer
        )
        
        if not is_valid:
            raise serializers.ValidationError(error_message)
        
        return normalize_iban(value) if value and value.strip() else value
    
    def validate_kpp(self, value):
        """Валидация KPP для России"""
        country = self.initial_data.get('country')
        organization_type = self.initial_data.get('organization_type', '')
        
        # KPP требуется только для России и только для ООО
        if country == 'RU' and 'ООО' in organization_type.upper():
            if not value or not value.strip():
                raise serializers.ValidationError(_('KPP is required for Russian LLCs'))
            
            from providers.validation_rules import validate_requisite_field
            
            is_valid, error_message = validate_requisite_field(
                'kpp',
                value,
                country,
                organization_type=organization_type
            )
            
            if not is_valid:
                raise serializers.ValidationError(error_message)
        
        return value
    
    def validate_swift_bic(self, value):
        """Валидация SWIFT/BIC через python-stdnum (формат 8 или 11 символов)"""
        if not value or not value.strip():
            return value
        from providers.validation_rules import validate_swift_bic as do_validate_swift_bic
        is_valid, error_message = do_validate_swift_bic(value)
        if not is_valid:
            raise serializers.ValidationError(error_message)
        return (value or '').strip()
    
    def validate_registration_number(self, value):
        """Валидация Registration Number"""
        country = self.initial_data.get('country')
        
        from providers.validation_rules import validate_requisite_field
        
        is_valid, error_message = validate_requisite_field(
            'registration_number',
            value,
            country
        )
        
        if not is_valid:
            raise serializers.ValidationError(error_message)
        
        return normalize_registration_number(value)
    
    def validate(self, attrs):
        """Общая валидация всех шагов"""
        # Валидация из Step1
        from billing.models import VATRate
        if not VATRate.objects.filter(country=attrs['country'], is_active=True).exists():
            raise serializers.ValidationError({
                'country': _('We do not currently work in this country.')
            })
        
        # Валидация из Step2 (таблица валидаций: уникальность при Завершении мастера)
        from providers.models import Provider
        name_clean = (attrs.get('provider_name') or '').strip()
        if name_clean:
            if Provider.objects.filter(name__iexact=name_clean).exists():
                raise serializers.ValidationError({
                    'provider_name': _('An organization with this name already exists.')
                })
            if ProviderForm.objects.filter(provider_name__iexact=name_clean, status__in=['pending', 'approved']).exists():
                raise serializers.ValidationError({
                    'provider_name': _('An organization with this name already exists.')
                })
        if Provider.objects.filter(email=attrs['provider_email']).exists():
            raise serializers.ValidationError({
                'provider_email': _('Provider with this email already exists')
            })
        if ProviderForm.objects.filter(provider_email=attrs['provider_email'], status__in=['pending', 'approved']).exists():
            raise serializers.ValidationError({
                'provider_email': _('Provider form with this email already exists')
            })
        phone_raw = (attrs.get('provider_phone') or '').strip()
        if phone_raw:
            if Provider.objects.filter(phone_number=phone_raw).exists():
                raise serializers.ValidationError({
                    'provider_phone': _('A provider with this phone number already exists.')
                })
            if ProviderForm.objects.filter(provider_phone=phone_raw, status__in=['pending', 'approved']).exists():
                raise serializers.ValidationError({
                    'provider_phone': _('An application with this phone number already exists.')
                })
        # Адрес должен быть распознан (выбран из подсказок Google): требуем address_components
        address_raw = (attrs.get('provider_address') or '').strip()
        address_components = attrs.get('address_components')
        if address_raw and not address_components:
            raise serializers.ValidationError({
                'provider_address': _('Address must be selected from the list. Please choose a suggested address so it can be recognized.')
            })
        if address_raw and isinstance(address_components, (list, dict)) and len(address_components) == 0:
            raise serializers.ValidationError({
                'provider_address': _('Address must be selected from the list. Please choose a suggested address so it can be recognized.')
            })
        # Если admin_email указан, проверяем существование пользователя
        # Если не указан, будет использован email создателя заявки (в модели save())
        if attrs.get('admin_email'):
            if not User.objects.filter(email=attrs['admin_email'], is_active=True).exists():
                raise serializers.ValidationError({
                    'admin_email': _('User with this email is not registered in the system.')
                })
        
        # Валидация из Step3
        from billing.models import Currency
        if not Currency.objects.filter(id=attrs['invoice_currency'], is_active=True).exists():
            raise serializers.ValidationError({
                'invoice_currency': _('Invalid currency')
            })
        
        # Уникальность в рамках страны: (country, tax_id), (country, registration_number), (country, vat_number)
        country_clean = (attrs.get('country') or '').strip().upper()[:2]
        tax_id_clean = (attrs.get('tax_id') or '').strip()
        if country_clean and tax_id_clean:
            if Provider.objects.filter(country=country_clean, tax_id__iexact=tax_id_clean).exists():
                raise serializers.ValidationError({
                    'tax_id': _('A provider with this Tax ID / INN already exists in this country.')
                })
            if ProviderForm.objects.filter(country=country_clean, tax_id__iexact=tax_id_clean, status__in=['pending', 'approved']).exists():
                raise serializers.ValidationError({
                    'tax_id': _('An application with this Tax ID / INN already exists in this country.')
                })
        reg_num_clean = (attrs.get('registration_number') or '').strip()
        if country_clean and reg_num_clean:
            if Provider.objects.filter(country=country_clean, registration_number__iexact=reg_num_clean).exists():
                raise serializers.ValidationError({
                    'registration_number': _('A provider with this Registration Number already exists in this country.')
                })
            if ProviderForm.objects.filter(country=country_clean, registration_number__iexact=reg_num_clean, status__in=['pending', 'approved']).exists():
                raise serializers.ValidationError({
                    'registration_number': _('An application with this Registration Number already exists in this country.')
                })
        vat_clean = (attrs.get('vat_number') or '').strip()
        if country_clean and vat_clean:
            if Provider.objects.filter(country=country_clean, vat_number__iexact=vat_clean).exists():
                raise serializers.ValidationError({
                    'vat_number': _('A provider with this VAT Number already exists in this country.')
                })
            if ProviderForm.objects.filter(country=country_clean, vat_number__iexact=vat_clean, status__in=['pending', 'approved']).exists():
                raise serializers.ValidationError({
                    'vat_number': _('An application with this VAT Number already exists in this country.')
                })
        # Уникальность IBAN глобально (один счёт — одно юрлицо)
        iban_clean = (attrs.get('iban') or '').strip()
        if iban_clean:
            if Provider.objects.filter(iban__iexact=iban_clean).exists():
                raise serializers.ValidationError({
                    'iban': _('A provider with this IBAN already exists.')
                })
            if ProviderForm.objects.filter(iban__iexact=iban_clean, status__in=['pending', 'approved']).exists():
                raise serializers.ValidationError({
                    'iban': _('An application with this IBAN already exists.')
                })
        
        # Валидация из Step4
        if not attrs.get('offer_accepted'):
            raise serializers.ValidationError({
                'offer_accepted': _('You must accept the offer to continue')
            })
        
        return attrs