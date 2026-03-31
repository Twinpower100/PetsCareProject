"""
Admin views for the billing module.

Этот модуль содержит административные представления для:
1. Управления типами контрактов
2. Управления контрактами
3. Управления комиссиями и скидками
4. Управления счетами и платежами
5. Генерации отчетов по биллингу
"""

from decimal import Decimal
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied
from django.http import Http404
from modeltranslation.admin import TranslationAdmin
from .models import (
    Currency, VATRate,
    Invoice, InvoiceLine, PaymentHistory, Payment, Refund, BillingManagerProvider, BillingManagerEvent,
    BlockingRule, ProviderBlocking, BlockingNotification, BlockingTemplate, BlockingTemplateHistory, BlockingSystemSettings, BlockingSchedule,
    BillingConfig, BillingReport, PlatformCompany
)
# УДАЛЕНО: ProviderSpecialTerms, SideLetter - используйте LegalDocument с типом side_letter в приложении legal
from django.urls import path, reverse
from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from .export_utils import build_excel_response
from .invoice_services import build_invoice_breakdown_rows, summarize_invoice_breakdown

def user_has_role(user, role_name):
    """Безопасная проверка роли пользователя"""
    if not user.is_authenticated:
        return False
    return hasattr(user, 'has_role') and user.has_role(role_name)


def _is_system_admin(user):
    """
    Безопасная проверка, является ли пользователь системным администратором.
    Работает с AnonymousUser и реальными пользователями.
    """
    from django.contrib.auth.models import AnonymousUser
    if isinstance(user, AnonymousUser):
        return False
    if not hasattr(user, 'is_system_admin'):
        return False
    try:
        return user.is_system_admin()
    except (AttributeError, TypeError):
        return False
from django.contrib import messages
from providers.models import Provider
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from custom_admin import custom_admin_site
from django.forms import HiddenInput


# Админка для Contract, ContractType, ContractCommission, ContractDiscount удалена
# Используется LegalDocument и DocumentAcceptance из приложения legal


class InvoiceLineInline(admin.TabularInline):
    """Строки счета доступны только для просмотра из карточки invoice."""
    model = InvoiceLine
    extra = 0
    can_delete = False
    fields = (
        'booking',
        'amount',
        'rate',
        'commission',
        'vat_rate',
        'vat_amount',
        'total_with_vat',
        'currency',
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class InvoiceAdmin(admin.ModelAdmin):
    """
    Административное представление для счетов.
    """
    list_display = (
        'number',
        'provider',
        'platform_company',
        'start_date',
        'end_date',
        'amount',
        'currency',
        'status',
        'payment_status_display',
        'outstanding_amount_display',
        'booking_breakdown_link',
        'download_pdf_link',
        'issued_at',
    )
    list_filter = ('status', 'currency', 'issued_at', 'provider')
    search_fields = ('number', 'provider__name')
    date_hierarchy = 'issued_at'
    inlines = [InvoiceLineInline]
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('provider', 'platform_company', 'number', 'status')
        }),
        (_('Period'), {
            'fields': ('start_date', 'end_date')
        }),
        (_('Financial Details'), {
            'fields': ('amount', 'currency')
        }),
        (_('Booking Breakdown'), {
            'fields': ('booking_count_display', 'booking_breakdown_link')
        }),
        (_('Files'), {
            'fields': ('pdf_file', 'download_pdf_link')
        }),
        (_('Payment Summary'), {
            'fields': (
                'payment_status_display',
                'due_date_display',
                'payment_date_display',
                'paid_amount_display',
                'refunded_amount_display',
                'outstanding_amount_display',
            )
        }),
        (_('Metadata'), {
            'fields': ('issued_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = (
        'issued_at',
        'created_at',
        'updated_at',
        'pdf_file',
        'download_pdf_link',
        'booking_count_display',
        'booking_breakdown_link',
        'payment_status_display',
        'due_date_display',
        'payment_date_display',
        'paid_amount_display',
        'refunded_amount_display',
        'outstanding_amount_display',
    )

    def get_urls(self):
        """
        Добавляет страницу детализации бронирований и выгрузку Excel по счету.
        """
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/bookings/',
                self.admin_site.admin_view(self.booking_breakdown_view),
                name='billing_invoice_booking_breakdown',
            ),
        ]
        return custom_urls + urls

    @admin.display(description=_('Payment Status'))
    def payment_status_display(self, obj):
        payment = obj.payment_record
        return payment.get_status_display() if payment else '—'

    @admin.display(description=_('Due Date'))
    def due_date_display(self, obj):
        payment = obj.payment_record
        return payment.due_date if payment else '—'

    @admin.display(description=_('Payment Date'))
    def payment_date_display(self, obj):
        payment = obj.payment_record
        return payment.payment_date if payment and payment.payment_date else '—'

    @admin.display(description=_('Paid Amount'))
    def paid_amount_display(self, obj):
        payment = obj.payment_record
        return payment.paid_amount if payment else Decimal('0.00')

    @admin.display(description=_('Refunded Amount'))
    def refunded_amount_display(self, obj):
        payment = obj.payment_record
        return payment.refunded_amount if payment else Decimal('0.00')

    @admin.display(description=_('Outstanding Amount'))
    def outstanding_amount_display(self, obj):
        return obj.outstanding_amount

    @admin.display(description=_('Bookings'))
    def booking_count_display(self, obj):
        return obj.lines.count() if obj.pk else 0

    @admin.display(description=_('Booking Breakdown'))
    def booking_breakdown_link(self, obj):
        if not obj.pk:
            return '—'
        url = reverse(f'{self.admin_site.name}:billing_invoice_booking_breakdown', args=[obj.pk])
        return format_html(
            '<a href="{}">{}</a>',
            url,
            _('View bookings / Export Excel'),
        )

    @admin.display(description=_('Download PDF'))
    def download_pdf_link(self, obj):
        if not obj.pk:
            return '—'
        if not obj.pdf_file:
            try:
                obj.ensure_pdf_file()
            except Exception:
                return '—'
        if not obj.pdf_file:
            return '—'
        return format_html(
            '<a href="{}" target="_blank">{}</a>',
            obj.pdf_file.url,
            _('Download PDF'),
        )

    def booking_breakdown_view(self, request, object_id):
        """
        Показывает детализацию бронирований по счету и отдает Excel при запросе export=xlsx.
        """
        invoice = self.get_object(request, object_id)
        if invoice is None:
            raise Http404(_('Invoice not found'))
        if not self.has_view_permission(request, invoice):
            raise PermissionDenied

        rows = self._build_admin_booking_breakdown_rows(invoice)
        summary = summarize_invoice_breakdown(invoice, rows=rows)
        breakdown_url = reverse(
            f'{self.admin_site.name}:billing_invoice_booking_breakdown',
            args=[invoice.pk],
        )

        if request.GET.get('export') == 'xlsx':
            return build_excel_response(
                f'invoice-{invoice.number}-bookings.xlsx',
                'Invoice Bookings',
                [
                    str(_('Booking ID')),
                    str(_('Booking Code')),
                    str(_('Completed At')),
                    str(_('Service')),
                    str(_('Client')),
                    str(_('Pet')),
                    str(_('Location')),
                    str(_('Booking Amount')),
                    str(_('Commission')),
                    str(_('VAT')),
                    str(_('Total')),
                ],
                [
                    [
                        row['booking_id'],
                        row['booking_code'],
                        row['completed_at_label'],
                        row['service'],
                        row['client'],
                        row['pet'],
                        row['location'],
                        row['amount'],
                        row['commission'],
                        row['vat_amount'],
                        row['total_with_vat'],
                    ]
                    for row in rows
                ],
            )

        context = dict(
            self.admin_site.each_context(request),
            title=_('Booking breakdown'),
            opts=self.model._meta,
            original=invoice,
            invoice=invoice,
            rows=rows,
            period_label=summary['period_label'],
            booking_count=summary['booking_count'],
            booking_amount_total=summary['booking_amount_total'],
            commission_total=summary['commission_total'],
            vat_total=summary['vat_total'],
            currency_code=summary['currency_code'],
            export_url=f'{breakdown_url}?export=xlsx',
            index_url=reverse(f'{self.admin_site.name}:index'),
            invoice_list_url=reverse(f'{self.admin_site.name}:billing_invoice_changelist'),
            invoice_change_url=reverse(f'{self.admin_site.name}:billing_invoice_change', args=[invoice.pk]),
        )
        request.current_app = self.admin_site.name
        return render(request, 'admin/billing/invoice_booking_breakdown.html', context)

    def _build_admin_booking_breakdown_rows(self, invoice):
        """
        Добавляет к общей детализации ссылки на booking change view для Django admin.
        """
        rows = build_invoice_breakdown_rows(invoice)
        for row in rows:
            row['booking_url'] = reverse(
                f'{self.admin_site.name}:booking_booking_change',
                args=[row['booking_id']],
            )
        return rows
    
    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к счетам.
        Биллинг-менеджер имеет полный доступ.
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            _is_system_admin(user) or
            user.is_billing_manager()
        )
    
    def has_view_permission(self, request, obj=None):
        """Биллинг-менеджер может просматривать счета"""
        return self.has_module_permission(request)


class PaymentAdmin(admin.ModelAdmin):
    """
    Административное представление для платежей.
    """
    list_display = (
        'provider',
        'invoice',
        'booking',
        'amount',
        'status',
        'payment_method',
        'applied_at',
        'created_at',
    )
    list_filter = ('status', 'payment_method', 'created_at', 'provider')
    search_fields = ('provider__name', 'invoice__number', 'booking__pet__name', 'transaction_id')
    date_hierarchy = 'created_at'
    actions = ['export_as_excel']
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('provider', 'invoice', 'booking', 'amount', 'status', 'payment_method')
        }),
        (_('Transaction Details'), {
            'fields': ('transaction_id', 'notes')
        }),
        (_('Metadata'), {
            'fields': ('applied_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('applied_at', 'created_at', 'updated_at')

    def get_changeform_initial_data(self, request):
        """
        Подставляет значения по умолчанию для бухгалтерского ввода платежа.
        """
        return {
            'status': 'completed',
            'payment_method': 'bank_transfer',
        }

    def save_model(self, request, obj, form, change):
        """
        Сохраняет платеж через модельный сервис проводки.
        """
        if obj.provider_id is None:
            if obj.invoice_id:
                obj.provider = obj.invoice.provider
            elif obj.booking_id:
                obj.provider = obj.booking.provider or getattr(obj.booking.provider_location, 'provider', None)
        super().save_model(request, obj, form, change)

    def export_as_excel(self, request, queryset):
        """
        Экспортирует реестр поступлений в Excel.
        """
        rows = [
            [
                payment.created_at.strftime('%Y-%m-%d %H:%M') if payment.created_at else '',
                payment.provider.name if payment.provider else '',
                payment.invoice.number if payment.invoice else '',
                payment.amount,
                payment.get_status_display(),
                payment.get_payment_method_display(),
                payment.applied_at.strftime('%Y-%m-%d %H:%M') if payment.applied_at else '',
            ]
            for payment in queryset.select_related('provider', 'invoice')
        ]
        return build_excel_response(
            'PaymentHistory.xlsx',
            'Payments',
            [
                str(_('Received At')),
                str(_('Provider')),
                str(_('Invoice')),
                str(_('Amount')),
                str(_('Status')),
                str(_('Payment Method')),
                str(_('Applied At')),
            ],
            rows,
        )
    export_as_excel.short_description = _('Export selected payments to Excel')
    
    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к платежам.
        Биллинг-менеджер имеет полный доступ.
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            _is_system_admin(user) or
            user.is_billing_manager()
        )
    
    def has_view_permission(self, request, obj=None):
        """Биллинг-менеджер может просматривать платежи"""
        return self.has_module_permission(request)


class PaymentHistoryAdmin(admin.ModelAdmin):
    """Административное представление для истории расчетов по инвойсам."""
    list_display = (
        'provider',
        'invoice',
        'status',
        'amount',
        'paid_amount',
        'refunded_amount',
        'outstanding_amount_display',
        'due_date',
        'payment_date',
    )
    list_filter = ('status', 'currency', 'due_date')
    search_fields = ('provider__name', 'invoice__number', 'description')
    date_hierarchy = 'due_date'
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('provider', 'invoice', 'offer_acceptance', 'status')
        }),
        (_('Amounts'), {
            'fields': (
                'amount',
                'paid_amount',
                'refunded_amount',
                'outstanding_amount_display',
                'currency',
            )
        }),
        (_('Dates'), {
            'fields': ('due_date', 'payment_date')
        }),
        (_('Additional Information'), {
            'fields': ('description',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('outstanding_amount_display', 'created_at', 'updated_at')

    @admin.display(description=_('Outstanding Amount'))
    def outstanding_amount_display(self, obj):
        return obj.outstanding_amount

    def has_module_permission(self, request):
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            _is_system_admin(user) or
            user.is_billing_manager()
        )

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')


class RefundAdmin(admin.ModelAdmin):
    """
    Административное представление для возвратов.
    """
    list_display = ('payment', 'amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('payment__booking__pet__name', 'payment__transaction_id', 'reason')
    date_hierarchy = 'created_at'
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('payment', 'amount', 'status')
        }),
        (_('Refund Details'), {
            'fields': ('reason',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')
    
    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к возвратам.
        Биллинг-менеджер имеет полный доступ.
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            _is_system_admin(user) or
            user.is_billing_manager()
        )
    
    def has_view_permission(self, request, obj=None):
        """Биллинг-менеджер может просматривать возвраты"""
        return self.has_module_permission(request)


class BillingManagerEventInline(admin.TabularInline):
    """
    Встроенное представление для событий менеджера по биллингу.
    """
    model = BillingManagerEvent
    extra = 0
    readonly_fields = ('event_type', 'effective_date', 'created_by', 'created_at')
    fields = ('event_type', 'effective_date', 'created_by', 'notes', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        """События создаются автоматически, ручное добавление запрещено"""
        return False


class BillingManagerProviderAdmin(admin.ModelAdmin):
    """
    Административное представление для связи менеджера по биллингу с провайдерами.
    """
    list_display = ('billing_manager', 'provider', 'start_date', 'status', 'temporary_manager', 'is_currently_managing')
    list_filter = ('status', 'start_date', 'created_at')
    search_fields = ('billing_manager__first_name', 'billing_manager__last_name', 'billing_manager__email', 'provider__name')
    date_hierarchy = 'start_date'
    inlines = [BillingManagerEventInline]
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('billing_manager', 'provider', 'status')
        }),
        (_('Dates'), {
            'fields': ('start_date',)
        }),
        (_('Temporary Management'), {
            'fields': ('temporary_manager',),
            'classes': ('collapse',)
        }),
        (_('Notes'), {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')
    
    def is_currently_managing(self, obj):
        """Отображает статус текущего управления"""
        return obj.is_currently_managing()
    is_currently_managing.boolean = True
    is_currently_managing.short_description = _('Currently Managing')

    def get_queryset(self, request):
        """
        Возвращает queryset с учетом прав доступа пользователя.
        """
        qs = super().get_queryset(request)
        if user_has_role(request.user, 'billing_manager'):
            # Менеджер по биллингу видит только свои связи
            return qs.filter(billing_manager=request.user)
        return qs

    def has_change_permission(self, request, obj=None):
        """
        Проверяет права на изменение связи.
        """
        if request.user.is_superuser or user_has_role(request.user, 'system_admin'):
            return True
        if user_has_role(request.user, 'billing_manager'):
            # Менеджер по биллингу может изменять только свои связи
            if obj is None:
                return True
            return obj.billing_manager == request.user
        return False

    def has_delete_permission(self, request, obj=None):
        """
        Проверяет права на удаление связи.
        """
        if request.user.is_superuser or user_has_role(request.user, 'system_admin'):
            return True
        if user_has_role(request.user, 'billing_manager'):
            # Менеджер по биллингу может удалять только свои связи
            if obj is None:
                return True
            return obj.billing_manager == request.user
        return False
    
    def get_deleted_objects(self, objs, request):
        """
        Переопределяем метод для корректной обработки каскадного удаления.
        Используем стандартный метод Django, так как has_delete_permission для BillingManagerEvent
        уже разрешает удаление для системных админов.
        """
        from django.contrib.admin.utils import get_deleted_objects
        
        # Используем стандартный метод Django - он правильно обработает все связанные объекты
        # BillingManagerEvent теперь разрешены для удаления системным админам
        return get_deleted_objects(list(objs), request, self.admin_site)
    
    def delete_model(self, request, obj):
        """
        Удаляет BillingManagerProvider и все связанные объекты.
        Обходит проверку прав на удаление BillingManagerEvent для каскадного удаления.
        """
        from django.db import transaction
        from billing.models import BillingManagerEvent
        
        with transaction.atomic():
            # Удаляем все связанные BillingManagerEvent напрямую через ORM
            # Это обходит проверку прав админки, так как удаление происходит каскадно
            BillingManagerEvent.objects.filter(billing_manager_provider=obj).delete()
            
            # Удаляем сам BillingManagerProvider
            super().delete_model(request, obj)
    
    def delete_queryset(self, request, queryset):
        """
        Удаляет несколько BillingManagerProvider и все связанные объекты.
        Обходит проверку прав на удаление BillingManagerEvent для каскадного удаления.
        """
        from django.db import transaction
        from billing.models import BillingManagerEvent
        
        with transaction.atomic():
            # Получаем все ID выбранных BillingManagerProvider
            bmp_ids = list(queryset.values_list('id', flat=True))
            
            # Удаляем все связанные BillingManagerEvent напрямую через ORM
            BillingManagerEvent.objects.filter(billing_manager_provider_id__in=bmp_ids).delete()
            
            # Удаляем BillingManagerProvider
            super().delete_queryset(request, queryset)

    def has_add_permission(self, request):
        """
        Проверяет права на добавление связи.
        Только системный админ может назначать менеджеров (утверждается системным админом).
        """
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')
    
    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к связям менеджеров с провайдерами.
        Биллинг-менеджер имеет доступ только для просмотра (назначение утверждается системным админом).
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            _is_system_admin(user) or
            user.is_billing_manager()
        )
    
    def has_view_permission(self, request, obj=None):
        """Биллинг-менеджер может просматривать связи менеджеров"""
        return self.has_module_permission(request)


class BillingManagerEventAdmin(admin.ModelAdmin):
    """
    Административное представление для событий менеджера по биллингу.
    """
    list_display = ('billing_manager_provider', 'event_type', 'effective_date', 'created_by', 'created_at')
    list_filter = ('event_type', 'effective_date', 'created_at')
    search_fields = ('billing_manager_provider__billing_manager__first_name', 
                    'billing_manager_provider__billing_manager__last_name',
                    'billing_manager_provider__provider__name',
                    'notes')
    date_hierarchy = 'effective_date'
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('billing_manager_provider', 'event_type', 'effective_date')
        }),
        (_('Details'), {
            'fields': ('created_by', 'notes')
        }),
        (_('Metadata'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at',)

    def get_queryset(self, request):
        """
        Возвращает queryset с учетом прав доступа пользователя.
        """
        qs = super().get_queryset(request)
        if user_has_role(request.user, 'billing_manager'):
            # Менеджер по биллингу видит только события своих связей
            return qs.filter(billing_manager_provider__billing_manager=request.user)
        return qs

    def has_change_permission(self, request, obj=None):
        """
        Проверяет права на изменение события.
        """
        if request.user.is_superuser or user_has_role(request.user, 'system_admin'):
            return True
        if user_has_role(request.user, 'billing_manager'):
            # Менеджер по биллингу может изменять только события своих связей
            if obj is None:
                return True
            return obj.billing_manager_provider.billing_manager == request.user
        return False

    def has_delete_permission(self, request, obj=None):
        """
        Проверяет права на удаление события.
        События не должны удаляться вручную для сохранения аудита,
        но системные админы могут удалять их при каскадном удалении.
        """
        # Разрешаем удаление только для системных админов (при каскадном удалении)
        if request.user.is_superuser or user_has_role(request.user, 'system_admin'):
            return True
        # Для всех остальных удаление запрещено
        return False

    def has_add_permission(self, request):
        """
        Проверяет права на добавление события.
        """
        # События создаются автоматически, ручное добавление запрещено
        return False
    
    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к событиям менеджеров.
        Биллинг-менеджер имеет полный доступ (просмотр).
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            _is_system_admin(user) or
            user.is_billing_manager()
        )
    
    def has_view_permission(self, request, obj=None):
        """Биллинг-менеджер может просматривать события"""
        return self.has_module_permission(request)


class BlockingRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'debt_amount_threshold', 'overdue_days_threshold', 'is_mass_rule', 'priority', 'is_active')
    list_filter = ('is_active', 'is_mass_rule', 'priority')
    search_fields = ('name', 'description')
    actions = ['activate_rules', 'deactivate_rules']

    def activate_rules(self, request, queryset):
        queryset.update(is_active=True)
    activate_rules.short_description = 'Активировать выбранные правила'

    def deactivate_rules(self, request, queryset):
        queryset.update(is_active=False)
    deactivate_rules.short_description = 'Деактивировать выбранные правила'
    
    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к правилам блокировки.
        Биллинг-менеджер имеет доступ только для просмотра.
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            _is_system_admin(user) or
            user.is_billing_manager()
        )
    
    def has_view_permission(self, request, obj=None):
        """Биллинг-менеджер может просматривать правила блокировки"""
        return self.has_module_permission(request)
    
    def has_add_permission(self, request):
        """Только системный админ может добавлять правила"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')
    
    def has_change_permission(self, request, obj=None):
        """Только системный админ может изменять правила"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')
    
    def has_delete_permission(self, request, obj=None):
        """Только системный админ может удалять правила"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')


class ProviderBlockingAdmin(admin.ModelAdmin):
    list_display = (
        'provider',
        'blocking_level',
        'blocking_rule',
        'status',
        'debt_amount',
        'overdue_days',
        'blocked_at',
        'resolved_at',
    )
    list_filter = ('blocking_level', 'status', 'blocking_rule', 'blocked_at')
    search_fields = ('provider__name', 'notes')
    actions = ['resolve_blockings', 'export_as_excel']

    def resolve_blockings(self, request, queryset):
        """Ручное снятие выбранных блокировок."""
        for blocking in queryset.filter(status='active'):
            blocking.resolve(resolved_by=request.user, notes='Resolved through admin panel')
    resolve_blockings.short_description = _('Unblock selected providers manually')

    def export_as_excel(self, request, queryset):
        """Экспортирует отчет по блокировкам в Excel."""
        rows = [
            [
                blocking.provider.name if blocking.provider else '',
                blocking.blocking_level,
                blocking.blocking_rule.name if blocking.blocking_rule else '',
                blocking.debt_amount,
                blocking.overdue_days,
                blocking.blocked_at.strftime('%Y-%m-%d %H:%M') if blocking.blocked_at else '',
                blocking.get_status_display(),
            ]
            for blocking in queryset.select_related('provider', 'blocking_rule')
        ]
        return build_excel_response(
            'BlockedProviders.xlsx',
            'Blocked Providers',
            [
                str(_('Provider')),
                str(_('Blocking Level')),
                str(_('Blocking Rule')),
                str(_('Debt Amount')),
                str(_('Overdue Days')),
                str(_('Blocked At')),
                str(_('Status')),
            ],
            rows,
        )
    export_as_excel.short_description = _('Export selected blockings to Excel')
    
    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к блокировкам провайдеров.
        Биллинг-менеджер имеет доступ только для просмотра (блокировка/разблокировка утверждается системным админом).
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            _is_system_admin(user) or
            user.is_billing_manager()
        )
    
    def has_view_permission(self, request, obj=None):
        """Биллинг-менеджер может просматривать блокировки"""
        return self.has_module_permission(request)
    
    def has_add_permission(self, request):
        """Только системный админ может добавлять блокировки"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')
    
    def has_change_permission(self, request, obj=None):
        """Только системный админ может изменять блокировки"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')
    
    def has_delete_permission(self, request, obj=None):
        """Только системный админ может удалять блокировки"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')


class BlockingNotificationAdmin(admin.ModelAdmin):
    list_display = ('provider_blocking', 'notification_type', 'status', 'recipient_email', 'created_at', 'sent_at')
    list_filter = ('notification_type', 'status', 'created_at')
    search_fields = ('provider_blocking__provider__name', 'subject', 'message')
    
    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к уведомлениям о блокировках.
        Биллинг-менеджер имеет полный доступ (просмотр).
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            _is_system_admin(user) or
            user.is_billing_manager()
        )
    
    def has_view_permission(self, request, obj=None):
        """Биллинг-менеджер может просматривать уведомления"""
        return self.has_module_permission(request)


class BlockingTemplateHistoryInline(admin.TabularInline):
    """
    Встроенное представление для истории изменений шаблона блокировки.
    """
    model = BlockingTemplateHistory
    extra = 0
    readonly_fields = ('changed_by', 'change_type', 'previous_values', 'new_values', 'change_reason', 'created_at')
    fields = ('changed_by', 'change_type', 'change_reason', 'created_at')
    can_delete = False
    max_num = 10  # Показываем только последние 10 изменений

    def has_add_permission(self, request, obj=None):
        """История создается автоматически, ручное добавление запрещено"""
        return False


class BlockingTemplateAdmin(admin.ModelAdmin):
    """
    Административное представление для шаблонов блокировки.
    """
    list_display = ('name', 'country', 'region', 'city', 'debt_threshold', 'threshold1_days', 'threshold2_days', 'threshold3_days', 'is_active')
    list_filter = ('is_active', 'country', 'region', 'city')
    search_fields = ('name', 'country', 'region', 'city', 'description')
    inlines = [BlockingTemplateHistoryInline]
    actions = ['activate_templates', 'deactivate_templates', 'apply_to_providers']
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'description', 'is_active')
        }),
        (_('Geographic Scope'), {
            'fields': ('country', 'region', 'city'),
            'description': _('Set geographic scope for this template. Leave empty for global scope.')
        }),
        (_('Blocking Thresholds'), {
            'fields': ('debt_threshold', 'threshold1_days', 'threshold2_days', 'threshold3_days'),
            'description': _('Set thresholds for different blocking levels.')
        }),
        (_('Notification Settings'), {
            'fields': ('notification_delay_hours', 'notify_provider_admins', 'notify_billing_managers'),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')

    def activate_templates(self, request, queryset):
        """Активирует выбранные шаблоны"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Активировано {updated} шаблонов.')
    activate_templates.short_description = _('Activate selected templates')

    def deactivate_templates(self, request, queryset):
        """Деактивирует выбранные шаблоны"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано {updated} шаблонов.')
    deactivate_templates.short_description = _('Deactivate selected templates')

    def apply_to_providers(self, request, queryset):
        """Применяет выбранные шаблоны к учреждениям"""
        from providers.models import Provider
        total_applied = 0
        
        for template in queryset:
            # Находим учреждения, подходящие под шаблон
            providers = Provider.objects.filter(is_active=True)
            
            if template.country:
                providers = providers.filter(
                    structured_address__formatted_address__icontains=template.country
                )
            if template.region:
                providers = providers.filter(
                    structured_address__formatted_address__icontains=template.region
                )
            if template.city:
                providers = providers.filter(
                    structured_address__formatted_address__icontains=template.city
                )
            
            # Применяем шаблон к найденным учреждениям
            # Теперь применяем к LegalDocument (side_letter) (если есть) или создаем их
            from legal.models import LegalDocument, LegalDocumentType
            from django.utils import timezone
            
            side_letter_type = LegalDocumentType.objects.filter(code='side_letter').first()
            if not side_letter_type:
                self.message_user(request, _('Side Letter document type not found. Please create it first.'), level='error')
                return
            
            for provider in providers:
                # Проверяем, есть ли у провайдера Side Letter
                side_letter = provider.legal_documents.filter(
                    document_type=side_letter_type,
                    is_active=True
                ).first()
                
                if not side_letter:
                    # Создаем новый Side Letter для провайдера
                    side_letter = LegalDocument.objects.create(
                        document_type=side_letter_type,
                        version='1.0',
                        title=f'Side Letter for {provider.name}',
                        effective_date=timezone.now().date(),
                        is_active=True,
                        debt_threshold=template.debt_threshold,
                        overdue_threshold_1=template.overdue_threshold_1,
                        overdue_threshold_2=template.overdue_threshold_2,
                        overdue_threshold_3=template.overdue_threshold_3,
                    )
                    side_letter.providers.add(provider)
                else:
                    # Обновляем пороги блокировки из шаблона
                    side_letter.debt_threshold = template.debt_threshold
                    side_letter.overdue_threshold_1 = template.overdue_threshold_1
                    side_letter.overdue_threshold_2 = template.overdue_threshold_2
                    side_letter.overdue_threshold_3 = template.overdue_threshold_3
                    side_letter.is_active = True
                    side_letter.save()
                
                total_applied += 1
        
        self.message_user(request, _('Templates applied to %(count)s providers.') % {'count': total_applied})
    apply_to_providers.short_description = _('Apply templates to providers')

    def save_model(self, request, obj, form, change):
        """Сохраняет модель и создает запись в истории"""
        if change:
            # Получаем старые значения
            old_obj = self.model.objects.get(pk=obj.pk)
            previous_values = {
                'name': old_obj.name,
                'debt_threshold': str(old_obj.debt_threshold),
                'overdue_threshold_1': old_obj.overdue_threshold_1,
                'overdue_threshold_2': old_obj.overdue_threshold_2,
                'overdue_threshold_3': old_obj.overdue_threshold_3,
                'is_active': old_obj.is_active,
            }
            new_values = {
                'name': obj.name,
                'debt_threshold': str(obj.debt_threshold),
                'overdue_threshold_1': obj.overdue_threshold_1,
                'overdue_threshold_2': obj.overdue_threshold_2,
                'overdue_threshold_3': obj.overdue_threshold_3,
                'is_active': obj.is_active,
            }
            
            # Создаем запись в истории
            BlockingTemplateHistory.objects.create(
                template=obj,
                changed_by=request.user,
                change_type='updated',
                previous_values=previous_values,
                new_values=new_values,
                change_reason=form.cleaned_data.get('change_reason', '')
            )
        else:
            # Создаем запись в истории для нового шаблона
            BlockingTemplateHistory.objects.create(
                template=obj,
                changed_by=request.user,
                change_type='created',
                new_values={
                    'name': obj.name,
                    'debt_threshold': str(obj.debt_threshold),
                    'overdue_threshold_1': obj.overdue_threshold_1,
                    'overdue_threshold_2': obj.overdue_threshold_2,
                    'overdue_threshold_3': obj.overdue_threshold_3,
                    'is_active': obj.is_active,
                }
            )
        
        super().save_model(request, obj, form, change)


class BlockingTemplateHistoryAdmin(admin.ModelAdmin):
    """
    Административное представление для истории изменений шаблонов блокировки.
    """
    list_display = ('template', 'changed_by', 'change_type', 'created_at')
    list_filter = ('change_type', 'created_at', 'template')
    search_fields = ('template__name', 'changed_by__email', 'change_reason')
    readonly_fields = ('template', 'changed_by', 'change_type', 'previous_values', 'new_values', 'change_reason', 'created_at')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('template', 'changed_by', 'change_type', 'created_at')
        }),
        (_('Change Details'), {
            'fields': ('previous_values', 'new_values', 'change_reason'),
            'classes': ('collapse',)
        })
    )

    def has_add_permission(self, request):
        """История создается автоматически"""
        return False

    def has_change_permission(self, request, obj=None):
        """История не должна изменяться"""
        return False

    def has_delete_permission(self, request, obj=None):
        """История не должна удаляться для сохранения аудита"""
        return False


class BlockingSystemSettingsAdmin(admin.ModelAdmin):
    """
    Административное представление для глобальных настроек системы блокировки.
    """
    list_display = ('id', 'is_system_enabled', 'check_frequency_hours', 'check_time', 'updated_at')
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    fieldsets = (
        (_('System Status'), {
            'fields': ('is_system_enabled',)
        }),
        (_('Check Schedule'), {
            'fields': ('check_frequency_hours', 'check_time'),
            'description': _('Configure when and how often to check for blocking conditions.')
        }),
        (_('Notifications'), {
            'fields': ('notification_delay_hours', 'notify_billing_managers', 'notify_provider_admins'),
            'description': _('Configure notification settings.')
        }),
        (_('Auto Resolution'), {
            'fields': ('auto_resolve_on_payment',),
            'description': _('Configure automatic blocking resolution.')
        }),
        (_('Working Days'), {
            'fields': ('working_days', 'exclude_holidays'),
            'description': _('Configure working days for overdue calculations.')
        }),
        (_('Logging'), {
            'fields': ('log_all_checks', 'log_resolutions'),
            'description': _('Configure logging settings.')
        }),
        (_('Metadata'), {
            'fields': ('id', 'created_at', 'updated_at', 'updated_by'),
            'classes': ('collapse',)
        })
    )

    def has_add_permission(self, request):
        """Только одна запись настроек разрешена"""
        return not BlockingSystemSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Настройки не должны удаляться"""
        return False

    def save_model(self, request, obj, form, change):
        """Сохраняет модель с указанием пользователя"""
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


class BlockingScheduleAdmin(admin.ModelAdmin):
    """
    Административное представление для расписаний блокировок.
    """
    list_display = ('name', 'frequency', 'time', 'is_active', 'last_run', 'next_run')
    list_filter = ('frequency', 'is_active')
    search_fields = ('name',)
    readonly_fields = ('last_run', 'next_run', 'created_at', 'updated_at')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'is_active')
        }),
        (_('Schedule Settings'), {
            'fields': ('frequency', 'time'),
            'description': _('Configure the frequency and time for blocking checks.')
        }),
        (_('Advanced Settings'), {
            'fields': ('days_of_week', 'day_of_month', 'custom_interval_hours'),
            'classes': ('collapse',),
            'description': _('Advanced settings for specific frequency types.')
        }),
        (_('Execution Status'), {
            'fields': ('last_run', 'next_run'),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    actions = ['activate_schedules', 'deactivate_schedules', 'run_schedules_now']

    def activate_schedules(self, request, queryset):
        """Активирует выбранные расписания"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Активировано {updated} расписаний.')
    activate_schedules.short_description = _('Activate selected schedules')

    def deactivate_schedules(self, request, queryset):
        """Деактивирует выбранные расписания"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано {updated} расписаний.')
    deactivate_schedules.short_description = _('Deactivate selected schedules')

    def run_schedules_now(self, request, queryset):
        """Запускает выбранные расписания немедленно"""
        from .tasks import check_all_providers_blocking
        
        for schedule in queryset:
            if schedule.is_active:
                # Запускаем задачу проверки блокировок
                task = check_all_providers_blocking.delay()
                
                # Отмечаем расписание как выполненное
                schedule.mark_as_run()
                
                self.message_user(
                    request, 
                    f'Расписание "{schedule.name}" запущено. Task ID: {task.id}'
                )
    run_schedules_now.short_description = _('Run selected schedules now')

    def get_form(self, request, obj=None, **kwargs):
        """Настраивает форму в зависимости от выбранной частоты"""
        form = super().get_form(request, obj, **kwargs)
        
        if obj:
            # Скрываем поля, не относящиеся к выбранной частоте
            if obj.frequency != 'weekly':
                form.base_fields['days_of_week'].widget = HiddenInput()
            if obj.frequency != 'monthly':
                form.base_fields['day_of_month'].widget = HiddenInput()
            if obj.frequency != 'custom':
                form.base_fields['custom_interval_hours'].widget = HiddenInput()
        
        return form

    def save_model(self, request, obj, form, change):
        """Сохраняет модель и пересчитывает следующее время выполнения"""
        super().save_model(request, obj, form, change)
        
        # Пересчитываем следующее время выполнения
        if change:  # Только для существующих записей
            obj.calculate_next_run()


# Админ-класс для валют
class CurrencyAdmin(admin.ModelAdmin):
    """
    Административное представление для валют.
    """
    list_display = ('code', 'name', 'symbol', 'exchange_rate', 'is_active', 'last_updated')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('code', 'name', 'symbol', 'is_active')
        }),
        (_('Exchange Rate'), {
            'fields': ('exchange_rate', 'last_updated')
        })
    )
    readonly_fields = ('last_updated',)
    
    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к валютам.
        Биллинг-менеджер имеет доступ только для просмотра.
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            _is_system_admin(user) or
            user.is_billing_manager()
        )
    
    def has_view_permission(self, request, obj=None):
        """Биллинг-менеджер может просматривать валюты"""
        return self.has_module_permission(request)
    
    def has_add_permission(self, request):
        """Только системный админ может добавлять валюты"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')
    
    def has_change_permission(self, request, obj=None):
        """Только системный админ может изменять валюты"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')
    
    def has_delete_permission(self, request, obj=None):
        """Только системный админ может удалять валюты"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')


class VATRateAdmin(admin.ModelAdmin):
    """
    Административное представление для ставок НДС.
    """
    list_display = ('country', 'rate', 'effective_date', 'is_active', 'created_at')
    list_filter = ('is_active', 'country', 'effective_date')
    search_fields = ('country',)
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('country', 'rate', 'effective_date', 'is_active')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at')
        })
    )
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'effective_date'
    
    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к ставкам НДС.
        Биллинг-менеджер имеет доступ только для просмотра.
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            _is_system_admin(user) or
            user.is_billing_manager()
        )
    
    def has_view_permission(self, request, obj=None):
        """Биллинг-менеджер может просматривать ставки НДС"""
        return self.has_module_permission(request)
    
    def has_add_permission(self, request):
        """Только системный админ может добавлять ставки НДС"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')
    
    def has_change_permission(self, request, obj=None):
        """Только системный админ может изменять ставки НДС"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')
    
    def has_delete_permission(self, request, obj=None):
        """Только системный админ может удалять ставки НДС"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')


class PlatformCompanyAdmin(admin.ModelAdmin):
    """
    Административное представление для реквизитов платформы.
    """
    list_display = ('name', 'tax_id', 'bank_name', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'tax_id', 'bank_name', 'countries__country')
    filter_horizontal = ('countries',)
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'address', 'tax_id', 'is_active')
        }),
        (_('Bank Details'), {
            'fields': ('bank_name', 'iban', 'bic', 'swift')
        }),
        (_('Coverage'), {
            'fields': ('countries',)
        }),
        (_('Signature Assets'), {
            'fields': ('seal_scan', 'signature_scan'),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at')

    def has_module_permission(self, request):
        """Только системный админ имеет доступ к реквизитам платформы."""
        return request.user.is_superuser or _is_system_admin(request.user)


# ============================================================================
# АДМИН-ПАНЕЛЬ ДЛЯ BILLING CONFIG
# ============================================================================

class BillingConfigAdmin(admin.ModelAdmin):
    """Административное представление для конфигурации биллинга"""
    list_display = ('name', 'commission_percent', 'payment_deferral_days', 'invoice_period_days', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'description', 'is_active')
        }),
        (_('Billing Parameters'), {
            'fields': ('commission_percent', 'payment_deferral_days', 'invoice_period_days'),
            'description': _('These values will be substituted into offer text as variables: {{commission_percent}}, {{payment_deferral_days}}, {{invoice_period_days}}')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')
    
    def has_module_permission(self, request):
        """Только системный админ имеет доступ к конфигурации биллинга"""
        return request.user.is_superuser or _is_system_admin(request.user)


# ============================================================================
# АДМИН-ПАНЕЛЬ ДЛЯ ПУБЛИЧНОЙ ОФЕРТЫ
# ============================================================================

# УДАЛЕНО: RegionalAddendumAdmin и PublicOfferAdmin - модели удалены
# Используйте LegalDocumentAdmin в разделе Legal


# ProviderOfferAcceptanceAdmin удален - используйте DocumentAcceptanceAdmin в разделе Legal
    
    def has_add_permission(self, request):
        """Только системный админ может добавлять акцепты (обычно создаются автоматически)"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')
    
    def has_change_permission(self, request, obj=None):
        """Только системный админ может изменять акцепты"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')
    
    def has_delete_permission(self, request, obj=None):
        """Только системный админ может удалять акцепты"""
        return request.user.is_superuser or user_has_role(request.user, 'system_admin')


# УДАЛЕНО: ProviderSpecialTermsAdmin и SideLetterAdmin
# Модели ProviderSpecialTerms и SideLetter удалены
# Используйте LegalDocumentAdmin в приложении legal для управления Side Letter (тип side_letter)


# Регистрация моделей в админ-панели
custom_admin_site.register(Currency, CurrencyAdmin)
custom_admin_site.register(PlatformCompany, PlatformCompanyAdmin)
# Регистрации Contract, ContractType, ContractCommission, ContractDiscount удалены
custom_admin_site.register(Invoice, InvoiceAdmin)
custom_admin_site.register(PaymentHistory, PaymentHistoryAdmin)
custom_admin_site.register(Payment, PaymentAdmin)
custom_admin_site.register(Refund, RefundAdmin)
custom_admin_site.register(BillingManagerProvider, BillingManagerProviderAdmin)
custom_admin_site.register(BillingManagerEvent, BillingManagerEventAdmin)
custom_admin_site.register(BlockingRule, BlockingRuleAdmin)
custom_admin_site.register(ProviderBlocking, ProviderBlockingAdmin)
custom_admin_site.register(BlockingNotification, BlockingNotificationAdmin)
custom_admin_site.register(BlockingTemplate, BlockingTemplateAdmin)
custom_admin_site.register(BlockingTemplateHistory, BlockingTemplateHistoryAdmin)
custom_admin_site.register(BlockingSystemSettings, BlockingSystemSettingsAdmin)
custom_admin_site.register(BlockingSchedule, BlockingScheduleAdmin)

# Регистрация BillingConfig
custom_admin_site.register(BillingConfig, BillingConfigAdmin)

# DEPRECATED: Модели PublicOffer и RegionalAddendum заменены на LegalDocument в приложении legal
# Регистрация удалена - используйте Legal Documents в разделе Legal
# ProviderOfferAcceptance удален - используйте DocumentAcceptance из приложения legal
# ProviderSpecialTerms и SideLetter удалены - используйте LegalDocument с типом side_letter в приложении legal

# Регистрация VATRate
custom_admin_site.register(VATRate, VATRateAdmin)


class BillingReportAdmin(admin.ModelAdmin):
    """
    Кастомный раздел отчетов по биллингу (экспорт и дашборд).
    """
    change_list_template = "admin/billing/reports_dashboard.html"

    def get_urls(self):
        """Добавляет кастомные страницы отчетов в раздел billing."""
        urls = super().get_urls()
        custom_urls = [
            path('', self.admin_site.admin_view(self.reports_dashboard), name='billing-reports-dashboard'),
            path('invoice-export/', self.admin_site.admin_view(self.invoice_export_view), name='billing-invoice-export'),
            path('provider-debt/', self.admin_site.admin_view(self.provider_debt_report_view), name='billing-provider-debt-report'),
            path('revenue/', self.admin_site.admin_view(self.revenue_report_view), name='billing-revenue-report'),
            path('aging/', self.admin_site.admin_view(self.aging_report_view), name='billing-aging-report'),
        ]
        return custom_urls + urls

    def reports_dashboard(self, request):
        """Отображает дашборд ссылок на биллинговые отчеты."""
        context = dict(
            self.admin_site.each_context(request),
            provider_debt_url=reverse('admin:billing-provider-debt-report'),
            revenue_report_url=reverse('admin:billing-revenue-report'),
            aging_report_url=reverse('admin:billing-aging-report'),
            blocked_providers_url=reverse('admin:billing_providerblocking_changelist'),
            payment_history_url=reverse('admin:billing_payment_changelist'),
            invoice_list_url=reverse('admin:billing_invoice_changelist'),
            invoice_export_url=reverse('admin:billing-invoice-export'),
        )
        return render(request, "admin/billing/reports_dashboard.html", context)

    def invoice_export_view(self, request):
        """Экспортирует список счетов в Excel."""
        invoices = Invoice.objects.all().select_related('provider', 'currency')
        rows = [
            [
                inv.number,
                str(inv.provider) if inv.provider else "",
                str(inv.amount),
                inv.currency.code if inv.currency else "",
                inv.status,
                inv.issued_at.strftime('%Y-%m-%d') if inv.issued_at else "",
            ]
            for inv in invoices
        ]
        return build_excel_response(
            'InvoicesExport.xlsx',
            'Invoices',
            [
                str(_("Number")),
                str(_("Provider")),
                str(_("Amount")),
                str(_("Currency")),
                str(_("Status")),
                str(_("Issued At")),
            ],
            rows,
        )

    def provider_debt_report_view(self, request):
        """Отображает отчет по задолженности провайдеров."""
        rows = self._build_provider_debt_rows(request)
        columns = [
            {'key': 'provider', 'label': _('Provider')},
            {'key': 'total_debt', 'label': _('Total Debt')},
            {'key': 'currency', 'label': _('Currency')},
            {'key': 'unpaid_invoices', 'label': _('Unpaid Invoices')},
            {'key': 'max_overdue_days', 'label': _('Max Overdue Days')},
            {'key': 'country', 'label': _('Country')},
        ]
        return self._render_report(
            request=request,
            title=_('Provider Debt Report'),
            sheet_title='Provider Debt',
            file_name='ProviderDebtReport.xlsx',
            columns=columns,
            rows=rows,
            export_name='billing-provider-debt-report',
        )

    def revenue_report_view(self, request):
        """Отображает агрегированный отчет по выручке."""
        rows = self._build_revenue_rows(request)
        columns = [
            {'key': 'period', 'label': _('Period')},
            {'key': 'currency', 'label': _('Currency')},
            {'key': 'invoice_count', 'label': _('Invoice Count')},
            {'key': 'invoiced_amount', 'label': _('Invoiced Amount')},
            {'key': 'paid_amount', 'label': _('Paid Amount')},
        ]
        return self._render_report(
            request=request,
            title=_('Revenue Report'),
            sheet_title='Revenue',
            file_name='RevenueReport.xlsx',
            columns=columns,
            rows=rows,
            export_name='billing-revenue-report',
        )

    def aging_report_view(self, request):
        """Отображает отчет по aging buckets дебиторской задолженности."""
        rows = self._build_aging_rows(request)
        columns = [
            {'key': 'provider', 'label': _('Provider')},
            {'key': 'currency', 'label': _('Currency')},
            {'key': 'bucket_0_30', 'label': _('0-30 Days')},
            {'key': 'bucket_31_60', 'label': _('31-60 Days')},
            {'key': 'bucket_61_90', 'label': _('61-90 Days')},
            {'key': 'bucket_over_90', 'label': _('Over 90 Days')},
            {'key': 'total', 'label': _('Total')},
        ]
        return self._render_report(
            request=request,
            title=_('Aging Report'),
            sheet_title='Aging',
            file_name='AgingReport.xlsx',
            columns=columns,
            rows=rows,
            export_name='billing-aging-report',
        )

    def _render_report(self, request, title, sheet_title, file_name, columns, rows, export_name):
        """
        Унифицированно рендерит HTML-страницу отчета или отдает Excel.
        """
        if request.GET.get('export') == 'xlsx':
            return build_excel_response(
                file_name,
                sheet_title,
                [str(column['label']) for column in columns],
                [[row[column['key']] for column in columns] for row in rows],
            )

        export_query = request.GET.copy()
        export_query['export'] = 'xlsx'
        table_rows = [
            {
                'raw': row,
                'values': [row[column['key']] for column in columns],
            }
            for row in rows
        ]
        context = dict(
            self.admin_site.each_context(request),
            title=title,
            report_title=title,
            columns=columns,
            rows=table_rows,
            export_url=f"{reverse(f'admin:{export_name}')}?{export_query.urlencode()}",
            q=request.GET.get('q', ''),
            country=request.GET.get('country', ''),
            currency=request.GET.get('currency', ''),
            has_debt=request.GET.get('has_debt', ''),
            year=request.GET.get('year', ''),
            month=request.GET.get('month', ''),
            ordering=request.GET.get('ordering', ''),
        )
        return render(request, 'admin/billing/report_list.html', context)

    def _build_provider_debt_rows(self, request):
        """
        Собирает строки отчета по задолженности провайдеров.
        """
        providers = Provider.objects.filter(is_active=True).prefetch_related(
            'payment_history__currency',
            'invoices',
        ).select_related('invoice_currency')

        search_query = request.GET.get('q', '').strip()
        country = request.GET.get('country', '').strip()
        currency = request.GET.get('currency', '').strip()
        has_debt = request.GET.get('has_debt', '').strip()
        ordering = request.GET.get('ordering', 'provider')
        today = timezone.now().date()

        if search_query:
            providers = providers.filter(name__icontains=search_query)
        if country:
            providers = providers.filter(country=country)

        rows = []
        for provider in providers:
            payment_records = [
                record for record in provider.payment_history.all()
                if record.outstanding_amount > Decimal('0.00')
            ]
            total_debt = sum((record.outstanding_amount for record in payment_records), Decimal('0.00'))
            invoice_ids = {record.invoice_id for record in payment_records if record.invoice_id}
            max_overdue_days = max(
                (
                    (today - record.due_date).days
                    for record in payment_records
                    if record.due_date < today
                ),
                default=0,
            )
            currency_code = (
                provider.invoice_currency.code if provider.invoice_currency
                else (payment_records[0].currency.code if payment_records else '')
            )

            if currency and currency_code != currency:
                continue
            if has_debt == 'yes' and total_debt <= Decimal('0.00'):
                continue
            if has_debt == 'no' and total_debt > Decimal('0.00'):
                continue

            rows.append({
                'provider': provider.name,
                'total_debt': total_debt,
                'currency': currency_code,
                'unpaid_invoices': len(invoice_ids),
                'max_overdue_days': max_overdue_days,
                'country': str(provider.country or ''),
            })

        return self._sort_rows(rows, ordering, default_key='provider')

    def _build_revenue_rows(self, request):
        """
        Собирает строки отчета по выручке по месяцам и годам.
        """
        invoices = Invoice.objects.select_related('currency').prefetch_related('payment_history').exclude(status='draft')
        year = request.GET.get('year', '').strip()
        month = request.GET.get('month', '').strip()
        ordering = request.GET.get('ordering', '-period')

        if year.isdigit():
            invoices = invoices.filter(issued_at__year=int(year))
        if month.isdigit():
            invoices = invoices.filter(issued_at__month=int(month))

        grouped_rows = {}
        for invoice in invoices:
            period = invoice.issued_at.strftime('%Y-%m')
            currency_code = invoice.currency.code if invoice.currency else ''
            key = (period, currency_code)
            payment_record = invoice.payment_record
            paid_amount = Decimal('0.00')
            if payment_record is not None:
                paid_amount = max(
                    payment_record.paid_amount - payment_record.refunded_amount,
                    Decimal('0.00'),
                )

            row = grouped_rows.setdefault(
                key,
                {
                    'period': period,
                    'currency': currency_code,
                    'invoice_count': 0,
                    'invoiced_amount': Decimal('0.00'),
                    'paid_amount': Decimal('0.00'),
                }
            )
            row['invoice_count'] += 1
            row['invoiced_amount'] += invoice.amount
            row['paid_amount'] += paid_amount

        return self._sort_rows(list(grouped_rows.values()), ordering, default_key='period')

    def _build_aging_rows(self, request):
        """
        Собирает строки aging report по провайдерам.
        """
        providers = Provider.objects.filter(is_active=True).prefetch_related(
            'payment_history__currency'
        ).select_related('invoice_currency')
        search_query = request.GET.get('q', '').strip()
        currency = request.GET.get('currency', '').strip()
        ordering = request.GET.get('ordering', 'provider')
        today = timezone.now().date()

        if search_query:
            providers = providers.filter(name__icontains=search_query)

        rows = []
        for provider in providers:
            buckets = {
                'bucket_0_30': Decimal('0.00'),
                'bucket_31_60': Decimal('0.00'),
                'bucket_61_90': Decimal('0.00'),
                'bucket_over_90': Decimal('0.00'),
            }
            payment_records = [
                record for record in provider.payment_history.all()
                if record.outstanding_amount > Decimal('0.00')
            ]
            currency_code = (
                provider.invoice_currency.code if provider.invoice_currency
                else (payment_records[0].currency.code if payment_records else '')
            )
            if currency and currency_code != currency:
                continue

            for record in payment_records:
                overdue_days = max((today - record.due_date).days, 0)
                if overdue_days <= 30:
                    buckets['bucket_0_30'] += record.outstanding_amount
                elif overdue_days <= 60:
                    buckets['bucket_31_60'] += record.outstanding_amount
                elif overdue_days <= 90:
                    buckets['bucket_61_90'] += record.outstanding_amount
                else:
                    buckets['bucket_over_90'] += record.outstanding_amount

            total_amount = sum(buckets.values(), Decimal('0.00'))
            if total_amount <= Decimal('0.00'):
                continue

            rows.append({
                'provider': provider.name,
                'currency': currency_code,
                'bucket_0_30': buckets['bucket_0_30'],
                'bucket_31_60': buckets['bucket_31_60'],
                'bucket_61_90': buckets['bucket_61_90'],
                'bucket_over_90': buckets['bucket_over_90'],
                'total': total_amount,
            })

        return self._sort_rows(rows, ordering, default_key='provider')

    def _sort_rows(self, rows, ordering, default_key):
        """
        Сортирует подготовленные строки отчета.
        """
        if not rows:
            return rows

        reverse_order = ordering.startswith('-')
        sort_key = ordering[1:] if reverse_order else ordering
        if sort_key not in rows[0]:
            sort_key = default_key
        return sorted(rows, key=lambda row: row[sort_key], reverse=reverse_order)

    def has_module_permission(self, request):
        """Проверяет доступ к разделу отчетов биллинга."""
        user = request.user
        if not user.is_authenticated:
            return False
        return user.is_superuser or _is_system_admin(user) or user.is_billing_manager()

    def has_view_permission(self, request, obj=None):
        """Проверяет право просмотра отчетов биллинга."""
        return self.has_module_permission(request)

custom_admin_site.register(BillingReport, BillingReportAdmin)
