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
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
from catalog.models import Service
import googlemaps
from geopy.distance import geodesic
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, MinLengthValidator
from users.models import User
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Point
from django_countries.fields import CountryField


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
    
    # Статус активности (автоматически устанавливается при activation_status=active)
    is_active = models.BooleanField(
        _('Is Active'),
        default=False,
        help_text=_('Whether the organization is currently active. Automatically set to True when activation_status is "active".')
    )
    
    # ОБЯЗАТЕЛЬНЫЕ для аппрува (заполняются биллинг-менеджерами)
    tax_id = models.CharField(
        _('Tax ID / INN'),
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Zа-яА-ЯёЁ0-9\s-]+$',
                message=_('Tax ID can only contain letters, digits, spaces, and hyphens.')
            ),
            MinLengthValidator(3, message=_('Tax ID must be at least 3 characters long.'))
        ],
        help_text=_('Tax identification number / INN (unique, required for approval). Format: letters, digits, spaces, hyphens. Minimum 3 characters.')
    )
    registration_number = models.CharField(
        _('Registration Number'),
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Zа-яА-ЯёЁ0-9\s-]+$',
                message=_('Registration number can only contain letters, digits, spaces, and hyphens.')
            ),
            MinLengthValidator(3, message=_('Registration number must be at least 3 characters long.'))
        ],
        help_text=_('Registration number (unique, required for approval). Format: letters, digits, spaces, hyphens. Minimum 3 characters.')
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
    vat_number = models.CharField(
        _('VAT Number (EU VAT ID)'),
        max_length=50,
        blank=True,
        help_text=_('VAT Number (EU VAT ID) - required for EU VAT payers. Format: PL12345678')
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
            models.Index(fields=['show_services', 'is_active']),
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
        
        super().save(*args, **kwargs)
    
    def clean(self):
        """
        Валидация модели перед сохранением.
        Проверяет наличие реквизитов перед активацией провайдера.
        Автоматически устанавливает is_active в зависимости от activation_status.
        """
        super().clean()
        
        # Автоматически устанавливаем is_active в зависимости от activation_status
        if self.activation_status == 'active':
            self.is_active = True
        elif self.activation_status in ['pending', 'activation_required', 'rejected', 'inactive']:
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
        Рассчитывает задолженность провайдера на основе неоплаченных Invoice.
        
        Returns:
            dict: Словарь с полями:
                - total_debt: Decimal - общая задолженность (сумма всех неоплаченных Invoice)
                - overdue_debt: Decimal - просроченная задолженность (Invoice со статусом 'overdue')
                - currency: Currency - валюта задолженности (из первого Invoice)
        """
        from billing.models import Invoice
        from decimal import Decimal
        
        # Получаем неоплаченные Invoice
        unpaid_invoices = Invoice.objects.filter(
            provider=self,
            status__in=['sent', 'overdue']
        )
        
        total_debt = Decimal('0.00')
        overdue_debt = Decimal('0.00')
        currency = None
        
        for invoice in unpaid_invoices:
            if currency is None:
                currency = invoice.currency
            
            total_debt += invoice.amount
            
            if invoice.status == 'overdue':
                overdue_debt += invoice.amount
        
        return {
            'total_debt': total_debt,
            'overdue_debt': overdue_debt,
            'currency': currency
        }
    
    def get_max_overdue_days(self):
        """
        Получает максимальное количество дней просрочки среди всех Invoice провайдера.
        
        Returns:
            int: Максимальное количество дней просрочки, или 0 если нет просроченных Invoice
        """
        from billing.models import Invoice
        from django.utils import timezone
        
        overdue_invoices = Invoice.objects.filter(
            provider=self,
            status='overdue'
        )
        
        max_overdue_days = 0
        today = timezone.now().date()
        
        for invoice in overdue_invoices:
            # Предполагаем, что у Invoice есть поле due_date или payment_deadline
            # Если нет, используем end_date + payment_deferral_days
            if hasattr(invoice, 'due_date') and invoice.due_date:
                due_date = invoice.due_date
            elif invoice.end_date:
                # Получаем payment_deferral_days из оферты или специальных условий
                payment_deferral_days = self._get_payment_deferral_days()
                due_date = invoice.end_date + timezone.timedelta(days=payment_deferral_days)
            else:
                continue
            
            if due_date < today:
                overdue_days = (today - due_date).days
                max_overdue_days = max(max_overdue_days, overdue_days)
        
        return max_overdue_days
    
    def _get_payment_deferral_days(self):
        """
        Получает количество дней отсрочки платежа для провайдера.
        
        Сначала проверяет ProviderSpecialTerms, затем LegalDocument/BillingConfig.
        
        Returns:
            int: Количество дней отсрочки платежа
        """
        from legal.models import LegalDocument, DocumentAcceptance
        
        # Проверяем специальные условия из LegalDocument (side_letter)
        side_letter = self.legal_documents.filter(
            document_type__code='side_letter',
            is_active=True
        ).first()
        if side_letter and side_letter.payment_deferral_days:
            return side_letter.payment_deferral_days
        
        # Получаем активный акцепт оферты
        active_acceptance = self.document_acceptances.filter(
            document__document_type__code='global_offer',
            is_active=True
        ).first()
        if active_acceptance:
            # НОВЫЙ ПОДХОД: Используем LegalDocument
            if active_acceptance.document and active_acceptance.document.billing_config:
                return active_acceptance.document.billing_config.payment_deferral_days
            # УДАЛЕНО: обратная совместимость с PublicOffer
        
        # Если нет активной оферты, используем значение по умолчанию
        return 5  # 5 дней по умолчанию
    
    def get_blocking_thresholds(self):
        """
        Получает пороги блокировки для провайдера.
        
        Сначала проверяет ProviderSpecialTerms, затем LegalDocument/BillingConfig.
        
        Returns:
            dict: Словарь с полями:
                - debt_threshold: Decimal или None
                - overdue_threshold_1: int или None
                - overdue_threshold_2: int или None
                - overdue_threshold_3: int или None
        """
        from legal.models import LegalDocument
        from django.conf import settings
        
        # Проверяем специальные условия из LegalDocument (side_letter)
        side_letter = self.legal_documents.filter(
            document_type__code='side_letter',
            is_active=True
        ).first()
        if side_letter:
            return {
                'debt_threshold': side_letter.debt_threshold,
                'overdue_threshold_1': side_letter.overdue_threshold_1,
                'overdue_threshold_2': side_letter.overdue_threshold_2,
                'overdue_threshold_3': side_letter.overdue_threshold_3,
            }
        
        # Получаем активный акцепт оферты
        active_acceptance = self.document_acceptances.filter(
            document__document_type__code='global_offer',
            is_active=True
        ).first()
        if active_acceptance and active_acceptance.document:
            # Пороги блокировки могут быть в оферте или в глобальных настройках
            # Пока используем глобальные настройки
            blocking_settings = getattr(settings, 'BLOCKING_SETTINGS', {})
            return {
                'debt_threshold': blocking_settings.get('DEFAULT_DEBT_THRESHOLD', 1000.00),
                'overdue_threshold_1': blocking_settings.get('DEFAULT_OVERDUE_THRESHOLD_1', 7),
                'overdue_threshold_2': blocking_settings.get('DEFAULT_OVERDUE_THRESHOLD_2', 14),
                'overdue_threshold_3': blocking_settings.get('DEFAULT_OVERDUE_THRESHOLD_3', 30),
            }
        
        # Если нет активной оферты, используем глобальные настройки
        blocking_settings = getattr(settings, 'BLOCKING_SETTINGS', {})
        return {
            'debt_threshold': blocking_settings.get('DEFAULT_DEBT_THRESHOLD', 1000.00),
            'overdue_threshold_1': blocking_settings.get('DEFAULT_OVERDUE_THRESHOLD_1', 7),
            'overdue_threshold_2': blocking_settings.get('DEFAULT_OVERDUE_THRESHOLD_2', 14),
            'overdue_threshold_3': blocking_settings.get('DEFAULT_OVERDUE_THRESHOLD_3', 30),
        }
    
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
    position = models.CharField(
        _('Position'),
        max_length=100,
        help_text=_('Employee position')
    )
    bio = models.TextField(
        _('Bio'),
        blank=True,
        help_text=_('Employee biography')
    )
    photo = models.ImageField(
        _('Photo'),
        upload_to='employees/photos/%Y/%m/%d/',
        blank=True,
        null=True,
        help_text=_('Employee photo')
    )
    services = models.ManyToManyField(
        Service,
        verbose_name=_('Services'),
        help_text=_('Services this employee can provide')
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
            models.Index(fields=['position']),
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

    def has_confirmed_provider(self):
        """
        Проверяет, есть ли у сотрудника подтвержденное учреждение.
        
        Returns:
            bool: True, если у сотрудника есть подтвержденное учреждение
        """
        return self.employeeprovider_set.filter(
            is_confirmed=True,
            end_date__isnull=True
        ).exists()

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


class EmployeeJoinRequest(models.Model):
    """
    Employee join request model.
    
    Основные характеристики:
    - Связь с пользователем и учреждением
    - Должность и комментарий
    - Статус заявки
    - Временные метки
    
    Технические особенности:
    - Автоматическое отслеживание времени создания и обновления
    - Управление статусом заявки
    - Связь с пользователем и учреждением через ForeignKey
    
    Примечание:
    Заявка может быть в одном из трех состояний:
    - pending (ожидает рассмотрения)
    - approved (одобрена)
    - rejected (отклонена)
    """
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='join_requests',
        verbose_name=_('User')
    )
    provider = models.ForeignKey(
        'Provider',
        on_delete=models.CASCADE,
        related_name='join_requests',
        verbose_name=_('Provider')
    )
    position = models.CharField(
        _('Position'),
        max_length=255
    )
    comment = models.TextField(
        _('Comment'),
        blank=True
    )
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=[
            ('pending', _('Pending')),
            ('approved', _('Approved')),
            ('rejected', _('Rejected'))
        ],
        default='pending'
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
        verbose_name = _('Employee Join Request')
        verbose_name_plural = _('Employee Join Requests')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление заявки.
        
        Returns:
            str: Строковое представление заявки
        """
        return f"{self.user} - {self.provider} ({self.status})"


class EmployeeProvider(models.Model):
    """
    Employee-Provider relationship model.
    
    Основные характеристики:
    - Связь с сотрудником и учреждением
    - Период работы
    - Статус менеджера
    - Подтверждение сотрудника
    
    Технические особенности:
    - Уникальная связь по сотруднику, учреждению и дате начала
    - Автоматическое отслеживание времени создания и обновления
    - Управление подтверждением сотрудника
    
    Примечание:
    Эта модель используется для отслеживания истории работы сотрудника
    в различных учреждениях.
    """
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
        help_text=_('Whether this employee is a manager at this provider')
    )
    is_confirmed = models.BooleanField(
        _('Is Confirmed'),
        default=False,
        help_text=_('Confirmed by employee')
    )
    confirmation_requested_at = models.DateTimeField(
        _('Confirmation Requested At'),
        null=True,
        blank=True,
        help_text=_('When the confirmation was requested')
    )
    confirmed_at = models.DateTimeField(
        _('Confirmed At'),
        null=True,
        blank=True,
        help_text=_('When the confirmation was received')
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
        unique_together = ['employee', 'provider', 'start_date']
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['start_date']),
            models.Index(fields=['end_date']),
            models.Index(fields=['is_confirmed']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление связи.
        
        Returns:
            str: Строковое представление связи
        """
        return f"{self.employee} - {self.provider} ({self.start_date})"

    def is_currently_employed(self):
        """
        Проверяет, работает ли сотрудник в учреждении в настоящее время.
        
        Returns:
            bool: True, если сотрудник работает в учреждении
        """
        return self.end_date is None

    def request_confirmation(self):
        """
        Запрашивает подтверждение сотрудника.
        
        Примечание:
        Устанавливает время запроса подтверждения.
        """
        self.confirmation_requested_at = timezone.now()
        self.save()

    def confirm(self):
        """
        Подтверждает сотрудника.
        
        Примечание:
        Устанавливает время подтверждения и статус подтверждения.
        """
        self.is_confirmed = True
        self.confirmed_at = timezone.now()
        self.save()

    def can_work(self):
        """
        Проверяет, может ли сотрудник работать в учреждении.
        
        Returns:
            bool: True, если сотрудник может работать
        """
        return self.is_currently_employed() and self.is_confirmed


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
        help_text=_('Start time of the working day')
    )
    end_time = models.TimeField(
        _('End Time'),
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


class ManagerTransferInvite(models.Model):
    """
    Модель приглашения на передачу полномочий менеджера учреждения.

    from_manager — сотрудник, инициирующий передачу прав
    to_employee — сотрудник, которому передают права
    provider — учреждение
    is_accepted — приглашение принято
    is_declined — приглашение отклонено
    created_at, accepted_at, declined_at — временные метки
    """
    from_manager = models.ForeignKey(
        'Employee', related_name='sent_manager_invites', on_delete=models.CASCADE,
        verbose_name=_('From manager')
    )
    to_employee = models.ForeignKey(
        'Employee', related_name='received_manager_invites', on_delete=models.CASCADE,
        verbose_name=_('To employee')
    )
    provider = models.ForeignKey('Provider', on_delete=models.CASCADE, verbose_name=_('Provider'))
    is_accepted = models.BooleanField(default=False, verbose_name=_('Accepted'))
    is_declined = models.BooleanField(default=False, verbose_name=_('Declined'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created at'))
    accepted_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Accepted at'))
    declined_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Declined at'))

    class Meta:
        verbose_name = _('Manager transfer invite')
        verbose_name_plural = _('Manager transfer invites')
        unique_together = ('to_employee', 'provider', 'is_accepted', 'is_declined')


class ProviderLocationService(models.Model):
    """
    Промежуточная модель для связи локации с услугами.
    
    Основные характеристики:
    - Связь с локацией и услугой
    - Цена услуги в конкретной локации
    - Длительность услуги
    - Статус активности
    
    Технические особенности:
    - Уникальная связь по локации и услуге
    - Автоматическое отслеживание времени создания и обновления
    - Управление статусом активности
    
    Примечание:
    Услуги должны быть из категорий уровня 0 организации (provider.available_category_levels).
    """
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
    price = models.DecimalField(
        _('Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Price of the service at this location')
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
        ordering = ['location', 'service']
        unique_together = ['location', 'service']
        indexes = [
            models.Index(fields=['location', 'service']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление связи.
        
        Returns:
            str: Строковое представление связи
        """
        return f"{self.location} - {self.service}"


class ProviderLocation(models.Model):
    """
    Локация (точка предоставления услуг) организации.
    
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
    
    # Адрес и координаты
    structured_address = models.ForeignKey(
        'geolocation.Address',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='provider_locations',
        verbose_name=_('Structured Address'),
        help_text=_('Structured address with validation and coordinates')
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
