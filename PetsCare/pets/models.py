"""
Модели для модуля pets.

Этот модуль содержит модели для управления питомцами в системе PetsCare.

Основные компоненты:
1. PetType - типы питомцев (кошки, собаки и т.д.)
2. Breed - породы питомцев
3. Pet - информация о питомцах
4. MedicalRecord - медицинские записи
5. PetRecord - записи о процедурах/услугах
6. PetRecordFile - файлы, прикрепленные к записям
7. PetAccess - доступ к карте питомца

Особенности реализации:
- Поддержка различных типов питомцев
- Управление медицинскими записями
- Система доступа к информации о питомцах
- Прикрепление файлов к записям
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from catalog.models import Service
from users.models import User
from datetime import date, timedelta
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone
import uuid
import os


class PetType(models.Model):
    """
    Тип питомца (кошка, собака, и т.д.)
    
    Особенности:
    - Уникальный технический код (code)
    - Проверка уникальности и формата кода
    - Мультиязычное наименование
    """
    name = models.CharField(
        _('Name'),
        max_length=50,
        unique=True,
        help_text=_('Type of pet (e.g., cat, dog, etc.)')
    )
    code = models.CharField(
        _('Code'),
        max_length=50,
        unique=True,
        validators=[RegexValidator(
            regex=r'^[a-zA-Z0-9_]+$',
            message='Code must contain only Latin letters, numbers and underscores.'
        )],
        help_text=_('Unique technical code (Latin letters, numbers, underscores). Used for integrations and business logic.')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of the pet type')
    )

    class Meta:
        verbose_name = _('Pet Type')
        verbose_name_plural = _('Pet Types')
        ordering = ['name']

    def __str__(self):
        return self.name


class Breed(models.Model):
    """
    Порода питомца
    
    Особенности:
    - Уникальный технический код (code)
    - Проверка уникальности и формата кода
    - Мультиязычное наименование
    """
    pet_type = models.ForeignKey(
        PetType,
        on_delete=models.CASCADE,
        verbose_name=_('Pet Type'),
        related_name='breeds',
        help_text=_('Type of pet this breed belongs to')
    )
    name = models.CharField(
        _('Name'),
        max_length=100,
        help_text=_('Name of the breed')
    )
    code = models.CharField(
        _('Code'),
        max_length=50,
        unique=True,
        validators=[RegexValidator(
            regex=r'^[a-zA-Z0-9_]+$',
            message='Code must contain only Latin letters, numbers and underscores.'
        )],
        help_text=_('Unique technical code (Latin letters, numbers, underscores). Used for integrations and business logic.')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of the breed')
    )

    class Meta:
        verbose_name = _('Breed')
        verbose_name_plural = _('Breeds')
        ordering = ['pet_type', 'name']
        unique_together = ['pet_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.pet_type.name})"


class Pet(models.Model):
    """
    Модель питомца.
    
    Особенности:
    - Связь с владельцем
    - Основная информация
    - Медицинские данные
    - Особенности ухода
    """
    main_owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='main_pets',
        verbose_name=_('Main Owner'),
        help_text=_('Main owner of the pet')
    )
    owners = models.ManyToManyField(
        User,
        related_name='pets',
        verbose_name=_('Owners'),
        help_text=_('All owners of the pet')
    )
    name = models.CharField(
        _('Name'),
        max_length=100,
        help_text=_('Pet name')
    )
    pet_type = models.ForeignKey(
        PetType,
        on_delete=models.PROTECT,
        verbose_name=_('Pet Type'),
        related_name='pets',
        help_text=_('Type of pet')
    )
    breed = models.ForeignKey(
        Breed,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Breed'),
        related_name='pets',
        help_text=_('Pet breed')
    )
    birth_date = models.DateField(
        _('Birth Date'),
        null=True,
        blank=True,
        help_text=_('Pet birth date')
    )
    weight = models.DecimalField(
        _('Weight'),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Pet weight in kg')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Additional information about the pet')
    )
    special_needs = models.JSONField(
        _('Special Needs'),
        default=dict,
        help_text=_('Special care requirements')
    )
    medical_conditions = models.JSONField(
        _('Medical Conditions'),
        default=dict,
        help_text=_('Medical conditions and history')
    )
    photo = models.ImageField(
        _('Photo'),
        upload_to='pets/%Y/%m/%d/',
        null=True,
        blank=True,
        help_text=_('Pet photo')
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
        verbose_name = _('Pet')
        verbose_name_plural = _('Pets')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_pet_type_display()})"

    def get_age(self):
        """Возвращает возраст питомца в годах"""
        if not self.birth_date:
            return None
        today = date.today()
        age = today.year - self.birth_date.year
        if today.month < self.birth_date.month or (
            today.month == self.birth_date.month and 
            today.day < self.birth_date.day
        ):
            age -= 1
        return age

    def clean(self):
        # Основной владелец не может быть пустым
        if not self.main_owner:
            raise ValidationError({'main_owner': _('Main owner must be set.')})
        # Owners не может быть пустым
        if not self.pk or self.owners.count() == 0:
            raise ValidationError({'owners': _('There must be at least one owner.')})
        # Основной владелец должен входить в owners
        if self.main_owner and self.main_owner not in self.owners.all():
            raise ValidationError({'main_owner': _('Main owner must be in owners list.')})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MedicalRecord(models.Model):
    """
    Медицинская карта питомца
    """
    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        verbose_name=_('Pet'),
        related_name='medical_records',
        help_text=_('Pet this record belongs to')
    )
    date = models.DateField(
        _('Date'),
        help_text=_('Date of the medical record')
    )
    title = models.CharField(
        _('Title'),
        max_length=200,
        help_text=_('Title of the medical record')
    )
    description = models.TextField(
        _('Description'),
        help_text=_('Description of the medical record')
    )
    attachments = models.FileField(
        _('Attachments'),
        upload_to='medical_records/%Y/%m/%d/',
        null=True,
        blank=True,
        help_text=_('Any attachments (test results, prescriptions, etc.)')
    )
    next_visit = models.DateField(
        _('Next Visit'),
        null=True,
        blank=True,
        help_text=_('Date of the next recommended visit')
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
        verbose_name = _('Medical Record')
        verbose_name_plural = _('Medical Records')
        ordering = ['-date']

    def __str__(self):
        return f"{self.pet.name} - {self.title} ({self.date})"


class PetRecord(models.Model):
    """
    Запись в карте питомца о выполненной процедуре/услуге
    
    Особенности:
    - Связь с питомцем и услугой
    - Отслеживание исполнителя и учреждения
    - Хранение результатов и документов
    - Планирование следующей процедуры
    """
    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        verbose_name=_('Pet'),
        related_name='records'
    )
    provider = models.ForeignKey(
        'providers.Provider',
        on_delete=models.PROTECT,
        verbose_name=_('Provider'),
        related_name='pet_records'
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        verbose_name=_('Service'),
        related_name='pet_records'
    )
    employee = models.ForeignKey(
        'providers.Employee',
        on_delete=models.PROTECT,
        verbose_name=_('Employee'),
        related_name='pet_records'
    )
    date = models.DateTimeField(
        _('Date'),
        help_text=_('Date and time when the procedure was performed')
    )
    next_date = models.DateField(
        _('Next Date'),
        null=True,
        blank=True,
        help_text=_('Date when the next procedure should be performed')
    )
    description = models.TextField(
        _('Description'),
        help_text=_('Description of what was done')
    )
    results = models.TextField(
        _('Results'),
        blank=True,
        help_text=_('Results of the procedure')
    )
    recommendations = models.TextField(
        _('Recommendations'),
        blank=True,
        help_text=_('Recommendations for the pet owner')
    )
    notes = models.TextField(
        _('Notes'),
        blank=True,
        help_text=_('Internal notes')
    )
    serial_number = models.CharField(
        _('Serial Number'),
        max_length=100,
        blank=True,
        help_text=_('Serial number (for vaccinations, medications, etc.)')
    )
    files = models.ManyToManyField(
        'PetRecordFile',
        verbose_name=_('Files'),
        related_name='records',
        blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('Created By'),
        related_name='created_records'
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
        verbose_name = _('Pet Record')
        verbose_name_plural = _('Pet Records')
        ordering = ['-date']

    def __str__(self):
        return f"{self.pet.name} - {self.service.name} ({self.date})"

    def save(self, *args, **kwargs):
        # Если это новая запись и услуга периодическая, устанавливаем дату следующей процедуры
        if not self.pk and self.service.is_periodic:
            self.next_date = self.date + timedelta(days=self.service.period_days)
        super().save(*args, **kwargs)


class PetRecordFile(models.Model):
    """
    Универсальная модель файла питомца
    
    Расширенная версия для поддержки системы документов с:
    - Типом документа
    - Метаданными (даты выдачи/истечения, номер, орган выдачи)
    - Аудитом (кто загрузил, дата загрузки)
    - Связями с записями
    """
    # Основные поля
    file = models.FileField(
        _('File'),
        upload_to='pets/documents/%Y/%m/%d/',
        help_text=_('Document file')
    )
    name = models.CharField(
        _('Name'),
        max_length=255,
        help_text=_('Document name')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Document description')
    )
    
    # Связи
    pet = models.ForeignKey(
        'Pet',
        on_delete=models.CASCADE,
        verbose_name=_('Pet'),
        related_name='documents',
        help_text=_('Pet to which the document belongs')
    )
    document_type = models.ForeignKey(
        'DocumentType',
        on_delete=models.PROTECT,
        verbose_name=_('Document Type'),
        related_name='documents',
        null=True,
        blank=True,
        help_text=_('Type of the document')
    )
    medical_record = models.ForeignKey(
        'MedicalRecord',
        on_delete=models.CASCADE,
        verbose_name=_('Medical Record'),
        related_name='documents',
        null=True,
        blank=True,
        help_text=_('Medical record to which the document is attached')
    )
    pet_record = models.ForeignKey(
        'PetRecord',
        on_delete=models.CASCADE,
        verbose_name=_('Pet Record'),
        related_name='documents',
        null=True,
        blank=True,
        help_text=_('Pet record to which the document is attached')
    )
    
    # Метаданные документа
    issue_date = models.DateField(
        _('Issue Date'),
        null=True,
        blank=True,
        help_text=_('Document issue date')
    )
    expiry_date = models.DateField(
        _('Expiry Date'),
        null=True,
        blank=True,
        help_text=_('Document expiry date')
    )
    document_number = models.CharField(
        _('Document Number'),
        max_length=100,
        blank=True,
        help_text=_('Document number')
    )
    issuing_authority = models.CharField(
        _('Issuing Authority'),
        max_length=200,
        blank=True,
        help_text=_('Issuing authority')
    )
    
    # Аудит
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('Uploaded By'),
        related_name='uploaded_documents',
        help_text=_('User who uploaded the document')
    )
    uploaded_at = models.DateTimeField(
        _('Uploaded At'),
        auto_now_add=True,
        help_text=_('Upload date and time')
    )
    
    # Системные поля
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Pet Document')
        verbose_name_plural = _('Pet Documents')
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.name} - {self.pet.name}"

    def clean(self):
        """Валидация модели"""
        super().clean()
        
        # Проверяем, что документ привязан к питомцу
        if not self.pet:
            raise ValidationError(_('Document must be attached to a pet'))
        
        # Проверяем, что документ привязан только к одной записи
        record_count = sum([
            1 if self.medical_record else 0,
            1 if self.pet_record else 0
        ])
        if record_count > 1:
            raise ValidationError(_('Document can only be attached to one record'))
        
        # Проверяем требования типа документа
        if self.document_type:
            if self.document_type.requires_issue_date and not self.issue_date:
                raise ValidationError(_('Issue date is required for this document type'))
            
            if self.document_type.requires_expiry_date and not self.expiry_date:
                raise ValidationError(_('Expiry date is required for this document type'))
            
            if self.document_type.requires_issuing_authority and not self.issuing_authority:
                raise ValidationError(_('Issuing authority is required for this document type'))
            
            if self.document_type.requires_document_number and not self.document_number:
                raise ValidationError(_('Document number is required for this document type'))
        
        # Проверяем даты
        if self.issue_date and self.expiry_date and self.issue_date > self.expiry_date:
            raise ValidationError(_('Issue date cannot be after expiry date'))

    @property
    def is_expired(self):
        """Проверяет, истек ли срок действия документа"""
        if self.expiry_date:
            return self.expiry_date < date.today()
        return False

    @property
    def days_until_expiry(self):
        """Возвращает количество дней до истечения документа"""
        if self.expiry_date:
            delta = self.expiry_date - date.today()
            return delta.days
        return None

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class PetAccess(models.Model):
    """
    Доступ к карте питомца
    """
    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        verbose_name=_('Pet'),
        related_name='accesses'
    )
    granted_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_('Granted To'),
        related_name='pet_accesses'
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_('Granted By'),
        related_name='granted_pet_accesses'
    )
    token = models.UUIDField(
        _('Token'),
        unique=True
    )
    expires_at = models.DateTimeField(
        _('Expires At')
    )
    permissions = models.JSONField(
        _('Permissions'),
        default=dict
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
        verbose_name = _('Pet Access')
        verbose_name_plural = _('Pet Accesses')
        ordering = ['-created_at']
        unique_together = ['pet', 'granted_to']

    def __str__(self):
        return f"{self.pet.name} - {self.granted_to}"

    @property
    def can_read(self):
        """
        Возвращает True, если у пользователя есть право на чтение карты питомца.
        """
        return self.permissions.get('read', False)

    @property
    def can_book(self):
        """
        Возвращает True, если у пользователя есть право на бронирование услуг для питомца.
        """
        return self.permissions.get('book', False)

    @property
    def can_write(self):
        """
        Возвращает True, если у пользователя есть право на редактирование карты питомца.
        """
        return self.permissions.get('write', False)


class PetOwnershipInvite(models.Model):
    """
    Инвайт для добавления совладельца или передачи прав основного владельца.
    type: 'invite' (добавление совладельца) или 'transfer' (передача прав основного владельца)
    """
    INVITE = 'invite'
    TRANSFER = 'transfer'
    TYPE_CHOICES = [
        (INVITE, _('Invite Owner')),
        (TRANSFER, _('Transfer Main Owner')),
    ]
    pet = models.ForeignKey('Pet', on_delete=models.CASCADE, related_name='ownership_invites', verbose_name=_('Pet'))
    email = models.EmailField(_('Email'))
    token = models.UUIDField(_('Token'), default=uuid.uuid4, unique=True)
    expires_at = models.DateTimeField(_('Expires At'))
    type = models.CharField(_('Type'), max_length=16, choices=TYPE_CHOICES)
    invited_by = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='sent_pet_invites', verbose_name=_('Invited By'))
    is_used = models.BooleanField(_('Is Used'), default=False)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Pet Ownership Invite')
        verbose_name_plural = _('Pet Ownership Invites')
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['expires_at']),
        ]

    def is_expired(self):
        return timezone.now() > self.expires_at or self.is_used

    def __str__(self):
        return f"{self.get_type_display()} for {self.email} (pet: {self.pet_id})"


class DocumentType(models.Model):
    """
    Тип документа питомца
    
    Особенности:
    - Уникальный технический код (code)
    - Связь с категориями услуг
    - Настройка обязательных полей
    - Мультиязычное наименование
    """
    name = models.CharField(
        _('Name'),
        max_length=100,
        help_text=_('Name of the document type (e.g., "Pet Passport", "Veterinary Certificate")')
    )
    code = models.CharField(
        _('Code'),
        max_length=50,
        unique=True,
        validators=[RegexValidator(
            regex=r'^[a-zA-Z0-9_]+$',
            message=_('Code must contain only Latin letters, numbers and underscores.')
        )],
        help_text=_('Unique technical code (Latin letters, numbers, underscores). Used for integrations and business logic.')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of the document type')
    )
    service_categories = models.ManyToManyField(
        'catalog.ServiceCategory',
        verbose_name=_('Service Categories'),
        related_name='document_types',
        blank=True,
        help_text=_('Service categories associated with this document type')
    )
    requires_issue_date = models.BooleanField(
        _('Requires Issue Date'),
        default=False,
        help_text=_('Whether issue date is required')
    )
    requires_expiry_date = models.BooleanField(
        _('Requires Expiry Date'),
        default=False,
        help_text=_('Whether expiry date is required')
    )
    requires_issuing_authority = models.BooleanField(
        _('Requires Issuing Authority'),
        default=False,
        help_text=_('Whether issuing authority is required')
    )
    requires_document_number = models.BooleanField(
        _('Requires Document Number'),
        default=False,
        help_text=_('Whether document number is required')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether the document type is active')
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
        verbose_name = _('Document Type')
        verbose_name_plural = _('Document Types')
        ordering = ['name']

    def __str__(self):
        return self.name

    def clean(self):
        """Валидация модели"""
        super().clean()
        if self.requires_expiry_date and not self.requires_issue_date:
            raise ValidationError(_('Issue date is required if expiry date is required'))
