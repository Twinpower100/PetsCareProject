from django.urls import path
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render
from django.http import HttpResponse
from .models import Invoice
import openpyxl
from custom_admin import custom_admin_site

class BillingReportsAdminView(admin.ModelAdmin):
    """
    Кастомный раздел отчетов по биллингу.
    - Дашборд отчетов
    - Выгрузка инвойсов
    """
    change_list_template = "admin/billing/reports_dashboard.html"

    def get_urls(self):
        """
        Добавляет кастомные URL для дашборда и выгрузки инвойсов.
        """
        urls = super().get_urls()
        custom_urls = [
            path('', self.admin_site.admin_view(self.reports_dashboard), name='billing-reports-dashboard'),
            path('invoice-export/', self.admin_site.admin_view(self.invoice_export_view), name='billing-invoice-export'),
        ]
        return custom_urls + urls

    def reports_dashboard(self, request):
        """
        Главная страница дашборда отчетов по биллингу.
        """
        context = dict(
            self.admin_site.each_context(request),
        )
        return render(request, "admin/billing/reports_dashboard.html", context)

    def invoice_export_view(self, request):
        """
        Страница-отчет для экспорта инвойсов.
        """
        invoices = Invoice.objects.all().select_related('provider', 'currency')
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Invoices"
        ws.append([_("Number"), _( "Provider"), _( "Amount"), _( "Currency"), _( "Status"), _( "Issued At")])
        for inv in invoices:
            ws.append([
                inv.number,
                str(inv.provider) if inv.provider else "",
                str(inv.amount),
                inv.currency.code if inv.currency else "",
                inv.status,
                inv.issued_at.strftime('%Y-%m-%d'),
            ])
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=InvoicesExport.xlsx'
        wb.save(response)
        return response

# Регистрируем как отдельный пункт меню
custom_admin_site.register_view(
    path='billing-reports/',
    view=BillingReportsAdminView().reports_dashboard,
    name='billing-reports-dashboard',
    verbose_name=_('Billing Reports')
) 