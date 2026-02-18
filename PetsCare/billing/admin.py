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
from django.core.exceptions import PermissionDenied
from django.http import Http404
from modeltranslation.admin import TranslationAdmin
from .models import (
    Currency, VATRate,
    Invoice, Payment, Refund, BillingManagerProvider, BillingManagerEvent,
    BlockingRule, ProviderBlocking, BlockingNotification, BlockingTemplate, BlockingTemplateHistory, BlockingSystemSettings, BlockingSchedule,
    BillingConfig
)
# УДАЛЕНО: ProviderSpecialTerms, SideLetter - используйте LegalDocument с типом side_letter в приложении legal
from django.urls import path, reverse
from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from django.utils.html import format_html

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
import openpyxl
from django.http import HttpResponse
from custom_admin import custom_admin_site
from django.forms import HiddenInput


# Админка для Contract, ContractType, ContractCommission, ContractDiscount удалена
# Используется LegalDocument и DocumentAcceptance из приложения legal


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
        return get_deleted_objects(objs, request, self.admin_site)
    
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
    list_display = ('provider', 'blocking_rule', 'status', 'debt_amount', 'overdue_days', 'blocked_at', 'resolved_at')
    list_filter = ('status', 'blocking_rule', 'blocked_at')
    search_fields = ('provider__name', 'notes')
    actions = ['resolve_blockings']

    def resolve_blockings(self, request, queryset):
        for blocking in queryset.filter(status='active'):
            blocking.resolve(resolved_by=request.user, notes='Снято через админку')
    resolve_blockings.short_description = 'Снять выбранные блокировки (разблокировать)'
    
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
# Регистрации Contract, ContractType, ContractCommission, ContractDiscount удалены
custom_admin_site.register(Invoice, InvoiceAdmin)
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
