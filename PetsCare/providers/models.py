"""
Models for the providers module.

Этот модуль содержит модели для управления провайдерами услуг в системе PetsCare.

Основные компоненты:
1. Provider - учреждения (ветклиники, груминг-салоны и т.д.)
2. Employee - специалисты (ветеринары, грумеры и т.д.)
3. EmployeeProvider - связь между специалистами и учреждениями
4. Schedule - расписание работы специалистов
5. ProviderService - связь между учреждениями и услугами
6. LocationSchedule - расписание работы локаций
8. EmployeeWorkSlot - рабочие слоты сотрудников
9. SchedulePattern - шаблоны расписаний
10. PatternDay - описание рабочих дней в шаблоне

Особенности реализации:
- Использование геолокации для поиска ближайших провайдеров
- Система подтверждения сотрудников
- Гибкое управление расписаниями
- Поддержка различных типов рабочих слотов
"""

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
from catalog.models import Service
import googlemaps
from geopy.distance import geodesic
from decimal import Decimal
from datetime import date, timedelta
from calendar import monthrange
import uuid
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, MinLengthValidator
from users.models import User
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Point
from django_countries.fields import CountryField


class ProviderLifecycleSettings(models.Model):
    """
    Глобальные настройки жизненного цикла организаций и филиалов.

    Хранится одна запись, редактируемая через кастомную админку.
    """

    singleton_key = models.PositiveSmallIntegerField(
        default=1,
        unique=True,
        editable=False,
        verbose_name=_('Singleton Key'),
        help_text=_('Technical key for the singleton settings record.'),
    )
    owner_post_termination_access_days = models.PositiveIntegerField(
        _('Owner Post-Termination Access Days'),
        default=30,
        help_text=_('How many days the owner keeps read-only access after organization termination.'),
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Provider Lifecycle Settings')
        verbose_name_plural = _('Provider Lifecycle Settings')

    def __str__(self):
        return str(_('Provider Lifecycle Settings'))

    @classmethod
    def get_solo(cls):
        """
        Возвращает singleton-настройки, создавая запись при первом обращении.
        """
        settings_obj, _ = cls.objects.get_or_create(
            singleton_key=1,
            defaults={'owner_post_termination_access_days': 30},
        )
        return settings_obj


class Provider(models.Model):
    """
    Модель организации (Provider) - юридическое лицо, предоставляющее услуги.
    
    Основные характеристики:
    - Название организации (уникальное)
    - Юридический адрес организации
    - Контактная информация (email, телефон - уникальные на уровне организации)
    - Категории услуг уровня 0, которые организация может предоставлять
    - Реквизиты для биллинга (ИНН, регистрационный номер)
    
    Технические особенности:
    - Адрес хранится в структурированном виде через Address
    - Координаты теперь в локациях (ProviderLocation), не в организации
    - Рейтинг рассчитывается в отчетах, не хранится в модели
    - Оптимизированные индексы для поиска
    
    Примечание:
    Организация может иметь множество локаций (ProviderLocation).
    Биллинг и блокировки работают на уровне организации.
    """
    # ОБЯЗАТЕЛЬНЫЕ поля организации (заполняются при подаче заявки)
    name = models.CharField(
        _('Name'),
        max_length=200,
        unique=True,
        help_text=_('Name of the organization (unique)')
    )
    
    # Юридический адрес организации
    structured_address = models.ForeignKey(
        'geolocation.Address',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='providers',
        verbose_name=_('Structured Address'),
        help_text=_('Legal address of the organization (for documents, contracts)')
    )
    
    # Контактная информация организации (уникальные на уровне организации)
    phone_number = models.CharField(
        _('Phone Number'),
        max_length=20,
        unique=True,
        help_text=_('Main contact phone number of the organization (unique)')
    )
    email = models.EmailField(
        _('Email'),
        unique=True,
        help_text=_('Main contact email of the organization (unique)')
    )
    
    # Категории услуг уровня 0, которые организация может предоставлять
    available_category_levels = models.ManyToManyField(
        'catalog.Service',
        related_name='available_providers',
        verbose_name=_('Available Category Levels'),
        help_text=_('Category levels (level 0) available for this organization')
    )
    
    # Статус активации провайдера
    ACTIVATION_STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('activation_required', _('Activation Required')),
        ('active', _('Active')),
        ('rejected', _('Rejected')),
        ('inactive', _('Inactive')),
    ]
    
    activation_status = models.CharField(
        _('Activation Status'),
        max_length=20,
        choices=ACTIVATION_STATUS_CHOICES,
        default='pending',
        help_text=_('Status of provider activation process')
    )

    PARTNERSHIP_STATUS_ACTIVE = 'active'
    PARTNERSHIP_STATUS_TEMPORARILY_INACTIVE = 'temporarily_inactive'
    PARTNERSHIP_STATUS_TERMINATED = 'terminated'
    PARTNERSHIP_STATUS_CHOICES = [
        (PARTNERSHIP_STATUS_ACTIVE, _('Active')),
        (PARTNERSHIP_STATUS_TEMPORARILY_INACTIVE, _('Temporarily Inactive')),
        (PARTNERSHIP_STATUS_TERMINATED, _('Terminated')),
    ]

    partnership_status = models.CharField(
        _('Partnership Status'),
        max_length=30,
        choices=PARTNERSHIP_STATUS_CHOICES,
        default=PARTNERSHIP_STATUS_ACTIVE,
        db_index=True,
        help_text=_('Operational partnership status of the organization on the platform.'),
    )
    partnership_effective_date = models.DateField(
        _('Partnership Effective Date'),
        null=True,
        blank=True,
        help_text=_('Date when the current partnership status became effective.'),
    )
    partnership_resume_date = models.DateField(
        _('Partnership Resume Date'),
        null=True,
        blank=True,
        help_text=_('Planned date when the organization is expected to return to active status.'),
    )
    partnership_reason = models.TextField(
        _('Partnership Reason'),
        blank=True,
        help_text=_('Reason for the current partnership status.'),
    )
    partnership_status_changed_at = models.DateTimeField(
        _('Partnership Status Changed At'),
        null=True,
        blank=True,
        help_text=_('When the current partnership status was last changed.'),
    )
    partnership_status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='provider_partnership_status_changes',
        verbose_name=_('Partnership Status Changed By'),
        help_text=_('User who last changed the partnership status.'),
    )
    pending_partnership_status = models.CharField(
        _('Pending Partnership Status'),
        max_length=30,
        blank=True,
        default='',
        help_text=_('Scheduled partnership status to apply in the future.'),
    )
    pending_partnership_effective_date = models.DateField(
        _('Pending Partnership Effective Date'),
        null=True,
        blank=True,
        help_text=_('Date when the pending partnership status should be applied.'),
    )
    pending_partnership_resume_date = models.DateField(
        _('Pending Partnership Resume Date'),
        null=True,
        blank=True,
        help_text=_('Planned resume date stored for the pending partnership change.'),
    )
    pending_partnership_reason = models.TextField(
        _('Pending Partnership Reason'),
        blank=True,
        help_text=_('Reason stored for the pending partnership change.'),
    )
    pending_partnership_requested_at = models.DateTimeField(
        _('Pending Partnership Requested At'),
        null=True,
        blank=True,
        help_text=_('When the pending partnership change was scheduled.'),
    )
    pending_partnership_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='provider_pending_partnership_requests',
        verbose_name=_('Pending Partnership Requested By'),
        help_text=_('User who scheduled the pending partnership change.'),
    )
    post_termination_access_until = models.DateTimeField(
        _('Post-Termination Access Until'),
        null=True,
        blank=True,
        help_text=_('Read-only owner access end time after organization termination.'),
    )
    
    # Статус активности (автоматически устанавливается при activation_status=active)
    is_active = models.BooleanField(
        _('Is Active'),
        default=False,
        help_text=_('Whether the organization is currently active. Automatically set to True when activation_status is "active".')
    )
    
    # Ссылка на заявку, по которой создан провайдер (для назначения ролей при активации)
    provider_form = models.ForeignKey(
        'users.ProviderForm',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_provider',
        verbose_name=_('Provider form'),
        help_text=_('Application form that created this provider; used to assign staff roles on activation.')
    )
    
    # ОБЯЗАТЕЛЬНЫЕ для аппрува (заполняются биллинг-менеджерами)
    # Уникальность в рамках страны: (country, tax_id), см. Meta.constraints
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
        help_text=_('Tax identification number / INN (unique per country, required for approval). Format: letters, digits, spaces, hyphens. Minimum 3 characters.')
    )
    # Уникальность в рамках страны: (country, registration_number), см. Meta.constraints
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
        help_text=_('Registration number (unique per country, required for approval). Format: letters, digits, spaces, hyphens. Minimum 3 characters.')
    )
    
    # РЕКВИЗИТЫ (расширенные поля для биллинга)
    # Основной блок
    country = CountryField(
        _('Country'),
        null=True,
        blank=True,
        help_text=_('Country of registration. Main trigger for regional addendums and VAT requirements.')
    )
    is_eu = models.BooleanField(
        _('Is EU Country'),
        default=False,
        db_index=True,
        help_text=_('Automatically set based on country. True if country is in EU. Used for filtering and VAT requirements.')
    )
    organization_type = models.CharField(
        _('Organization Type'),
        max_length=50,
        blank=True,
        help_text=_('Type of organization: SP, OOO, Corp, LLC, etc.')
    )
    director_name = models.CharField(
        _('Director Name'),
        max_length=200,
        blank=True,
        help_text=_('Full name of director (for offer template substitution)')
    )
    
    # Налоговый блок
    kpp = models.CharField(
        _('KPP (Russia only)'),
        max_length=20,
        blank=True,
        help_text=_('KPP (tax registration reason code) - required for Russian LLCs, hidden for other countries')
    )
    is_vat_payer = models.BooleanField(
        _('Is VAT Payer'),
        default=False,
        help_text=_('Whether the organization is a VAT payer')
    )
    # Уникальность в рамках страны: (country, vat_number), см. Meta.constraints
    vat_number = models.CharField(
        _('VAT Number (EU VAT ID)'),
        max_length=50,
        blank=True,
        help_text=_('VAT Number (EU VAT ID) - required for EU VAT payers. Unique per country. Format: PL12345678')
    )
    vat_verified = models.BooleanField(
        _('VAT Verified'),
        default=False,
        help_text=_('Whether VAT number was verified via VIES API')
    )
    vat_verification_date = models.DateTimeField(
        _('VAT Verification Date'),
        null=True,
        blank=True,
        help_text=_('Date when VAT number was verified via VIES API')
    )
    
    # Расширенные поля для валидации VAT ID
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
        help_text=_('Whether VAT ID was manually confirmed by administrator (checked on VIES website)')
    )
    
    vat_verification_manual_comment = models.TextField(
        _('Manual Verification Comment'),
        blank=True,
        help_text=_('Comment when manually confirming VAT ID (required if manually confirmed)')
    )
    
    vat_verification_manual_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='manually_verified_vat_providers',
        verbose_name=_('Manually Verified By'),
        help_text=_('User who manually confirmed VAT ID')
    )
    
    vat_verification_manual_at = models.DateTimeField(
        _('Manually Verified At'),
        null=True,
        blank=True,
        help_text=_('Date and time when VAT ID was manually confirmed')
    )
    
    # Финансовые данные
    invoice_currency = models.ForeignKey(
        'billing.Currency',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='providers',
        verbose_name=_('Invoice Currency'),
        help_text=_('Currency for provider invoices')
    )
    # Уникальность: один IBAN = один счёт = одно юрлицо; см. Meta.constraints
    iban = models.CharField(
        _('IBAN'),
        max_length=34,
        blank=True,
        help_text=_('IBAN - required for EU/UA. Unique per system (one account per legal entity). For Russia, use "Account Number" field instead')
    )
    swift_bic = models.CharField(
        _('SWIFT / BIC'),
        max_length=11,
        blank=True,
        help_text=_('SWIFT / BIC - bank identifier')
    )
    bank_name = models.CharField(
        _('Bank Name'),
        max_length=200,
        blank=True,
        help_text=_('Bank name for invoices')
    )
    
    # Управление видимостью услуг
    show_services = models.BooleanField(
        _('Show Services'),
        default=False,
        help_text=_('Whether provider services should be displayed on UI. Provider can toggle this in admin panel.')
    )
    use_unified_service_pricing = models.BooleanField(
        _('Use Unified Service Pricing'),
        default=False,
        help_text=_('Whether service prices are managed centrally at the organization level and synced to branches.'),
    )
    served_pet_types = models.ManyToManyField(
        'pets.PetType',
        related_name='providers_served',
        verbose_name=_('Organization served pet types'),
        help_text=_('Pet types that can be priced at the organization level and used as the allowed scope for branches in unified pricing mode.'),
        blank=True,
    )
    show_services_toggled_at = models.DateTimeField(
        _('Show Services Toggled At'),
        null=True,
        blank=True,
        help_text=_('When show_services was last toggled')
    )
    
    # ОПЦИОНАЛЬНЫЕ поля
    website = models.URLField(
        _('Website'),
        blank=True,
        help_text=_('Organization website')
    )
    logo = models.ImageField(
        _('Logo'),
        upload_to='providers/logos/%Y/%m/%d/',
        blank=True,
        null=True,
        help_text=_('Organization logo')
    )
    
    # Настройки блокировки
    blocking_region_code = models.CharField(
        _('Blocking region override'),
        max_length=32,
        blank=True,
        help_text=_(
            'Optional region code for billing blocking policy (EU, ME, …). '
            'If empty, region is derived from country (EU aggregate for EU members).'
        ),
    )
    exclude_from_blocking_checks = models.BooleanField(
        _('Exclude From Blocking Checks'),
        default=False,
        help_text=_('Whether this provider should be excluded from automatic blocking checks')
    )
    blocking_exclusion_reason = models.TextField(
        _('Blocking Exclusion Reason'),
        blank=True,
        help_text=_('Reason for excluding this provider from blocking checks')
    )
    
    # Временные метки
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        app_label = 'providers'
        verbose_name = _('Provider')
        verbose_name_plural = _('Providers')
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['activation_status']),
            models.Index(fields=['exclude_from_blocking_checks']),
            models.Index(fields=['tax_id']),
            models.Index(fields=['registration_number']),
            models.Index(fields=['country', 'is_eu']),
            models.Index(fields=['is_eu']),
            models.Index(fields=['use_unified_service_pricing']),
            models.Index(fields=['show_services', 'is_active']),
        ]
        constraints = [
            # Уникальность в рамках страны
            models.UniqueConstraint(
                fields=['country', 'tax_id'],
                condition=Q(country__isnull=False) & ~Q(country='') & Q(tax_id__gt=''),
                name='providers_provider_unique_tax_id_per_country',
            ),
            models.UniqueConstraint(
                fields=['country', 'registration_number'],
                condition=Q(country__isnull=False) & ~Q(country='') & Q(registration_number__gt=''),
                name='providers_provider_unique_reg_num_per_country',
            ),
            models.UniqueConstraint(
                fields=['country', 'vat_number'],
                condition=Q(country__isnull=False) & ~Q(country='') & Q(vat_number__gt=''),
                name='providers_provider_unique_vat_per_country',
            ),
            # Уникальность IBAN глобально (один счёт — одно юрлицо)
            models.UniqueConstraint(
                fields=['iban'],
                condition=Q(iban__gt=''),
                name='providers_provider_unique_iban',
            ),
        ]

    def __str__(self):
        """
        Возвращает строковое представление учреждения.
        
        Returns:
            str: Название учреждения
        """
        return self.name
    
    def save(self, *args, **kwargs):
        """
        Переопределение save() для автоматической установки is_eu на основе country.
        """
        # Автоматически устанавливаем is_eu на основе country
        if self.country:
            from utils.countries import is_eu_country
            self.is_eu = is_eu_country(self.country.code)
        else:
            self.is_eu = False
        
        # Обновляем show_services_toggled_at при изменении show_services
        if self.pk:
            try:
                old_instance = Provider.objects.get(pk=self.pk)
                if old_instance.show_services != self.show_services:
                    self.show_services_toggled_at = timezone.now()
            except Provider.DoesNotExist:
                # Новый объект, не нужно обновлять
                pass
        
        # Обновляем vat_verification_manual_at при установке manual_override
        if self.pk:
            try:
                old_instance = Provider.objects.get(pk=self.pk)
                if not old_instance.vat_verification_manual_override and self.vat_verification_manual_override:
                    # Чекбокс только что установлен
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    # Сохраняем пользователя, который установил чекбокс (если есть в контексте)
                    # Это будет обработано в админке через save_model
                    if not self.vat_verification_manual_at:
                        self.vat_verification_manual_at = timezone.now()
            except Provider.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
    
    def check_vat_id_now(self, user=None):
        """
        Проверяет VAT ID через VIES API и обновляет статус проверки.
        
        Args:
            user: Пользователь, выполняющий проверку (для логирования)
            
        Returns:
            dict: Результат проверки:
                {
                    'success': bool,
                    'status': str,  # 'valid', 'invalid', 'failed'
                    'message': str,
                    'company_name': str | None,
                    'address': str | None
                }
        """
        if not self.vat_number or not self.country:
            return {
                'success': False,
                'status': 'failed',
                'message': _('VAT number or country is not specified'),
                'company_name': None,
                'address': None
            }
        
        # Проверяем, что страна в ЕС
        from utils.countries import is_eu_country
        # CountryField хранит код страны как строку (ISO 3166-1 alpha-2)
        country_code = str(self.country) if self.country else None
        if not country_code or not is_eu_country(country_code):
            return {
                'success': False,
                'status': 'failed',
                'message': _('VAT ID verification is only available for EU countries'),
                'company_name': None,
                'address': None
            }
        
        from .vat_validation_service import validate_vat_id_vies
        
        # Извлекаем VAT ID без префикса страны
        country_code = self.country.code if hasattr(self.country, 'code') else str(self.country)
        vat_clean = self.vat_number.upper().strip()
        if vat_clean.startswith(country_code.upper()):
            vat_clean = vat_clean[len(country_code.upper()):]
        
        # Проверяем через VIES API
        result = validate_vat_id_vies(country_code, vat_clean)
        
        # Обновляем поля провайдера
        if result['is_valid']:
            self.vat_verification_status = 'valid'
            self.vat_verified = True
            self.vat_verification_result = {
                'company_name': result.get('company_name'),
                'address': result.get('address'),
                'request_date': result.get('request_date'),
                'verified_by': user.email if user else None,
                'verified_at': timezone.now().isoformat()
            }
            self.vat_verification_date = timezone.now()
            message = _('VAT ID is valid')
        elif result.get('error') and ('timeout' in result['error'].lower() or 'unavailable' in result['error'].lower()):
            self.vat_verification_status = 'failed'
            self.vat_verified = False
            self.vat_verification_result = {
                'error': result.get('error'),
                'request_date': result.get('request_date'),
                'verified_by': user.email if user else None,
                'verified_at': timezone.now().isoformat()
            }
            message = _('VIES API is unavailable. Please try again later or verify manually.')
        else:
            self.vat_verification_status = 'invalid'
            self.vat_verified = False
            self.vat_verification_result = {
                'error': result.get('error'),
                'request_date': result.get('request_date'),
                'verified_by': user.email if user else None,
                'verified_at': timezone.now().isoformat()
            }
            message = _('VAT ID not found in EU registry')
        
        self.save(update_fields=[
            'vat_verification_status',
            'vat_verified',
            'vat_verification_result',
            'vat_verification_date'
        ])
        
        return {
            'success': result['is_valid'],
            'status': self.vat_verification_status,
            'message': message,
            'company_name': result.get('company_name'),
            'address': result.get('address')
        }
    
    def clean(self):
        """
        Валидация модели перед сохранением.
        Проверяет наличие реквизитов перед активацией провайдера.
        Автоматически устанавливает is_active в зависимости от activation_status.
        """
        super().clean()
        
        # Организация операционно активна только если завершён онбординг и не применён lifecycle-stop.
        if (
            self.activation_status == 'active'
            and self.partnership_status == self.PARTNERSHIP_STATUS_ACTIVE
        ):
            self.is_active = True
        elif self.activation_status in ['pending', 'activation_required', 'rejected', 'inactive']:
            self.is_active = False
        elif self.partnership_status in [
            self.PARTNERSHIP_STATUS_TEMPORARILY_INACTIVE,
            self.PARTNERSHIP_STATUS_TERMINATED,
        ]:
            self.is_active = False
        
        # Если провайдер в статусе activation_required или active, реквизиты должны быть заполнены
        if self.activation_status in ['activation_required', 'active']:
            if not self.tax_id or not self.tax_id.strip():
                raise ValidationError({
                    'tax_id': _('Tax ID is required for providers with status "activation_required" or "active".')
                })
            if not self.registration_number or not self.registration_number.strip():
                raise ValidationError({
                    'registration_number': _('Registration number is required for providers with status "activation_required" or "active".')
                })
            
            # Проверка VAT ID для стран ЕС (если провайдер - плательщик НДС)
            if self.is_vat_payer and self.country:
                from utils.countries import is_eu_country
                country_code = str(self.country) if self.country else None
                if is_eu_country(country_code):
                    # Для ЕС стран и плательщиков НДС требуется подтверждение VAT ID
                    if not (self.vat_verification_status == 'valid' or self.vat_verification_manual_override):
                        raise ValidationError({
                            'vat_number': _('VAT ID must be verified or manually confirmed before activation.')
                        })

    def get_locations(self):
        """
        Получает все локации организации.
        
        Returns:
            QuerySet: Все локации организации
        """
        return self.locations.all()
    
    def get_active_locations(self):
        """
        Получает активные локации организации.
        
        Returns:
            QuerySet: Активные локации организации
        """
        return self.locations.filter(is_active=True)

    def has_post_termination_owner_access(self, moment=None):
        """
        Проверяет, действует ли post-termination read-only окно для owner.
        """
        if self.partnership_status != self.PARTNERSHIP_STATUS_TERMINATED:
            return False
        if self.post_termination_access_until is None:
            return False
        current_moment = moment or timezone.now()
        return self.post_termination_access_until >= current_moment
    
    def get_available_categories(self):
        """
        Получает все доступные категории уровня 0 для организации.
        
        Returns:
            QuerySet: Категории уровня 0 организации
        """
        return self.available_category_levels.filter(level=0, parent__isnull=True)
    
    def has_active_offer_acceptance(self):
        """
        Проверяет, есть ли у провайдера активный акцепт текущей активной оферты.
        
        Используется для блокировки доступа провайдера, пока он не акцептует новую оферту.
        
        Returns:
            bool: True если есть активный акцепт текущей активной оферты, False иначе
        """
        from legal.models import LegalDocument, CountryLegalConfig, DocumentAcceptance
        
        # НОВЫЙ ПОДХОД: Используем LegalDocument и DocumentAcceptance
        if self.country:
            try:
                country_config = CountryLegalConfig.objects.get(country=self.country)
                global_offer = country_config.global_offer
                if global_offer:
                    # Проверяем, есть ли активный акцепт этого документа
                    return DocumentAcceptance.objects.filter(
                        provider=self,
                        document=global_offer,
                        is_active=True
                    ).exists()
            except CountryLegalConfig.DoesNotExist:
                pass
        
        # Если нет активной оферты через новую структуру, считаем что акцепт не требуется
        return True
    
    def get_pending_offer_acceptance(self):
        """
        Получает оферту, которую провайдер должен акцептовать.
        
        Returns:
            LegalDocument или None: Оферта, которую нужно акцептовать, или None если акцепт не требуется
        """
        from legal.models import LegalDocument, CountryLegalConfig
        
        # Используем LegalDocument
        if self.country:
            try:
                country_config = CountryLegalConfig.objects.get(country=self.country)
                global_offer = country_config.global_offer
                if global_offer:
                    # Проверяем, есть ли активный акцепт
                    if self.has_active_offer_acceptance():
                        return None
                    # Если нет активного акцепта, возвращаем документ для акцепта
                    return global_offer
            except CountryLegalConfig.DoesNotExist:
                pass
        
        return None
    
    def calculate_debt(self):
        """
        Рассчитывает задолженность провайдера на основе актуальной PaymentHistory.
        
        Returns:
            dict: Словарь с полями:
                - total_debt: Decimal - общая задолженность (сумма всех неоплаченных Invoice)
                - overdue_debt: Decimal - просроченная задолженность (Invoice со статусом 'overdue')
                - currency: Currency - валюта задолженности (из первого Invoice)
        """
        from billing.models import PaymentHistory
        from decimal import Decimal
        
        payment_records = PaymentHistory.objects.filter(
            provider=self,
            status__in=['pending', 'partially_paid', 'overdue']
        )
        
        total_debt = Decimal('0.00')
        overdue_debt = Decimal('0.00')
        currency = None
        
        for payment_record in payment_records:
            if currency is None:
                currency = payment_record.currency
            
            total_debt += payment_record.outstanding_amount
            
            if payment_record.due_date < timezone.now().date():
                overdue_debt += payment_record.outstanding_amount
        
        return {
            'total_debt': total_debt,
            'overdue_debt': overdue_debt,
            'currency': currency
        }
    
    def get_max_overdue_days(self):
        """
        Получает максимальное количество дней просрочки среди всех долгов provайдера.
        
        Returns:
            int: Максимальное количество дней просрочки, или 0 если нет просроченных Invoice
        """
        from billing.models import PaymentHistory

        overdue_payments = PaymentHistory.objects.filter(
            provider=self,
            status__in=['pending', 'partially_paid', 'overdue']
        )
        
        max_overdue_days = 0
        today = timezone.now().date()
        
        for payment_record in overdue_payments:
            if payment_record.outstanding_amount > Decimal('0.00') and payment_record.due_date < today:
                overdue_days = (today - payment_record.due_date).days
                max_overdue_days = max(max_overdue_days, overdue_days)
        
        return max_overdue_days
    
    def _get_payment_deferral_days(self):
        """
        Возвращает порядковый номер рабочего дня месяца для срока оплаты счета.

        Legacy-имя поля сохранено, но в текущем биллинге значение трактуется
        как рабочий день месяца, а не как количество календарных дней.
        """
        offer_config = self.get_offer_billing_config()
        side_letter = self.legal_documents.filter(
            document_type__code='side_letter',
            is_active=True
        ).first()
        if side_letter and side_letter.payment_deferral_days:
            return side_letter.payment_deferral_days
        if offer_config and offer_config.payment_deferral_days:
            return offer_config.payment_deferral_days
        return 5

    def get_offer_billing_config(self):
        """
        Возвращает billing config активной глобальной оферты провайдера.
        """
        active_acceptance = self.document_acceptances.filter(
            document__document_type__code='global_offer',
            is_active=True
        ).select_related('document__billing_config').first()
        if active_acceptance and active_acceptance.document:
            return active_acceptance.document.billing_config
        return None

    def get_invoice_generation_working_day(self):
        """
        Возвращает порядковый номер рабочего дня месяца для выставления счета.
        """
        offer_config = self.get_offer_billing_config()
        if offer_config and offer_config.invoice_period_days:
            return offer_config.invoice_period_days
        return 3

    def _get_billing_country_code(self):
        """
        Возвращает ISO-код страны провайдера для расчета рабочих дней.
        """
        if not self.country:
            return ''
        return getattr(self.country, 'code', str(self.country) or '').upper()

    def _is_working_billing_day(self, target_date):
        """
        Проверяет рабочий день через ProductionCalendar с fallback на CalendarProvider.
        """
        country_code = self._get_billing_country_code()
        if not country_code:
            return target_date.weekday() < 5

        from production_calendar.calendar_provider import CalendarProvider
        from production_calendar.models import (
            DAY_TYPE_SHORT_DAY,
            DAY_TYPE_WORKING,
            ProductionCalendar,
        )

        calendar_day = ProductionCalendar.objects.filter(
            country=country_code,
            date=target_date,
        ).first()
        if calendar_day is not None:
            return calendar_day.day_type in {DAY_TYPE_WORKING, DAY_TYPE_SHORT_DAY}

        info = CalendarProvider.get_day_info(country_code, target_date)
        return info.get('day_type') in {DAY_TYPE_WORKING, DAY_TYPE_SHORT_DAY}

    def resolve_working_day_of_month(self, year, month, working_day_number):
        """
        Возвращает дату N-го рабочего дня месяца.

        Если номер больше количества рабочих дней, используется последний
        рабочий день месяца.
        """
        if not working_day_number or working_day_number <= 0:
            return None

        last_working_day = None
        working_day_counter = 0
        days_in_month = monthrange(year, month)[1]

        for day_number in range(1, days_in_month + 1):
            candidate_date = date(year, month, day_number)
            if not self._is_working_billing_day(candidate_date):
                continue

            last_working_day = candidate_date
            working_day_counter += 1
            if working_day_counter == working_day_number:
                return candidate_date

        return last_working_day

    def get_scheduled_invoice_issue_date(self, reference_date):
        """
        Возвращает дату выставления счета в месяце reference_date.
        """
        return self.resolve_working_day_of_month(
            reference_date.year,
            reference_date.month,
            self.get_invoice_generation_working_day(),
        )

    def should_generate_invoice_on(self, run_date):
        """
        Проверяет, должен ли счет автоматически выставляться в указанную дату.
        """
        return self.get_scheduled_invoice_issue_date(run_date) == run_date

    def calculate_invoice_due_date(self, issue_date):
        """
        Возвращает срок оплаты как N-й рабочий день месяца.

        Если расчетный рабочий день уже прошел относительно issue_date,
        используется следующий месяц.
        """
        due_working_day = self._get_payment_deferral_days()
        due_date = self.resolve_working_day_of_month(
            issue_date.year,
            issue_date.month,
            due_working_day,
        )
        if due_date and due_date >= issue_date:
            return due_date

        next_month_anchor = (issue_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        return self.resolve_working_day_of_month(
            next_month_anchor.year,
            next_month_anchor.month,
            due_working_day,
        )
    
    def get_blocking_thresholds(self):
        """
        Возвращает пороги блокировки по региональной политике платформы.

        Юридические документы на суммы блокировок не влияют: допуск и дни задаются
        моделью RegionalBlockingPolicy по коду региона (или дефолты из settings).

        Returns:
            dict: Поля tolerance_amount, overdue_days_l2_from, overdue_days_l3_from,
            blocking_region_code, policy_currency_code; устаревшие ключи
            overdue_threshold_* оставлены для совместимости чтения.
        """
        from billing.regional_blocking import resolve_blocking_thresholds_for_provider

        return resolve_blocking_thresholds_for_provider(self)
    
    def can_show_services(self):
        """
        Проверяет, можно ли показывать услуги провайдера на UI.
        
        Услуги показываются только если:
        - show_services = True (провайдер сам включил показ)
        - Провайдер активен (is_active = True, activation_status = 'active')
        - Провайдер не в блоке (нет активных блокировок)
        - Провайдер имеет активную оферту (опционально, но рекомендуется)
        
        Returns:
            bool: True если услуги можно показывать, False иначе
        """
        # Проверяем, включен ли показ услуг провайдером
        if not self.show_services:
            return False
        
        # Проверяем, активен ли провайдер
        if not self.is_active or self.activation_status != 'active':
            return False
        
        # Проверяем наличие активной оферты
        if not self.has_active_offer_acceptance():
            return False
        
        # Проверяем, не заблокирован ли провайдер
        from billing.models import ProviderBlocking
        active_blockings = ProviderBlocking.objects.filter(
            provider=self,
            status='active'
        )
        if active_blockings.exists():
            # Проверяем уровень блокировки
            # Уровень 1 (информация) - услуги можно показывать
            # Уровень 2 (исключение из поиска) - услуги не показываются
            # Уровень 3 (полная блокировка) - услуги не показываются
            for blocking in active_blockings:
                if blocking.blocking_level >= 2:
                    return False
        
        return True
    
    def calculate_commission(self, booking_amount, booking_currency, provider_currency=None):
        """
        Рассчитывает комиссию для указанной суммы бронирования.
        
        Использует ProviderSpecialTerms если есть, иначе стандартный процент из оферты.
        
        Args:
            booking_amount: Decimal - сумма бронирования
            booking_currency: Currency - валюта бронирования
            provider_currency: Currency - валюта провайдера (опционально, для конвертации)
            
        Returns:
            Decimal: сумма комиссии в валюте провайдера (или booking_currency, если provider_currency не указан)
        """
        from legal.models import LegalDocument, DocumentAcceptance
        from decimal import Decimal
        
        # Проверяем, есть ли специальные условия из LegalDocument (side_letter)
        side_letter = self.legal_documents.filter(
            document_type__code='side_letter',
            is_active=True
        ).first()
        if side_letter and side_letter.document_type.allows_financial_terms:
            return side_letter.calculate_commission(booking_amount, booking_currency, provider_currency)
        
        # Используем стандартный процент из активной оферты
        active_acceptance = self.document_acceptances.filter(
            document__document_type__code='global_offer',
            is_active=True
        ).first()
        if active_acceptance:
            # НОВЫЙ ПОДХОД: Используем LegalDocument
            if active_acceptance.document and active_acceptance.document.billing_config:
                commission_percent = active_acceptance.document.billing_config.commission_percent
            # УДАЛЕНО: обратная совместимость с PublicOffer
            else:
                commission_percent = Decimal('5.00')
        else:
            # Если нет активной оферты, используем значение по умолчанию (5%)
            commission_percent = Decimal('5.00')
        
        # Определяем валюту провайдера
        if not provider_currency:
            provider_currency = self.invoice_currency or booking_currency
        
        # Конвертируем сумму в валюту провайдера, если нужно
        if booking_currency != provider_currency:
            booking_amount = booking_currency.convert_amount(booking_amount, provider_currency)
        
        # Рассчитываем комиссию
        commission = booking_amount * (commission_percent / Decimal('100'))
        
        return commission

    def calculate_commission_with_vat(self, booking_amount, booking_currency, provider_currency=None):
        """
        Рассчитывает комиссию с учетом НДС для указанной суммы бронирования.
        
        Логика расчета НДС:
        - Если провайдер НЕ плательщик НДС (is_vat_payer=False): 
          комиссия * (1 + vat_rate/100)
        - Если провайдер плательщик НДС (is_vat_payer=True):
          - Для ЕС: Reverse Charge (0% НДС)
          - Для других стран: зависит от законодательства
        
        Args:
            booking_amount: Decimal - сумма бронирования
            booking_currency: Currency - валюта бронирования
            provider_currency: Currency - валюта провайдера (опционально, для конвертации)
            
        Returns:
            dict: {
                'commission': Decimal - базовая комиссия без НДС,
                'vat_rate': Decimal - ставка НДС (или None),
                'vat_amount': Decimal - сумма НДС,
                'total_with_vat': Decimal - итоговая сумма с НДС
            }
        """
        from billing.models import VATRate
        from decimal import Decimal
        
        # Рассчитываем базовую комиссию
        commission = self.calculate_commission(booking_amount, booking_currency, provider_currency)
        
        # Инициализируем значения по умолчанию
        vat_rate = None
        vat_amount = Decimal('0.00')
        total_with_vat = commission
        
        # Если провайдер НЕ плательщик НДС, добавляем НДС
        if not self.is_vat_payer:
            # Получаем ставку НДС для страны провайдера
            if self.country:
                vat_rate = VATRate.get_rate_for_country(self.country)
                
                if vat_rate:
                    # Рассчитываем НДС: комиссия * (vat_rate / 100)
                    vat_amount = commission * (vat_rate / Decimal('100'))
                    total_with_vat = commission + vat_amount
        else:
            # Если провайдер плательщик НДС
            if self.is_eu:
                # Для ЕС: Reverse Charge (0% НДС, провайдер сам начисляет)
                vat_rate = Decimal('0.00')
                vat_amount = Decimal('0.00')
                total_with_vat = commission
            else:
                # Для других стран: зависит от законодательства
                # Пока оставляем без НДС (можно расширить логику)
                vat_rate = None
                vat_amount = Decimal('0.00')
                total_with_vat = commission
        
        return {
            'commission': commission,
            'vat_rate': vat_rate,
            'vat_amount': vat_amount,
            'total_with_vat': total_with_vat
        }


class Employee(models.Model):
    """
    Employee model (veterinarian, groomer, etc.).
    
    Основные характеристики:
    - Связь с пользовательским аккаунтом
    - Список учреждений, где работает
    - Должность и биография
    - Специализации и услуги
    
    Технические особенности:
    - Мягкое удаление через флаг is_active
    - Автоматическое отслеживание времени создания и обновления
    - Связь с пользователем через OneToOneField
    - Связь с учреждениями через ManyToManyField
    
    Примечание:
    При деактивации сотрудника все связанные записи должны быть обработаны
    через сигналы Django (см. signals.py).
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='employee_profile',
        help_text=_('User account of the employee')
    )
    providers = models.ManyToManyField(
        Provider,
        through='EmployeeProvider',
        verbose_name=_('Providers'),
        related_name='employees',
        help_text=_('Providers this employee works for')
    )
    locations = models.ManyToManyField(
        'ProviderLocation',
        related_name='employees',
        verbose_name=_('Locations'),
        help_text=_('Locations where this employee works')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether the employee is currently active')
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
        verbose_name = _('Employee')
        verbose_name_plural = _('Employees')
        ordering = ['user__last_name', 'user__first_name']
        indexes = [
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление сотрудника.
        
        Returns:
            str: Полное имя сотрудника
        """
        return self.user.get_full_name()

    def can_view_pet_medical_history(self):
        """
        Проверяет, может ли сотрудник просматривать медицинскую историю питомца.
        
        Returns:
            bool: True, если сотрудник имеет право просматривать историю
        """
        return self.specializations.filter(
            permissions__contains={'view_medical_history': True}
        ).exists()

    def can_edit_pet_medical_history(self):
        """
        Проверяет, может ли сотрудник редактировать медицинскую историю питомца.
        
        Returns:
            bool: True, если сотрудник имеет право редактировать историю
        """
        return self.specializations.filter(
            permissions__contains={'edit_medical_history': True}
        ).exists()

    def can_perform_grooming(self):
        """
        Проверяет, может ли сотрудник выполнять груминг.
        
        Returns:
            bool: True, если сотрудник имеет право выполнять груминг
        """
        return self.specializations.filter(
            permissions__contains={'perform_grooming': True}
        ).exists()

    def can_schedule_appointments(self):
        """
        Проверяет, может ли сотрудник планировать встречи.
        
        Returns:
            bool: True, если сотрудник имеет право планировать встречи
        """
        return self.specializations.filter(
            permissions__contains={'schedule_appointments': True}
        ).exists()

    def has_active_provider(self):
        """
        Проверяет, есть ли у сотрудника активная связь с учреждением.
        """
        return self.employeeprovider_set.filter(end_date__isnull=True).exists()

    def get_active_providers(self):
        """
        Возвращает список активных учреждений сотрудника.
        
        Returns:
            QuerySet: Список активных учреждений
        """
        return self.providers.filter(
            employeeprovider_set__end_date__isnull=True
        )

    def deactivate(self, by_user):
        """
        Деактивирует сотрудника.
        
        Параметры:
            by_user (User): Пользователь, выполняющий деактивацию
            
        Примечание:
        При деактивации сотрудника все связанные записи должны быть обработаны
        через сигналы Django (см. signals.py).
        """
        if not by_user.is_system_admin():
            raise ValueError(_("Only system admin can deactivate employees"))
        
        self.is_active = False
        self.save()


class EmployeeLocationService(models.Model):
    """
    Услуги, которые сотрудник оказывает в конкретной локации (филиале).

    Связь «персонал — локация — услуга»: один и тот же сотрудник может оказывать
    разные наборы услуг в разных филиалах и у разных провайдеров. Слоты для записи
    считаются по графикам сотрудника в локации и уже существующим бронированиям.
    """
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='location_services',
        verbose_name=_('Employee'),
    )
    provider_location = models.ForeignKey(
        'ProviderLocation',
        on_delete=models.CASCADE,
        related_name='employee_services',
        verbose_name=_('Location'),
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        verbose_name=_('Service'),
    )

    class Meta:
        verbose_name = _('Employee location service')
        verbose_name_plural = _('Employee location services')
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'provider_location', 'service'],
                name='providers_employeelocationservice_employee_location_service_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['provider_location', 'service'], name='prov_emplocsvc_loc_svc_idx'),
        ]

    def __str__(self):
        return f"{self.employee} @ {self.provider_location}: {self.service}"


class ProviderRole(models.Model):
    """DB-managed provider RBAC roles."""

    CODE_OWNER = 'owner'
    CODE_PROVIDER_ADMIN = 'provider_admin'
    CODE_PROVIDER_MANAGER = 'provider_manager'
    CODE_BRANCH_MANAGER = 'branch_manager'
    CODE_WORKER = 'worker'

    code = models.CharField(_('Code'), max_length=30, unique=True)
    name = models.CharField(_('Name'), max_length=100)
    description = models.TextField(_('Description'), blank=True)
    level = models.PositiveSmallIntegerField(
        _('Level'),
        help_text=_('Hierarchy level: 1=Owner, 2=Admin, 3=Manager, 4=Branch Manager, 5=Worker'),
    )
    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Provider Role')
        verbose_name_plural = _('Provider Roles')
        ordering = ['level', 'code']

    def __str__(self):
        return f'{self.name} ({self.code})'


class ProviderResource(models.Model):
    """DB-managed provider admin resources."""

    code = models.CharField(_('Code'), max_length=60, unique=True)
    name = models.CharField(_('Name'), max_length=150)
    description = models.TextField(_('Description'), blank=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name=_('Parent Resource'),
        help_text=_('Parent resource for hierarchical grouping (e.g., org -> org.profile)'),
    )
    sort_order = models.PositiveIntegerField(_('Sort Order'), default=0)
    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Provider Resource')
        verbose_name_plural = _('Provider Resources')
        ordering = ['sort_order', 'code']

    def __str__(self):
        return f'{self.name} ({self.code})'


class ProviderRolePermission(models.Model):
    """RBAC matrix entry Role <-> Resource <-> CRUD + scope."""

    SCOPE_ALL = 'all'
    SCOPE_OWN_BRANCH = 'own_branch'
    SCOPE_OWN_ONLY = 'own_only'
    SCOPE_CHOICES = [
        (SCOPE_ALL, _('Full access')),
        (SCOPE_OWN_BRANCH, _('Own branches only')),
        (SCOPE_OWN_ONLY, _('Own records only')),
    ]

    role = models.ForeignKey(
        ProviderRole,
        on_delete=models.CASCADE,
        related_name='permissions',
        verbose_name=_('Role'),
    )
    resource = models.ForeignKey(
        ProviderResource,
        on_delete=models.CASCADE,
        related_name='permissions',
        verbose_name=_('Resource'),
    )
    can_create = models.BooleanField(_('Can Create'), default=False)
    can_read = models.BooleanField(_('Can Read'), default=False)
    can_update = models.BooleanField(_('Can Update'), default=False)
    can_delete = models.BooleanField(_('Can Delete'), default=False)
    scope = models.CharField(
        _('Scope'),
        max_length=20,
        default=SCOPE_ALL,
        choices=SCOPE_CHOICES,
        help_text=_('Scope of the permission: all data, own branches only, or own records only'),
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Provider Role Permission')
        verbose_name_plural = _('Provider Role Permissions')
        constraints = [
            models.UniqueConstraint(
                fields=['role', 'resource'],
                name='providers_rolepermission_role_resource_uniq',
            ),
        ]
        ordering = ['role__level', 'resource__sort_order', 'resource__code']

    def __str__(self):
        actions = []
        if self.can_create:
            actions.append('C')
        if self.can_read:
            actions.append('R')
        if self.can_update:
            actions.append('U')
        if self.can_delete:
            actions.append('D')
        return f'{self.role.code} -> {self.resource.code}: {"".join(actions) or "-"} ({self.scope})'


class EmployeeLocationRole(models.Model):
    """
    Роль сотрудника в филиале (локации).

    - branch_manager: руководитель филиала, один на филиал.
    - worker: исполнитель филиала.
    """
    ROLE_BRANCH_MANAGER = 'branch_manager'
    ROLE_WORKER = 'worker'
    ROLE_LOCATION_MANAGER = ROLE_BRANCH_MANAGER
    ROLE_SERVICE_WORKER = ROLE_WORKER
    ROLE_TECHNICAL_WORKER = ROLE_WORKER
    ROLE_CHOICES = [
        (ROLE_BRANCH_MANAGER, _('Branch Manager')),
        (ROLE_WORKER, _('Worker')),
    ]

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='location_roles',
        verbose_name=_('Employee'),
    )
    provider_location = models.ForeignKey(
        'ProviderLocation',
        on_delete=models.CASCADE,
        related_name='employee_roles',
        verbose_name=_('Location'),
    )
    role = models.CharField(
        _('Role'),
        max_length=20,
        choices=ROLE_CHOICES,
        help_text=_('Staff role at this location. Only one branch manager per location.'),
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether the employee is currently active at this location. '
                    'Set to False for soft-delete / deactivation (offboarding).'),
    )
    end_date = models.DateTimeField(
        _('End Date'),
        null=True,
        blank=True,
        help_text=_('Date/time when employee was deactivated at this location.'),
    )

    class Meta:
        verbose_name = _('Employee location role')
        verbose_name_plural = _('Employee location roles')
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'provider_location'],
                name='providers_employeelocationrole_employee_location_uniq',
            ),
            # В одном филиале только один руководитель.
            models.UniqueConstraint(
                fields=['provider_location'],
                condition=models.Q(role='branch_manager'),
                name='providers_employeelocationrole_one_branch_manager_per_location',
            ),
        ]
        indexes = [
            models.Index(fields=['provider_location', 'role'], name='prov_emplocrole_loc_role_idx'),
        ]

    def __str__(self):
        return f"{self.employee} @ {self.provider_location}: {self.get_role_display()}"

    def is_active_record(self) -> bool:
        if not self.is_active:
            return False
        if self.end_date is None:
            return True
        return self.end_date >= timezone.now()

    @classmethod
    def sync_location_manager(cls, location):
        active_manager = (
            cls.objects.filter(
                provider_location=location,
                role=cls.ROLE_BRANCH_MANAGER,
                is_active=True,
            )
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=timezone.now()))
            .select_related('employee__user')
            .order_by('-id')
            .first()
        )
        manager_user = active_manager.employee.user if active_manager else None
        if location.manager_id != getattr(manager_user, 'id', None):
            ProviderLocation.objects.filter(pk=location.pk).update(manager=manager_user)
            location.manager = manager_user

    def save(self, *args, **kwargs):
        previous_location_id = None
        if self.pk:
            previous_location_id = (
                type(self).objects.filter(pk=self.pk).values_list('provider_location_id', flat=True).first()
            )
        super().save(*args, **kwargs)
        self.sync_location_manager(self.provider_location)
        if previous_location_id and previous_location_id != self.provider_location_id:
            old_location = ProviderLocation.objects.filter(pk=previous_location_id).first()
            if old_location is not None:
                self.sync_location_manager(old_location)

    def delete(self, *args, **kwargs):
        location = self.provider_location
        super().delete(*args, **kwargs)
        self.sync_location_manager(location)


class EmployeeProvider(models.Model):
    """
    Связь сотрудника (Employee) с провайдером и роль в организации.
    Единственный источник правды по ролям в провайдере (вместо ProviderAdmin).
    """
    ROLE_OWNER = 'owner'
    ROLE_PROVIDER_MANAGER = 'provider_manager'
    ROLE_PROVIDER_ADMIN = 'provider_admin'
    ROLE_WORKER = 'worker'
    ROLE_SERVICE_WORKER = ROLE_WORKER
    ROLE_TECHNICAL_WORKER = ROLE_WORKER
    ROLE_CHOICES = [
        (ROLE_OWNER, _('Owner')),
        (ROLE_PROVIDER_MANAGER, _('Provider manager')),
        (ROLE_PROVIDER_ADMIN, _('Provider admin')),
        (ROLE_WORKER, _('Worker')),
    ]
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        verbose_name=_('Employee'),
        related_name='employeeprovider_set'
    )
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        verbose_name=_('Provider'),
        related_name='employeeprovider_set'
    )
    role = models.CharField(
        _('Role'),
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_WORKER,
        help_text=_('Primary role at this provider. Effective permissions are calculated from flags and location roles.'),
    )
    start_date = models.DateField(
        _('Start Date'),
        help_text=_('Date when employee started working at this provider')
    )
    end_date = models.DateField(
        _('End Date'),
        null=True,
        blank=True,
        help_text=_('Date when employee stopped working at this provider')
    )
    is_manager = models.BooleanField(
        _('Is Manager'),
        default=False,
        help_text=_('Whether this employee is a manager at this provider (aligns with is_provider_manager)')
    )
    is_owner = models.BooleanField(
        _('Is Owner'),
        default=False,
        help_text=_('Owner of the organization')
    )
    is_provider_manager = models.BooleanField(
        _('Is Provider Manager'),
        default=False,
        help_text=_('Provider manager (organization manager)')
    )
    is_provider_admin = models.BooleanField(
        _('Is Provider Admin'),
        default=False,
        help_text=_('Provider admin (organization admin)')
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
        verbose_name = _('Employee Provider')
        verbose_name_plural = _('Employee Providers')
        unique_together = [['employee', 'provider', 'start_date']]
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['start_date']),
            models.Index(fields=['end_date']),
            models.Index(fields=['provider', 'is_owner']),
            models.Index(fields=['provider', 'is_provider_manager']),
            models.Index(fields=['provider', 'is_provider_admin']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление связи.
        
        Returns:
            str: Строковое представление связи
        """
        return f"{self.employee} - {self.provider} ({self.start_date})"

    def get_primary_role_code(self):
        if self.is_owner:
            return self.ROLE_OWNER
        if self.is_provider_admin:
            return self.ROLE_PROVIDER_ADMIN
        if self.is_provider_manager:
            return self.ROLE_PROVIDER_MANAGER
        return self.role or self.ROLE_WORKER

    def get_effective_role_codes(self):
        roles = set()
        if self.is_owner:
            roles.add(self.ROLE_OWNER)
        if self.is_provider_admin:
            roles.add(self.ROLE_PROVIDER_ADMIN)
        if self.is_provider_manager:
            roles.add(self.ROLE_PROVIDER_MANAGER)
        if self.role:
            roles.add(self.role)
        if not roles:
            roles.add(self.ROLE_WORKER)
        return roles

    def sync_primary_role_from_flags(self):
        self.is_manager = bool(self.is_provider_manager)
        self.role = self.get_primary_role_code()

    def is_currently_employed(self):
        """
        Проверяет, работает ли сотрудник в учреждении в настоящее время.
        
        Returns:
            bool: True, если сотрудник работает в учреждении
        """
        return self.end_date is None or self.end_date >= timezone.localdate()

    @classmethod
    def get_active_admin_links(cls, provider):
        """
        Активные связи «админ провайдера» (owner / provider_manager / provider_admin) для провайдера.
        Используется для уведомлений и поиска контактов админа.
        """
        from django.db.models import Q
        from django.utils import timezone
        today = timezone.now().date()
        q = Q(end_date__isnull=True) | Q(end_date__gte=today)
        role_q = Q(is_owner=True) | Q(is_provider_manager=True) | Q(is_provider_admin=True)
        return cls.objects.filter(provider=provider).filter(role_q).filter(q).select_related('employee', 'employee__user')

    def can_work(self):
        """
        Проверяет, может ли сотрудник работать в учреждении.
        """
        return self.is_currently_employed()

    def can_conduct_visits(self):
        """
        Может ли сотрудник проводить приёмы и вносить записи в карточку питомца.
        """
        return True

    @classmethod
    def get_active_ep_for_user_provider(cls, user, provider):
        """
        Возвращает активную связь EmployeeProvider (user → provider), если есть.
        """
        from django.utils import timezone
        from django.db.models import Q
        today = timezone.now().date()
        return cls.objects.filter(
            employee__user=user,
            provider=provider,
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today)).select_related('employee').first()

    def save(self, *args, **kwargs):
        self.sync_primary_role_from_flags()
        super().save(*args, **kwargs)


class Schedule(models.Model):
    """
    Employee schedule model.
    
    Основные характеристики:
    - Связь с сотрудником и локацией
    - День недели
    - Время начала и окончания работы
    - Перерыв
    
    Технические особенности:
    - Уникальная связь по сотруднику, локации и дню недели
    - Валидация времени работы
    - Управление статусом рабочего дня
    
    Примечание:
    Расписание используется для определения доступности
    специалиста в конкретной локации в конкретные дни недели.
    Сотрудник может иметь разное расписание в разных локациях.
    """
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        verbose_name=_('Employee'),
        related_name='schedules',
        help_text=_('Employee this schedule belongs to')
    )
    provider_location = models.ForeignKey(
        'ProviderLocation',
        on_delete=models.CASCADE,
        verbose_name=_('Provider Location'),
        related_name='schedules',
        help_text=_('Location where this schedule applies')
    )
    day_of_week = models.PositiveSmallIntegerField(
        _('Day Of Week'),
        choices=[
            (0, _('Monday')),
            (1, _('Tuesday')),
            (2, _('Wednesday')),
            (3, _('Thursday')),
            (4, _('Friday')),
            (5, _('Saturday')),
            (6, _('Sunday')),
        ],
        help_text=_('Day of the week')
    )
    start_time = models.TimeField(
        _('Start Time'),
        null=True,
        blank=True,
        help_text=_('Start time of the working day')
    )
    end_time = models.TimeField(
        _('End Time'),
        null=True,
        blank=True,
        help_text=_('End time of the working day')
    )
    break_start = models.TimeField(
        _('Break Start'),
        null=True,
        blank=True,
        help_text=_('Start time of the break')
    )
    break_end = models.TimeField(
        _('Break End'),
        null=True,
        blank=True,
        help_text=_('End time of the break')
    )
    is_working = models.BooleanField(
        _('Is Working'),
        default=True,
        help_text=_('Whether the employee works on this day')
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
        verbose_name = _('Schedule')
        verbose_name_plural = _('Schedules')
        ordering = ['employee', 'provider_location', 'day_of_week']
        unique_together = ['employee', 'provider_location', 'day_of_week']
        indexes = [
            models.Index(fields=['employee', 'provider_location']),
            models.Index(fields=['day_of_week']),
            models.Index(fields=['is_working']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление расписания.
        
        Returns:
            str: Строковое представление расписания
        """
        day_names = {
            0: _('Monday'),
            1: _('Tuesday'),
            2: _('Wednesday'),
            3: _('Thursday'),
            4: _('Friday'),
            5: _('Saturday'),
            6: _('Sunday'),
        }
        day_name = day_names.get(self.day_of_week, '')
        return f"{self.employee} - {self.provider_location.name} - {day_name}"

    def clean(self):
        """
        Проверяет корректность времени работы.
        
        Raises:
            ValidationError: Если время работы некорректно
        """
        # Нерабочий день — валидация времени не нужна
        if not self.is_working:
            return

        # Рабочий день — start_time и end_time обязательны
        if not self.start_time or not self.end_time:
            raise ValidationError(_("Start time and end time are required for working days"))

        if self.start_time >= self.end_time:
            raise ValidationError(_("Start time must be before end time"))
        
        if self.break_start and self.break_end:
            if self.break_start >= self.break_end:
                raise ValidationError(_("Break start time must be before break end time"))
            if not (self.start_time <= self.break_start < self.break_end <= self.end_time):
                raise ValidationError(_("Break must be within working hours"))
        
        # Проверяем, что расписание сотрудника не выходит за рамки рабочего времени локации
        try:
            location_schedule = LocationSchedule.objects.get(
                provider_location=self.provider_location,
                weekday=self.day_of_week
            )
            
            if not location_schedule.is_closed:
                if location_schedule.open_time and self.start_time < location_schedule.open_time:
                    raise ValidationError(
                        _("Employee start time cannot be earlier than location opening time")
                    )
                if location_schedule.close_time and self.end_time > location_schedule.close_time:
                    raise ValidationError(
                        _("Employee end time cannot be later than location closing time")
                    )
        except LocationSchedule.DoesNotExist:
            # Если расписание локации не настроено, пропускаем проверку
            pass

    def save(self, *args, **kwargs):
        """
        Сохраняет модель и проверяет корректность.
        
        Примечание:
        Перед сохранением выполняется проверка корректности времени работы.
        """
        self.clean()
        super().save(*args, **kwargs)


class ProviderService(models.Model):
    """
    Provider-Service relationship model.
    
    ⚠️ DEPRECATED: Эта модель устарела и будет удалена в будущих версиях.
    Используйте ProviderLocationService вместо ProviderService.
    
    Основные характеристики:
    - Связь с учреждением и услугой
    - Цена услуги в учреждении
    - Статус активности
    
    Технические особенности:
    - Уникальная связь по учреждению и услуге
    - Автоматическое отслеживание времени создания и обновления
    - Управление статусом активности
    
    Примечание:
    Эта модель используется для управления ценами на услуги
    в конкретных учреждениях. В новой архитектуре услуги управляются
    на уровне локаций (ProviderLocationService), а не организаций.
    
    Миграция:
    - Все существующие ProviderService должны быть мигрированы в ProviderLocationService
    - После миграции эта модель будет удалена
    """
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        verbose_name=_('Provider'),
        related_name='provider_services',
        help_text=_('Provider offering this service')
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        verbose_name=_('Service'),
        related_name='provider_services',
        help_text=_('Service being offered')
    )
    price = models.DecimalField(
        _('Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Price of the service at this provider')
    )
    duration_minutes = models.PositiveIntegerField(
        _('Duration In Minutes'),
        help_text=_('Duration of the service in minutes for this provider')
    )
    tech_break_minutes = models.PositiveIntegerField(
        _('Technical Break Minutes'),
        default=0,
        help_text=_('Technical break time in minutes after the service (for cleaning, preparation, etc.)')
    )
    base_price = models.DecimalField(
        _('Base Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Base price for the service at this provider')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this service is currently available')
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
        verbose_name = _('Provider Service')
        verbose_name_plural = _('Provider Services')
        ordering = ['provider', 'service']
        unique_together = ['provider', 'service']
        indexes = [
            models.Index(fields=['provider', 'service']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление связи.
        
        Returns:
            str: Строковое представление связи
        """
        return f"{self.provider} - {self.service}"


class LocationSchedule(models.Model):
    """
    Location schedule model.
    
    Расписание работы локации (точки предоставления услуг).
    
    Основные характеристики:
    - Связь с локацией
    - День недели
    - Время открытия и закрытия
    - Статус выходного дня
    
    Технические особенности:
    - Уникальная связь по локации и дню недели
    - Управление статусом выходного дня
    - Автоматическое отслеживание времени создания и обновления
    
    Примечание:
    Расписание используется для определения часов работы
    локации в конкретные дни недели. Расписание сотрудников
    должно соответствовать расписанию локации.
    """
    provider_location = models.ForeignKey(
        'ProviderLocation',
        on_delete=models.CASCADE,
        related_name='location_schedules',
        verbose_name=_('Provider Location'),
        help_text=_('Location this schedule belongs to')
    )
    weekday = models.IntegerField(
        choices=[
            (0, _('Monday')),
            (1, _('Tuesday')),
            (2, _('Wednesday')),
            (3, _('Thursday')),
            (4, _('Friday')),
            (5, _('Saturday')),
            (6, _('Sunday'))
        ],
        verbose_name=_('Day Of Week')
    )
    open_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name=_('Open Time')
    )
    close_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name=_('Close Time')
    )
    is_closed = models.BooleanField(
        _('Is Closed'),
        default=False,
        help_text=_('Whether the location is closed on this day')
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
        unique_together = ('provider_location', 'weekday')
        verbose_name = _('Location Schedule')
        verbose_name_plural = _('Location Schedules')
        indexes = [
            models.Index(fields=['weekday']),
            models.Index(fields=['is_closed']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление расписания.
        
        Returns:
            str: Строковое представление расписания
        """
        return f"{self.provider_location} - {self.get_weekday_display()}"


class HolidayShift(models.Model):
    """
    Смена в праздничный день: явное решение работать в дату, объявленную праздником в глобальном календаре.
    Для обычных дней используется стандартное LocationSchedule по дню недели.
    """
    provider_location = models.ForeignKey(
        'ProviderLocation',
        on_delete=models.CASCADE,
        related_name='holiday_shifts',
        verbose_name=_('Provider Location'),
    )
    date = models.DateField(_('Date'), db_index=True)
    start_time = models.TimeField(_('Start time'))
    end_time = models.TimeField(_('End time'))

    class Meta:
        verbose_name = _('Holiday shift')
        verbose_name_plural = _('Holiday shifts')
        constraints = [
            models.UniqueConstraint(
                fields=['provider_location', 'date'],
                name='providers_holidayshift_location_date_uniq',
            ),
        ]
        ordering = ['date', 'provider_location']

    def __str__(self):
        return f"{self.provider_location} — {self.date} {self.start_time}-{self.end_time}"

    def clean(self):
        from production_calendar.models import ProductionCalendar, DAY_TYPE_HOLIDAY
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError(
                _('Start time must be earlier than end time.')
            )
        if not self.provider_location_id or not self.date:
            return
        country = _get_location_country_code(self.provider_location)
        if not country:
            raise ValidationError(
                _('Location must have a country (2-letter code) in its address to use holiday shifts.')
            )
        cal = ProductionCalendar.objects.filter(
            date=self.date,
            country=country,
        ).first()
        if not cal or cal.day_type != DAY_TYPE_HOLIDAY:
            raise ValidationError(
                _('You can only set Holiday Shifts for dates marked as Holidays in the Global Calendar. '
                  'For regular days, use the standard Weekly Schedule.')
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


def _get_location_country_code(location):
    """Возвращает ISO 3166-1 alpha-2 код страны локации из адреса или None."""
    if not location or not getattr(location, 'structured_address', None):
        return None
    addr = location.structured_address
    c = (getattr(addr, 'country', None) or '').strip().upper()
    if len(c) == 2:
        return c
    name_to_code = {
        'RUSSIA': 'RU', 'RUSSIAN FEDERATION': 'RU',
        'GERMANY': 'DE', 'DEUTSCHLAND': 'DE',
        'UNITED STATES': 'US', 'UNITED STATES OF AMERICA': 'US', 'USA': 'US',
        'FRANCE': 'FR', 'UNITED KINGDOM': 'GB', 'UK': 'GB', 'GREAT BRITAIN': 'GB',
        'AUSTRIA': 'AT', 'SWITZERLAND': 'CH', 'BELARUS': 'BY', 'UKRAINE': 'UA',
        'KAZAKHSTAN': 'KZ', 'SERBIA': 'RS', 'MONTENEGRO': 'ME',
    }
    return name_to_code.get(c)


class EmployeeWorkSlot(models.Model):
    """
    Employee work slot model.
    
    Основные характеристики:
    - Связь с сотрудником
    - Дата и время работы
    - Тип слота
    - Комментарий
    
    Технические особенности:
    - Различные типы слотов (работа, отпуск, больничный и т.д.)
    - Валидация времени работы
    - Управление доступностью
    
    Примечание:
    Эта модель используется для управления конкретными рабочими
    интервалами сотрудника в определенные даты.
    """
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='work_slots'
    )
    date = models.DateField(
        verbose_name=_('Date')
    )
    start_time = models.TimeField(
        verbose_name=_('Start Time')
    )
    end_time = models.TimeField(
        verbose_name=_('End Time')
    )
    slot_type = models.CharField(
        max_length=20,
        choices=[
            ('work', _('Work')),
            ('vacation', _('Vacation')),
            ('sick', _('Sick Leave')),
            ('dayoff', _('Day Off')),
            ('substitution', _('Substitution')),
        ],
        default='work',
        verbose_name=_('Slot Type')
    )
    comment = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Comment')
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
        verbose_name = _('Employee Work Slot')
        verbose_name_plural = _('Employee Work Slots')
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['slot_type']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление слота.
        
        Returns:
            str: Строковое представление слота
        """
        return f"{self.employee} - {self.date} ({self.slot_type})"

    def clean(self):
        """
        Проверяет корректность времени работы.
        
        Raises:
            ValidationError: Если время работы некорректно
        """
        if self.start_time >= self.end_time:
            raise ValidationError(_("Start time must be before end time"))

    def save(self, *args, **kwargs):
        """
        Сохраняет модель и проверяет корректность.
        
        Примечание:
        Перед сохранением выполняется проверка корректности времени работы.
        """
        self.clean()
        super().save(*args, **kwargs)

    def is_available(self, start_time, end_time):
        """
        Проверяет, доступен ли слот в указанное время.
        
        Параметры:
            start_time (time): Время начала
            end_time (time): Время окончания
            
        Returns:
            bool: True, если слот доступен
        """
        if self.slot_type != 'work':
            return False
        
        return (
            self.start_time <= start_time and
            self.end_time >= end_time
        )


class SchedulePattern(models.Model):
    """
    Schedule pattern model.
    
    Основные характеристики:
    - Название и описание шаблона
    - Связь с локацией (ProviderLocation)
    - Дни недели в шаблоне
    
    Технические особенности:
    - Управление типовыми расписаниями для конкретных локаций
    - Автоматическое отслеживание времени создания и обновления
    - Связь с днями недели через ForeignKey
    
    Примечание:
    Шаблоны используются для быстрого создания типовых
    расписаний для сотрудников в конкретных локациях.
    """
    name = models.CharField(
        max_length=100,
        verbose_name=_('Name')
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
    provider_location = models.ForeignKey(
        'ProviderLocation',
        on_delete=models.CASCADE,
        related_name='schedule_patterns',
        verbose_name=_('Provider Location'),
        help_text=_('Location this schedule pattern belongs to')
    )
    description = models.TextField(
        blank=True,
        verbose_name=_('Description')
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
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Schedule Pattern')
        verbose_name_plural = _('Schedule Patterns')
        ordering = ['provider_location', 'name']
        indexes = [
            models.Index(fields=['provider_location', 'name']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление шаблона.
        
        Returns:
            str: Строковое представление шаблона
        """
        return f"{self.get_localized_name()} ({self.provider_location})"
    
    def get_localized_name(self, language_code=None):
        """
        Получает локализованное название шаблона расписания.
        
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
        Получает локализованное описание шаблона расписания.
        
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


class PatternDay(models.Model):
    """
    Pattern day model.
    
    Основные характеристики:
    - Связь с шаблоном
    - День недели
    - Время начала и окончания работы
    - Статус выходного дня
    
    Технические особенности:
    - Уникальная связь по шаблону и дню недели
    - Управление статусом выходного дня
    - Автоматическое отслеживание времени создания и обновления
    
    Примечание:
    Эта модель используется для определения рабочих часов
    в конкретные дни недели в рамках шаблона.
    """
    pattern = models.ForeignKey(
        SchedulePattern,
        on_delete=models.CASCADE,
        related_name='days'
    )
    weekday = models.IntegerField(
        choices=[
            (0, _('Monday')),
            (1, _('Tuesday')),
            (2, _('Wednesday')),
            (3, _('Thursday')),
            (4, _('Friday')),
            (5, _('Saturday')),
            (6, _('Sunday'))
        ],
        verbose_name=_('Day Of Week')
    )
    start_time = models.TimeField(
        null=True,
        blank=True
    )
    end_time = models.TimeField(
        null=True,
        blank=True
    )
    is_day_off = models.BooleanField(
        _('Is Day Off'),
        default=False,
        help_text=_('Whether this is a day off')
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
        verbose_name = _('Pattern Day')
        verbose_name_plural = _('Pattern Days')
        unique_together = ('pattern', 'weekday')
        ordering = ['pattern', 'weekday']
        indexes = [
            models.Index(fields=['weekday']),
            models.Index(fields=['is_day_off']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление дня.
        
        Returns:
            str: Строковое представление дня
        """
        return f"{self.pattern} - {self.get_weekday_display()}"


class ProviderLocationService(models.Model):
    """
    Цена и длительность услуги в локации для одной комбинации (тип животного, размер).

    Одна запись = локация + услуга + тип животного + размер (S/M/L/XL) с ценой и длительностью.
    Уникальность: (location, service, pet_type, size_code).
    """
    SIZE_CHOICES = [('S', 'S'), ('M', 'M'), ('L', 'L'), ('XL', 'XL')]

    location = models.ForeignKey(
        'ProviderLocation',
        on_delete=models.CASCADE,
        verbose_name=_('Location'),
        related_name='location_services',
        help_text=_('Location offering this service')
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        verbose_name=_('Service'),
        related_name='location_services',
        help_text=_('Service being offered at this location')
    )
    pet_type = models.ForeignKey(
        'pets.PetType',
        on_delete=models.CASCADE,
        verbose_name=_('Pet Type'),
        related_name='location_services',
        help_text=_('Pet type (dog, cat, etc.) for this price row')
    )
    size_code = models.CharField(
        _('Size Code'),
        max_length=10,
        choices=SIZE_CHOICES,
        help_text=_('Size category: S, M, L, XL (must match SizeRule)')
    )
    price = models.DecimalField(
        _('Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Price of the service at this location for this pet type and size')
    )
    duration_minutes = models.PositiveIntegerField(
        _('Duration In Minutes'),
        help_text=_('Duration of the service in minutes for this location')
    )
    tech_break_minutes = models.PositiveIntegerField(
        _('Technical Break Minutes'),
        default=0,
        help_text=_('Technical break time in minutes after the service (for cleaning, preparation, etc.)')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this service is currently available at this location')
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
        verbose_name = _('Provider Location Service')
        verbose_name_plural = _('Provider Location Services')
        ordering = ['location', 'service', 'pet_type', 'size_code']
        unique_together = [['location', 'service', 'pet_type', 'size_code']]
        indexes = [
            models.Index(fields=['location', 'service']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.location} - {self.service} ({self.pet_type.code}/{self.size_code})"


class ProviderServicePricing(models.Model):
    """
    Организационная матрица цен по услугам.

    Используется, когда у провайдера включён режим единых цен.
    Одна запись = организация + услуга + тип животного + размер.
    """

    SIZE_CHOICES = ProviderLocationService.SIZE_CHOICES

    provider = models.ForeignKey(
        'Provider',
        on_delete=models.CASCADE,
        related_name='service_pricing_rows',
        verbose_name=_('Provider'),
        help_text=_('Organization that owns the unified service price row.'),
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='provider_pricing_rows',
        verbose_name=_('Service'),
        help_text=_('Service covered by the unified organization-level price.'),
    )
    pet_type = models.ForeignKey(
        'pets.PetType',
        on_delete=models.CASCADE,
        related_name='provider_pricing_rows',
        verbose_name=_('Pet Type'),
        help_text=_('Pet type covered by the organization-level price row.'),
    )
    size_code = models.CharField(
        _('Size Code'),
        max_length=10,
        choices=SIZE_CHOICES,
        help_text=_('Size category: S, M, L, XL (must match SizeRule).'),
    )
    price = models.DecimalField(
        _('Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Organization-level price for this service, pet type, and size.'),
    )
    duration_minutes = models.PositiveIntegerField(
        _('Duration In Minutes'),
        help_text=_('Organization-level duration in minutes for this service row.'),
    )
    tech_break_minutes = models.PositiveIntegerField(
        _('Technical Break Minutes'),
        default=0,
        help_text=_('Technical break time in minutes after the service.'),
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this organization-level pricing row is active.'),
    )
    version = models.PositiveIntegerField(
        _('Version'),
        default=1,
        help_text=_('Optimistic locking version for the organization pricing row.'),
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True,
    )

    class Meta:
        verbose_name = _('Provider Service Pricing')
        verbose_name_plural = _('Provider Service Pricing')
        ordering = ['provider', 'service', 'pet_type', 'size_code']
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'service', 'pet_type', 'size_code'],
                name='providers_providerpricing_provider_service_pet_type_size_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['provider', 'service'], name='prov_prc_prov_svc_idx'),
            models.Index(fields=['is_active'], name='prov_prc_active_idx'),
        ]

    def __str__(self):
        """
        Возвращает человекочитаемое представление строки org-level прайса.
        """
        return f'{self.provider} - {self.service} ({self.pet_type.code}/{self.size_code})'


class ProviderLocation(models.Model):
    """
    Локация (филиал организации по предоставлению услуг).
    
    Каждая организация (Provider) может иметь множество локаций.
    Локация - это физическое место, где предоставляются услуги.
    
    Основные характеристики:
    - Связь с организацией
    - Адрес и координаты локации
    - Контактная информация (email, телефон - НЕ уникальные)
    - Набор услуг, доступных в локации
    - Статус активности
    
    Технические особенности:
    - Адрес хранится в структурированном виде через Address
    - Услуги связаны через промежуточную модель ProviderLocationService
    - Автоматическое отслеживание времени создания и обновления
    """
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='locations',
        verbose_name=_('Provider Organization'),
        help_text=_('Organization this location belongs to')
    )
    
    # Название локации (например, "Филиал на Тимирязевской")
    name = models.CharField(
        _('Location Name'),
        max_length=200,
        help_text=_('Name of this location (e.g., "Branch on Timiryazevskaya")')
    )
    
    # Адрес и координаты (обязательно для точки предоставления услуг)
    structured_address = models.ForeignKey(
        'geolocation.Address',
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        related_name='provider_locations',
        verbose_name=_('Structured Address'),
        help_text=_('Structured address with validation and coordinates (required for service location)')
    )
    
    # Контактная информация локации (НЕ уникальные)
    phone_number = models.CharField(
        _('Phone Number'),
        max_length=20,
        help_text=_('Contact phone number for this location (not unique)')
    )
    email = models.EmailField(
        _('Email'),
        help_text=_('Contact email for this location (not unique)')
    )
    
    # Типы животных, которых обслуживает филиал (обязательно для открытия вкладки «Услуги и цены»)
    served_pet_types = models.ManyToManyField(
        'pets.PetType',
        related_name='provider_locations_served',
        verbose_name=_('Served pet types'),
        help_text=_('Pet types (e.g. dog, cat) that this location serves. Required before adding services and prices.'),
        blank=True,
    )

    # Услуги, доступные в этой локации
    # ВАЖНО: Услуги должны быть из категорий уровня 0 организации (provider.available_category_levels)
    # Локация может выбирать конкретные услуги из этих категорий
    available_services = models.ManyToManyField(
        Service,
        through='ProviderLocationService',
        related_name='locations',
        verbose_name=_('Available Services'),
        help_text=_('Services available at this location. Must be from provider\'s level 0 categories.')
    )

    # Статус активности
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this location is currently active')
    )

    LIFECYCLE_STATUS_ACTIVE = 'active'
    LIFECYCLE_STATUS_TEMPORARILY_CLOSED = 'temporarily_closed'
    LIFECYCLE_STATUS_DEACTIVATED = 'deactivated'
    LIFECYCLE_STATUS_CHOICES = [
        (LIFECYCLE_STATUS_ACTIVE, _('Active')),
        (LIFECYCLE_STATUS_TEMPORARILY_CLOSED, _('Temporarily Closed')),
        (LIFECYCLE_STATUS_DEACTIVATED, _('Deactivated')),
    ]

    lifecycle_status = models.CharField(
        _('Lifecycle Status'),
        max_length=30,
        choices=LIFECYCLE_STATUS_CHOICES,
        default=LIFECYCLE_STATUS_ACTIVE,
        db_index=True,
        help_text=_('Operational lifecycle status of the location.'),
    )
    lifecycle_effective_date = models.DateField(
        _('Lifecycle Effective Date'),
        null=True,
        blank=True,
        help_text=_('Date when the current lifecycle status became effective.'),
    )
    lifecycle_resume_date = models.DateField(
        _('Lifecycle Resume Date'),
        null=True,
        blank=True,
        help_text=_('Planned date when the location is expected to return to active status.'),
    )
    lifecycle_reason = models.TextField(
        _('Lifecycle Reason'),
        blank=True,
        help_text=_('Reason for the current lifecycle status.'),
    )
    lifecycle_status_changed_at = models.DateTimeField(
        _('Lifecycle Status Changed At'),
        null=True,
        blank=True,
        help_text=_('When the current lifecycle status was last changed.'),
    )
    lifecycle_status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='provider_location_lifecycle_status_changes',
        verbose_name=_('Lifecycle Status Changed By'),
        help_text=_('User who last changed the lifecycle status.'),
    )
    pending_lifecycle_status = models.CharField(
        _('Pending Lifecycle Status'),
        max_length=30,
        blank=True,
        default='',
        help_text=_('Scheduled lifecycle status to apply in the future.'),
    )
    pending_lifecycle_effective_date = models.DateField(
        _('Pending Lifecycle Effective Date'),
        null=True,
        blank=True,
        help_text=_('Date when the pending lifecycle status should be applied.'),
    )
    pending_lifecycle_resume_date = models.DateField(
        _('Pending Lifecycle Resume Date'),
        null=True,
        blank=True,
        help_text=_('Planned resume date stored for the pending lifecycle change.'),
    )
    pending_lifecycle_reason = models.TextField(
        _('Pending Lifecycle Reason'),
        blank=True,
        help_text=_('Reason stored for the pending lifecycle change.'),
    )
    pending_lifecycle_requested_at = models.DateTimeField(
        _('Pending Lifecycle Requested At'),
        null=True,
        blank=True,
        help_text=_('When the pending lifecycle change was scheduled.'),
    )
    pending_lifecycle_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='provider_location_pending_lifecycle_requests',
        verbose_name=_('Pending Lifecycle Requested By'),
        help_text=_('User who scheduled the pending lifecycle change.'),
    )

    # Руководитель филиала (назначается после принятия инвайта по email)
    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_provider_locations',
        verbose_name=_('Location manager'),
        help_text=_('User who accepted the manager invite for this location (for support/escalation only)')
    )
    
    # Временные метки
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Provider Location')
        verbose_name_plural = _('Provider Locations')
        ordering = ['provider', 'name']
        indexes = [
            models.Index(fields=['provider', 'is_active']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление локации.
        
        Returns:
            str: Название локации
        """
        return f"{self.name} ({self.provider.name})"
    
    def get_full_address(self):
        """
        Возвращает полный адрес локации.
        
        Returns:
            str: Полный адрес или пустая строка
        """
        if self.structured_address:
            return self.structured_address.formatted_address or str(self.structured_address)
        return ''

    def clean(self):
        """
        Валидация формата телефона и email локации.
        Телефон и email могут совпадать с реквизитами организации (предзаполнение).
        """
        from .contact_validators import validate_phone_contact, validate_email_contact
        if self.phone_number:
            ok, err = validate_phone_contact(self.phone_number)
            if not ok:
                raise ValidationError({'phone_number': err or 'Invalid phone format'})
        if self.email:
            ok, err = validate_email_contact(self.email)
            if not ok:
                raise ValidationError({'email': err or 'Invalid email format'})
        if self.structured_address_id and self.pk:
            # При редактировании: при необходимости проверять open_time < close_time у LocationSchedule
            pass

        # Филиал операционно активен только в lifecycle_status=active.
        if self.lifecycle_status == self.LIFECYCLE_STATUS_ACTIVE:
            self.is_active = True
        else:
            self.is_active = False

    def save(self, *args, **kwargs):
        """Сохранение с полной валидацией (в т.ч. телефон и email)."""
        self.full_clean()
        super().save(*args, **kwargs)
    
    @property
    def point(self):
        """
        Возвращает координаты из структурированного адреса.
        
        Returns:
            Point: Географические координаты или None
        """
        if self.structured_address and self.structured_address.point:
            return self.structured_address.point
        return None


class ProviderLifecycleEvent(models.Model):
    """
    Audit trail lifecycle-операций организаций и филиалов.
    """

    ENTITY_PROVIDER = 'provider'
    ENTITY_LOCATION = 'location'
    ENTITY_CHOICES = [
        (ENTITY_PROVIDER, _('Provider')),
        (ENTITY_LOCATION, _('Location')),
    ]

    ACTION_PROVIDER_PAUSE = 'provider_pause'
    ACTION_PROVIDER_TERMINATE = 'provider_terminate'
    ACTION_PROVIDER_REACTIVATE = 'provider_reactivate'
    ACTION_LOCATION_TEMP_CLOSE = 'location_temporary_close'
    ACTION_LOCATION_DEACTIVATE = 'location_deactivate'
    ACTION_LOCATION_REACTIVATE = 'location_reactivate'
    ACTION_CHOICES = [
        (ACTION_PROVIDER_PAUSE, _('Provider Pause')),
        (ACTION_PROVIDER_TERMINATE, _('Provider Terminate')),
        (ACTION_PROVIDER_REACTIVATE, _('Provider Reactivate')),
        (ACTION_LOCATION_TEMP_CLOSE, _('Location Temporary Close')),
        (ACTION_LOCATION_DEACTIVATE, _('Location Deactivate')),
        (ACTION_LOCATION_REACTIVATE, _('Location Reactivate')),
    ]

    entity_type = models.CharField(
        _('Entity Type'),
        max_length=20,
        choices=ENTITY_CHOICES,
        help_text=_('Type of entity affected by the lifecycle action.'),
    )
    action = models.CharField(
        _('Action'),
        max_length=40,
        choices=ACTION_CHOICES,
        help_text=_('Lifecycle action that was executed or scheduled.'),
    )
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='lifecycle_events',
        verbose_name=_('Provider'),
        help_text=_('Provider affected by the lifecycle action.'),
    )
    location = models.ForeignKey(
        'ProviderLocation',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='lifecycle_events',
        verbose_name=_('Location'),
        help_text=_('Location affected by the lifecycle action when applicable.'),
    )
    previous_status = models.CharField(
        _('Previous Status'),
        max_length=40,
        blank=True,
        help_text=_('Previous lifecycle status before the action.'),
    )
    new_status = models.CharField(
        _('New Status'),
        max_length=40,
        blank=True,
        help_text=_('New lifecycle status after the action.'),
    )
    effective_date = models.DateField(
        _('Effective Date'),
        null=True,
        blank=True,
        help_text=_('Effective date of the lifecycle action.'),
    )
    resume_date = models.DateField(
        _('Resume Date'),
        null=True,
        blank=True,
        help_text=_('Planned resume date linked to the lifecycle action.'),
    )
    reason = models.TextField(
        _('Reason'),
        blank=True,
        help_text=_('Reason supplied for the lifecycle action.'),
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='provider_lifecycle_events',
        verbose_name=_('Initiated By'),
        help_text=_('User who initiated the lifecycle action.'),
    )
    is_staff_override = models.BooleanField(
        _('Is Staff Override'),
        default=False,
        help_text=_('Whether the action was initiated by platform staff override.'),
    )
    correlation_id = models.UUIDField(
        _('Correlation ID'),
        default=uuid.uuid4,
        db_index=True,
        help_text=_('Correlation identifier for grouped lifecycle operations.'),
    )
    metadata = models.JSONField(
        _('Metadata'),
        default=dict,
        blank=True,
        help_text=_('Additional audit metadata for lifecycle processing.'),
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Provider Lifecycle Event')
        verbose_name_plural = _('Provider Lifecycle Events')
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['entity_type', 'created_at']),
            models.Index(fields=['provider', 'created_at']),
            models.Index(fields=['correlation_id']),
        ]

    def __str__(self):
        target = self.location.name if self.location_id else self.provider.name
        return f'{self.action} - {target}'


def provider_report_export_upload_to(instance, filename):
    """
    Строит путь хранения файла экспорта отчетов.

    Args:
        instance: Экземпляр ProviderReportExportJob.
        filename: Исходное имя файла.

    Returns:
        str: Относительный путь внутри MEDIA_ROOT.
    """
    extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'
    return (
        f'provider_reports/{instance.provider_id}/'
        f'{instance.requested_by_id}/{instance.export_token}.{extension}'
    )


class ProviderReportExportJob(models.Model):
    """
    Асинхронная задача генерации выгрузки отчета для provider admin.

    Особенности:
    - Хранит snapshot параметров отчета
    - Поддерживает optimistic locking через version
    - Позволяет безопасно поллить статус и скачивать готовый файл
    """

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, _('Pending')),
        (STATUS_RUNNING, _('Running')),
        (STATUS_COMPLETED, _('Completed')),
        (STATUS_FAILED, _('Failed')),
    ]

    FORMAT_XLSX = 'xlsx'
    FORMAT_CHOICES = [
        (FORMAT_XLSX, _('XLSX')),
    ]

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='report_export_jobs',
        verbose_name=_('Provider'),
    )
    location = models.ForeignKey(
        'providers.ProviderLocation',
        on_delete=models.SET_NULL,
        related_name='report_export_jobs',
        verbose_name=_('Location'),
        null=True,
        blank=True,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='provider_report_export_jobs',
        verbose_name=_('Requested By'),
    )
    report_code = models.CharField(
        _('Report Code'),
        max_length=64,
    )
    scope = models.CharField(
        _('Scope'),
        max_length=20,
    )
    export_format = models.CharField(
        _('Export Format'),
        max_length=20,
        choices=FORMAT_CHOICES,
        default=FORMAT_XLSX,
    )
    language_code = models.CharField(
        _('Language Code'),
        max_length=16,
        default='en',
    )
    start_date = models.DateField(
        _('Start Date'),
        null=True,
        blank=True,
    )
    end_date = models.DateField(
        _('End Date'),
        null=True,
        blank=True,
    )
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    file = models.FileField(
        _('File'),
        upload_to=provider_report_export_upload_to,
        null=True,
        blank=True,
    )
    filename = models.CharField(
        _('Filename'),
        max_length=255,
        blank=True,
    )
    task_id = models.CharField(
        _('Task Id'),
        max_length=128,
        blank=True,
    )
    export_token = models.UUIDField(
        _('Export Token'),
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )
    error_message = models.TextField(
        _('Error Message'),
        blank=True,
    )
    version = models.PositiveIntegerField(
        _('Version'),
        default=1,
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True,
    )
    started_at = models.DateTimeField(
        _('Started At'),
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(
        _('Completed At'),
        null=True,
        blank=True,
    )
    downloaded_at = models.DateTimeField(
        _('Downloaded At'),
        null=True,
        blank=True,
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True,
    )

    class Meta:
        verbose_name = _('Provider Report Export Job')
        verbose_name_plural = _('Provider Report Export Jobs')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['requested_by', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        """
        Возвращает краткое представление async job.

        Returns:
            str: Человекочитаемая строка job.
        """
        return f'{self.provider_id}:{self.report_code}:{self.export_format}:{self.status}'
