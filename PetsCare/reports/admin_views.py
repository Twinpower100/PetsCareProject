"""
Админские views для системы отчетности PetCare.

Этот модуль содержит админские views для:
1. Дашборда отчетов
2. Генерации отчетов через админку
3. Экспорта отчетов в Excel
4. Управления шаблонами отчетов
"""

from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone
from datetime import datetime, timedelta
from typing import Dict, Any, List
import json

from .services import (
    IncomeReportService,
    EmployeeWorkloadReportService,
    DebtReportService,
    ActivityReportService,
    PaymentReportService,
    CancellationReportService
)
from .models import Report, ReportTemplate, ReportSchedule
from providers.models import Provider
from users.models import User
from custom_admin import custom_admin_site


class ReportsAdminView:
    """Админский view для управления отчетами."""
    
    def __init__(self):
        self.report_services = {
            'income': IncomeReportService,
            'debt': DebtReportService,
            'activity': ActivityReportService,
            'payment': PaymentReportService,
            'cancellation': CancellationReportService,
        }
    
    def get_urls(self):
        """Возвращает URL patterns для админских views."""
        return [
            path('dashboard/', self.dashboard_view, name='reports-dashboard'),
            path('generate/', self.generate_report_view, name='reports-generate'),
            path('export/', self.export_report_view, name='reports-export'),
            path('templates/', self.templates_view, name='reports-templates'),
            path('schedule/', self.schedule_view, name='reports-schedule'),
        ]
    
    @method_decorator(login_required)
    def dashboard_view(self, request):
        """Главная страница дашборда отчетов."""
        context = {
            'title': _('Reports Dashboard'),
            'report_types': [
                {
                    'id': 'income',
                    'name': _('Income Report'),
                    'description': _('Report on income through the booking system'),
                    'icon': '💰'
                },
                {
                    'id': 'debt',
                    'name': _('Debt Report'),
                    'description': _('Report on accounts receivable'),
                    'icon': '📊'
                },
                {
                    'id': 'activity',
                    'name': _('Activity Report'),
                    'description': _('Report on provider activity'),
                    'icon': '📈'
                },
                {
                    'id': 'payment',
                    'name': _('Payment Report'),
                    'description': _('Report on payments and overdue payments'),
                    'icon': '💳'
                },
                {
                    'id': 'cancellation',
                    'name': _('Cancellation Report'),
                    'description': _('Report on booking cancellations'),
                    'icon': '❌'
                },
            ],
            'recent_reports': Report.objects.filter(
                created_by=request.user
            ).order_by('-created_at')[:10],
            'providers': Provider.objects.all()[:20],  # Ограничиваем для производительности
        }
        
        context.update(custom_admin_site.each_context(request))
        return render(request, 'admin/reports/dashboard.html', context)
    
    @method_decorator(login_required)
    def generate_report_view(self, request):
        """Страница генерации отчета."""
        if request.method == 'POST':
            return self._handle_report_generation(request)
        
        report_type = request.GET.get('type', 'income')
        
        context = {
            'title': _('Generate Report'),
            'report_type': report_type,
            'report_types': self.report_services.keys(),
            'providers': Provider.objects.all(),
            'date_range_options': [
                {'value': 'today', 'label': _('Today')},
                {'value': 'yesterday', 'label': _('Yesterday')},
                {'value': 'week', 'label': _('This Week')},
                {'value': 'month', 'label': _('This Month')},
                {'value': 'quarter', 'label': _('This Quarter')},
                {'value': 'year', 'label': _('This Year')},
                {'value': 'custom', 'label': _('Custom Range')},
            ]
        }
        
        context.update(custom_admin_site.each_context(request))
        return render(request, 'admin/reports/generate.html', context)
    
    @method_decorator(login_required)
    def export_report_view(self, request):
        """Быстрый экспорт отчета за текущий месяц."""
        report_type = request.GET.get('type', 'income')
        start_date, end_date = self._get_date_range('month')
        
        service_class = self.report_services.get(report_type)
        if not service_class:
            messages.error(request, _('Invalid report type'))
            return redirect('admin:reports-dashboard')
            
        try:
            service = service_class(request.user)
            report_data = service.generate_report(start_date, end_date, None)
            return self._export_to_excel(report_data, report_type)
        except Exception as e:
            messages.error(request, _('Error exporting report: {error}').format(error=str(e)))
            return redirect('admin:reports-dashboard')
    
    def _handle_report_generation(self, request):
        """Обрабатывает генерацию отчета."""
        try:
            report_type = request.POST.get('report_type')
            date_range = request.POST.get('date_range')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            provider_ids = request.POST.getlist('providers')
            format_type = request.POST.get('format', 'json')
            
            # Определяем даты
            if date_range == 'custom':
                start_date = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
                end_date = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59))
            else:
                start_date, end_date = self._get_date_range(date_range)
            
            # Получаем провайдеров
            providers = None
            if provider_ids:
                providers = Provider.objects.filter(id__in=provider_ids)
            
            # Генерируем отчет
            service_class = self.report_services.get(report_type)
            if not service_class:
                messages.error(request, _('Invalid report type'))
                return redirect('admin:reports-generate')
            
            service = service_class(request.user)
            report_data = service.generate_report(start_date, end_date, providers)
            
            # Сериализуем данные для JSON (datetime, Decimal и др.)
            import json
            from django.core.serializers.json import DjangoJSONEncoder
            safe_report_data = json.loads(json.dumps(report_data, cls=DjangoJSONEncoder))
            
            # Сохраняем отчет в базе
            report = Report.objects.create(
                name=f"{report_type.title()} Report",
                type=report_type,
                created_by=request.user,
                data=safe_report_data
            )
            
            if format_type == 'excel':
                return self._export_to_excel(report_data, report_type)
            else:
                messages.success(request, _('Report generated successfully'))
                return redirect('admin:reports-dashboard')
                
        except Exception as e:
            messages.error(
                request,
                _('Error generating report: {error}').format(error=str(e))
            )
            return redirect('admin:reports-generate')
    
    def _get_date_range(self, date_range: str) -> tuple:
        """Возвращает диапазон дат на основе выбранного периода."""
        now = timezone.now()
        
        if date_range == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
        elif date_range == 'yesterday':
            start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date.replace(hour=23, minute=59, second=59)
        elif date_range == 'week':
            start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
        elif date_range == 'month':
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = now
        elif date_range == 'quarter':
            quarter = (now.month - 1) // 3
            start_date = now.replace(month=quarter * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = now
        elif date_range == 'year':
            start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = now
        else:
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = now
        
        return start_date, end_date
    
    def _export_to_excel(self, report_data: Dict[str, Any], report_type: str) -> HttpResponse:
        """Экспортирует отчет в Excel."""
        from .api_views import (
            generate_income_excel_report,
            generate_debt_excel_report,
            generate_activity_excel_report,
            generate_payment_excel_report,
            generate_cancellation_excel_report
        )
        
        export_functions = {
            'income': generate_income_excel_report,
            'debt': generate_debt_excel_report,
            'activity': generate_activity_excel_report,
            'payment': generate_payment_excel_report,
            'cancellation': generate_cancellation_excel_report,
        }
        
        export_function = export_functions.get(report_type)
        if export_function:
            return export_function(report_data)
        else:
            return HttpResponse('Unsupported report type', status=400)
    
    @method_decorator(login_required)
    def templates_view(self, request):
        """Страница управления шаблонами отчетов."""
        if request.method == 'POST':
            return self._handle_template_creation(request)
        
        templates = ReportTemplate.objects.all()
        
        context = {
            'title': _('Report Templates'),
            'templates': templates,
        }
        
        context.update(custom_admin_site.each_context(request))
        return render(request, 'admin/reports/templates.html', context)
    
    def _handle_template_creation(self, request):
        """Обрабатывает создание шаблона отчета."""
        try:
            name = request.POST.get('name')
            report_type = request.POST.get('report_type')
            template_data = request.POST.get('template_data', '{}')
            
            template = ReportTemplate.objects.create(
                name=name,
                type=report_type,
                template=json.loads(template_data)
            )
            
            messages.success(request, _('Template created successfully'))
            return redirect('admin:reports-templates')
            
        except Exception as e:
            messages.error(
                request,
                _('Error creating template: {error}').format(error=str(e))
            )
            return redirect('admin:reports-templates')
    
    @method_decorator(login_required)
    def schedule_view(self, request):
        """Страница управления расписанием отчетов."""
        if request.method == 'POST':
            return self._handle_schedule_creation(request)
        
        schedules = ReportSchedule.objects.all()
        
        context = {
            'title': _('Report Schedule'),
            'schedules': schedules,
            'reports': Report.objects.all(),
            'frequency_options': [
                {'value': 'daily', 'label': _('Daily')},
                {'value': 'weekly', 'label': _('Weekly')},
                {'value': 'monthly', 'label': _('Monthly')},
                {'value': 'quarterly', 'label': _('Quarterly')},
            ]
        }
        
        context.update(custom_admin_site.each_context(request))
        return render(request, 'admin/reports/schedule.html', context)
    
    def _handle_schedule_creation(self, request):
        """Обрабатывает создание расписания отчета."""
        try:
            report_id = request.POST.get('report')
            frequency = request.POST.get('frequency')
            
            report = Report.objects.get(id=report_id)
            
            schedule = ReportSchedule.objects.create(
                report=report,
                frequency=frequency
            )
            
            messages.success(request, _('Schedule created successfully'))
            return redirect('admin:reports-schedule')
            
        except Exception as e:
            messages.error(
                request,
                _('Error creating schedule: {error}').format(error=str(e))
            )
            return redirect('admin:reports-schedule')


# Регистрируем админские views
reports_admin = ReportsAdminView() 