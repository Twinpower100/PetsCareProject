from django.contrib import admin
from custom_admin import custom_admin_site
from .models import Report, ReportTemplate, ReportSchedule

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

custom_admin_site.register(Report, ReportAdmin)
custom_admin_site.register(ReportTemplate, ReportTemplateAdmin)
custom_admin_site.register(ReportSchedule, ReportScheduleAdmin) 