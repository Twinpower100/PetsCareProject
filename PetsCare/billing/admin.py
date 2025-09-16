"""
Admin views for the billing module.

Этот модуль содержит административные представления для:
1. Управления типами контрактов
2. Управления контрактами
3. Управления комиссиями и скидками
4. Управления счетами и платежами
5. Генерации отчетов по биллингу
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    ContractType, Contract, ContractCommission, ContractDiscount,
    Invoice, Payment, Refund, BillingManagerProvider, BillingManagerEvent,
    BlockingRule, ProviderBlocking, BlockingNotification, BlockingTemplate, BlockingTemplateHistory, BlockingSystemSettings, BlockingSchedule
)
from django.urls import path
from django.shortcuts import render, redirect

def user_has_role(user, role_name):
    """Безопасная проверка роли пользователя"""
    if not user.is_authenticated:
        return False
    return hasattr(user, 'has_role') and user.has_role(role_name)
from django.contrib import messages
from providers.models import Provider
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
import openpyxl
from django.http import HttpResponse
from custom_admin import custom_admin_site
from django.forms import HiddenInput


class ContractTypeAdmin(admin.ModelAdmin):
    """
    Административное представление для типов контрактов.
    """
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'description')
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'code', 'is_active')
        }),
        (_('Description'), {
            'fields': ('description',),
            'classes': ('collapse',)
        })
    )


class ContractCommissionInline(admin.TabularInline):
    """
    Встроенное представление для комиссий контракта.
    """
    model = ContractCommission
    extra = 0
    fields = ('service', 'rate', 'fixed_amount', 'period', 'start_date', 'end_date', 'is_active')
    readonly_fields = ('created_at', 'updated_at')


class ContractDiscountInline(admin.TabularInline):
    """
    Встроенное представление для скидок контракта.
    """
    model = ContractDiscount
    extra = 0
    fields = ('service', 'rate', 'fixed_amount', 'start_date', 'end_date', 'is_active')
    readonly_fields = ('created_at', 'updated_at')


class ContractAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для модели договора.
    """
    list_display = [
        'number', 'provider', 'contract_type',
        'start_date', 'end_date', 'status', 'get_blocking_level'
    ]
    list_filter = ['status', 'contract_type', 'start_date', 'end_date']
    search_fields = ['number', 'provider__name', 'terms']
    date_hierarchy = 'start_date'
    inlines = [ContractCommissionInline, ContractDiscountInline]
    actions = ['set_default_blocking_thresholds', 'apply_mass_blocking_rules']
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('provider', 'contract_type', 'number', 'status')
        }),
        (_('Dates'), {
            'fields': ('start_date', 'end_date')
        }),
        (_('Financial'), {
            'fields': ('currency', 'base_currency', 'payment_deferral_days')
        }),
        (_('Blocking Thresholds'), {
            'fields': ('debt_threshold', 'overdue_threshold_1', 'overdue_threshold_2', 'overdue_threshold_3'),
            'description': _('Configure automatic blocking thresholds.')
        }),
        (_('Blocking Exclusions'), {
            'fields': ('exclude_from_automatic_blocking', 'blocking_exclusion_reason'),
            'classes': ('collapse',),
            'description': _('Configure exclusions from automatic blocking checks.')
        }),
        (_('Invoice Settings'), {
            'fields': ('invoice_period', 'invoice_period_value'),
            'classes': ('collapse',)
        }),
        (_('Document'), {
            'fields': ('document', 'document_name'),
            'classes': ('collapse',)
        }),
        (_('Terms'), {
            'fields': ('terms',),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_by', 'created_at', 'updated_at')
    
    def get_blocking_level(self, obj):
        """Отображает текущий уровень блокировки договора."""
        if hasattr(obj, 'get_blocking_level'):
            level = obj.get_blocking_level()
            if level == 0:
                return _("No blocking")
            elif level == 1:
                return _("Info notification")
            elif level == 2:
                return _("Search exclusion")
            elif level == 3:
                return _("Full blocking")
        return _("Not defined")
    get_blocking_level.short_description = _('Blocking Level')
    
    def set_default_blocking_thresholds(self, request, queryset):
        """Устанавливает стандартные пороги блокировки для выбранных договоров."""
        updated = queryset.update(
            debt_threshold=10000.00,
            overdue_threshold_1=7,
            overdue_threshold_2=30,
            overdue_threshold_3=60
        )
        self.message_user(request, _('Default thresholds set for %(count)d contracts.') % {'count': updated})
    set_default_blocking_thresholds.short_description = _('Set default blocking thresholds')
    
    def apply_mass_blocking_rules(self, request, queryset):
        """Применяет массовые правила блокировки."""
        from .services import MultiLevelBlockingService
        
        total_processed = 0
        for contract in queryset:
            if contract.provider:
                result = MultiLevelBlockingService.check_provider_debt(contract.provider)
                if result['blocking_level'] > 0:
                    total_processed += 1
        
        self.message_user(request, _('Processed %(count)d providers with blocking rules.') % {'count': total_processed})
    apply_mass_blocking_rules.short_description = _('Apply mass blocking rules')

    def get_queryset(self, request):
        """
        Возвращает queryset с учетом прав доступа пользователя.
        """
        qs = super().get_queryset(request)
        if user_has_role(request.user, 'billing_manager'):
            # Менеджер по биллингу видит все активные провайдеры
            return qs.filter(provider__in=Provider.objects.filter(is_active=True))
        return qs

    def has_change_permission(self, request, obj=None):
        """
        Проверяет права на изменение контракта.
        """
        if request.user.is_superuser or user_has_role(request.user, 'system_admin'):
            return True
        if user_has_role(request.user, 'billing_manager'):
            # Менеджер по биллингу может изменять контракты всех активных провайдеров
            if obj is None:
                return True
            return obj.provider.is_active
        return False

    def has_delete_permission(self, request, obj=None):
        """
        Проверяет права на удаление контракта.
        """
        return request.user.is_superuser or (hasattr(request.user, 'user_type') and request.user.is_system_admin())


class ContractCommissionAdmin(admin.ModelAdmin):
    """
    Административное представление для комиссий контрактов.
    """
    list_display = ('contract', 'service', 'rate', 'fixed_amount', 'period', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'period', 'start_date', 'end_date')
    search_fields = ('contract__number', 'service__name')
    date_hierarchy = 'start_date'
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('contract', 'service')
        }),
        (_('Commission Details'), {
            'fields': ('rate', 'fixed_amount', 'period')
        }),
        (_('Dates'), {
            'fields': ('start_date', 'end_date', 'is_active')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')


class ContractDiscountAdmin(admin.ModelAdmin):
    """
    Административное представление для скидок контрактов.
    """
    list_display = ('contract', 'service', 'rate', 'fixed_amount', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'start_date', 'end_date')
    search_fields = ('contract__number', 'service__name')
    date_hierarchy = 'start_date'
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('contract', 'service')
        }),
        (_('Discount Details'), {
            'fields': ('rate', 'fixed_amount')
        }),
        (_('Dates'), {
            'fields': ('start_date', 'end_date', 'is_active')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')


class InvoiceAdmin(admin.ModelAdmin):
    """
    Административное представление для счетов.
    """
    list_display = ('number', 'provider', 'start_date', 'end_date', 'amount', 'currency', 'status', 'issued_at')
    list_filter = ('status', 'currency', 'issued_at')
    search_fields = ('number', 'provider__name')
    date_hierarchy = 'issued_at'
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('provider', 'number', 'status')
        }),
        (_('Period'), {
            'fields': ('start_date', 'end_date')
        }),
        (_('Financial Details'), {
            'fields': ('amount', 'currency')
        }),
        (_('Metadata'), {
            'fields': ('issued_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('issued_at', 'created_at', 'updated_at')


class PaymentAdmin(admin.ModelAdmin):
    """
    Административное представление для платежей.
    """
    list_display = ('booking', 'amount', 'status', 'payment_method', 'created_at')
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('booking__pet__name', 'booking__provider_service__service__name', 'transaction_id')
    date_hierarchy = 'created_at'
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('booking', 'amount', 'status', 'payment_method')
        }),
        (_('Transaction Details'), {
            'fields': ('transaction_id',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')


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

    def has_add_permission(self, request):
        """
        Проверяет права на добавление связи.
        """
        return (request.user.is_superuser or 
                user_has_role(request.user, 'system_admin') or 
                user_has_role(request.user, 'billing_manager'))


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
        """
        # События не должны удаляться для сохранения аудита
        return False

    def has_add_permission(self, request):
        """
        Проверяет права на добавление события.
        """
        # События создаются автоматически, ручное добавление запрещено
        return False


@admin.register(BlockingRule)
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


@admin.register(ProviderBlocking)
class ProviderBlockingAdmin(admin.ModelAdmin):
    list_display = ('provider', 'blocking_rule', 'status', 'debt_amount', 'overdue_days', 'blocked_at', 'resolved_at')
    list_filter = ('status', 'blocking_rule', 'blocked_at')
    search_fields = ('provider__name', 'notes')
    actions = ['resolve_blockings']

    def resolve_blockings(self, request, queryset):
        for blocking in queryset.filter(status='active'):
            blocking.resolve(resolved_by=request.user, notes='Снято через админку')
    resolve_blockings.short_description = 'Снять выбранные блокировки (разблокировать)'


@admin.register(BlockingNotification)
class BlockingNotificationAdmin(admin.ModelAdmin):
    list_display = ('provider_blocking', 'notification_type', 'status', 'recipient_email', 'created_at', 'sent_at')
    list_filter = ('notification_type', 'status', 'created_at')
    search_fields = ('provider_blocking__provider__name', 'subject', 'message')


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


@admin.register(BlockingTemplate)
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
                providers = providers.filter(address__icontains=template.country)
            if template.region:
                providers = providers.filter(address__icontains=template.region)
            if template.city:
                providers = providers.filter(address__icontains=template.city)
            
            # Применяем шаблон к найденным учреждениям
            for provider in providers:
                contracts = provider.contracts.filter(status='active')
                for contract in contracts:
                    contract.debt_threshold = template.debt_threshold
                    contract.overdue_threshold_1 = template.overdue_threshold_1
                    contract.overdue_threshold_2 = template.overdue_threshold_2
                    contract.overdue_threshold_3 = template.overdue_threshold_3
                    contract.save()
                    total_applied += 1
        
        self.message_user(request, f'Шаблоны применены к {total_applied} договорам.')
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


@admin.register(BlockingTemplateHistory)
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


@admin.register(BlockingSystemSettings)
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


@admin.register(BlockingSchedule)
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


# Регистрация моделей в админ-панели
custom_admin_site.register(ContractType, ContractTypeAdmin)
custom_admin_site.register(Contract, ContractAdmin)
custom_admin_site.register(ContractCommission, ContractCommissionAdmin)
custom_admin_site.register(ContractDiscount, ContractDiscountAdmin)
custom_admin_site.register(Invoice, InvoiceAdmin)
custom_admin_site.register(Payment, PaymentAdmin)
custom_admin_site.register(Refund, RefundAdmin)
custom_admin_site.register(BillingManagerProvider, BillingManagerProviderAdmin)
custom_admin_site.register(BillingManagerEvent, BillingManagerEventAdmin)
