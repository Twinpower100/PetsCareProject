from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Avg, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import timedelta
from .models import UserGrowth, UserActivity, UserConversion, UserMetrics
from .services import user_analytics_service, conversion_tracking_service, activity_tracking_service

class AnalyticsAccessMixin:
    """Миксин для ограничения доступа к аналитике только админам проекта"""
    
    def has_module_permission(self, request):
        """Проверка доступа к модулю"""
        return request.user.is_superuser or request.user.is_staff and hasattr(request.user, 'is_project_admin') and request.user.is_project_admin
    
    def has_view_permission(self, request, obj=None):
        """Проверка доступа к просмотру"""
        return self.has_module_permission(request)
    
    def has_add_permission(self, request):
        """Проверка доступа к добавлению"""
        return self.has_module_permission(request)
    
    def has_change_permission(self, request, obj=None):
        """Проверка доступа к изменению"""
        return self.has_module_permission(request)
    
    def has_delete_permission(self, request, obj=None):
        """Проверка доступа к удалению"""
        return self.has_module_permission(request)


@admin.register(UserGrowth)
class UserGrowthAdmin(AnalyticsAccessMixin, admin.ModelAdmin):
    """Админский интерфейс для роста пользователей"""
    
    list_display = [
        'period_type', 'period_start', 'period_end', 'new_registrations', 
        'total_users', 'growth_rate', 'new_owners', 'new_sitters', 'new_providers'
    ]
    list_filter = ['period_type', 'period_start', 'period_end']
    search_fields = ['period_type']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-period_start']
    
    fieldsets = (
        (_('Period'), {
            'fields': ('period_type', 'period_start', 'period_end')
        }),
        (_('Growth Metrics'), {
            'fields': ('new_registrations', 'total_users', 'growth_rate')
        }),
        (_('User Types Breakdown'), {
            'fields': ('new_owners', 'new_sitters', 'new_providers')
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['recalculate_growth']
    
    def recalculate_growth(self, request, queryset):
        """Пересчитать метрики роста"""
        for growth in queryset:
            user_analytics_service.calculate_user_growth(
                growth.period_type, 
                growth.period_start, 
                growth.period_end
            )
        self.message_user(request, _("Recalculated {} user growth records").format(queryset.count()))
    recalculate_growth.short_description = _("Recalculate growth metrics")


@admin.register(UserActivity)
class UserActivityAdmin(AnalyticsAccessMixin, admin.ModelAdmin):
    """Админский интерфейс для активности пользователей"""
    
    list_display = [
        'user', 'date', 'login_count', 'page_views', 'actions_count',
        'searches_count', 'bookings_count', 'session_duration_formatted'
    ]
    list_filter = ['date']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at', 'first_activity', 'last_activity']
    ordering = ['-date', '-last_activity']
    
    fieldsets = (
        (_('User and Date'), {
            'fields': ('user', 'date')
        }),
        (_('Main Metrics'), {
            'fields': ('login_count', 'session_duration', 'page_views', 'actions_count')
        }),
        (_('Action Breakdown'), {
            'fields': ('searches_count', 'bookings_count', 'reviews_count', 'messages_count')
        }),
        (_('Activity Time'), {
            'fields': ('first_activity', 'last_activity')
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def session_duration_formatted(self, obj):
        """Форматированная длительность сессии"""
        if obj.session_duration:
            minutes = obj.session_duration // 60
            seconds = obj.session_duration % 60
            return f"{minutes}m {seconds}s"
        return "0m 0s"
    session_duration_formatted.short_description = _("Session Duration")
    
    actions = ['recalculate_activity']
    
    def recalculate_activity(self, request, queryset):
        """Пересчитать активность"""
        for activity in queryset:
            # Здесь можно добавить логику пересчета
            pass
        self.message_user(request, _("Recalculated {} activity records").format(queryset.count()))
    recalculate_activity.short_description = _("Recalculate activity")


@admin.register(UserConversion)
class UserConversionAdmin(AnalyticsAccessMixin, admin.ModelAdmin):
    """Админский интерфейс для конверсии пользователей"""
    
    list_display = [
        'user', 'stage', 'achieved_at', 'time_to_achieve_formatted', 'source'
    ]
    list_filter = ['stage', 'achieved_at', 'source']
    search_fields = ['user__username', 'user__email', 'stage']
    readonly_fields = ['achieved_at']
    ordering = ['-achieved_at']
    
    fieldsets = (
        (_('User and Stage'), {
            'fields': ('user', 'stage')
        }),
        (_('Conversion Details'), {
            'fields': ('achieved_at', 'time_to_achieve', 'source')
        }),
    )
    
    def time_to_achieve_formatted(self, obj):
        """Форматированное время до достижения"""
        if obj.time_to_achieve:
            hours = obj.time_to_achieve
            if hours < 24:
                return f"{hours}h"
            else:
                days = hours // 24
                remaining_hours = hours % 24
                return f"{days}d {remaining_hours}h"
        return "N/A"
    time_to_achieve_formatted.short_description = _("Time to Achieve")


@admin.register(UserMetrics)
class UserMetricsAdmin(AnalyticsAccessMixin, admin.ModelAdmin):
    """Админский интерфейс для агрегированных метрик"""
    
    list_display = [
        'period_type', 'period_start', 'period_end', 'total_users', 
        'active_users', 'new_users', 'retention_rate', 'churn_rate_display'
    ]
    list_filter = ['period_type', 'period_start', 'period_end']
    search_fields = ['period_type']
    readonly_fields = ['created_at', 'updated_at', 'churn_rate']
    ordering = ['-period_start']
    
    fieldsets = (
        (_('Period'), {
            'fields': ('period_type', 'period_start', 'period_end')
        }),
        (_('General Metrics'), {
            'fields': ('total_users', 'active_users', 'new_users', 'churned_users')
        }),
        (_('Activity Metrics'), {
            'fields': ('avg_session_duration', 'avg_page_views', 'retention_rate')
        }),
        (_('Conversion Metrics'), {
            'fields': ('conversion_rate', 'booking_rate', 'payment_rate')
        }),
        (_('User Types Breakdown'), {
            'fields': ('owners_count', 'sitters_count', 'providers_count')
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at', 'churn_rate'),
            'classes': ('collapse',)
        }),
    )
    
    def churn_rate_display(self, obj):
        """Отображение коэффициента оттока"""
        return f"{obj.churn_rate}%"
    churn_rate_display.short_description = _("Churn Rate")
    
    actions = ['recalculate_metrics']
    
    def recalculate_metrics(self, request, queryset):
        """Пересчитать метрики"""
        for metrics in queryset:
            user_analytics_service.calculate_user_metrics(
                metrics.period_type,
                metrics.period_start,
                metrics.period_end
            )
        self.message_user(request, _("Recalculated {} metrics records").format(queryset.count()))
    recalculate_metrics.short_description = _("Recalculate metrics")


class AnalyticsDashboardAdmin(AnalyticsAccessMixin, admin.ModelAdmin):
    """Дашборд аналитики"""
    
    change_list_template = 'admin/analytics_dashboard.html'
    
    def changelist_view(self, request, extra_context=None):
        """Переопределяем для отображения дашборда"""
        extra_context = extra_context or {}
        
        # Получаем данные для дашборда
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Рост пользователей
        growth_week = user_analytics_service.calculate_user_growth('daily', week_ago, today)
        growth_month = user_analytics_service.calculate_user_growth('monthly', month_ago, today)
        
        # Воронка конверсии
        conversion_funnel = conversion_tracking_service.get_conversion_funnel(month_ago, today)
        conversion_rates = conversion_tracking_service.get_conversion_rates(month_ago, today)
        
        # Активные пользователи
        active_users = activity_tracking_service.get_most_active_users(7, 5)
        
        extra_context.update({
            'growth_week': growth_week,
            'growth_month': growth_month,
            'conversion_funnel': conversion_funnel,
            'conversion_rates': conversion_rates,
            'active_users': active_users,
        })
        
        return super().changelist_view(request, extra_context)


# Регистрируем дашборд
# admin.site.register(UserMetrics, AnalyticsDashboardAdmin)  # Уже зарегистрирован через @admin.register
