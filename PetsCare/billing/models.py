"""
Модели для работы с биллингом.

Этот модуль содержит модели для:
1. Управления валютами и курсами обмена
2. Работы с договорами и комиссиями
3. Обработки платежей и возвратов
4. Выставления счетов
5. Ценообразования услуг
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from providers.models import Provider
from catalog.models import Service
from users.models import User
from booking.models import Booking
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
import django_countries.fields


class Currency(models.Model):
    """
    Модель для работы с валютами.
    
    Особенности:
    - Поддержка ISO 4217
    - Управление курсами обмена
    - Автоматическое обновление курсов
    - Отслеживание статуса активности
    """
    code = models.CharField(
        _('Currency Code'),
        max_length=3,
        unique=True,
        help_text=_('ISO 4217 currency code (e.g. USD, EUR, RUB)')
    )
    name = models.CharField(
        _('Currency Name'),
        max_length=50
    )
    symbol = models.CharField(
        _('Currency Symbol'),
        max_length=5
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )
    exchange_rate = models.DecimalField(
        _('Exchange Rate'),
        max_digits=10,
        decimal_places=4,
        help_text=_('Exchange rate to base currency')
    )
    last_updated = models.DateTimeField(
        _('Last Updated'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Currency')
        verbose_name_plural = _('Currencies')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def convert_amount(self, amount, target_currency):
        """Конвертирует сумму из текущей валюты в указанную"""
        if self == target_currency:
            return amount
        
        # Convert through base currency
        base_amount = amount / self.exchange_rate
        return base_amount * target_currency.exchange_rate

    @classmethod
    def update_exchange_rates(cls):
        """Обновляет курсы валют через внешний API"""
        # Implementation for updating rates through external API
        # For example, through https://exchangeratesapi.io/ or other service
        pass


class VATRate(models.Model):
    """
    Модель для хранения ставок НДС по странам.
    
    Используется для расчета НДС в счетах:
    - Если провайдер НЕ плательщик НДС: комиссия * (1 + vat_rate/100)
    - Если провайдер плательщик НДС (ЕС): Reverse Charge (0% НДС)
    """
    country = django_countries.fields.CountryField(
        verbose_name=_('Country'),
        help_text=_('Country code (ISO 3166-1 alpha-2)')
    )
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name=_('VAT Rate'),
        help_text=_('VAT rate percentage (e.g., 20.00 for 20%)')
    )
    effective_date = models.DateField(
        verbose_name=_('Effective Date'),
        help_text=_('Date when this VAT rate becomes effective')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Is Active'),
        help_text=_('Whether this VAT rate is currently active')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))
    
    class Meta:
        verbose_name = _('VAT Rate')
        verbose_name_plural = _('VAT Rates')
        unique_together = ['country', 'effective_date']
        ordering = ['country', '-effective_date']
        indexes = [
            models.Index(fields=['country', 'is_active']),
            models.Index(fields=['effective_date']),
        ]
    
    def __str__(self):
        return f"{self.country} - {self.rate}% (from {self.effective_date})"
    
    @classmethod
    def get_rate_for_country(cls, country_code, date=None):
        """
        Получает актуальную ставку НДС для страны на указанную дату.
        
        Args:
            country_code: ISO 3166-1 alpha-2 код страны
            date: Дата для проверки (по умолчанию - сегодня)
            
        Returns:
            Decimal или None: Ставка НДС или None если не найдена
        """
        from django.utils import timezone
        
        if date is None:
            date = timezone.now().date()
        
        try:
            rate = cls.objects.filter(
                country=country_code,
                is_active=True,
                effective_date__lte=date
            ).order_by('-effective_date').first()
            
            return rate.rate if rate else None
        except Exception:
            return None


# Модели Contract, ContractType, ContractCommission, ContractDiscount, ContractApprovalHistory удалены
# Используется LegalDocument и DocumentAcceptance из приложения legal

# Все классы контрактов (Contract, ContractApprovalHistory, ContractCommission, ContractDiscount) удалены
# Используется LegalDocument и DocumentAcceptance из приложения legal


class Payment(models.Model):
    """
    Модель для работы с платежами.
    
    Особенности:
    - Различные методы оплаты
    - Отслеживание статуса
    - Поддержка возвратов
    - Привязка к бронированиям
    """
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
        ('refunded', _('Refunded')),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('card', _('Credit Card')),
        ('bank_transfer', _('Bank Transfer')),
        ('cash', _('Cash')),
    ]

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name=_('Booking')
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_('Amount')
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name=_('Status')
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        verbose_name=_('Payment Method')
    )
    transaction_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_('Transaction ID')
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
        verbose_name = _('Payment')
        verbose_name_plural = _('Payments')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.booking} - {self.amount}"


def get_default_currency():
    from billing.models import Currency
    from django.conf import settings
    if not settings.configured:
        return 1  # Возвращаем дефолтное значение
    try:
        return Currency.objects.get(code='EUR').id
    except Currency.DoesNotExist:
        return 1  # Возвращаем дефолтное значение


class Invoice(models.Model):
    """
    Модель для работы со счетами.
    
    Особенности:
    - Уникальная нумерация
    - Отслеживание статуса
    - Срок оплаты
    - Привязка к бронированиям
    """
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('sent', _('Sent')),
        ('paid', _('Paid')),
        ('overdue', _('Overdue')),
        ('cancelled', _('Cancelled')),
    ]

    number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_('Invoice Number')
    )
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='invoices',
        verbose_name=_('Provider'),
        null=True
    )
    start_date = models.DateField(_('Start Date'), null=True)
    end_date = models.DateField(_('End Date'), null=True)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('Amount')
    )
    currency = models.ForeignKey(
        'Currency',
        on_delete=models.PROTECT,
        verbose_name=_('Currency'),
        null=True
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name=_('Status')
    )
    issued_at = models.DateTimeField(_('Issued At'), default=timezone.now)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Invoice')
        verbose_name_plural = _('Invoices')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.number} - {self.provider} ({self.start_date} - {self.end_date})"

    def save(self, *args, **kwargs):
        if not self.number:
            # Генерация номера: IN-ГОД-МЕСЯЦ-ID
            from django.conf import settings
            if settings.configured:
                last_id = Invoice.objects.all().order_by('-id').first()
                next_id = (last_id.id + 1) if last_id else 1
            else:
                next_id = 1  # Дефолтное значение при инициализации
            self.number = f"IN-{timezone.now().year}-{timezone.now().month:02d}-{next_id}"
        super().save(*args, **kwargs)

    def calculate_amount(self):
        # Сумма по всем строкам инвойса
        return sum(line.amount for line in self.lines.all())


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_('Invoice')
    )
    booking = models.ForeignKey(
        Booking,
        on_delete=models.PROTECT,
        verbose_name=_('Booking')
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('Booking Amount')
    )
    commission = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('Commission Amount')
    )
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name=_('Commission Rate')
    )
    currency = models.ForeignKey(
        'Currency',
        on_delete=models.PROTECT,
        verbose_name=_('Currency')
    )
    # Поля для НДС
    vat_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('VAT Rate'),
        help_text=_('VAT rate percentage (e.g., 20.00 for 20%)')
    )
    vat_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('VAT Amount'),
        help_text=_('VAT amount added to commission')
    )
    total_with_vat = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('Total with VAT'),
        help_text=_('Commission amount including VAT')
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Invoice Line')
        verbose_name_plural = _('Invoice Lines')
        ordering = ['invoice', 'booking']

    def __str__(self):
        return f"{self.invoice.number} - {self.booking}"


class Refund(models.Model):
    """
    Модель для работы с возвратами средств.
    
    Особенности:
    - Отслеживание статуса возврата
    - Указание причины
    - Привязка к платежу
    - История изменений
    """
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('approved', _('Approved')),
        ('rejected', _('Rejected')),
        ('completed', _('Completed')),
    ]

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name='refunds',
        verbose_name=_('Payment')
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_('Amount')
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name=_('Status')
    )
    reason = models.TextField(
        verbose_name=_('Reason')
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
        verbose_name = _('Refund')
        verbose_name_plural = _('Refunds')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.payment} - {self.amount}"


class PaymentHistory(models.Model):
    """
    Модель для работы с историей платежей провайдеров.
    
    Особенности:
    - Отслеживание статуса платежей
    - Даты оплаты и сроки
    - Мультивалютность
    - Подробное описание
    - Связь с Provider (вместо Contract)
    - Опциональная связь с Invoice и DocumentAcceptance
    """
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('paid', _('Paid')),
        ('overdue', _('Overdue')),
    ]

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='payment_history',
        verbose_name=_('Provider'),
        help_text=_('Provider for this payment')
    )
    # Опциональная связь с Invoice (для истории)
    invoice = models.ForeignKey(
        'Invoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_history',
        verbose_name=_('Invoice'),
        help_text=_('Invoice this payment is for (optional)')
    )
    # Опциональная связь с DocumentAcceptance (для истории)
    offer_acceptance = models.ForeignKey(
        'legal.DocumentAcceptance',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_history',
        verbose_name=_('Offer Acceptance'),
        help_text=_('Document acceptance this payment is related to (optional)')
    )
    # Поле contract удалено - используется provider, invoice и offer_acceptance
    amount = models.DecimalField(
        _('Amount'),
        max_digits=10,
        decimal_places=2
    )
    due_date = models.DateField(_('Due Date'))
    payment_date = models.DateField(
        _('Payment Date'),
        null=True,
        blank=True
    )
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of the payment')
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        verbose_name=_('Currency'),
        related_name='payment_history'
    )

    class Meta:
        verbose_name = _('Payment History')
        verbose_name_plural = _('Payment History')
        ordering = ['-due_date']

    def __str__(self):
        # Используем invoice.number или offer.version или provider.name
        if self.invoice:
            return f"{self.invoice.number} - {self.amount} {self.currency.code}"
        elif self.offer_acceptance:
            if self.offer_acceptance.document:
                return f"{self.provider.name} - Offer {self.offer_acceptance.document.version} - {self.amount} {self.currency.code}"
            return f"{self.provider.name} - Offer Acceptance - {self.amount} {self.currency.code}"
        else:
            return f"{self.provider.name} - {self.amount} {self.currency.code}"

    def save(self, *args, **kwargs):
        """Обновляет статус при сохранении"""
        if self.payment_date:
            self.status = 'paid'
        elif self.due_date < timezone.now().date():
            self.status = 'overdue'
        super().save(*args, **kwargs)

    @classmethod
    def update_overdue_status(cls):
        """Обновляет статус просроченных платежей"""
        overdue_payments = cls.objects.filter(
            status='pending',
            due_date__lt=timezone.now().date()
        )
        for payment in overdue_payments:
            payment.status = 'overdue'
            payment.save()

    def mark_as_paid(self, payment_date=None):
        """Отмечает платеж как оплаченный"""
        if not payment_date:
            payment_date = timezone.now().date()
        self.payment_date = payment_date
        self.status = 'paid'
        self.save()

    def convert_to_currency(self, target_currency):
        """Конвертирует сумму в указанную валюту"""
        if self.currency == target_currency:
            return self.amount
        return self.currency.convert_amount(self.amount, target_currency)


class ServicePrice(models.Model):
    """
    Модель для работы с ценами на услуги.
    
    Особенности:
    - Мультивалютность
    - Период действия цены
    - Отслеживание активности
    - История изменений
    """
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        verbose_name=_('Service'),
        related_name='prices'
    )
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        verbose_name=_('Currency'),
        related_name='service_prices'
    )
    amount = models.DecimalField(
        _('Amount'),
        max_digits=10,
        decimal_places=2
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )
    valid_from = models.DateField(
        _('Valid From'),
        default=timezone.now
    )
    valid_to = models.DateField(
        _('Valid To'),
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Service Price')
        verbose_name_plural = _('Service Prices')
        ordering = ['-valid_from']
        unique_together = ['service', 'currency', 'valid_from']

    def __str__(self):
        return f"{self.service.name} - {self.amount} {self.currency.code}"

    def convert_to_currency(self, target_currency):
        """Конвертирует цену в указанную валюту"""
        if self.currency == target_currency:
            return self.amount
        return self.currency.convert_amount(self.amount, target_currency)


class BillingManagerProvider(models.Model):
    """
    Модель для связи менеджера по биллингу с провайдерами.
    
    Особенности:
    - Один менеджер по биллингу может управлять несколькими провайдерами
    - Отслеживание статуса управления (активно, в отпуске, временно, завершено)
    - Поддержка временных заместителей
    - История изменений через связанные события
    
    Технические особенности:
    - Уникальная связь по менеджеру, провайдеру и дате начала
    - Автоматическое отслеживание времени создания и обновления
    - Управление статусом активности
    """
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('vacation', _('On Vacation')),
        ('temporary', _('Temporary')),
        ('terminated', _('Terminated')),
    ]

    billing_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_('Billing Manager'),
        related_name='managed_providers',
        help_text=_('User with billing_manager role')
    )
    provider = models.ForeignKey(
        'providers.Provider',
        on_delete=models.CASCADE,
        verbose_name=_('Provider'),
        related_name='billing_managers',
        help_text=_('Provider managed by this billing manager')
    )
    start_date = models.DateField(
        _('Start Date'),
        help_text=_('Date when billing manager started managing this provider')
    )
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        help_text=_('Current status of the management relationship')
    )
    temporary_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Temporary Manager'),
        related_name='temporary_managed_providers',
        help_text=_('Temporary manager during vacation or absence')
    )
    notes = models.TextField(
        _('Notes'),
        blank=True,
        help_text=_('Additional notes about this management relationship')
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
        verbose_name = _('Billing Manager Provider')
        verbose_name_plural = _('Billing Manager Providers')
        unique_together = ['billing_manager', 'provider', 'start_date']
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['billing_manager']),
            models.Index(fields=['provider']),
            models.Index(fields=['status']),
            models.Index(fields=['start_date']),
        ]

    def __str__(self):
        """Возвращает строковое представление связи менеджера по биллингу с провайдером"""
        return f"{self.billing_manager.get_full_name()} - {self.provider.name} ({self.get_status_display()})"

    def is_currently_managing(self):
        """
        Проверяет, активно ли управление в данный момент.
        
        Returns:
            bool: True если менеджер активно управляет провайдером
        """
        return self.status in ['active', 'temporary']

    def get_effective_manager(self):
        """
        Возвращает эффективного менеджера (основного или временного).
        
        Returns:
            User: Активный менеджер (временный или основной)
        """
        if self.status == 'temporary' and self.temporary_manager:
            return self.temporary_manager
        return self.billing_manager

    def start_vacation(self, temporary_manager, notes=''):
        """
        Начинает отпуск менеджера с назначением временного заместителя.
        
        Args:
            temporary_manager (User): Временный менеджер
            notes (str): Примечания к событию
        """
        self.status = 'vacation'
        self.temporary_manager = temporary_manager
        self.notes = notes
        self.save()
        
        # Создаем событие
        BillingManagerEvent.objects.create(
            billing_manager_provider=self,
            event_type='vacation_start',
            effective_date=timezone.now().date(),
            created_by=self.billing_manager,
            notes=notes
        )

    def end_vacation(self, notes=''):
        """
        Завершает отпуск менеджера.
        
        Args:
            notes (str): Примечания к событию
        """
        self.status = 'active'
        self.temporary_manager = None
        self.notes = notes
        self.save()
        
        # Создаем событие
        BillingManagerEvent.objects.create(
            billing_manager_provider=self,
            event_type='vacation_end',
            effective_date=timezone.now().date(),
            created_by=self.billing_manager,
            notes=notes
        )

    def terminate(self, notes=''):
        """
        Завершает управление провайдером.
        
        Args:
            notes (str): Примечания к событию
        """
        self.status = 'terminated'
        self.notes = notes
        self.save()
        
        # Создаем событие
        BillingManagerEvent.objects.create(
            billing_manager_provider=self,
            event_type='terminated',
            effective_date=timezone.now().date(),
            created_by=self.billing_manager,
            notes=notes
        )

    @classmethod
    def get_active_managers_for_provider(cls, provider):
        """
        Получает активных менеджеров по биллингу для провайдера.
        
        Args:
            provider: Объект Provider
            
        Returns:
            QuerySet: Активные менеджеры по биллингу для провайдера
        """
        return cls.objects.filter(
            provider=provider,
            status__in=['active', 'temporary']
        ).select_related('billing_manager', 'temporary_manager')

    @classmethod
    def get_active_providers_for_manager(cls, billing_manager):
        """
        Получает активных провайдеров для менеджера по биллингу.
        
        Args:
            billing_manager: Объект User с ролью billing_manager
            
        Returns:
            QuerySet: Активные провайдеры для менеджера
        """
        return cls.objects.filter(
            billing_manager=billing_manager,
            status__in=['active', 'vacation']
        ).select_related('provider')


class BillingManagerEvent(models.Model):
    """
    Модель для отслеживания событий в управлении провайдерами менеджерами по биллингу.
    
    Особенности:
    - Полная история всех изменений
    - Отслеживание кто, когда и почему принял решение
    - Поддержка аудита и compliance
    - Автоматическое создание событий при изменениях
    """
    EVENT_TYPES = [
        ('assigned', _('Assigned')),
        ('vacation_start', _('Vacation Started')),
        ('vacation_end', _('Vacation Ended')),
        ('temporary_assigned', _('Temporary Assigned')),
        ('terminated', _('Terminated')),
    ]

    billing_manager_provider = models.ForeignKey(
        BillingManagerProvider,
        on_delete=models.CASCADE,
        verbose_name=_('Billing Manager Provider'),
        related_name='events'
    )
    event_type = models.CharField(
        _('Event Type'),
        max_length=20,
        choices=EVENT_TYPES,
        help_text=_('Type of event that occurred')
    )
    effective_date = models.DateField(
        _('Effective Date'),
        help_text=_('Date when this event became effective')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('Created By'),
        related_name='billing_manager_events_created',
        help_text=_('User who created this event')
    )
    notes = models.TextField(
        _('Notes'),
        blank=True,
        help_text=_('Additional notes about this event')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _('Billing Manager Event')
        verbose_name_plural = _('Billing Manager Events')
        ordering = ['-effective_date', '-created_at']
        indexes = [
            models.Index(fields=['billing_manager_provider']),
            models.Index(fields=['event_type']),
            models.Index(fields=['effective_date']),
            models.Index(fields=['created_by']),
        ]

    def __str__(self):
        """Возвращает строковое представление события"""
        return f"{self.billing_manager_provider} - {self.get_event_type_display()} ({self.effective_date})"

    @classmethod
    def get_events_for_provider(cls, provider, start_date=None, end_date=None):
        """
        Получает события для провайдера за указанный период.
        
        Args:
            provider: Объект Provider
            start_date (date, optional): Начальная дата периода
            end_date (date, optional): Конечная дата периода
            
        Returns:
            QuerySet: События для провайдера
        """
        queryset = cls.objects.filter(
            billing_manager_provider__provider=provider
        ).select_related(
            'billing_manager_provider__billing_manager',
            'billing_manager_provider__temporary_manager',
            'created_by'
        )
        
        if start_date:
            queryset = queryset.filter(effective_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(effective_date__lte=end_date)
            
        return queryset

    @classmethod
    def get_events_for_manager(cls, billing_manager, start_date=None, end_date=None):
        """
        Получает события для менеджера за указанный период.
        
        Args:
            billing_manager: Объект User с ролью billing_manager
            start_date (date, optional): Начальная дата периода
            end_date (date, optional): Конечная дата периода
            
        Returns:
            QuerySet: События для менеджера
        """
        queryset = cls.objects.filter(
            billing_manager_provider__billing_manager=billing_manager
        ).select_related(
            'billing_manager_provider__provider',
            'billing_manager_provider__temporary_manager',
            'created_by'
        )
        
        if start_date:
            queryset = queryset.filter(effective_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(effective_date__lte=end_date)
            
        return queryset


class OverdueThresholdSettings(models.Model):
    """
    Модель для настройки пороговых значений просрочки платежей.
    
    Особенности:
    - Настройка порогов по дням просрочки
    - Настройка порогов по сумме задолженности
    - Привязка к валютам и регионам
    - Приоритеты уведомлений
    - Автоматические действия при достижении порогов
    """
    name = models.CharField(
        _('Name'),
        max_length=100,
        help_text=_('Descriptive name for this threshold setting')
    )
    
    # Пороговые значения по дням
    warning_days = models.PositiveIntegerField(
        _('Warning Days'),
        default=7,
        help_text=_('Days after which to send warning notification')
    )
    critical_days = models.PositiveIntegerField(
        _('Critical Days'),
        default=30,
        help_text=_('Days after which to send critical notification')
    )
    suspension_days = models.PositiveIntegerField(
        _('Suspension Days'),
        default=60,
        help_text=_('Days after which to suspend provider services')
    )
    termination_days = models.PositiveIntegerField(
        _('Termination Days'),
        default=90,
        help_text=_('Days after which to terminate contract')
    )
    
    # Пороговые значения по сумме
    warning_amount = models.DecimalField(
        _('Warning Amount'),
        max_digits=12,
        decimal_places=2,
        default=1000.00,
        help_text=_('Amount threshold for warning notification')
    )
    critical_amount = models.DecimalField(
        _('Critical Amount'),
        max_digits=12,
        decimal_places=2,
        default=5000.00,
        help_text=_('Amount threshold for critical notification')
    )
    suspension_amount = models.DecimalField(
        _('Suspension Amount'),
        max_digits=12,
        decimal_places=2,
        default=10000.00,
        help_text=_('Amount threshold for service suspension')
    )
    termination_amount = models.DecimalField(
        _('Termination Amount'),
        max_digits=12,
        decimal_places=2,
        default=20000.00,
        help_text=_('Amount threshold for contract termination')
    )
    
    # Привязка к валюте и региону
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        verbose_name=_('Currency'),
        help_text=_('Currency for amount thresholds')
    )
    region = models.CharField(
        _('Region'),
        max_length=50,
        blank=True,
        help_text=_('Geographic region (e.g., Europe, Asia, Americas)')
    )
    country = models.CharField(
        _('Country'),
        max_length=50,
        blank=True,
        help_text=_('Specific country code (ISO 3166-1 alpha-2)')
    )
    
    # Настройки уведомлений
    notify_provider = models.BooleanField(
        _('Notify Provider'),
        default=True,
        help_text=_('Send notifications to provider')
    )
    notify_billing_manager = models.BooleanField(
        _('Notify Billing Manager'),
        default=True,
        help_text=_('Send notifications to billing manager')
    )
    notify_admin = models.BooleanField(
        _('Notify Admin'),
        default=False,
        help_text=_('Send notifications to system admin')
    )
    
    # Автоматические действия
    auto_suspend = models.BooleanField(
        _('Auto Suspend'),
        default=False,
        help_text=_('Automatically suspend services when thresholds are reached')
    )
    auto_terminate = models.BooleanField(
        _('Auto Terminate'),
        default=False,
        help_text=_('Automatically terminate contract when thresholds are reached')
    )
    
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Overdue Threshold Setting')
        verbose_name_plural = _('Overdue Threshold Settings')
        ordering = ['name']
        indexes = [
            models.Index(fields=['currency', 'region']),
            models.Index(fields=['country', 'region']),
        ]

    def __str__(self):
        return f"{self.name} ({self.currency.code})"


class BlockingRule(models.Model):
    """
    Модель для правил автоматической блокировки учреждений.
    
    Особенности:
    - Настройка порогов по сумме и дням просрочки
    - Массовая настройка по географии и типу услуг
    - Приоритет правил
    - Отслеживание активности
    """
    name = models.CharField(
        _('Rule Name'),
        max_length=200,
        help_text=_('Descriptive name for this blocking rule')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Detailed description of the rule')
    )
    
    # Пороги блокировки
    debt_amount_threshold = models.DecimalField(
        _('Debt Amount Threshold'),
        max_digits=12,
        decimal_places=2,
        help_text=_('Minimum debt amount to trigger blocking')
    )
    overdue_days_threshold = models.PositiveIntegerField(
        _('Overdue Days Threshold'),
        help_text=_('Minimum number of overdue days to trigger blocking')
    )
    
    # Массовая настройка
    is_mass_rule = models.BooleanField(
        _('Is Mass Rule'),
        default=False,
        help_text=_('If True, applies to multiple providers based on criteria')
    )
    
    # Критерии для массовой настройки
    regions = models.JSONField(
        _('Regions'),
        default=list,
        blank=True,
        help_text=_('List of region IDs for mass rule application')
    )
    service_types = models.JSONField(
        _('Service Types'),
        default=list,
        blank=True,
        help_text=_('List of service type IDs for mass rule application')
    )
    
    # Приоритет правила (меньше = выше приоритет)
    priority = models.PositiveIntegerField(
        _('Priority'),
        default=100,
        help_text=_('Rule priority (lower number = higher priority)')
    )
    
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this rule is active')
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('Created By'),
        related_name='created_blocking_rules'
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Blocking Rule')
        verbose_name_plural = _('Blocking Rules')
        ordering = ['priority', 'name']
        indexes = [
            models.Index(fields=['is_active', 'priority']),
            models.Index(fields=['is_mass_rule', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} (Priority: {self.priority})"

    def get_applicable_providers(self):
        """Возвращает список провайдеров, к которым применяется это правило"""
        from providers.models import Provider
        
        if not self.is_mass_rule:
            return []
        
        providers = Provider.objects.filter(is_active=True)
        
        if self.regions:
            providers = providers.filter(
                structured_address__region__in=self.regions
            )
        
        if self.service_types:
            # Фильтр по типам услуг, которые предоставляет провайдер
            providers = providers.filter(
                locations__available_services__id__in=self.service_types
            ).distinct()
        
        return providers


class ProviderBlocking(models.Model):
    """
    Модель для отслеживания блокировок учреждений.
    
    Особенности:
    - Отслеживание статуса блокировки
    - История блокировок
    - Привязка к правилу блокировки
    - Автоматическое управление статусом
    """
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('resolved', _('Resolved')),
        ('manual_override', _('Manual Override')),
    ]

    provider = models.ForeignKey(
        'providers.Provider',
        on_delete=models.CASCADE,
        verbose_name=_('Provider'),
        related_name='blockings'
    )
    blocking_rule = models.ForeignKey(
        BlockingRule,
        on_delete=models.PROTECT,
        verbose_name=_('Blocking Rule'),
        related_name='provider_blockings'
    )
    
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )
    
    # Данные о задолженности на момент блокировки
    debt_amount = models.DecimalField(
        _('Debt Amount'),
        max_digits=12,
        decimal_places=2,
        help_text=_('Debt amount at the time of blocking')
    )
    overdue_days = models.PositiveIntegerField(
        _('Overdue Days'),
        help_text=_('Number of overdue days at the time of blocking')
    )
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        verbose_name=_('Currency')
    )
    
    # Даты блокировки и разблокировки
    blocked_at = models.DateTimeField(_('Blocked At'), auto_now_add=True)
    resolved_at = models.DateTimeField(
        _('Resolved At'),
        null=True,
        blank=True
    )
    
    # Кто инициировал разблокировку
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Resolved By'),
        related_name='resolved_blockings'
    )
    
    # Примечания
    notes = models.TextField(
        _('Notes'),
        blank=True,
        help_text=_('Additional notes about this blocking')
    )

    class Meta:
        verbose_name = _('Provider Blocking')
        verbose_name_plural = _('Provider Blockings')
        ordering = ['-blocked_at']
        indexes = [
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['status', 'blocked_at']),
        ]

    def __str__(self):
        return f"{self.provider.name} - {self.get_status_display()} ({self.blocked_at.strftime('%Y-%m-%d %H:%M')})"

    def resolve(self, resolved_by=None, notes=''):
        """Разблокирует учреждение"""
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        self.resolved_by = resolved_by
        if notes:
            self.notes = notes
        self.save()

    def manual_override(self, resolved_by, notes=''):
        """Ручное снятие блокировки"""
        self.status = 'manual_override'
        self.resolved_at = timezone.now()
        self.resolved_by = resolved_by
        if notes:
            self.notes = notes
        self.save()

    @property
    def is_active_blocking(self):
        """Проверяет, активна ли блокировка"""
        return self.status == 'active'


class BlockingNotification(models.Model):
    """
    Модель для отслеживания уведомлений о блокировках.
    
    Особенности:
    - Отслеживание статуса отправки
    - Различные типы уведомлений
    - История уведомлений
    """
    NOTIFICATION_TYPES = [
        ('blocking_warning', _('Blocking Warning')),
        ('blocking_activated', _('Blocking Activated')),
        ('blocking_resolved', _('Blocking Resolved')),
    ]

    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('sent', _('Sent')),
        ('failed', _('Failed')),
    ]

    provider_blocking = models.ForeignKey(
        ProviderBlocking,
        on_delete=models.CASCADE,
        verbose_name=_('Provider Blocking'),
        related_name='notifications'
    )
    
    notification_type = models.CharField(
        _('Notification Type'),
        max_length=20,
        choices=NOTIFICATION_TYPES
    )
    
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Получатели уведомления
    recipient_email = models.EmailField(
        _('Recipient Email'),
        blank=True
    )
    recipient_phone = models.CharField(
        _('Recipient Phone'),
        max_length=20,
        blank=True
    )
    
    # Содержание уведомления
    subject = models.CharField(
        _('Subject'),
        max_length=200
    )
    message = models.TextField(_('Message'))
    
    # Время отправки
    sent_at = models.DateTimeField(
        _('Sent At'),
        null=True,
        blank=True
    )
    
    # Ошибки при отправке
    error_message = models.TextField(
        _('Error Message'),
        blank=True
    )
    
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Blocking Notification')
        verbose_name_plural = _('Blocking Notifications')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'notification_type']),
            models.Index(fields=['provider_blocking', 'notification_type']),
        ]

    def __str__(self):
        return f"{self.provider_blocking.provider.name} - {self.get_notification_type_display()} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"

    def mark_as_sent(self):
        """Отмечает уведомление как отправленное"""
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.save()

    def mark_as_failed(self, error_message=''):
        """Отмечает уведомление как неудачное"""
        self.status = 'failed'
        self.error_message = error_message
        self.save()


class BlockingTemplate(models.Model):
    """
    Модель для шаблонов автоматической блокировки учреждений.
    
    Особенности:
    - Географическая иерархия (страна → область → город)
    - Автоматическое применение параметров при создании договоров
    - Централизованное управление порогами блокировки
    - Строгое разграничение прав доступа
    - Интеграция с системой геолокации
    """
    name = models.CharField(
        _('Template Name'),
        max_length=200,
        help_text=_('Descriptive name for this blocking template')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Detailed description of the template')
    )
    
    # Географическая иерархия (устаревшие поля для обратной совместимости)
    country = models.CharField(
        _('Country'),
        max_length=100,
        help_text=_('Country (required)')
    )
    region = models.CharField(
        _('Region'),
        max_length=100,
        blank=True,
        null=True,
        help_text=_('Region/state (optional)')
    )
    city = models.CharField(
        _('City'),
        max_length=100,
        blank=True,
        null=True,
        help_text=_('City (optional)')
    )
    
    # Интеграция с системой геолокации
    location = models.ForeignKey(
        'geolocation.Location',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Location'),
        related_name='blocking_templates',
        help_text=_('Associated location for precise geographic targeting')
    )
    radius_km = models.PositiveIntegerField(
        _('Radius (km)'),
        default=10,
        help_text=_('Radius in kilometers for geographic targeting')
    )
    
    # Параметры блокировки
    debt_threshold = models.DecimalField(
        _('Debt Threshold'),
        max_digits=12,
        decimal_places=2,
        help_text=_('Maximum allowed debt amount in contract currency')
    )
    threshold1_days = models.PositiveIntegerField(
        _('Threshold 1 (Days)'),
        help_text=_('Days overdue for information notification')
    )
    threshold2_days = models.PositiveIntegerField(
        _('Threshold 2 (Days)'),
        help_text=_('Days overdue for exclusion from search')
    )
    threshold3_days = models.PositiveIntegerField(
        _('Threshold 3 (Days)'),
        help_text=_('Days overdue for full blocking')
    )
    payment_delay_days = models.PositiveIntegerField(
        _('Payment Delay Days'),
        default=0,
        help_text=_('Allowed payment delay in days')
    )
    
    # Валюта
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        verbose_name=_('Currency'),
        help_text=_('Currency for debt threshold')
    )
    
    # Статус
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this template is active')
    )
    
    # Метаданные
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('Created By'),
        related_name='created_blocking_templates'
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Blocking Template')
        verbose_name_plural = _('Blocking Templates')
        ordering = ['country', 'region', 'city', 'name']
        indexes = [
            models.Index(fields=['country', 'region', 'city']),
            models.Index(fields=['is_active']),
            models.Index(fields=['location']),
        ]
        unique_together = [
            ('country', 'region', 'city', 'name'),
        ]

    def __str__(self):
        location_str = f" - {self.country}"
        if self.region:
            location_str += f", {self.region}"
        if self.city:
            location_str += f", {self.city}"
        return f"{self.name}{location_str}"

    def clean(self):
        """Валидация географической иерархии."""
        # Проверяем, что указана хотя бы страна
        if not self.country:
            raise ValidationError(_('Country is required'))
        
        # Проверяем логику иерархии
        if self.city and not self.region:
            raise ValidationError(_('Region must be specified if city is provided'))
        
        # Проверяем радиус
        if self.radius_km <= 0:
            raise ValidationError(_('Radius must be greater than 0'))

    def save(self, *args, **kwargs):
        """Сохраняет модель с автоматическим обновлением геоданных."""
        self.clean()
        
        # Если указана локация, обновляем географические поля
        if self.location:
            self.country = self.location.country or self.country
            self.city = self.location.city or self.city
        
        super().save(*args, **kwargs)

    @classmethod
    def find_template_for_provider(cls, provider):
        """
        Находит подходящий шаблон для учреждения.
        
        Args:
            provider: Объект Provider
            
        Returns:
            BlockingTemplate или None
        """
        # Сначала ищем по точной локации
        provider_point = None
        if provider.structured_address and provider.structured_address.point:
            provider_point = provider.structured_address.point
        
        if provider_point:
            from django.contrib.gis.db.models.functions import Distance
            
            # Ищем шаблоны с привязкой к локации
            location_templates = cls.objects.filter(
                is_active=True,
                location__isnull=False,
                location__point__isnull=False
            ).annotate(
                distance=Distance('location__point', provider_point)
            ).filter(
                distance__lte=models.F('radius_km') * 1000  # Convert km to meters
            ).order_by('distance')
            
            if location_templates.exists():
                return location_templates.first()
        
        # Затем ищем по иерархии (город -> регион -> страна)
        full_address = ''
        if provider.structured_address:
            full_address = provider.structured_address.formatted_address or str(provider.structured_address)
        
        if full_address:
            address_lower = full_address.lower()
            
            # Ищем по городу
            city_templates = cls.objects.filter(
                is_active=True,
                city__isnull=False,
                city__icontains=address_lower
            ).order_by('city')
            
            if city_templates.exists():
                return city_templates.first()
            
            # Ищем по региону
            region_templates = cls.objects.filter(
                is_active=True,
                region__isnull=False,
                region__icontains=address_lower
            ).order_by('region')
            
            if region_templates.exists():
                return region_templates.first()
            
            # Ищем по стране
            country_templates = cls.objects.filter(
                is_active=True,
                country__icontains=address_lower
            ).order_by('country')
            
            if country_templates.exists():
                return country_templates.first()
        
        # Возвращаем глобальный шаблон (без географических ограничений)
        return cls.objects.filter(
            is_active=True,
            country='',
            region='',
            city=''
        ).first()

    # Метод apply_to_contract удален - используется ProviderSpecialTerms и LegalDocument вместо Contract


class BlockingTemplateHistory(models.Model):
    """
    История изменений шаблонов блокировки для аудита.
    
    Особенности:
    - Отслеживание всех изменений шаблонов
    - Хранение предыдущих значений
    - Связь с пользователем, внесшим изменения
    - Автоматическое создание при изменении шаблона
    """
    template = models.ForeignKey(
        BlockingTemplate,
        on_delete=models.CASCADE,
        verbose_name=_('Template'),
        related_name='history'
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('Changed By'),
        help_text=_('User who made the change')
    )
    change_type = models.CharField(
        _('Change Type'),
        max_length=20,
        choices=[
        ('created', _('Created')),
        ('updated', _('Updated')),
        ('deleted', _('Deleted')),
        ],
        help_text=_('Type of change made')
    )
    previous_values = models.JSONField(
        _('Previous Values'),
        default=dict,
        help_text=_('Previous values before the change')
    )
    new_values = models.JSONField(
        _('New Values'),
        default=dict,
        help_text=_('New values after the change')
    )
    change_reason = models.TextField(
        _('Change Reason'),
        blank=True,
        help_text=_('Reason for the change')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _('Blocking Template History')
        verbose_name_plural = _('Blocking Template Histories')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['template', 'created_at']),
            models.Index(fields=['changed_by', 'created_at']),
        ]

    def __str__(self):
        return f"{self.template.name} - {self.change_type} by {self.changed_by}"


class BlockingSystemSettings(models.Model):
    """
    Глобальные настройки системы блокировки учреждений.
    
    Особенности:
    - Централизованное управление настройками
    - Настройка периодичности проверок
    - Управление уведомлениями
    - Автоматическое снятие блокировок
    """
    # Основные настройки системы
    is_system_enabled = models.BooleanField(
        _('System Enabled'),
        default=True,
        help_text=_('Whether the blocking system is enabled')
    )
    
    # Настройки периодичности проверок
    check_frequency_hours = models.PositiveIntegerField(
        _('Check Frequency (Hours)'),
        default=24,
        help_text=_('How often to check for blocking conditions (in hours)')
    )
    check_time = models.TimeField(
        _('Check Time'),
        default='02:00',
        help_text=_('Time of day to perform checks (HH:MM format)')
    )
    
    # Настройки уведомлений
    notification_delay_hours = models.PositiveIntegerField(
        _('Notification Delay (Hours)'),
        default=1,
        help_text=_('Delay before sending notifications after blocking (in hours)')
    )
    notify_billing_managers = models.BooleanField(
        _('Notify Billing Managers'),
        default=True,
        help_text=_('Whether to notify billing managers about blockings')
    )
    notify_provider_admins = models.BooleanField(
        _('Notify Provider Admins'),
        default=True,
        help_text=_('Whether to notify provider administrators about blockings')
    )
    
    # Настройки автоматического снятия блокировок
    auto_resolve_on_payment = models.BooleanField(
        _('Auto Resolve On Payment'),
        default=True,
        help_text=_('Automatically resolve blockings when debt is paid')
    )
    
    # Настройки рабочих дней
    working_days = models.JSONField(
        _('Working Days'),
        default=list,
        help_text=_('List of working days (0=Monday, 6=Sunday)')
    )
    exclude_holidays = models.BooleanField(
        _('Exclude Holidays'),
        default=True,
        help_text=_('Whether to exclude holidays from overdue calculations')
    )
    
    # Настройки логирования
    log_all_checks = models.BooleanField(
        _('Log All Checks'),
        default=True,
        help_text=_('Whether to log all blocking checks')
    )
    log_resolutions = models.BooleanField(
        _('Log Resolutions'),
        default=True,
        help_text=_('Whether to log blocking resolutions')
    )
    
    # Глобальные пороги блокировки для наследования в контрактах
    global_debt_threshold = models.DecimalField(
        _('Global Debt Threshold'),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Global debt threshold for automatic inheritance in contracts')
    )
    global_overdue_threshold_1 = models.PositiveIntegerField(
        _('Global Overdue Threshold 1 (Days)'),
        null=True,
        blank=True,
        help_text=_('Global overdue threshold 1 for automatic inheritance in contracts')
    )
    global_overdue_threshold_2 = models.PositiveIntegerField(
        _('Global Overdue Threshold 2 (Days)'),
        null=True,
        blank=True,
        help_text=_('Global overdue threshold 2 for automatic inheritance in contracts')
    )
    global_overdue_threshold_3 = models.PositiveIntegerField(
        _('Global Overdue Threshold 3 (Days)'),
        null=True,
        blank=True,
        help_text=_('Global overdue threshold 3 for automatic inheritance in contracts')
    )
    
    # Настройки обработки недееспособности владельцев
    inactive_owner_threshold_days = models.PositiveIntegerField(
        _('Inactive Owner Threshold (Days)'),
        default=180,
        help_text=_('Number of days of inactivity to consider owner as inactive (default: 6 months)')
    )
    pet_confirmation_deadline_days = models.PositiveIntegerField(
        _('Pet Confirmation Deadline (Days)'),
        default=30,
        help_text=_('Number of days to wait for pet status confirmation before taking action (default: 1 month)')
    )
    auto_delete_unconfirmed_pets = models.BooleanField(
        _('Auto Delete Unconfirmed Pets'),
        default=True,
        help_text=_('Automatically delete pets if no confirmation received within deadline')
    )
    auto_assign_coowner_as_main = models.BooleanField(
        _('Auto Assign Co-owner as Main'),
        default=True,
        help_text=_('Automatically assign a co-owner as main owner if primary owner is inactive')
    )
    coowner_assignment_priority = models.CharField(
        _('Co-owner Assignment Priority'),
        max_length=20,
        choices=[
            ('oldest', _('Oldest co-owner')),
            ('newest', _('Newest co-owner')),
            ('random', _('Random co-owner')),
        ],
        default='oldest',
        help_text=_('Priority method for assigning co-owner as main owner')
    )
    
    # Метаданные
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Updated By'),
        help_text=_('User who last updated the settings')
    )

    class Meta:
        verbose_name = _('Blocking System Settings')
        verbose_name_plural = _('Blocking System Settings')
        # Только одна запись настроек
        constraints = [
            models.CheckConstraint(
                check=models.Q(id=1),
                name='single_blocking_settings'
            )
        ]

    def __str__(self):
        return f"Blocking System Settings (ID: {self.id})"

    def save(self, *args, **kwargs):
        """Обеспечивает создание только одной записи настроек."""
        if not self.pk:
            # Проверяем, есть ли уже настройки
            if BlockingSystemSettings.objects.exists():
                raise ValidationError(_('Only one instance of BlockingSystemSettings is allowed'))
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        """Получает настройки системы, создавая их при необходимости."""
        settings, created = cls.objects.get_or_create(
            id=1,
            defaults={
                'working_days': [0, 1, 2, 3, 4],  # Понедельник-Пятница
            }
        )
        return settings

    def get_working_days(self):
        """Возвращает список рабочих дней."""
        return self.working_days or [0, 1, 2, 3, 4]  # По умолчанию Пн-Пт

    def is_working_day(self, date):
        """Проверяет, является ли дата рабочим днем."""
        return date.weekday() in self.get_working_days()
    
    def get_global_debt_threshold(self):
        """Возвращает глобальный порог долга из настроек или дефолтное значение."""
        if self.global_debt_threshold is not None:
            return self.global_debt_threshold
        from django.conf import settings
        return settings.BLOCKING_SETTINGS.get('DEFAULT_DEBT_THRESHOLD', 1000.00)
    
    def get_global_overdue_threshold_1(self):
        """Возвращает глобальный порог просрочки 1 из настроек или дефолтное значение."""
        if self.global_overdue_threshold_1 is not None:
            return self.global_overdue_threshold_1
        from django.conf import settings
        return settings.BLOCKING_SETTINGS.get('DEFAULT_OVERDUE_THRESHOLD_1', 7)
    
    def get_global_overdue_threshold_2(self):
        """Возвращает глобальный порог просрочки 2 из настроек или дефолтное значение."""
        if self.global_overdue_threshold_2 is not None:
            return self.global_overdue_threshold_2
        from django.conf import settings
        return settings.BLOCKING_SETTINGS.get('DEFAULT_OVERDUE_THRESHOLD_2', 14)
    
    def get_global_overdue_threshold_3(self):
        """Возвращает глобальный порог просрочки 3 из настроек или дефолтное значение."""
        if self.global_overdue_threshold_3 is not None:
            return self.global_overdue_threshold_3
        from django.conf import settings
        return settings.BLOCKING_SETTINGS.get('DEFAULT_OVERDUE_THRESHOLD_3', 30)
    
    def get_inactive_owner_threshold_days(self):
        """Возвращает порог неактивности владельца в днях"""
        return self.inactive_owner_threshold_days
    
    def get_pet_confirmation_deadline_days(self):
        """Возвращает дедлайн подтверждения статуса питомца в днях"""
        return self.pet_confirmation_deadline_days
    
    def should_auto_delete_unconfirmed_pets(self):
        """Возвращает True если нужно автоматически удалять неподтвержденных питомцев"""
        return self.auto_delete_unconfirmed_pets
    
    def should_auto_assign_coowner_as_main(self):
        """Возвращает True если нужно автоматически назначать совладельца основным"""
        return self.auto_assign_coowner_as_main
    
    def get_coowner_assignment_priority(self):
        """Возвращает приоритет назначения совладельца"""
        return self.coowner_assignment_priority


class BlockingSchedule(models.Model):
    """
    Расписание для автоматических проверок блокировок.
    
    Особенности:
    - Гибкая настройка частоты проверок
    - Поддержка различных временных интервалов
    - Управление активностью расписания
    - Интеграция с Celery Beat
    """
    FREQUENCY_CHOICES = [
        ('hourly', _('Hourly')),
        ('daily', _('Daily')),
        ('weekly', _('Weekly')),
        ('monthly', _('Monthly')),
        ('custom', _('Custom Interval')),
    ]
    
    name = models.CharField(
        _('Name'),
        max_length=100,
        help_text=_('Name of the schedule')
    )
    frequency = models.CharField(
        _('Frequency'),
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='daily',
        help_text=_('Frequency of checks')
    )
    time = models.TimeField(
        _('Time'),
        default='02:00',
        help_text=_('Time of day to perform checks (HH:MM format)')
    )
    days_of_week = models.JSONField(
        _('Days of Week'),
        default=list,
        help_text=_('Days of week for weekly frequency (0=Monday, 6=Sunday)')
    )
    day_of_month = models.PositiveIntegerField(
        _('Day of Month'),
        null=True,
        blank=True,
        help_text=_('Day of month for monthly frequency (1-31)')
    )
    custom_interval_hours = models.PositiveIntegerField(
        _('Custom Interval (Hours)'),
        null=True,
        blank=True,
        help_text=_('Custom interval in hours for custom frequency')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this schedule is active')
    )
    last_run = models.DateTimeField(
        _('Last Run'),
        null=True,
        blank=True,
        help_text=_('When this schedule was last executed')
    )
    next_run = models.DateTimeField(
        _('Next Run'),
        null=True,
        blank=True,
        help_text=_('When this schedule will run next')
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
        verbose_name = _('Blocking Schedule')
        verbose_name_plural = _('Blocking Schedules')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()})"

    def clean(self):
        """Валидация настроек расписания."""
        from django.core.exceptions import ValidationError
        
        if self.frequency == 'weekly' and not self.days_of_week:
            raise ValidationError(_('Days of week must be specified for weekly frequency'))
        
        if self.frequency == 'monthly' and not self.day_of_month:
            raise ValidationError(_('Day of month must be specified for monthly frequency'))
        
        if self.frequency == 'custom' and not self.custom_interval_hours:
            raise ValidationError(_('Custom interval must be specified for custom frequency'))
        
        if self.day_of_month and (self.day_of_month < 1 or self.day_of_month > 31):
            raise ValidationError(_('Day of month must be between 1 and 31'))

    def save(self, *args, **kwargs):
        """Сохраняет модель и рассчитывает следующее время выполнения."""
        self.clean()
        super().save(*args, **kwargs)
        self.calculate_next_run()

    def calculate_next_run(self):
        """Рассчитывает время следующего выполнения."""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        
        if self.frequency == 'hourly':
            self.next_run = now + timedelta(hours=1)
        elif self.frequency == 'daily':
            # Следующий день в указанное время
            next_day = now.date() + timedelta(days=1)
            self.next_run = timezone.make_aware(
                timezone.datetime.combine(next_day, self.time)
            )
        elif self.frequency == 'weekly':
            # Следующий указанный день недели
            current_weekday = now.weekday()
            for day in sorted(self.days_of_week):
                if day > current_weekday:
                    days_ahead = day - current_weekday
                    next_date = now.date() + timedelta(days=days_ahead)
                    self.next_run = timezone.make_aware(
                        timezone.datetime.combine(next_date, self.time)
                    )
                    break
            else:
                # Следующая неделя
                days_ahead = 7 - current_weekday + min(self.days_of_week)
                next_date = now.date() + timedelta(days=days_ahead)
                self.next_run = timezone.make_aware(
                    timezone.datetime.combine(next_date, self.time)
                )
        elif self.frequency == 'monthly':
            # Следующий месяц в указанный день
            if now.day >= self.day_of_month:
                # Следующий месяц
                if now.month == 12:
                    next_date = now.replace(year=now.year + 1, month=1, day=self.day_of_month)
                else:
                    next_date = now.replace(month=now.month + 1, day=self.day_of_month)
            else:
                # Текущий месяц
                next_date = now.replace(day=self.day_of_month)
            self.next_run = timezone.make_aware(
                timezone.datetime.combine(next_date.date(), self.time)
            )
        elif self.frequency == 'custom':
            self.next_run = now + timedelta(hours=self.custom_interval_hours)
        
        if self.pk:  # Только для существующих записей
            self.save(update_fields=['next_run'])

    def should_run_now(self):
        """Проверяет, должно ли расписание выполняться сейчас."""
        from django.utils import timezone
        return self.is_active and self.next_run and timezone.now() >= self.next_run

    def mark_as_run(self):
        """Отмечает расписание как выполненное."""
        from django.utils import timezone
        self.last_run = timezone.now()
        self.calculate_next_run()
        self.save(update_fields=['last_run', 'next_run'])

    def get_celery_schedule(self):
        """Возвращает настройки для Celery Beat."""
        if self.frequency == 'hourly':
            return {'schedule': 3600.0}  # 1 час
        elif self.frequency == 'daily':
            return {'schedule': 86400.0}  # 1 день
        elif self.frequency == 'weekly':
            return {'schedule': 604800.0}  # 1 неделя
        elif self.frequency == 'monthly':
            return {'schedule': 2592000.0}  # 30 дней
        elif self.frequency == 'custom':
            return {'schedule': self.custom_interval_hours * 3600.0}
        return {'schedule': 86400.0}  # По умолчанию ежедневно


# ============================================================================
# МОДЕЛИ ДЛЯ ПУБЛИЧНОЙ ОФЕРТЫ
# ============================================================================
# УДАЛЕНО: RegionalAddendum и PublicOffer заменены на LegalDocument в приложении legal
# Модели полностью удалены, так как база данных пуста и обратная совместимость не требуется
# Используйте LegalDocument, DocumentTranslation, CountryLegalConfig из приложения legal


class BillingConfig(models.Model):
    """
    Конфигурация биллинга для глобальной оферты.
    Хранит финансовые параметры, которые подставляются в текст оферты через переменные.
    """
    name = models.CharField(
        max_length=200,
        verbose_name=_('Name'),
        help_text=_('Name of this billing configuration')
    )
    description = models.TextField(
        blank=True,
        verbose_name=_('Description'),
        help_text=_('Description of this billing configuration')
    )
    
    # Базовые условия комиссии (подставляются в текст через {{commission_percent}})
    commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        verbose_name=_('Commission Percentage'),
        help_text=_('Commission percentage (e.g., 5.00 for 5%). This value is substituted into offer text as {{commission_percent}}.')
    )
    payment_deferral_days = models.PositiveIntegerField(
        default=5,
        verbose_name=_('Payment Deferral Days'),
        help_text=_('Payment deferral days after service completion. Used in offer text as {{payment_deferral_days}}')
    )
    invoice_period_days = models.PositiveIntegerField(
        default=3,
        verbose_name=_('Invoice Period Days'),
        help_text=_('Days to generate invoice after period end. Used in offer text as {{invoice_period_days}}')
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Is Active'),
        help_text=_('Whether this billing configuration is currently active')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))
    
    class Meta:
        verbose_name = _('Billing Config')
        verbose_name_plural = _('Billing Configs')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.commission_percent}%)"


# УДАЛЕНО: PublicOffer модель полностью удалена
# Заменена на LegalDocument в приложении legal


# ProviderOfferAcceptance удален - используйте DocumentAcceptance из приложения legal

# УДАЛЕНО: ProviderSpecialTerms и SideLetter
# Модели удалены - используйте LegalDocument с типом side_letter в приложении legal
# Все функциональность (финансовые условия, modified_clauses, document_file) перенесена в LegalDocument
