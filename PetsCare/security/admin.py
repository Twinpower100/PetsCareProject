from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from django.core.cache import cache
import logging

from .models import SecurityThreat, IPBlacklist, ThreatPattern, SecurityPolicy, PolicyViolation, SessionPolicy, AccessPolicy, DataClassificationPolicy
from .services import get_ip_blocking_service

logger = logging.getLogger(__name__)

class SecurityAccessMixin:
    """Миксин для ограничения доступа к моделям безопасности только админам проекта"""
    
    def has_module_permission(self, request):
        return self._check_security_access(request)
    
    def has_view_permission(self, request, obj=None):
        return self._check_security_access(request)
    
    def has_add_permission(self, request):
        return self._check_security_access(request)
    
    def has_change_permission(self, request, obj=None):
        return self._check_security_access(request)
    
    def has_delete_permission(self, request, obj=None):
        return self._check_security_access(request)
    
    def _check_security_access(self, request):
        """Проверить доступ к моделям безопасности"""
        if not request.user.is_authenticated:
            self._log_unauthorized_access(request, "Unauthenticated user")
            return False
        
        if request.user.is_superuser:
            return True
        
        if request.user.is_staff and request.user.has_role('system_admin'):
            return True
        
        self._log_unauthorized_access(request, f"User {request.user.email} lacks required permissions")
        return False
    
    def _log_unauthorized_access(self, request, reason):
        """Логировать попытки несанкционированного доступа"""
        logger.warning(
            f"Unauthorized access attempt to security models: {reason}. "
            f"User: {getattr(request.user, 'email', 'Unknown')}, "
            f"IP: {request.META.get('REMOTE_ADDR', 'Unknown')}, "
            f"Path: {request.path}"
        )
    
    def get_queryset(self, request):
        """Ограничить queryset для неавторизованных пользователей"""
        if not self._check_security_access(request):
            return self.model.objects.none()
        return super().get_queryset(request)

@admin.register(SecurityThreat)
class SecurityThreatAdmin(SecurityAccessMixin, admin.ModelAdmin):
    """Админский интерфейс для угроз безопасности"""
    
    list_display = [
        'threat_type', 'severity', 'ip_address', 'user', 
        'detected_at', 'status', 'get_actions'
    ]
    
    list_filter = [
        'threat_type', 'severity', 'status', 'detected_at',
        ('user', admin.RelatedOnlyFieldListFilter),
    ]
    
    search_fields = [
        'ip_address', 'description', 'user__email', 'user_agent'
    ]
    
    readonly_fields = [
        'detected_at', 'ip_address', 'user_agent', 'request_path',
        'request_method', 'request_data', 'description'
    ]
    
    fieldsets = (
        (_('Threat Information'), {
            'fields': ('threat_type', 'severity', 'status', 'description')
        }),
        (_('Source Information'), {
            'fields': ('ip_address', 'user', 'user_agent')
        }),
        (_('Request Details'), {
            'fields': ('request_path', 'request_method', 'request_data'),
            'classes': ('collapse',)
        }),
        (_('Resolution'), {
            'fields': ('resolved_at', 'resolved_by', 'notes'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['resolve_threats', 'mark_false_positive', 'block_ip_addresses']
    
    def get_actions(self, obj):
        """Получить действия для угрозы"""
        if obj.status == 'active':
            return format_html(
                '<a href="{}" class="button">Resolve</a> '
                '<a href="{}" class="button">False Positive</a>',
                reverse('admin:security_securitythreat_resolve', args=[obj.pk]),
                reverse('admin:security_securitythreat_false_positive', args=[obj.pk])
            )
        return '-'
    get_actions.short_description = _('Actions')
    
    def resolve_threats(self, request, queryset):
        """Разрешить выбранные угрозы"""
        count = 0
        for threat in queryset.filter(status='active'):
            threat.resolve(resolved_by=request.user)
            count += 1
        
        self.message_user(
            request,
            f"Successfully resolved {count} threats.",
            messages.SUCCESS
        )
    resolve_threats.short_description = _("Resolve selected threats")
    
    def mark_false_positive(self, request, queryset):
        """Пометить как ложные срабатывания"""
        count = 0
        for threat in queryset.filter(status='active'):
            threat.mark_false_positive(resolved_by=request.user)
            count += 1
        
        self.message_user(
            request,
            f"Marked {count} threats as false positives.",
            messages.SUCCESS
        )
    mark_false_positive.short_description = _("Mark as false positive")
    
    def block_ip_addresses(self, request, queryset):
        """Заблокировать IP-адреса"""
        count = 0
        for threat in queryset:
            if get_ip_blocking_service().block_ip(
                threat.ip_address,
                f"Blocked due to threat: {threat.threat_type}",
                'manual',
                blocked_by=request.user
            ):
                count += 1
        
        self.message_user(
            request,
            f"Successfully blocked {count} IP addresses.",
            messages.SUCCESS
        )
    block_ip_addresses.short_description = _("Block IP addresses")
    
    def get_queryset(self, request):
        """Оптимизированный queryset"""
        return super().get_queryset(request).select_related('user', 'resolved_by')
    
    def has_add_permission(self, request):
        """Запретить создание угроз вручную"""
        return False


@admin.register(IPBlacklist)
class IPBlacklistAdmin(SecurityAccessMixin, admin.ModelAdmin):
    """Админский интерфейс для черного списка IP"""
    
    list_display = [
        'ip_address', 'block_type', 'threat_count', 'blocked_at',
        'expires_at', 'is_active', 'get_actions'
    ]
    
    list_filter = [
        'block_type', 'is_active', 'blocked_at',
        ('blocked_by', admin.RelatedOnlyFieldListFilter),
    ]
    
    search_fields = ['ip_address', 'reason']
    
    readonly_fields = ['blocked_at', 'threat_count']
    
    fieldsets = (
        (_('IP Information'), {
            'fields': ('ip_address', 'block_type', 'is_active')
        }),
        (_('Block Details'), {
            'fields': ('reason', 'blocked_at', 'expires_at', 'blocked_by')
        }),
        (_('Statistics'), {
            'fields': ('threat_count',),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['unblock_ips', 'extend_blocks']
    
    def get_actions(self, obj):
        """Получить действия для IP"""
        if obj.is_active:
            return format_html(
                '<a href="{}" class="button">Unblock</a>',
                reverse('admin:security_ipblacklist_unblock', args=[obj.pk])
            )
        return '-'
    get_actions.short_description = _('Actions')
    
    def unblock_ips(self, request, queryset):
        """Разблокировать выбранные IP"""
        count = 0
        for ip_block in queryset.filter(is_active=True):
            if get_ip_blocking_service().unblock_ip(ip_block.ip_address, request.user):
                count += 1
        
        self.message_user(
            request,
            f"Successfully unblocked {count} IP addresses.",
            messages.SUCCESS
        )
    unblock_ips.short_description = _("Unblock selected IPs")
    
    def extend_blocks(self, request, queryset):
        """Продлить блокировки"""
        count = 0
        for ip_block in queryset.filter(is_active=True):
            ip_block.expires_at = timezone.now() + timezone.timedelta(days=7)
            ip_block.save()
            count += 1
        
        self.message_user(
            request,
            f"Extended {count} IP blocks by 7 days.",
            messages.SUCCESS
        )
    extend_blocks.short_description = _("Extend blocks by 7 days")
    
    def get_queryset(self, request):
        """Оптимизированный queryset"""
        return super().get_queryset(request).select_related('blocked_by')


@admin.register(ThreatPattern)
class ThreatPatternAdmin(SecurityAccessMixin, admin.ModelAdmin):
    """Админский интерфейс для шаблонов угроз"""
    
    list_display = [
        'name', 'pattern_type', 'threat_type', 'severity',
        'is_active', 'created_at'
    ]
    
    list_filter = [
        'pattern_type', 'threat_type', 'severity', 'is_active',
        'created_at'
    ]
    
    search_fields = ['name', 'pattern', 'description']
    
    fieldsets = (
        (_('Pattern Information'), {
            'fields': ('name', 'pattern_type', 'pattern', 'description')
        }),
        (_('Threat Configuration'), {
            'fields': ('threat_type', 'severity', 'is_active')
        }),
    )
    
    actions = ['activate_patterns', 'deactivate_patterns']
    
    def activate_patterns(self, request, queryset):
        """Активировать шаблоны"""
        count = queryset.update(is_active=True)
        # Очистить кэш шаблонов
        cache.delete('security_patterns')
        
        self.message_user(
            request,
            f"Activated {count} patterns.",
            messages.SUCCESS
        )
    activate_patterns.short_description = _("Activate selected patterns")
    
    def deactivate_patterns(self, request, queryset):
        """Деактивировать шаблоны"""
        count = queryset.update(is_active=False)
        # Очистить кэш шаблонов
        cache.delete('security_patterns')
        
        self.message_user(
            request,
            f"Deactivated {count} patterns.",
            messages.SUCCESS
        )
    deactivate_patterns.short_description = _("Deactivate selected patterns")
    
    def save_model(self, request, obj, form, change):
        """Сохранить модель и очистить кэш"""
        super().save_model(request, obj, form, change)
        # Очистить кэш шаблонов
        cache.delete('security_patterns')


# === НОВЫЕ АДМИНСКИЕ КЛАССЫ ДЛЯ ПОЛИТИК БЕЗОПАСНОСТИ ===

@admin.register(SecurityPolicy)
class SecurityPolicyAdmin(SecurityAccessMixin, admin.ModelAdmin):
    """Админский интерфейс для политик безопасности"""
    
    list_display = [
        'name', 'policy_type', 'severity', 'is_active', 
        'created_at', 'get_violation_count'
    ]
    
    list_filter = [
        'policy_type', 'severity', 'is_active', 'created_at',
        ('created_by', admin.RelatedOnlyFieldListFilter),
    ]
    
    search_fields = ['name', 'description']
    
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    
    fieldsets = (
        (_('Policy Information'), {
            'fields': ('name', 'policy_type', 'description', 'severity', 'is_active')
        }),
        (_('Policy Parameters'), {
            'fields': ('parameters',),
            'classes': ('collapse',)
        }),
        (_('Violation Actions'), {
            'fields': ('violation_actions',),
            'classes': ('collapse',)
        }),
        (_('Applicability'), {
            'fields': ('applicable_roles', 'applicable_groups', 'exceptions'),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at', 'created_by', 'updated_by'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activate_policies', 'deactivate_policies', 'duplicate_policies']
    
    def get_violation_count(self, obj):
        """Получить количество нарушений политики"""
        count = PolicyViolation.objects.filter(policy=obj).count()
        return count
    get_violation_count.short_description = _('Violations')
    
    def activate_policies(self, request, queryset):
        """Активировать политики"""
        count = queryset.update(is_active=True)
        # Очистить кэш политик
        cache.delete('security_policies')
        
        self.message_user(
            request,
            f"Activated {count} policies.",
            messages.SUCCESS
        )
    activate_policies.short_description = _("Activate selected policies")
    
    def deactivate_policies(self, request, queryset):
        """Деактивировать политики"""
        count = queryset.update(is_active=False)
        # Очистить кэш политик
        cache.delete('security_policies')
        
        self.message_user(
            request,
            f"Deactivated {count} policies.",
            messages.SUCCESS
        )
    deactivate_policies.short_description = _("Deactivate selected policies")
    
    def duplicate_policies(self, request, queryset):
        """Дублировать политики"""
        count = 0
        for policy in queryset:
            policy.pk = None
            policy.name = f"{policy.name} (Copy)"
            policy.is_active = False
            policy.save()
            count += 1
        
        self.message_user(
            request,
            f"Duplicated {count} policies.",
            messages.SUCCESS
        )
    duplicate_policies.short_description = _("Duplicate selected policies")
    
    def save_model(self, request, obj, form, change):
        """Сохранить модель и очистить кэш"""
        if not change:  # Создание новой политики
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        # Очистить кэш политик
        cache.delete('security_policies')
    
    def get_queryset(self, request):
        """Оптимизированный queryset"""
        return super().get_queryset(request).select_related('created_by', 'updated_by')


@admin.register(PolicyViolation)
class PolicyViolationAdmin(SecurityAccessMixin, admin.ModelAdmin):
    """Админский интерфейс для нарушений политик"""
    
    list_display = [
        'policy', 'user', 'violation_type', 'severity', 
        'status', 'detected_at', 'get_actions'
    ]
    
    list_filter = [
        'policy__policy_type', 'severity', 'status', 'detected_at',
        ('user', admin.RelatedOnlyFieldListFilter),
        ('policy', admin.RelatedOnlyFieldListFilter),
    ]
    
    search_fields = [
        'policy__name', 'user__email', 'violation_type', 'description'
    ]
    
    readonly_fields = [
        'detected_at', 'ip_address', 'user_agent', 'request_path',
        'context_data', 'actions_taken'
    ]
    
    fieldsets = (
        (_('Violation Information'), {
            'fields': ('policy', 'user', 'violation_type', 'description', 'severity', 'status')
        }),
        (_('Context Information'), {
            'fields': ('ip_address', 'user_agent', 'request_path', 'context_data'),
            'classes': ('collapse',)
        }),
        (_('Resolution'), {
            'fields': ('resolved_at', 'resolved_by', 'notes'),
            'classes': ('collapse',)
        }),
        (_('Actions Taken'), {
            'fields': ('actions_taken',),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['resolve_violations', 'mark_false_positive', 'escalate_violations']
    
    def get_actions(self, obj):
        """Получить действия для нарушения"""
        if obj.status == 'detected':
            return format_html(
                '<a href="{}" class="button">Resolve</a> '
                '<a href="{}" class="button">False Positive</a> '
                '<a href="{}" class="button">Escalate</a>',
                reverse('admin:security_policyviolation_resolve', args=[obj.pk]),
                reverse('admin:security_policyviolation_false_positive', args=[obj.pk]),
                reverse('admin:security_policyviolation_escalate', args=[obj.pk])
            )
        return '-'
    get_actions.short_description = _('Actions')
    
    def resolve_violations(self, request, queryset):
        """Разрешить нарушения"""
        count = 0
        for violation in queryset.filter(status='detected'):
            violation.resolve(resolved_by=request.user)
            count += 1
        
        self.message_user(
            request,
            f"Successfully resolved {count} violations.",
            messages.SUCCESS
        )
    resolve_violations.short_description = _("Resolve selected violations")
    
    def mark_false_positive(self, request, queryset):
        """Пометить как ложные срабатывания"""
        count = 0
        for violation in queryset.filter(status='detected'):
            violation.resolve(resolved_by=request.user, status='false_positive')
            count += 1
        
        self.message_user(
            request,
            f"Marked {count} violations as false positives.",
            messages.SUCCESS
        )
    mark_false_positive.short_description = _("Mark as false positive")
    
    def escalate_violations(self, request, queryset):
        """Эскалировать нарушения"""
        count = 0
        for violation in queryset.filter(status='detected'):
            violation.status = 'escalated'
            violation.save()
            count += 1
        
        self.message_user(
            request,
            f"Escalated {count} violations.",
            messages.SUCCESS
        )
    escalate_violations.short_description = _("Escalate selected violations")
    
    def get_queryset(self, request):
        """Оптимизированный queryset"""
        return super().get_queryset(request).select_related('policy', 'user', 'resolved_by')
    
    def has_add_permission(self, request):
        """Запретить создание нарушений вручную"""
        return False


@admin.register(SessionPolicy)
class SessionPolicyAdmin(SecurityAccessMixin, admin.ModelAdmin):
    """Админский интерфейс для политик сессий"""
    
    list_display = [
        'name', 'max_session_duration_hours', 'max_concurrent_sessions',
        'inactivity_timeout_minutes', 'is_active', 'created_at'
    ]
    
    list_filter = [
        'is_active', 'created_at'
    ]
    
    search_fields = ['name', 'description']
    
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (_('Policy Information'), {
            'fields': ('name', 'description', 'is_active')
        }),
        (_('Session Parameters'), {
            'fields': (
                'max_session_duration_hours', 'max_concurrent_sessions',
                'inactivity_timeout_minutes', 'force_logout_on_password_change'
            )
        }),
        (_('Additional Parameters'), {
            'fields': ('parameters',),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activate_policies', 'deactivate_policies']
    
    def activate_policies(self, request, queryset):
        """Активировать политики"""
        count = queryset.update(is_active=True)
        self.message_user(
            request,
            f"Activated {count} session policies.",
            messages.SUCCESS
        )
    activate_policies.short_description = _("Activate selected policies")
    
    def deactivate_policies(self, request, queryset):
        """Деактивировать политики"""
        count = queryset.update(is_active=False)
        self.message_user(
            request,
            f"Deactivated {count} session policies.",
            messages.SUCCESS
        )
    deactivate_policies.short_description = _("Deactivate selected policies")


@admin.register(AccessPolicy)
class AccessPolicyAdmin(SecurityAccessMixin, admin.ModelAdmin):
    """Админский интерфейс для политик доступа"""
    
    list_display = [
        'name', 'access_type', 'is_active', 'created_at'
    ]
    
    list_filter = [
        'access_type', 'is_active', 'created_at'
    ]
    
    search_fields = ['name', 'description']
    
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (_('Policy Information'), {
            'fields': ('name', 'description', 'access_type', 'is_active')
        }),
        (_('Access Parameters'), {
            'fields': (
                'allowed_ips', 'allowed_time_ranges', 'allowed_roles',
                'allowed_resources', 'conditions'
            ),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activate_policies', 'deactivate_policies']
    
    def activate_policies(self, request, queryset):
        """Активировать политики"""
        count = queryset.update(is_active=True)
        self.message_user(
            request,
            f"Activated {count} access policies.",
            messages.SUCCESS
        )
    activate_policies.short_description = _("Activate selected policies")
    
    def deactivate_policies(self, request, queryset):
        """Деактивировать политики"""
        count = queryset.update(is_active=False)
        self.message_user(
            request,
            f"Deactivated {count} access policies.",
            messages.SUCCESS
        )
    deactivate_policies.short_description = _("Deactivate selected policies")


@admin.register(DataClassificationPolicy)
class DataClassificationPolicyAdmin(SecurityAccessMixin, admin.ModelAdmin):
    """Админский интерфейс для политик классификации данных"""
    
    list_display = [
        'name', 'classification_level', 'is_active', 'created_at'
    ]
    
    list_filter = [
        'classification_level', 'is_active', 'created_at'
    ]
    
    search_fields = ['name', 'description']
    
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (_('Policy Information'), {
            'fields': ('name', 'description', 'classification_level', 'is_active')
        }),
        (_('Classification Rules'), {
            'fields': ('classification_rules',),
            'classes': ('collapse',)
        }),
        (_('Handling Requirements'), {
            'fields': ('handling_requirements',),
            'classes': ('collapse',)
        }),
        (_('Access Restrictions'), {
            'fields': ('access_restrictions',),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activate_policies', 'deactivate_policies']
    
    def activate_policies(self, request, queryset):
        """Активировать политики"""
        count = queryset.update(is_active=True)
        self.message_user(
            request,
            f"Activated {count} data classification policies.",
            messages.SUCCESS
        )
    activate_policies.short_description = _("Activate selected policies")
    
    def deactivate_policies(self, request, queryset):
        """Деактивировать политики"""
        count = queryset.update(is_active=False)
        self.message_user(
            request,
            f"Deactivated {count} data classification policies.",
            messages.SUCCESS
        )
    deactivate_policies.short_description = _("Deactivate selected policies")


class SecurityDashboardAdmin(admin.ModelAdmin):
    """Админский интерфейс для дашборда безопасности"""
    
    def changelist_view(self, request, extra_context=None):
        """Показать дашборд безопасности"""
        # Получить статистику
        stats = self._get_security_stats()
        
        extra_context = extra_context or {}
        extra_context.update(stats)
        
        return super().changelist_view(request, extra_context)
    
    def _get_security_stats(self):
        """Получить статистику безопасности"""
        try:
            # Проверить, готова ли база данных
            from django.db import connection
            if not connection.introspection.table_names():
                # Если таблицы еще не созданы, возвращаем пустую статистику
                return {
                    'threats_24h': 0,
                    'threats_7d': 0,
                    'active_threats': 0,
                    'threat_types': [],
                    'blocked_ips': 0,
                    'recent_blocks': 0,
                    'top_ips': [],
                    'active_policies': 0,
                    'policy_violations_24h': 0,
                    'policy_violations_7d': 0,
                    'policy_types': [],
                }
        except:
            # Если БД еще не готова, возвращаем пустую статистику
            return {
                'threats_24h': 0,
                'threats_7d': 0,
                'active_threats': 0,
                'threat_types': [],
                'blocked_ips': 0,
                'recent_blocks': 0,
                'top_ips': [],
                'active_policies': 0,
                'policy_violations_24h': 0,
                'policy_violations_7d': 0,
                'policy_types': [],
            }
        
        now = timezone.now()
        last_24h = now - timezone.timedelta(hours=24)
        last_7d = now - timezone.timedelta(days=7)
        
        # Статистика угроз
        threats_24h = SecurityThreat.objects.filter(detected_at__gte=last_24h).count()
        threats_7d = SecurityThreat.objects.filter(detected_at__gte=last_7d).count()
        active_threats = SecurityThreat.objects.filter(status='active').count()
        
        # Статистика по типам угроз
        threat_types = SecurityThreat.objects.filter(
            detected_at__gte=last_7d
        ).values('threat_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Статистика IP
        blocked_ips = IPBlacklist.objects.filter(is_active=True).count()
        recent_blocks = IPBlacklist.objects.filter(
            blocked_at__gte=last_24h
        ).count()
        
        # Топ IP по угрозам
        top_ips = SecurityThreat.objects.filter(
            detected_at__gte=last_7d
        ).values('ip_address').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Статистика политик
        active_policies = SecurityPolicy.objects.filter(is_active=True).count()
        policy_violations_24h = PolicyViolation.objects.filter(detected_at__gte=last_24h).count()
        policy_violations_7d = PolicyViolation.objects.filter(detected_at__gte=last_7d).count()
        
        # Статистика по типам политик
        policy_types = PolicyViolation.objects.filter(
            detected_at__gte=last_7d
        ).values('policy__policy_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        return {
            'threats_24h': threats_24h,
            'threats_7d': threats_7d,
            'active_threats': active_threats,
            'threat_types': threat_types,
            'blocked_ips': blocked_ips,
            'recent_blocks': recent_blocks,
            'top_ips': top_ips,
            'active_policies': active_policies,
            'policy_violations_24h': policy_violations_24h,
            'policy_violations_7d': policy_violations_7d,
            'policy_types': policy_types,
        }


# Кастомный админский сайт для скрытия моделей безопасности
class SecurityAdminSite(admin.AdminSite):
    """Кастомный админский сайт для скрытия моделей безопасности от неавторизованных пользователей"""
    
    def get_app_list(self, request):
        """Переопределить список приложений для скрытия security от неавторизованных пользователей"""
        app_list = super().get_app_list(request)
        
        for app in app_list:
            if app['app_label'] == 'security':
                # Проверить доступ к моделям безопасности
                if not self._check_security_access(request):
                    # Скрыть приложение security полностью
                    app_list.remove(app)
                else:
                    # Показать только модели, к которым есть доступ
                    filtered_models = []
                    for model in app['models']:
                        model_admin = self._registry.get(model['model'])
                        if hasattr(model_admin, '_check_security_access'):
                            if model_admin._check_security_access(request):
                                filtered_models.append(model)
                        else:
                            filtered_models.append(model)
                    app['models'] = filtered_models
        
        return app_list
    
    def _check_security_access(self, request):
        """Проверить доступ к моделям безопасности"""
        if not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        if request.user.is_staff and request.user.has_role('system_admin'):
            return True
        
        return False

# Создать экземпляр кастомного админского сайта
security_admin_site = SecurityAdminSite(name='security_admin')

# Регистрация моделей в кастомном админском сайте
security_admin_site.register(SecurityThreat, SecurityThreatAdmin)
security_admin_site.register(IPBlacklist, IPBlacklistAdmin)
security_admin_site.register(ThreatPattern, ThreatPatternAdmin)
security_admin_site.register(SecurityPolicy, SecurityPolicyAdmin)
security_admin_site.register(PolicyViolation, PolicyViolationAdmin)
security_admin_site.register(SessionPolicy, SessionPolicyAdmin)
security_admin_site.register(AccessPolicy, AccessPolicyAdmin)
security_admin_site.register(DataClassificationPolicy, DataClassificationPolicyAdmin)

# Регистрация в основном админском сайте происходит через @admin.register декораторы
