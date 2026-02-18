"""
Модели для работы с юридическими документами.

Этот модуль содержит модели для:
1. Типов юридических документов (настраиваемые)
2. Юридических документов (оферты, политики, дополнения)
3. Переводов документов
4. Конфигурации стран (какие документы требуются)
5. Принятия документов пользователями
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import django_countries.fields
import logging
from django_ckeditor_5.fields import CKEditor5Field

logger = logging.getLogger(__name__)

# Choices для регионов и типов дополнений (из billing/models.py)
REGION_CHOICES = [
    ('EU', _('European Union')),
    ('EEA', _('European Economic Area')),
    ('RU', _('Russian Federation')),
    ('UA', _('Ukraine')),
    ('EAEU', _('Eurasian Economic Union')),
    ('US', _('United States')),
]

ADDENDUM_TYPE_CHOICES = [
    ('tax', _('Tax and VAT')),
    ('data_protection', _('Data Protection (GDPR, etc.)')),
    ('fiscal', _('Fiscal Requirements')),
    ('consumer_protection', _('Consumer Protection')),
    ('other', _('Other')),
]


class LegalDocumentType(models.Model):
    """
    Типы юридических документов.
    Настраивается администратором, можно добавлять новые типы без изменения кода.
    """
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_('Code'),
        help_text=_('Unique code for document type (e.g., "global_offer", "privacy_policy")')
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_('Name'),
        help_text=_('Human-readable name (e.g., "Global Offer", "Privacy Policy")')
    )
    description = models.TextField(
        blank=True,
        verbose_name=_('Description'),
        help_text=_('Description of this document type')
    )
    
    # Флаги поведения типа документа
    requires_billing_config = models.BooleanField(
        default=False,
        verbose_name=_('Requires Billing Config'),
        help_text=_('Whether this document type requires billing configuration (e.g., Global Offer)')
    )
    requires_region_code = models.BooleanField(
        default=False,
        verbose_name=_('Requires Region Code'),
        help_text=_('Whether this document type requires region code (e.g., Regional Addendum)')
    )
    requires_addendum_type = models.BooleanField(
        default=False,
        verbose_name=_('Requires Addendum Type'),
        help_text=_('Whether this document type requires addendum type (e.g., Regional Addendum)')
    )
    allows_variables = models.BooleanField(
        default=False,
        verbose_name=_('Allows Variables'),
        help_text=_('Whether this document type allows custom variables (e.g., {{vat_rate}})')
    )
    requires_provider = models.BooleanField(
        default=False,
        verbose_name=_('Requires Provider'),
        help_text=_('Whether this document type requires a provider (e.g., Side Letter)')
    )
    allows_financial_terms = models.BooleanField(
        default=False,
        verbose_name=_('Allows Financial Terms'),
        help_text=_('Whether this document type allows financial terms (commissions, deferrals, thresholds)')
    )
    
    # Настройки для CountryLegalConfig
    is_required_for_all_countries = models.BooleanField(
        default=False,
        verbose_name=_('Required for All Countries'),
        help_text=_('Whether this document type is required for all countries (e.g., Global Offer)')
    )
    is_multiple_allowed = models.BooleanField(
        default=False,
        verbose_name=_('Multiple Allowed'),
        help_text=_('Whether multiple documents of this type can be assigned to one country (e.g., Regional Addendums)')
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Is Active'),
        help_text=_('Whether this document type is currently active')
    )
    display_order = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Display Order'),
        help_text=_('Order for display in admin and API')
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))
    
    class Meta:
        verbose_name = _('Legal Document Type')
        verbose_name_plural = _('Legal Document Types')
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return self.name


class LegalDocument(models.Model):
    """
    Юридический документ.
    Может быть глобальной офертой, региональным дополнением, Privacy Policy и т.д.
    """
    document_type = models.ForeignKey(
        LegalDocumentType,
        on_delete=models.PROTECT,
        related_name='documents',
        verbose_name=_('Document Type'),
        help_text=_('Type of legal document')
    )
    version = models.CharField(
        max_length=20,
        verbose_name=_('Version'),
        help_text=_('Version of the document (e.g., 1.0, 1.1)')
    )
    title = models.CharField(
        max_length=200,
        verbose_name=_('Title'),
        help_text=_('Title of the document')
    )
    
    # Условные поля (зависят от document_type)
    billing_config = models.ForeignKey(
        'billing.BillingConfig',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_('Billing Config'),
        help_text=_('Billing configuration (only for document types that require it)')
    )
    
    region_code = models.CharField(
        max_length=10,
        choices=REGION_CHOICES,
        null=True,
        blank=True,
        verbose_name=_('Region Code'),
        help_text=_('Region code (only for regional addendums)')
    )
    addendum_type = models.CharField(
        max_length=20,
        choices=ADDENDUM_TYPE_CHOICES,
        null=True,
        blank=True,
        verbose_name=_('Addendum Type'),
        help_text=_('Type of addendum (only for regional addendums)')
    )
    
    # Переменные для подстановки в документ (опционально)
    variables = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('Variables'),
        help_text=_('Additional variables for this document. Example: {"vat_rate": "20", "fiscal_law": "Law 54-FZ"}')
    )
    
    effective_date = models.DateField(
        verbose_name=_('Effective Date'),
        help_text=_('Date when this document becomes effective')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Is Active'),
        help_text=_('Whether this document is currently active')
    )
    
    # Уведомление об изменении условий (особенно для оферты)
    change_notification_days = models.PositiveIntegerField(
        default=30,
        verbose_name=_('Change Notification Days'),
        help_text=_('Days before effective_date to notify about document changes. Minimum: 30 days.')
    )
    notification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Notification Sent At'),
        help_text=_('When notification about document changes was sent')
    )
    
    # Поля для Side Letter (только для document_type с requires_provider=True)
    # Связь с провайдерами (M2M, так как один документ может быть для нескольких провайдеров)
    providers = models.ManyToManyField(
        'providers.Provider',
        related_name='legal_documents',
        blank=True,
        verbose_name=_('Providers'),
        help_text=_('Providers associated with this document (for Side Letter)')
    )
    # Измененные пункты оферты (для Side Letter)
    modified_clauses = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('Modified Clauses'),
        help_text=_('Modified clauses from the offer. Example: {"5.1": "Commission 5% instead of 10%", "4.3": "Payment deferral 10 days instead of 5"}')
    )
    # Файл подписанного документа (для Side Letter)
    document_file = models.FileField(
        upload_to='legal/side_letters/%Y/%m/%d/',
        null=True,
        blank=True,
        verbose_name=_('Document File'),
        help_text=_('Scanned signed Side Letter document')
    )
    signed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Signed At'),
        help_text=_('Date when Side Letter was signed')
    )
    
    # Поля для финансовых условий (только для document_type с allows_financial_terms=True)
    # Тип комиссии
    COMMISSION_TYPE_CHOICES = [
        ('percent', _('Percentage')),  # Процент от стоимости (стандарт)
        ('fixed', _('Fixed Amount')),  # Фиксированная сумма
        ('hybrid', _('Hybrid')),  # Гибрид: фикс + процент
        ('tiered', _('Tiered')),  # Прогрессивная шкала (чем больше объем, тем меньше процент)
    ]
    commission_type = models.CharField(
        max_length=20,
        choices=COMMISSION_TYPE_CHOICES,
        null=True,
        blank=True,
        verbose_name=_('Commission Type'),
        help_text=_('Type of commission calculation')
    )
    # Процентная комиссия
    commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('Commission Percentage'),
        help_text=_('Commission percentage (if commission_type is "percent" or "hybrid")')
    )
    # Фиксированная комиссия
    commission_fixed = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('Fixed Commission Amount'),
        help_text=_('Fixed commission amount per booking (if commission_type is "fixed" or "hybrid")')
    )
    # Минимальная/максимальная комиссия
    commission_min = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('Minimum Commission'),
        help_text=_('Minimum commission amount (e.g., 50 rubles minimum even if 5% is less)')
    )
    commission_max = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('Maximum Commission'),
        help_text=_('Maximum commission amount per booking')
    )
    # Прогрессивная шкала (для tiered)
    tiered_rates = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('Tiered Rates'),
        help_text=_('Tiered commission rates. Example: [{"min": 0, "max": 10000, "percent": 10}, {"min": 10000, "max": 50000, "percent": 8}, {"min": 50000, "percent": 5}]')
    )
    # Отсрочка платежа
    payment_deferral_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Payment Deferral Days'),
        help_text=_('Payment deferral days (overrides default from offer)')
    )
    # Пороги блокировки
    debt_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('Debt Threshold'),
        help_text=_('Debt threshold for blocking (overrides default)')
    )
    overdue_threshold_1 = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Overdue Threshold 1'),
        help_text=_('Days overdue for information notification (overrides default)')
    )
    overdue_threshold_2 = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Overdue Threshold 2'),
        help_text=_('Days overdue for exclusion from search (overrides default)')
    )
    overdue_threshold_3 = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Overdue Threshold 3'),
        help_text=_('Days overdue for full blocking (overrides default)')
    )
    # Скидки на объем (опционально)
    volume_discount_enabled = models.BooleanField(
        default=False,
        verbose_name=_('Volume Discount Enabled'),
        help_text=_('Enable volume-based discounts')
    )
    volume_discount_rules = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('Volume Discount Rules'),
        help_text=_('Volume discount rules. Example: [{"min_bookings": 100, "discount_percent": 1}, {"min_bookings": 500, "discount_percent": 2}]')
    )
    # Бонусы за активность (опционально)
    activity_bonus_enabled = models.BooleanField(
        default=False,
        verbose_name=_('Activity Bonus Enabled'),
        help_text=_('Enable activity-based bonuses')
    )
    activity_bonus_rules = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('Activity Bonus Rules'),
        help_text=_('Activity bonus rules. Example: [{"min_rating": 4.5, "bonus_percent": 0.5}, {"min_bookings_per_month": 50, "bonus_percent": 1}]')
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))
    
    class Meta:
        verbose_name = _('Legal Document')
        verbose_name_plural = _('Legal Documents')
        # Для региональных дополнений уникальность по (document_type, version, region_code)
        # Для остальных (global_offer и т.д.) - по (document_type, version)
        # Используем constraints вместо unique_together, чтобы учесть region_code
        constraints = [
            models.UniqueConstraint(
                fields=['document_type', 'version', 'region_code'],
                name='legal_document_unique_with_region',
                condition=models.Q(region_code__isnull=False),
            ),
            models.UniqueConstraint(
                fields=['document_type', 'version'],
                name='legal_document_unique_without_region',
                condition=models.Q(region_code__isnull=True),
            ),
        ]
        ordering = ['-effective_date', 'document_type']
        indexes = [
            models.Index(fields=['document_type', 'is_active']),
            models.Index(fields=['region_code', 'is_active']),
            models.Index(fields=['signed_at']),
        ]
    
    def __str__(self):
        return f"{self.title} v{self.version}"
    
    def clean(self):
        """Валидация полей в зависимости от типа документа"""
        from django.core.exceptions import ValidationError
        
        if self.document_type:
            # Проверяем, что требуемые поля заполнены
            if self.document_type.requires_billing_config and not self.billing_config:
                raise ValidationError({
                    'billing_config': _('This document type requires billing configuration.')
                })
            
            if self.document_type.requires_region_code and not self.region_code:
                raise ValidationError({
                    'region_code': _('This document type requires region code.')
                })
            
            if self.document_type.requires_addendum_type and not self.addendum_type:
                raise ValidationError({
                    'addendum_type': _('This document type requires addendum type.')
                })
            
            if self.document_type.requires_provider and not self.providers.exists():
                raise ValidationError({
                    'providers': _('This document type requires at least one provider.')
                })
    
    def calculate_commission(self, booking_amount, booking_currency, provider_currency=None):
        """
        Рассчитывает комиссию для указанной суммы бронирования.
        Используется только для документов с allows_financial_terms=True.
        
        Args:
            booking_amount: Decimal - сумма бронирования
            booking_currency: Currency - валюта бронирования
            provider_currency: Currency - валюта провайдера (опционально, для конвертации)
            
        Returns:
            Decimal: сумма комиссии в валюте провайдера (или booking_currency, если provider_currency не указан)
        """
        from decimal import Decimal
        
        if not self.document_type or not self.document_type.allows_financial_terms:
            return Decimal('0.00')
        
        # Определяем валюту провайдера
        if not provider_currency:
            # Пытаемся получить валюту из первого связанного провайдера
            first_provider = self.providers.first()
            if first_provider:
                provider_currency = first_provider.invoice_currency or booking_currency
            else:
                provider_currency = booking_currency
        
        # Конвертируем сумму в валюту провайдера, если нужно
        if booking_currency != provider_currency:
            booking_amount = booking_currency.convert_amount(booking_amount, provider_currency)
        
        commission = Decimal('0.00')
        
        if self.commission_type == 'percent':
            # Процентная комиссия
            if self.commission_percent:
                commission = booking_amount * (self.commission_percent / Decimal('100'))
            else:
                commission = Decimal('0.00')
        
        elif self.commission_type == 'fixed':
            # Фиксированная комиссия
            if self.commission_fixed:
                commission = self.commission_fixed
            else:
                commission = Decimal('0.00')
        
        elif self.commission_type == 'hybrid':
            # Гибридная: фикс + процент
            fixed_part = self.commission_fixed or Decimal('0.00')
            percent_part = Decimal('0.00')
            if self.commission_percent:
                percent_part = booking_amount * (self.commission_percent / Decimal('100'))
            commission = fixed_part + percent_part
        
        elif self.commission_type == 'tiered':
            # Прогрессивная шкала
            if self.tiered_rates:
                # Находим подходящий диапазон
                for tier in sorted(self.tiered_rates, key=lambda x: x.get('min', 0)):
                    min_amount = Decimal(str(tier.get('min', 0)))
                    max_amount = Decimal(str(tier.get('max', float('inf')))) if tier.get('max') else Decimal('999999999')
                    percent = Decimal(str(tier.get('percent', 0)))
                    
                    if min_amount <= booking_amount <= max_amount:
                        commission = booking_amount * (percent / Decimal('100'))
                        break
        
        # Применяем минимальную/максимальную комиссию
        if self.commission_min and commission < self.commission_min:
            commission = self.commission_min
        if self.commission_max and commission > self.commission_max:
            commission = self.commission_max
        
        return commission


class DocumentTranslation(models.Model):
    """
    Перевод юридического документа на конкретный язык.
    Одна запись = один язык.
    Администратор сам определяет, какие языки добавлять.
    """
    document = models.ForeignKey(
        LegalDocument,
        on_delete=models.CASCADE,
        related_name='translations',
        verbose_name=_('Document'),
        help_text=_('Legal document this translation belongs to')
    )
    language = models.CharField(
        max_length=10,
        choices=settings.LANGUAGES,
        verbose_name=_('Language'),
        help_text=_('Language code (e.g., en, ru, de, sr)')
    )
    
    # DOCX файл для этого языка
    content_docx_file = models.FileField(
        upload_to='legal/documents/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name=_('Content DOCX File'),
        help_text=_('Upload DOCX file for this language. Will be converted to HTML automatically.')
    )
    
    # HTML контент (редактируется через CKEditor или конвертируется из DOCX)
    content = CKEditor5Field(
        blank=True,
        verbose_name=_('Content'),
        help_text=_('HTML content. Can be edited directly or auto-converted from DOCX file. Can contain variables like {{commission_percent}}.'),
        config_name='legal'
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))
    
    class Meta:
        verbose_name = _('Document Translation')
        verbose_name_plural = _('Document Translations')
        unique_together = ['document', 'language']
        ordering = ['language']
    
    def __str__(self):
        return f"{self.document.title} ({self.language})"
    
    def save(self, *args, **kwargs):
        """
        Автоматическая конвертация DOCX в HTML при сохранении.
        """
        # Сохраняем сначала, чтобы файл был доступен на диске
        super().save(*args, **kwargs)
        
        # Конвертируем DOCX в HTML ПОСЛЕ сохранения
        if self.content_docx_file:
            converted = self._convert_docx_to_html()
            if converted:
                super().save(update_fields=['content'])
    
    def _convert_docx_to_html(self):
        """
        Конвертирует загруженный DOCX файл в HTML и сохраняет в поле content.
        Использует библиотеку Mammoth для конвертации.
        
        Returns:
            bool: True если файл был сконвертирован, False иначе
        """
        try:
            import mammoth
        except ImportError:
            logger.error('Mammoth library is not installed. Please install it: pip install mammoth')
            return False
        
        if not self.content_docx_file or not self.content_docx_file.file:
            return False
        
        try:
            # Настройка style_map для сохранения форматирования, включая нумерацию
            # Это сохраняет нумерацию списков (1.1., 2.1. и т.д.)
            # И форматирование (выравнивание, стили и т.д.)
            style_map = """
            p[style-name='List Paragraph'] => ol > li:fresh
            p[style-name='List Number'] => ol > li:fresh
            p[style-name='List Number 2'] => ol > li:fresh
            p[style-name='List Number 3'] => ol > li:fresh
            p[style-name='List Bullet'] => ul > li:fresh
            p[style-name='List Bullet 2'] => ul > li:fresh
            p[style-name='List Bullet 3'] => ul > li:fresh
            p[style-name='Heading 1'] => h1:fresh
            p[style-name='Heading 2'] => h2:fresh
            p[style-name='Heading 3'] => h3:fresh
            p[style-name='Title'] => h1.title:fresh
            p[style-name='Subtitle'] => h2.subtitle:fresh
            """
            
            # Опции конвертации для сохранения форматирования
            # include_default_style_map=True сохраняет базовое форматирование
            convert_options = {
                'style_map': style_map,
                'include_default_style_map': True,  # Сохраняет базовое форматирование (жирный, курсив и т.д.)
            }
            
            # Читаем DOCX файл
            with self.content_docx_file.open('rb') as f:
                result = mammoth.convert_to_html(f, **convert_options)
                html_content = result.value
                
                if not html_content or len(html_content.strip()) == 0:
                    logger.warning(f'Converted HTML is empty for {self.language} translation of document {self.document.id}')
                    return False
                
                # Проверяем, что переменные сохраняются как есть (только предупреждения)
                # Подстановка должна происходить только при показе провайдеру через сервис
                if '5%' in html_content and '{{commission_percent}}' not in html_content:
                    logger.warning(
                        f'Variable {{commission_percent}} NOT found in HTML for {self.language} translation. '
                        f'HTML contains "5%" instead. Check DOCX file!'
                    )
                
                # Постобработка HTML для сохранения явной нумерации вложенных списков
                html_content = self._postprocess_html_numbering(html_content)
                
                # Сохраняем HTML в поле content
                # ПЕРЕМЕННЫЕ ДОЛЖНЫ СОХРАНЯТЬСЯ КАК ЕСТЬ, без подстановки
                self.content = html_content
                
                # Логируем предупреждения, если есть
                if result.messages:
                    for message in result.messages:
                        logger.warning(f'Mammoth conversion warning for {self.language}: {message}')
                
                return True
                
        except Exception as e:
            logger.error(f'Error converting DOCX to HTML for {self.language}: {str(e)}', exc_info=True)
            return False
    
    def _postprocess_html_numbering(self, html_content):
        """
        Постобработка HTML для добавления явной нумерации вложенных списков
        и сохранения форматирования (выравнивание, стили и т.д.).
        
        Обрабатывает вложенные <ol> списки и добавляет явную нумерацию типа "1.1.", "2.1." и т.д.
        Также добавляет CSS стили для сохранения форматирования из Word.
        
        Args:
            html_content: HTML контент после конвертации из DOCX
            
        Returns:
            str: Обработанный HTML с явной нумерацией и форматированием
        """
        import re
        
        # Добавляем CSS стили для нумерации и форматирования в начало HTML
        # Это позволит фронту правильно отображать нумерацию и форматирование
        css_styles = """
        <style>
        /* Нумерация вложенных списков */
        ol { counter-reset: item; list-style-type: none; }
        ol > li { counter-increment: item; }
        ol > li:before { content: counters(item, ".") ". "; font-weight: bold; }
        ol ol { counter-reset: item; }
        ol ol > li:before { content: counters(item, ".") ". "; }
        
        /* Сохранение форматирования из Word */
        /* Выравнивание по центру */
        p[style*="text-align:center"], p[align="center"], .center { text-align: center; }
        /* Выравнивание по правому краю */
        p[style*="text-align:right"], p[align="right"], .right { text-align: right; }
        /* Выравнивание по левому краю */
        p[style*="text-align:left"], p[align="left"], .left { text-align: left; }
        /* Выравнивание по ширине */
        p[style*="text-align:justify"], p[align="justify"], .justify { text-align: justify; }
        
        /* Заголовки */
        h1.title { font-size: 1.8em; font-weight: bold; margin: 1em 0; }
        h2.subtitle { font-size: 1.4em; font-weight: bold; margin: 0.8em 0; }
        
        /* Сохранение базового форматирования (уже должно быть в HTML от mammoth) */
        strong, b { font-weight: bold; }
        em, i { font-style: italic; }
        u { text-decoration: underline; }
        </style>
        """
        
        # Обрабатываем атрибуты выравнивания из Word
        # Mammoth может сохранять выравнивание в атрибутах или стилях
        # Обрабатываем оба случая
        
        # Если есть атрибуты align, преобразуем их в классы
        html_content = re.sub(r'<p\s+align="center">', '<p class="center">', html_content, flags=re.IGNORECASE)
        html_content = re.sub(r'<p\s+align="right">', '<p class="right">', html_content, flags=re.IGNORECASE)
        html_content = re.sub(r'<p\s+align="left">', '<p class="left">', html_content, flags=re.IGNORECASE)
        html_content = re.sub(r'<p\s+align="justify">', '<p class="justify">', html_content, flags=re.IGNORECASE)
        
        # Если в HTML еще нет <style>, добавляем его
        if '<style>' not in html_content and '</style>' not in html_content:
            # Вставляем стили после первого <p> или в начало, если нет <p>
            if '<p>' in html_content:
                html_content = html_content.replace('<p>', css_styles + '<p>', 1)
            elif '<h1>' in html_content or '<h2>' in html_content:
                # Если есть заголовки, вставляем перед ними
                html_content = re.sub(r'(<h[1-6])', css_styles + r'\1', html_content, count=1)
            else:
                html_content = css_styles + html_content
        
        return html_content
    
    def convert_docx_file(self):
        """
        Явная конвертация DOCX файла в HTML.
        Используется для ручной конвертации через админку.
        
        Returns:
            dict: Результат конвертации с информацией
        """
        if not self.content_docx_file:
            return {
                'success': False,
                'message': _('No DOCX file uploaded'),
                'converted': False
            }
        
        converted = self._convert_docx_to_html()
        
        if converted:
            self.save(update_fields=['content'])
            return {
                'success': True,
                'message': _('DOCX file converted successfully'),
                'converted': True
            }
        else:
            return {
                'success': False,
                'message': _('Failed to convert DOCX file. Check logs for details.'),
                'converted': False
            }


class CountryLegalConfig(models.Model):
    """
    Связь страны с необходимыми документами.
    Отвечает на вопрос: "Какие документы показать провайдеру из Германии?"
    """
    country = django_countries.fields.CountryField(
        primary_key=True,
        verbose_name=_('Country'),
        help_text=_('Country code (ISO 3166-1 alpha-2)')
    )
    
    # Глобальная оферта (обязательна для всех)
    global_offer = models.ForeignKey(
        LegalDocument,
        on_delete=models.PROTECT,
        related_name='country_configs_global',
        limit_choices_to={'document_type__code': 'global_offer', 'is_active': True},
        verbose_name=_('Global Offer'),
        help_text=_('Global offer (same for all providers)')
    )
    
    # Региональные дополнения (M2M - может быть несколько)
    regional_addendums = models.ManyToManyField(
        LegalDocument,
        related_name='country_configs_regional',
        limit_choices_to={'document_type__code': 'regional_addendum', 'is_active': True},
        blank=True,
        verbose_name=_('Regional Addendums'),
        help_text=_('Regional addendums required for this country')
    )
    
    # Privacy Policy, Terms of Service, Cookie Policy (опционально)
    privacy_policy = models.ForeignKey(
        LegalDocument,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='country_configs_privacy',
        limit_choices_to={'document_type__code': 'privacy_policy', 'is_active': True},
        verbose_name=_('Privacy Policy'),
        help_text=_('Privacy Policy for this country')
    )
    terms_of_service = models.ForeignKey(
        LegalDocument,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='country_configs_terms',
        limit_choices_to={'document_type__code': 'terms_of_service', 'is_active': True},
        verbose_name=_('Terms of Service'),
        help_text=_('Terms of Service for this country')
    )
    cookie_policy = models.ForeignKey(
        LegalDocument,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='country_configs_cookie',
        limit_choices_to={'document_type__code': 'cookie_policy', 'is_active': True},
        verbose_name=_('Cookie Policy'),
        help_text=_('Cookie Policy for this country')
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))
    
    class Meta:
        verbose_name = _('Country Legal Config')
        verbose_name_plural = _('Country Legal Configs')
    
    def __str__(self):
        return f"Legal config for {self.country}"


class DocumentAcceptance(models.Model):
    """
    Факт принятия юридического документа конкретным пользователем/провайдером.
    Юридически значимая запись.
    
    Универсальная модель для всех типов документов:
    - Оферты провайдеров (global_offer) - требует provider и может иметь региональные дополнения
    - Privacy Policy, Terms of Service, Cookie Policy - может быть принято user или provider
    """
    # Может быть принято пользователем или провайдером
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='document_acceptances',
        verbose_name=_('User'),
        help_text=_('User who accepted the document')
    )
    provider = models.ForeignKey(
        'providers.Provider',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='document_acceptances',
        verbose_name=_('Provider'),
        help_text=_('Provider who accepted the document')
    )
    
    # Пользователь, который принял документ (для оферт провайдеров - это Owner)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accepted_documents',
        verbose_name=_('Accepted By'),
        help_text=_('User who accepted the document (for provider offers - this is the Owner)')
    )
    
    # Ссылаемся на конкретную версию документа, которую приняли
    document = models.ForeignKey(
        LegalDocument,
        on_delete=models.PROTECT,
        related_name='acceptances',
        verbose_name=_('Document'),
        help_text=_('Legal document that was accepted')
    )
    
    # Версия документа, которая была принята
    document_version = models.CharField(
        max_length=20,
        verbose_name=_('Document Version'),
        help_text=_('Version of the document that was accepted')
    )
    
    accepted_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Accepted At'),
        help_text=_('Date and time when the document was accepted')
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_('IP Address'),
        help_text=_('IP address from which the document was accepted')
    )
    user_agent = models.TextField(
        blank=True,
        verbose_name=_('User Agent'),
        help_text=_('User agent (browser/device) from which the document was accepted')
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Is Active'),
        help_text=_('Whether this acceptance is currently active (if document is updated, old acceptances become inactive)')
    )
    
    class Meta:
        verbose_name = _('Document Acceptance')
        verbose_name_plural = _('Document Acceptances')
        ordering = ['-accepted_at']
        indexes = [
            models.Index(fields=['user', 'document', 'is_active']),
            models.Index(fields=['provider', 'document', 'is_active']),
            models.Index(fields=['provider', 'is_active']),
            models.Index(fields=['document', 'is_active']),
            models.Index(fields=['accepted_at']),
        ]
    
    def __str__(self):
        if self.user:
            return f"{self.user.email} accepted {self.document.title} v{self.document_version}"
        elif self.provider:
            return f"{self.provider.name} accepted {self.document.title} v{self.document_version}"
        else:
            return f"Document {self.document.title} v{self.document_version} accepted"
    
    def clean(self):
        """Валидация: должен быть указан либо user, либо provider"""
        from django.core.exceptions import ValidationError
        
        if not self.user and not self.provider:
            raise ValidationError(_('Either user or provider must be specified.'))
        
        # Для оферт провайдеров (global_offer) должен быть указан provider
        if self.document and self.document.document_type and self.document.document_type.code == 'global_offer':
            if not self.provider:
                raise ValidationError(_('Provider must be specified for global offer acceptance.'))