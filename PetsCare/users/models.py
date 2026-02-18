"""
Модели пользователей для системы PetCare.

Содержит:
- Кастомную модель пользователя с поддержкой ролей
- Модели для управления типами пользователей
- Модели для заявок учреждений
- Модели для администраторов учреждений
"""

import os
from django.db import models, transaction
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField
from django.conf import settings
from datetime import timedelta
from django_countries.fields import CountryField
from django.core.validators import RegexValidator, MinLengthValidator


class UserManager(BaseUserManager):
    """
    Менеджер для модели User.
    
    Предоставляет методы для создания:
    - Обычных пользователей
    - Суперпользователей
    
    Особенности:
    - Использует email как основное поле для входа
    - Автоматически нормализует email
    - Проверяет обязательные поля
    """
    use_in_migrations = True

    def _generate_username(self, email):
        """
        Генерирует username на основе email.
        Поскольку email уникален, используем его напрямую.
        
        Args:
            email (str): Email пользователя
            
        Returns:
            str: Username (тот же email)
        """
        return email

    def create_user(self, email, password=None, **extra_fields):
        """
        Создает и сохраняет обычного пользователя.
        
        Args:
            email (str): Email пользователя
            password (str): Пароль пользователя
            **extra_fields: Дополнительные поля
        
        Returns:
            User: Созданный пользователь
        """
        if not email:
            raise ValueError(_('The Email field must be set'))
        
        email = self.normalize_email(email)
        
        # Автоматически генерируем username если не указан
        if 'username' not in extra_fields or not extra_fields['username']:
            extra_fields['username'] = self._generate_username(email)
        
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Создает и сохраняет суперпользователя.
        
        Args:
            email (str): Email пользователя
            password (str): Пароль пользователя
            **extra_fields: Дополнительные поля
        
        Returns:
            User: Созданный суперпользователь
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)


class UserType(models.Model):
    """
    Тип пользователя (роль) в системе.
    
    Определяет права и возможности пользователя:
    - basic_user: Базовый пользователь
    - system_admin: Администратор системы
    - provider_admin: Администратор учреждения
    - billing_manager: Менеджер по биллингу
    - booking_manager: Менеджер по бронированиям
    - employee: Сотрудник учреждения
    - pet_owner: Владелец питомца (автоматически)
    - pet_sitter: Передержка питомцев (автоматически)
    """
    name = models.CharField(
        _('Name'),
        max_length=50,
        unique=True,
        help_text=_('Unique role name')
    )
    name_en = models.CharField(
        _('Name (English)'),
        max_length=50,
        blank=True,
        help_text=_('Name in English')
    )
    name_ru = models.CharField(
        _('Name (Russian)'),
        max_length=50,
        blank=True,
        help_text=_('Name in Russian')
    )
    name_me = models.CharField(
        _('Name (Montenegrian)'),
        max_length=50,
        blank=True,
        help_text=_('Name in Montenegrian')
    )
    name_de = models.CharField(
        _('Name (German)'),
        max_length=50,
        blank=True,
        help_text=_('Name in German')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Role description')
    )
    permissions = ArrayField(
        models.CharField(max_length=100),
        default=list,
        verbose_name=_('Permissions'),
        help_text=_('List of permissions for this role')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this role is currently active')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('User Type')
        verbose_name_plural = _('User Types')
        ordering = ['name']

    def __str__(self):
        return self.get_localized_name()
    
    def get_localized_name(self, language_code=None):
        """
        Получает локализованное название типа пользователя.
        
        Args:
            language_code: Код языка (en, ru, me, de). Если None, используется текущий язык.
            
        Returns:
            str: Локализованное название
        """
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()
        
        if language_code == 'en' and self.name_en:
            return self.name_en
        elif language_code == 'ru' and self.name_ru:
            return self.name_ru
        elif language_code == 'me' and self.name_me:
            return self.name_me
        elif language_code == 'de' and self.name_de:
            return self.name_de
        else:
            return self.name
    
    def get_permissions(self):
        """
        Возвращает список разрешений для роли.
        
        Returns:
            list: Список разрешений
        """
        return self.permissions
    
    def get_permission_descriptions(self):
        """
        Возвращает словарь разрешений с описаниями.
        
        Returns:
            dict: Словарь {permission: description}
        """
        from .permissions import get_permission_description
        return {perm: get_permission_description(perm) for perm in self.permissions}
    
    def has_permission(self, permission):
        """
        Проверяет, есть ли у роли указанное разрешение.
        
        Args:
            permission (str): Код разрешения
            
        Returns:
            bool: True, если разрешение есть
        """
        return permission in self.permissions
    
    def clean(self):
        """
        Валидация модели.
        """
        from django.core.exceptions import ValidationError
        from .permissions import validate_permissions, ROLE_PERMISSION_SETS
        
        # Обрабатываем предопределенные наборы разрешений
        if self.permissions:
            processed_permissions = []
            for perm in self.permissions:
                if perm.startswith('SET:'):
                    # Это предопределенный набор
                    role_key = perm[4:]  # Убираем 'SET:'
                    if role_key in ROLE_PERMISSION_SETS:
                        from .permissions import get_role_permissions
                        role_permissions = get_role_permissions(role_key)
                        processed_permissions.extend(role_permissions)
                    else:
                        raise ValidationError({
                            'permissions': _('Invalid role set: %(role)s') % {'role': role_key}
                        })
                else:
                    # Это отдельное разрешение
                    processed_permissions.append(perm)
            
            # Убираем дубликаты и обновляем
            self.permissions = list(set(processed_permissions))
        
        # Валидация разрешений
        valid_permissions, invalid_permissions = validate_permissions(self.permissions)
        if invalid_permissions:
            raise ValidationError({
                'permissions': _('Invalid permissions: %(permissions)s') % {
                    'permissions': ', '.join(invalid_permissions)
                }
            })
    
    def save(self, *args, **kwargs):
        """
        Сохранение модели с валидацией.
        """
        self.clean()
        super().save(*args, **kwargs)


class User(AbstractUser):
    """
    Кастомная модель пользователя.
    
    Расширяет стандартную модель пользователя Django:
    - Аутентификация по email вместо username
    - Расширенный профиль с дополнительными полями
    - Настройки для передержки питомцев
    - Поддержка разных типов пользователей
    
    Основные поля:
    - email: Уникальный email для входа
    - phone_number: Уникальный номер телефона
    - user_types: Роли пользователя в системе
    - profile_picture: Аватар пользователя
    - date_of_birth: Дата рождения
    """
    # Базовые поля
    username = models.CharField(
        _('Username'),
        max_length=150,
        unique=True,         # username уникален, но генерируется автоматически
        blank=True,         # не обязательно для заполнения (генерируется автоматически)
        null=False,          # не может быть NULL в базе
        help_text=_('Auto-generated unique username for system compatibility.'),
        error_messages={
            'unique': _('A user with that username already exists.'),
            'max_length': _('Username is too long.')
        }
    )
    email = models.EmailField(
        _('Email Address'),
        unique=True,
        help_text=_('Required. Unique email for authentication.'),
        error_messages={'unique': _('A user with that email already exists.')}
    )
    first_name = models.CharField(
        _('First Name'),
        max_length=30,
        blank=False,
        null=False,
        help_text=_('Required. User\'s first name.'),
    )
    last_name = models.CharField(
        _('Last Name'),
        max_length=150,
        blank=False,
        null=False,
        help_text=_('Required. User\'s last name.'),
    )
    date_of_birth = models.DateField(
        _('Date Of Birth'),
        null=True,
        blank=True,
        help_text=_('Format: YYYY-MM-DD'),
    )
    profile_picture = models.ImageField(
        _('Profile Picture'),
        upload_to='users/%Y/%m/%d/',
        blank=True,
        null=True,
        help_text=_('Optional. User avatar.'),
    )
    phone_number = PhoneNumberField(
        _('Phone Number'),
        blank=False,
        null=False,
        unique=True,
        help_text=_('Required. Unique phone number for contact and verification.')
    )
    
    # Структурированный адрес пользователя (убрано для избежания циклических зависимостей)
    # Адрес пользователя можно получить через geolocation.Location
    # Дефолтная роль basic_user назначается в post_save-сигнале при создании пользователя.

    user_types = models.ManyToManyField(
        UserType,
        blank=True,
        verbose_name=_('User Types'),
        help_text=_('Roles of the user in the system.'),
    )

    # Переопределяем поля для избежания конфликтов related_name
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name=_('Groups'),
        blank=True,
        help_text=_('The groups this user belongs to. A user will get all permissions granted to each of their groups.'),
        related_name='custom_user_set',
        related_query_name='custom_user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name=_('User permissions'),
        blank=True,
        help_text=_('Specific permissions for this user.'),
        related_name='custom_user_set',
        related_query_name='custom_user',
    )

    # Настройки аутентификации
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # username генерируется автоматически

    objects = UserManager()

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-date_joined']

    def __str__(self):
        """
        Возвращает строковое представление пользователя.
        
        Returns:
            str: Email пользователя
        """
        return self.email
    
    def to_dict(self):
        """
        Возвращает словарь с основными полями пользователя для JSON сериализации.
        
        Returns:
            dict: Словарь с данными пользователя
        """
        return {
            'id': self.id,
            'email': self.email,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'is_active': self.is_active,
        }

    def get_full_name(self):
        """
        Возвращает полное имя пользователя.
        
        Returns:
            str: Полное имя пользователя (first_name + last_name)
        """
        full_name = f"{self.first_name} {self.last_name}"
        return full_name.strip()

    def has_role(self, role_name):
        """
        Проверяет, имеет ли пользователь указанную роль.
        
        Args:
            role_name (str): Название роли для проверки
            
        Returns:
            bool: True, если пользователь имеет указанную роль
        """
        return self.user_types.filter(name=role_name).exists()

    def add_role(self, role_name):
        """
        Добавляет роль пользователю.
        
        Args:
            role_name (str): Название роли для добавления
        """
        role, created = UserType.objects.get_or_create(name=role_name)
        self.user_types.add(role)

    def remove_role(self, role_name):
        """
        Удаляет роль у пользователя.
        
        Args:
            role_name (str): Название роли для удаления
        """
        try:
            role = UserType.objects.get(name=role_name)
            self.user_types.remove(role)
        except UserType.DoesNotExist:
            pass

    def get_roles(self):
        """
        Возвращает список ролей пользователя.
        
        Returns:
            QuerySet: Список ролей пользователя
        """
        return self.user_types.all()

    def has_any_role(self, role_names):
        """
        Проверяет, имеет ли пользователь хотя бы одну из указанных ролей.
        
        Args:
            role_names (list): Список названий ролей для проверки
            
        Returns:
            bool: True, если пользователь имеет хотя бы одну из указанных ролей
        """
        return self.user_types.filter(name__in=role_names).exists()

    def has_all_roles(self, role_names):
        """
        Проверяет, имеет ли пользователь все указанные роли.
        
        Args:
            role_names (list): Список названий ролей для проверки
            
        Returns:
            bool: True, если пользователь имеет все указанные роли
        """
        return self.user_types.filter(name__in=role_names).count() == len(role_names)

    def get_managed_providers(self):
        """
        Возвращает queryset учреждений, которыми управляет пользователь.
        
        Returns:
            QuerySet: Queryset объектов Provider
        """
        from providers.models import Provider
        
        if self.has_role('provider_admin'):
            # Получаем провайдеров через связь ProviderAdmin
            return Provider.objects.filter(
                admins__user=self,
                admins__is_active=True
            ).distinct()
        elif self.has_role('billing_manager'):
            # Менеджер по биллингу имеет доступ ко всем провайдерам
            return Provider.objects.filter(is_active=True)
        return Provider.objects.none()
    
    def has_active_role(self, role_name):
        """
        Проверяет, имеет ли пользователь активную функциональную роль.
        
        Активная роль означает:
        1. Роль назначена пользователю (в user_types)
        2. У пользователя есть необходимые данные для использования роли
        
        Например:
        - pet_owner: роль назначена И есть хотя бы один питомец
        - provider_admin: роль назначена И есть управляемые провайдеры
        
        Суперпользователь НЕ получает автоматически активные роли.
        Он должен иметь роль в user_types и соответствующие данные.
        
        Args:
            role_name (str): Название роли для проверки
            
        Returns:
            bool: True, если роль активна (назначена и есть данные)
        """
        # Сначала проверяем, назначена ли роль
        if not self.has_role(role_name):
            return False
        
        # Проверяем наличие необходимых данных в зависимости от роли
        if role_name == 'pet_owner':
            # Для pet_owner требуется наличие хотя бы одного питомца
            return self.pets.filter(is_active=True).exists()
        
        elif role_name == 'provider_admin':
            # Для provider_admin требуется наличие управляемых провайдеров
            return self.get_managed_providers().exists()
        
        elif role_name == 'pet_sitter':
            # Для pet_sitter можно добавить проверку наличия профиля ситтера
            # Пока возвращаем True, если роль назначена
            return True
        
        # Для остальных ролей считаем активной, если она назначена
        return True
    
    def has_system_permission(self, permission_name=None):
        """
        Проверяет системные права пользователя.
        
        Системные права - это права на управление системой:
        - Суперпользователь имеет все системные права
        - Остальные пользователи проверяются по ролям (system_admin, billing_manager и т.д.)
        
        Args:
            permission_name (str, optional): Название разрешения для проверки.
                                           Если None, проверяет общий доступ к админке.
            
        Returns:
            bool: True, если пользователь имеет системное право
        """
        # Суперпользователь имеет все системные права
        if self.is_superuser:
            return True
        
        # Для конкретного разрешения можно добавить проверку через permissions
        if permission_name:
            # Здесь можно добавить проверку через Django permissions
            pass
        
        # Проверяем системные роли
        return self.has_role('system_admin') or self.has_role('billing_manager')
    
    def is_system_admin(self):
        """
        Проверяет, является ли пользователь системным администратором.
        
        Returns:
            bool: True, если пользователь имеет роль system_admin
        """
        return self.has_role('system_admin')
    
    def is_billing_manager(self):
        """
        Проверяет, является ли пользователь биллинг-менеджером.
        
        Returns:
            bool: True, если пользователь имеет роль billing_manager
        """
        return self.has_role('billing_manager')
    
    def is_provider_admin(self):
        """
        Проверяет, является ли пользователь администратором провайдера.

        Returns:
            bool: True, если пользователь имеет роль provider_admin
        """
        return self.has_role('provider_admin')

    def is_provider_owner(self, provider=None):
        """
        Проверяет, является ли пользователь владельцем провайдера (роль owner в ProviderAdmin).

        Args:
            provider: Provider или id провайдера. Если None — проверяет, есть ли
                     у пользователя роль владельца хотя бы у одного провайдера.

        Returns:
            bool: True, если пользователь является владельцем (роль owner в ProviderAdmin).
        """
        from .models import ProviderAdmin
        qs = ProviderAdmin.objects.filter(user=self, is_active=True, role=ProviderAdmin.ROLE_OWNER)
        if provider is not None:
            provider_id = getattr(provider, 'id', provider)
            qs = qs.filter(provider_id=provider_id)
        return qs.exists()

    def is_employee(self):
        """
        Проверяет, является ли пользователь сотрудником учреждения.
        
        Returns:
            bool: True, если пользователь имеет роль employee
        """
        return self.has_role('employee')
    
    def is_client(self):
        """
        Проверяет, является ли пользователь клиентом (владельцем питомца/базовым).
        
        Returns:
            bool: True, если пользователь имеет роль pet_owner или basic_user
        """
        return self.has_role('pet_owner') or self.has_role('basic_user')
    
    def get_active_roles(self):
        """
        Возвращает список активных функциональных ролей пользователя.
        
        Активная роль = роль назначена + есть необходимые данные.
        
        Returns:
            list: Список названий активных ролей
        """
        active_roles = []
        assigned_roles = self.user_types.filter(is_active=True).values_list('name', flat=True)
        
        for role_name in assigned_roles:
            if self.has_active_role(role_name):
                active_roles.append(role_name)
        
        return active_roles
    
    def save(self, *args, **kwargs):
        """
        Переопределенный метод save для автоматической генерации username.
        """
        # Если username пустой или не указан, генерируем его автоматически
        if not self.username and self.email:
            self.username = self.email
        
        super().save(*args, **kwargs)


class EmployeeSpecialization(models.Model):
    """
    Модель специализации сотрудника учреждения.
    Управляется системным администратором.
    """
    name = models.CharField(
        max_length=100,
        verbose_name=_('Specialization Name'),
        unique=True
    )
    name_en = models.CharField(
        _('Name (English)'),
        max_length=100,
        blank=True,
        help_text=_('Name in English')
    )
    name_ru = models.CharField(
        _('Name (Russian)'),
        max_length=100,
        blank=True,
        help_text=_('Name in Russian')
    )
    name_me = models.CharField(
        _('Name (Montenegrian)'),
        max_length=100,
        blank=True,
        help_text=_('Name in Montenegrian')
    )
    name_de = models.CharField(
        _('Name (German)'),
        max_length=100,
        blank=True,
        help_text=_('Name in German')
    )
    description = models.TextField(
        verbose_name=_('Description'),
        blank=True
    )
    description_en = models.TextField(
        _('Description (English)'),
        blank=True,
        help_text=_('Description in English')
    )
    description_ru = models.TextField(
        _('Description (Russian)'),
        blank=True,
        help_text=_('Description in Russian')
    )
    description_me = models.TextField(
        _('Description (Montenegrian)'),
        blank=True,
        help_text=_('Description in Montenegrian')
    )
    description_de = models.TextField(
        _('Description (German)'),
        blank=True,
        help_text=_('Description in German')
    )
    permissions = ArrayField(
        models.CharField(max_length=100),
        default=list,
        verbose_name=_('Permissions'),
        help_text=_('List of specific permissions for this specialization')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Is Active')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )

    class Meta:
        verbose_name = _('Employee Specialization')
        verbose_name_plural = _('Employee Specializations')
        ordering = ['name']

    def __str__(self):
        return self.get_localized_name()
    
    def get_localized_name(self, language_code=None):
        """
        Получает локализованное название специализации.
        
        Args:
            language_code: Код языка (en, ru, me, de). Если None, используется текущий язык.
            
        Returns:
            str: Локализованное название
        """
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()
        
        if language_code == 'en' and self.name_en:
            return self.name_en
        elif language_code == 'ru' and self.name_ru:
            return self.name_ru
        elif language_code == 'me' and self.name_me:
            return self.name_me
        elif language_code == 'de' and self.name_de:
            return self.name_de
        else:
            return self.name
    
    def get_localized_description(self, language_code=None):
        """
        Получает локализованное описание специализации.
        
        Args:
            language_code: Код языка (en, ru, me, de). Если None, используется текущий язык.
            
        Returns:
            str: Локализованное описание
        """
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()
        
        if language_code == 'en' and self.description_en:
            return self.description_en
        elif language_code == 'ru' and self.description_ru:
            return self.description_ru
        elif language_code == 'me' and self.description_me:
            return self.description_me
        elif language_code == 'de' and self.description_de:
            return self.description_de
        else:
            return self.description

    def get_permissions(self):
        """Возвращает разрешения для специализации"""
        return self.permissions


class ProviderForm(models.Model):
    """
    Модель для хранения заявок учреждений на регистрацию администратора.
    """
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('approved', _('Approved')),
        ('rejected', _('Rejected')),
    ]

    provider_name = models.CharField(
        max_length=100,
        verbose_name=_('Provider Name')
    )
    
    # Старое поле адреса (для обратной совместимости)
    provider_address = models.CharField(
        max_length=200,
        verbose_name=_('Provider Address')
    )
    # Компоненты адреса из Google Places Autocomplete (город, улица, дом и т.д.). Опционально.
    address_components = models.JSONField(
        verbose_name=_('Address components'),
        null=True,
        blank=True,
        help_text=_('Structured address from Google Places: formatted_address, street, house_number, city, postal_code, country, region.')
    )

    # Новая структурированная модель адреса (убрано для избежания циклических зависимостей)
    # Адрес провайдера можно получить через geolocation.Location
    
    provider_phone = PhoneNumberField(
        verbose_name=_('Provider Phone')
    )
    provider_email = models.EmailField(
        verbose_name=_('Provider Email'),
        help_text=_('Email address of the provider (may differ from the applicant email). Login credentials will be sent to this address upon approval.')
    )
    admin_email = models.EmailField(
        verbose_name=_('Admin Email'),
        help_text=_('Email address of the registered user who will be appointed as provider administrator. The user must exist in the system. If not specified, will use the email of the user who created the form.'),
        null=True,
        blank=True
    )
    documents = models.FileField(
        upload_to='provider_docs/%Y/%m/%d/',
        verbose_name=_('Registration Documents'),
        blank=True,
        null=True,
        help_text=_('Optional. If uploaded, we show consumers a "Documents available" badge and the documents on request.')
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name=_('Status')
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='provider_forms',
        verbose_name=_('Created By')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )
    
    # Выбранные категории услуг (уровень 0)
    selected_categories = models.ManyToManyField(
        'catalog.Service',
        blank=True,
        verbose_name=_('Selected Service Categories'),
        help_text=_('Service categories that the provider wants to offer'),
        related_name='provider_forms'
    )
    
    # РЕКВИЗИТЫ (обязательные для упрощенного процесса)
    # Временно nullable для миграции, но обязательные через валидацию clean()
    tax_id = models.CharField(
        _('Tax ID / INN'),
        max_length=50,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Zа-яА-ЯёЁ0-9\s-]+$',
                message=_('Tax ID can only contain letters, digits, spaces, and hyphens.')
            ),
            MinLengthValidator(3, message=_('Tax ID must be at least 3 characters long.'))
        ],
        help_text=_('Tax identification number / INN (required). Format: letters, digits, spaces, hyphens. Minimum 3 characters.')
    )
    registration_number = models.CharField(
        _('Registration Number'),
        max_length=100,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Zа-яА-ЯёЁ0-9\s-]+$',
                message=_('Registration number can only contain letters, digits, spaces, and hyphens.')
            ),
            MinLengthValidator(3, message=_('Registration number must be at least 3 characters long.'))
        ],
        help_text=_('Registration number (required). Format: letters, digits, spaces, hyphens. Minimum 3 characters.')
    )
    country = CountryField(
        _('Country'),
        null=True,
        blank=True,
        help_text=_('Country of registration. Required for regional addendums and VAT requirements.')
    )
    # Язык интерфейса при подаче заявки (en, ru, de, me) — для писем на языке регистрировавшего
    language = models.CharField(
        _('Registration language'),
        max_length=10,
        blank=True,
        default='en',
        help_text=_('UI language of the user who submitted the form. Used for sending emails in that language.')
    )
    invoice_currency = models.ForeignKey(
        'billing.Currency',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='provider_forms',
        verbose_name=_('Invoice Currency'),
        help_text=_('Currency for provider invoices (required)')
    )
    
    # ДОПОЛНИТЕЛЬНЫЕ РЕКВИЗИТЫ (из вашего списка)
    organization_type = models.CharField(
        _('Organization Type'),
        max_length=50,
        blank=True,
        help_text=_('Type of organization: SP, OOO, Corp, LLC, etc. (required)')
    )
    director_name = models.CharField(
        _('Director Name'),
        max_length=200,
        blank=True,
        help_text=_('Full name of director (for offer template substitution) (required)')
    )
    kpp = models.CharField(
        _('KPP (Russia only)'),
        max_length=20,
        blank=True,
        help_text=_('KPP (tax registration reason code) - required for Russian LLCs, hidden for other countries')
    )
    is_vat_payer = models.BooleanField(
        _('Is VAT Payer'),
        default=False,
        help_text=_('Whether the organization is a VAT payer (required)')
    )
    vat_number = models.CharField(
        _('VAT Number (EU VAT ID)'),
        max_length=50,
        blank=True,
        help_text=_('VAT Number (EU VAT ID) - required for EU VAT payers. Format: PL12345678')
    )
    iban = models.CharField(
        _('IBAN'),
        max_length=34,
        blank=True,
        help_text=_('IBAN - required for EU/UA. For Russia, use "Account Number" field instead')
    )
    swift_bic = models.CharField(
        _('SWIFT / BIC'),
        max_length=11,
        blank=True,
        help_text=_('SWIFT / BIC - bank identifier (required)')
    )
    bank_name = models.CharField(
        _('Bank Name'),
        max_length=200,
        blank=True,
        help_text=_('Bank name for invoices (required)')
    )
    
    # ПРИНЯТИЕ ОФЕРТЫ (обязательное для упрощенного процесса)
    offer_accepted = models.BooleanField(
        _('Offer Accepted'),
        default=False,
        help_text=_('I have read and accepted the public offer (required)')
    )
    offer_accepted_at = models.DateTimeField(
        _('Offer Accepted At'),
        null=True,
        blank=True,
        help_text=_('Date and time when the offer was accepted')
    )
    offer_accepted_ip = models.GenericIPAddressField(
        _('Offer Accepted IP'),
        null=True,
        blank=True,
        help_text=_('IP address from which the offer was accepted')
    )
    offer_accepted_user_agent = models.TextField(
        _('Offer Accepted User Agent'),
        blank=True,
        help_text=_('User agent from which the offer was accepted')
    )
    
    # Поля для валидации VAT ID (копируются в Provider при создании)
    VAT_VERIFICATION_STATUS_CHOICES = [
        ('pending', _('Pending Verification')),
        ('valid', _('Valid')),
        ('invalid', _('Invalid')),
        ('failed', _('Verification Failed')),
    ]
    
    vat_verification_status = models.CharField(
        _('VAT Verification Status'),
        max_length=20,
        choices=VAT_VERIFICATION_STATUS_CHOICES,
        default='pending',
        help_text=_('Status of VAT ID verification')
    )
    
    vat_verification_result = models.JSONField(
        _('VAT Verification Result'),
        null=True,
        blank=True,
        help_text=_('Result of VAT ID verification from VIES API (company name, address, etc.)')
    )
    
    vat_verification_manual_override = models.BooleanField(
        _('VAT ID Manually Confirmed'),
        default=False,
        help_text=_('Whether VAT ID was manually confirmed by administrator')
    )
    
    vat_verification_date = models.DateTimeField(
        _('VAT Verification Date'),
        null=True,
        blank=True,
        help_text=_('Date when VAT ID was verified via VIES API')
    )
    
    vat_verification_manual_comment = models.TextField(
        _('Manual Verification Comment'),
        blank=True,
        help_text=_('Comment when manually confirming VAT ID (required if manually confirmed)')
    )
    
    vat_verification_manual_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='manually_verified_vat_forms',
        verbose_name=_('Manually Verified By'),
        help_text=_('User who manually confirmed VAT ID')
    )
    
    vat_verification_manual_at = models.DateTimeField(
        _('Manually Verified At'),
        null=True,
        blank=True,
        help_text=_('Date and time when VAT ID was manually confirmed')
    )
    
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_forms',
        verbose_name=_('Approved By')
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Approved At')
    )

    class Meta:
        verbose_name = _('Provider Form')
        verbose_name_plural = _('Provider Forms')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.provider_name} - {self.get_status_display()}"

    def approve(self, approved_by):
        """Одобряет заявку учреждения"""
        self.status = 'approved'
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        self.save()

    def reject(self, approved_by):
        """Отклоняет заявку учреждения"""
        self.status = 'rejected'
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        self.save()

    def save(self, *args, **kwargs):
        """
        Переопределяем save для установки admin_email по умолчанию из created_by.email
        если admin_email не указан
        """
        # Если admin_email не указан и есть created_by, используем email создателя
        if not self.admin_email:
            if self.pk and not self.created_by_id:
                # Если объект уже сохранен, загружаем created_by
                try:
                    self.refresh_from_db(fields=['created_by'])
                except:
                    pass
            if self.created_by_id:
                if not hasattr(self, '_created_by_loaded'):
                    try:
                        # Загружаем created_by если еще не загружен
                        self.created_by
                        self._created_by_loaded = True
                    except:
                        pass
                if self.created_by:
                    self.admin_email = self.created_by.email
        super().save(*args, **kwargs)
    
    def clean(self):
        """Валидация обязательных полей для упрощенного процесса"""
        super().clean()
        
        # Если admin_email не указан, устанавливаем из created_by
        if not self.admin_email and self.created_by:
            self.admin_email = self.created_by.email
        
        # Проверяем обязательные реквизиты
        if not self.tax_id or not self.tax_id.strip():
            raise ValidationError({'tax_id': _('Tax ID is required')})
        
        if not self.registration_number or not self.registration_number.strip():
            raise ValidationError({'registration_number': _('Registration number is required')})
        
        if not self.country:
            raise ValidationError({'country': _('Country is required')})
        
        if not self.invoice_currency:
            raise ValidationError({'invoice_currency': _('Invoice currency is required')})
        
        # Проверяем обязательные поля из вашего списка
        if not self.organization_type or not self.organization_type.strip():
            raise ValidationError({'organization_type': _('Organization type is required')})
        
        if not self.director_name or not self.director_name.strip():
            raise ValidationError({'director_name': _('Director name is required')})
        
        if not self.swift_bic or not self.swift_bic.strip():
            raise ValidationError({'swift_bic': _('SWIFT / BIC is required')})
        
        if not self.bank_name or not self.bank_name.strip():
            raise ValidationError({'bank_name': _('Bank name is required')})
        
        # Условная валидация для РФ
        if self.country == 'RU':
            # For RU LLCs, KPP is required
            if self.organization_type and any(token in self.organization_type for token in ['OOO', 'ООО']):
                if not self.kpp or not self.kpp.strip():
                    raise ValidationError({'kpp': _('KPP is required for Russian LLCs')})
        
        # Условная валидация для ЕС
        from utils.countries import EU_COUNTRIES
        if self.country in EU_COUNTRIES:
            # Для ЕС требуется IBAN
            if not self.iban or not self.iban.strip():
                raise ValidationError({'iban': _('IBAN is required for EU countries')})
            
            # Если плательщик НДС, требуется VAT номер
            if self.is_vat_payer:
                if not self.vat_number or not self.vat_number.strip():
                    raise ValidationError({'vat_number': _('VAT number is required for EU VAT payers')})
        
        # Проверяем принятие оферты
        if not self.offer_accepted:
            raise ValidationError({'offer_accepted': _('You must accept the public offer to submit the application')})
        
        # Если оферта принята, должны быть заполнены метаданные
        if self.offer_accepted and not self.offer_accepted_at:
            # Устанавливаем время принятия, если оно не указано
            if not self.offer_accepted_at:
                self.offer_accepted_at = timezone.now()

    def clean_documents(self):
        """Проверяет тип загруженного файла"""
        file = self.documents
        if file:
            ext = os.path.splitext(file.name)[1].lower()
            allowed_extensions = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png']
            if ext not in allowed_extensions:
                raise ValidationError(_('File type not supported'))
        return file


class ProviderFormDocument(models.Model):
    """
    Дополнительные загруженные документы заявки провайдера (лицензии, сертификаты).
    Все файлы из мульти-загрузки сохраняются здесь; первый также дублируется в ProviderForm.documents
    для обратной совместимости.
    """
    provider_form = models.ForeignKey(
        ProviderForm,
        on_delete=models.CASCADE,
        related_name='registration_documents',
        verbose_name=_('Provider Form'),
    )
    file = models.FileField(
        upload_to='provider_docs/%Y/%m/%d/',
        verbose_name=_('Document File'),
    )

    class Meta:
        verbose_name = _('Provider form document')
        verbose_name_plural = _('Provider form documents')
        ordering = ['id']


class ProviderAdmin(models.Model):
    """
    Модель для связи пользователя с учреждением в роли администратора.

    Роли:
    - owner: владелец провайдера. У каждого провайдера один владелец; один пользователь может быть владельцем нескольких провайдеров. Назначается системой при активации заявки.
    - provider_manager: менеджер провайдера (бизнес-менеджер).
    - provider_admin: админ провайдера (управление персоналом, настройки).
    Один пользователь может иметь несколько ролей у одного провайдера и/или быть владельцем нескольких провайдеров (несколько бизнесов).
    """
    ROLE_OWNER = 'owner'
    ROLE_PROVIDER_MANAGER = 'provider_manager'
    ROLE_PROVIDER_ADMIN = 'provider_admin'
    ROLE_CHOICES = [
        (ROLE_OWNER, _('Owner')),
        (ROLE_PROVIDER_MANAGER, _('Provider manager')),
        (ROLE_PROVIDER_ADMIN, _('Provider admin')),
    ]

    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='admin_providers',
        verbose_name=_('User')
    )
    provider = models.ForeignKey(
        'providers.Provider',
        on_delete=models.CASCADE,
        related_name='admins',
        verbose_name=_('Provider')
    )
    role = models.CharField(
        _('Role'),
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_PROVIDER_ADMIN,
        help_text=_('Owner / Provider manager / Provider admin. One user can have several roles per provider.')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Is Active')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )

    class Meta:
        verbose_name = _('Provider Admin')
        verbose_name_plural = _('Provider Admins')
        unique_together = [['user', 'provider', 'role']]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.provider}"

    def is_owner(self):
        """Является ли этот админ владельцем провайдера (единственным на провайдера)."""
        return self.role == self.ROLE_OWNER

    def deactivate(self):
        """Деактивирует администратора учреждения"""
        self.is_active = False
        self.save()


class RoleInvite(models.Model):
    """
    Модель для инвайтов на роли (employee, billing_manager).
    
    Особенности:
    - Токен для веб/мобильного приложения
    - QR-код для сканирования
    - Email уведомления
    - Временное ограничение действия
    - Подтверждение пользователем
    """
    ROLE_CHOICES = [
        ('employee', _('Employee')),
        ('billing_manager', _('Billing Manager')),
        ('owner', _('Owner')),
        ('provider_manager', _('Provider manager')),
        ('provider_admin', _('Provider admin')),
    ]
    
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('accepted', _('Accepted')),
        ('declined', _('Declined')),
        ('expired', _('Expired')),
    ]
    
    # Кто создает инвайт
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_role_invites',
        verbose_name=_('Created By'),
        help_text=_('User who created this invite')
    )
    
    # Для кого инвайт (по email)
    email = models.EmailField(
        _('Email'),
        help_text=_('Email of the user to invite')
    )
    
    # Роль для назначения
    role = models.CharField(
        _('Role'),
        max_length=20,
        choices=ROLE_CHOICES,
        help_text=_('Role to assign')
    )
    
    # Учреждение (для employee) или проект (для billing_manager)
    provider = models.ForeignKey(
        'providers.Provider',
        on_delete=models.CASCADE,
        verbose_name=_('Provider'),
        help_text=_('Provider for employee role or project for billing manager')
    )
    
    # Должность (для employee)
    position = models.CharField(
        _('Position'),
        max_length=100,
        blank=True,
        help_text=_('Position for employee role')
    )
    
    # Комментарий
    comment = models.TextField(
        _('Comment'),
        blank=True,
        help_text=_('Additional comment about this invite')
    )
    
    # Токен для подтверждения
    token = models.CharField(
        _('Token'),
        max_length=64,
        unique=True,
        help_text=_('Unique token for invite confirmation')
    )
    
    # QR-код (генерируется из токена)
    qr_code = models.TextField(
        _('QR Code'),
        blank=True,
        help_text=_('QR code data for mobile app scanning')
    )
    
    # Статус инвайта
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text=_('Current status of the invite')
    )
    
    # Временные метки
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    expires_at = models.DateTimeField(
        _('Expires At'),
        help_text=_('When this invite expires')
    )
    accepted_at = models.DateTimeField(
        _('Accepted At'),
        null=True,
        blank=True,
        help_text=_('When the invite was accepted')
    )
    declined_at = models.DateTimeField(
        _('Declined At'),
        null=True,
        blank=True,
        help_text=_('When the invite was declined')
    )
    
    # Пользователь, который принял инвайт
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accepted_role_invites',
        verbose_name=_('Accepted By'),
        help_text=_('User who accepted this invite')
    )
    
    class Meta:
        verbose_name = _('Role Invite')
        verbose_name_plural = _('Role Invites')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['token']),
            models.Index(fields=['status']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['role', 'provider']),
        ]
    
    def __str__(self):
        return f"{self.email} - {self.get_role_display()} at {self.provider.name}"
    
    def save(self, *args, **kwargs):
        # Генерируем токен при создании
        if not self.token:
            self.token = self._generate_token()
        
        # Генерируем QR-код
        if not self.qr_code:
            self.qr_code = self._generate_qr_code()
        
        # Устанавливаем срок действия (7 дней по умолчанию)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        
        super().save(*args, **kwargs)
    
    def _generate_token(self):
        """Генерирует уникальный токен для инвайта."""
        import secrets
        return secrets.token_urlsafe(32)
    
    def _generate_qr_code(self):
        """Генерирует QR-код для мобильного приложения."""
        # Формат QR-кода: petcare://invite/{token}
        return f"petcare://invite/{self.token}"
    
    def is_expired(self):
        """Проверяет, истек ли срок действия инвайта."""
        return timezone.now() > self.expires_at
    
    def can_be_accepted(self):
        """Проверяет, можно ли принять инвайт."""
        return (
            self.status == 'pending' and 
            not self.is_expired()
        )
    
    def accept(self, user):
        """
        Принимает инвайт пользователем.
        
        Args:
            user: Пользователь, принимающий инвайт
        """
        if not self.can_be_accepted():
            raise ValueError(_("Invite cannot be accepted"))
        
        if user.email != self.email:
            raise ValueError(_("Email does not match invite"))
        
        # Назначаем роль
        if self.role == 'employee':
            self._assign_employee_role(user)
        elif self.role == 'billing_manager':
            self._assign_billing_manager_role(user)
        elif self.role in ('owner', 'provider_manager', 'provider_admin'):
            self._assign_provider_admin_role(user)
        
        # Обновляем статус
        self.status = 'accepted'
        self.accepted_at = timezone.now()
        self.accepted_by = user
        self.save()
    
    def decline(self, user):
        """
        Отклоняет инвайт пользователем.
        
        Args:
            user: Пользователь, отклоняющий инвайт
        """
        if self.status != 'pending':
            raise ValueError(_("Invite cannot be declined"))
        
        if user.email != self.email:
            raise ValueError(_("Email does not match invite"))
        
        self.status = 'declined'
        self.declined_at = timezone.now()
        self.accepted_by = user
        self.save()
    
    def _assign_employee_role(self, user):
        """Назначает роль сотрудника."""
        from providers.models import Employee, EmployeeProvider
        
        # Создаем профиль сотрудника
        employee, created = Employee.objects.get_or_create(
            user=user,
            defaults={
                'position': self.position or 'Employee',
                'bio': '',
            }
        )
        
        # Создаем связь с учреждением
        EmployeeProvider.objects.create(
            employee=employee,
            provider=self.provider,
            start_date=timezone.now().date(),
            is_confirmed=True,
            confirmed_at=timezone.now()
        )
    
    def _assign_billing_manager_role(self, user):
        """Назначает роль менеджера по биллингу."""
        from billing.models import BillingManagerProvider
        
        # Создаем связь с провайдером
        BillingManagerProvider.objects.create(
            billing_manager=user,
            provider=self.provider,
            start_date=timezone.now().date(),
            status='active'
        )

    def _assign_provider_admin_role(self, user):
        """
        Назначает роль владельца/менеджера/админа организации (ProviderAdmin).
        При принятии инвайта: снимаем роль с предыдущих (один владелец, один менеджер), создаём запись для user.
        """
        from . import ProviderAdmin, UserType
        role = self.role
        provider = self.provider
        with transaction.atomic():
            if role == ProviderAdmin.ROLE_OWNER:
                for prev in ProviderAdmin.objects.filter(provider=provider, role=ProviderAdmin.ROLE_OWNER, is_active=True):
                    prev.deactivate()
            elif role == ProviderAdmin.ROLE_PROVIDER_MANAGER:
                for prev in ProviderAdmin.objects.filter(
                    provider=provider, role=ProviderAdmin.ROLE_PROVIDER_MANAGER, is_active=True
                ):
                    prev.deactivate()
            ProviderAdmin.objects.create(user=user, provider=provider, role=role, is_active=True)
            ut, _ = UserType.objects.get_or_create(name='provider_admin')
            if not user.user_types.filter(name='provider_admin').exists():
                user.user_types.add(ut)
            if role in (ProviderAdmin.ROLE_OWNER, ProviderAdmin.ROLE_PROVIDER_MANAGER):
                role_ut, _ = UserType.objects.get_or_create(name=role)
                if not user.user_types.filter(name=role).exists():
                    user.user_types.add(role_ut)
    
    @classmethod
    def cleanup_expired(cls):
        """Очищает истекшие инвайты."""
        expired_invites = cls.objects.filter(
            status='pending',
            expires_at__lt=timezone.now()
        )
        expired_invites.update(status='expired')
        return expired_invites.count()
    
    @classmethod
    def get_pending_for_email(cls, email):
        """Получает активные инвайты для email."""
        return cls.objects.filter(
            email=email,
            status='pending',
            expires_at__gt=timezone.now()
        )


# Сигналы
from django.db.models.signals import pre_delete
from django.dispatch import receiver

@receiver(pre_delete, sender=User)
def prevent_user_delete_with_active_sitter(sender, instance, **kwargs):
    """
    Предотвращает удаление пользователя с активным профилем ситтера.
    """
    if hasattr(instance, 'sitter') and instance.sitter.is_active:
        raise ValidationError(
            _('Cannot delete user with active sitter profile. Deactivate the sitter profile first.')
        )


class PasswordResetToken(models.Model):
    """
    Модель для токенов восстановления пароля.
    
    Обеспечивает безопасное восстановление пароля с:
    - Временным токеном с истечением
    - Одноразовым использованием
    - Защитой от атак
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='password_reset_tokens',
        verbose_name=_('User')
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        verbose_name=_('Reset Token'),
        help_text=_('Unique token for password reset')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )
    expires_at = models.DateTimeField(
        verbose_name=_('Expires At'),
        help_text=_('Token expiration time')
    )
    used = models.BooleanField(
        default=False,
        verbose_name=_('Used'),
        help_text=_('Whether the token has been used')
    )
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Used At'),
        help_text=_('When the token was used')
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_('IP Address'),
        help_text=_('IP address of the request')
    )
    user_agent = models.TextField(
        null=True,
        blank=True,
        verbose_name=_('User Agent'),
        help_text=_('User agent of the request')
    )
    
    class Meta:
        verbose_name = _('Password Reset Token')
        verbose_name_plural = _('Password Reset Tokens')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"Password reset token for {self.user.email} ({'used' if self.used else 'active'})"
    
    def is_valid(self):
        """
        Проверяет, действителен ли токен.
        
        Returns:
            bool: True если токен действителен
        """
        return (
            not self.used and
            timezone.now() <= self.expires_at
        )
    
    def mark_as_used(self):
        """
        Отмечает токен как использованный.
        """
        self.used = True
        self.used_at = timezone.now()
        self.save(update_fields=['used', 'used_at'])
    
    def save(self, *args, **kwargs):
        """
        Автоматически устанавливает время истечения при создании.
        """
        if not self.pk:  # Новый объект
            from django.conf import settings
            timeout = getattr(settings, 'PASSWORD_RESET_TIMEOUT', 1800)  # 30 минут по умолчанию
            self.expires_at = timezone.now() + timedelta(seconds=timeout)
        super().save(*args, **kwargs)
    
    @classmethod
    def create_for_user(cls, user, ip_address=None, user_agent=None):
        """
        Создает новый токен восстановления для пользователя.
        
        Args:
            user: Пользователь
            ip_address: IP адрес запроса
            user_agent: User agent запроса
            
        Returns:
            PasswordResetToken: Созданный токен
        """
        import secrets
        
        # Генерируем уникальный токен
        token = secrets.token_urlsafe(32)
        
        # Проверяем уникальность
        while cls.objects.filter(token=token).exists():
            token = secrets.token_urlsafe(32)
        
        return cls.objects.create(
            user=user,
            token=token,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @classmethod
    def get_valid_token(cls, token):
        """
        Получает действительный токен по строке.
        
        Args:
            token (str): Токен для поиска
            
        Returns:
            PasswordResetToken or None: Действительный токен или None
        """
        try:
            reset_token = cls.objects.get(token=token)
            if reset_token.is_valid():
                return reset_token
        except cls.DoesNotExist:
            pass
        return None
    
    @classmethod
    def cleanup_expired_tokens(cls):
        """
        Удаляет истекшие токены.
        """
        expired_tokens = cls.objects.filter(
            expires_at__lt=timezone.now()
        )
        count = expired_tokens.count()
        expired_tokens.delete()
        return count 


# Сигналы для автоматического назначения ролей
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def assign_basic_user_role(sender, instance, created, **kwargs):
    """
    Автоматически назначает роль basic_user новым пользователям.
    """
    # Проверяем, что Django полностью инициализирован
    from django.conf import settings
    if not settings.configured:
        return
        
    if created and not instance.user_types.exists():
        try:
            basic_user_type = UserType.objects.get(name='basic_user')
            instance.user_types.add(basic_user_type)
        except UserType.DoesNotExist:
            pass