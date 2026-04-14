from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from custom_admin import custom_admin_site
from .models import Report, ReportTemplate, ReportSchedule, ReportsDashboardProxy

class ReportAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'created_by', 'created_at')
    search_fields = ('name', 'created_by__email')
    list_filter = ('type', 'created_at')
    readonly_fields = ('created_at', 'updated_at')

class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'is_active')
    search_fields = ('name',)
    list_filter = ('type', 'is_active')

class ReportScheduleAdmin(admin.ModelAdmin):
    list_display = ('report', 'frequency', 'last_run', 'next_run', 'is_active')
    search_fields = ('report__name',)
    list_filter = ('frequency', 'is_active', 'last_run')
    readonly_fields = ('last_run', 'next_run')

class ReportsDashboardProxyAdmin(admin.ModelAdmin):
    """
    Пустышка в админке для редиректа на кастомный дашборд отчетов.
    """
    def changelist_view(self, request, extra_context=None):
        return redirect('admin:reports-dashboard')

custom_admin_site.register(Report, ReportAdmin)
custom_admin_site.register(ReportTemplate, ReportTemplateAdmin)
custom_admin_site.register(ReportSchedule, ReportScheduleAdmin)
custom_admin_site.register(ReportsDashboardProxy, ReportsDashboardProxyAdmin) 