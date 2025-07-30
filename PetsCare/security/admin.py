from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from django.core.cache import cache

from .models import SecurityThreat, IPBlacklist, ThreatPattern
from .services import ip_blocking_service

@admin.register(SecurityThreat)
class SecurityThreatAdmin(admin.ModelAdmin):
    """Админский интерфейс для угроз безопасности"""
    
    list_display = [
        'threat_type', 'severity', 'ip_address', 'user', 
        'detected_at', 'status', 'get_actions'
    ]
    
    list_filter = [
        'threat_type', 'severity', 'status', 'detected_at',
        ('user', admin.RelatedOnlyFieldFilter),
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
            if ip_blocking_service.block_ip(
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
class IPBlacklistAdmin(admin.ModelAdmin):
    """Админский интерфейс для черного списка IP"""
    
    list_display = [
        'ip_address', 'block_type', 'threat_count', 'blocked_at',
        'expires_at', 'is_active', 'get_actions'
    ]
    
    list_filter = [
        'block_type', 'is_active', 'blocked_at',
        ('blocked_by', admin.RelatedOnlyFieldFilter),
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
            if ip_blocking_service.unblock_ip(ip_block.ip_address, request.user):
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
class ThreatPatternAdmin(admin.ModelAdmin):
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
        
        return {
            'threats_24h': threats_24h,
            'threats_7d': threats_7d,
            'active_threats': active_threats,
            'threat_types': threat_types,
            'blocked_ips': blocked_ips,
            'recent_blocks': recent_blocks,
            'top_ips': top_ips,
        }


# Регистрация дашборда
admin.site.register(SecurityThreat, SecurityThreatAdmin)
admin.site.register(IPBlacklist, IPBlacklistAdmin)
admin.site.register(ThreatPattern, ThreatPatternAdmin)
