from django.urls import path
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render
from django.http import HttpResponse
from .models import Provider, Employee, EmployeeWorkSlot
import openpyxl
from custom_admin import custom_admin_site

class ProviderReportsAdminView(admin.ModelAdmin):
    """
    Кастомный раздел отчетов по провайдерам.
    - Дашборд отчетов
    - Выгрузка расписания
    """
    change_list_template = "admin/providers/reports_dashboard.html"

    def get_urls(self):
        """
        Добавляет кастомные URL для дашборда и выгрузки расписания.
        """
        urls = super().get_urls()
        custom_urls = [
            path('', self.admin_site.admin_view(self.reports_dashboard), name='provider-reports-dashboard'),
            path('schedule-export/', self.admin_site.admin_view(self.provider_schedule_export_view), name='provider-schedule-export'),
        ]
        return custom_urls + urls

    def reports_dashboard(self, request):
        """
        Главная страница дашборда отчетов по провайдерам.
        """
        context = dict(
            self.admin_site.each_context(request),
        )
        return render(request, "admin/providers/reports_dashboard.html", context)

    def provider_schedule_export_view(self, request):
        """
        Страница-отчет для экспорта расписания.
        """
        employees = Employee.objects.filter(is_active=True).prefetch_related('providers', 'user')
        employees_for_template = []
        for emp in employees:
            provider_ids = list(emp.providers.values_list('id', flat=True))
            employees_for_template.append({
                'id': emp.id,
                'provider_ids': provider_ids,
                '__str__': str(emp),
            })
        if request.method == 'POST':
            provider_ids = request.POST.getlist('provider_ids')
            employee_ids = request.POST.getlist('employee_ids')
            if not employee_ids:
                employees_qs = Employee.objects.filter(providers__id__in=provider_ids).distinct()
            else:
                employees_qs = Employee.objects.filter(id__in=employee_ids)
            slots = EmployeeWorkSlot.objects.filter(employee__in=employees_qs).select_related('employee')
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Schedule"
            ws.append([_("Employee"), _( "Date"), _( "Start Time"), _( "End Time"), _( "Slot Type"), _( "Provider(s)")])
            for slot in slots:
                ws.append([
                    str(slot.employee),
                    slot.date.strftime('%Y-%m-%d'),
                    slot.start_time.strftime('%H:%M'),
                    slot.end_time.strftime('%H:%M'),
                    slot.get_slot_type_display(),
                    ", ".join([p.name for p in slot.employee.providers.all()]),
                ])
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = 'attachment; filename=ProviderScheduleExport.xlsx'
            wb.save(response)
            return response
        context = dict(
            self.admin_site.each_context(request),
            employees=employees_for_template,
            providers=Provider.objects.all(),
        )
        return render(request, "admin/providers/provider_schedule_export.html", context)

# Регистрируем как отдельный пункт меню
custom_admin_site.register_view(
    path='provider-reports/',
    view=ProviderReportsAdminView().reports_dashboard,
    name='provider-reports-dashboard',
    verbose_name=_('Provider Reports')
) 