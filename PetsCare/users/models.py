"""
Модели пользователей для системы PetCare.

Содержит:
- Кастомную модель пользователя с поддержкой ролей
- Модели для управления типами пользователей
- Модели для заявок учреждений
- Модели для администраторов учреждений
"""

import os
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField
from django.conf import settings
from datetime import timedelta


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
        Генерирует уникальный username на основе email.
        
        Args:
            email (str): Email пользователя
            
        Returns:
            str: Уникальный username
        """
        import time
        import re
        
        # Извлекаем имя пользователя из email
        username_base = email.split('@')[0]
        # Убираем специальные символы, оставляем только буквы, цифры и точки
        username_base = re.sub(r'[^a-zA-Z0-9.]', '', username_base)
        # Ограничиваем длину
        username_base = username_base[:20]
        
        # Добавляем timestamp для уникальности
        timestamp = str(int(time.time()))
        username = f"{username_base}_{timestamp}"
        
        # Проверяем уникальность и добавляем суффикс если нужно
        counter = 1
        original_username = username
        while self.model.objects.filter(username=username).exists():
            username = f"{original_username}_{counter}"
            counter += 1
            
        return username

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
        """Возвращает список учреждений, которыми управляет пользователь"""
        if self.has_role('provider_admin'):
            from providers.models import Provider
            try:
                provider = Provider.objects.filter(admins=self).first()
                return [provider] if provider else []
            except Provider.DoesNotExist:
                return []
        elif self.has_role('billing_manager'):
            # Менеджер по биллингу имеет доступ ко всем провайдерам
            from providers.models import Provider
            return Provider.objects.filter(is_active=True)
        return []


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
    
    # Новая структурированная модель адреса (убрано для избежания циклических зависимостей)
    # Адрес провайдера можно получить через geolocation.Location
    
    provider_phone = PhoneNumberField(
        verbose_name=_('Provider Phone')
    )
    documents = models.FileField(
        upload_to='provider_docs/%Y/%m/%d/',
        verbose_name=_('Registration Documents'),
        blank=True,
        null=True,
        help_text=_('Required only if the institution provides services that require licensing or certification')
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

    def clean_documents(self):
        """Проверяет тип загруженного файла"""
        file = self.documents
        if file:
            ext = os.path.splitext(file.name)[1].lower()
            allowed_extensions = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png']
            if ext not in allowed_extensions:
                raise ValidationError(_('File type not supported'))
        return file


class ProviderAdmin(models.Model):
    """
    Модель для связи пользователя с учреждением в роли администратора.
    """
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
        unique_together = ['user', 'provider']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.provider}"

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