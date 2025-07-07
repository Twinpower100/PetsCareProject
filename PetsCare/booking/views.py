from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from datetime import datetime, timedelta
import csv
import io

from .models import Booking, BookingAutoCompleteSettings
from .services import BookingReportService
from users.models import User


def is_billing_manager(user):
    """Проверка, является ли пользователь биллинг-менеджером"""
    return user.has_role('billing_manager')


def is_system_admin(user):
    """Проверка, является ли пользователь системным администратором"""
    return user.has_role('system_admin')


@login_required
@user_passes_test(lambda u: is_billing_manager(u) or is_system_admin(u))
def cancellations_report(request):
    """Представление для отчёта по отменам бронирований"""
    
    # Получаем параметры фильтрации
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    # По умолчанию - последние 30 дней
    if not start_date_str:
        start_date = datetime.now().date() - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    
    if not end_date_str:
        end_date = datetime.now().date()
    else:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    # Ограничиваем доступ по учреждениям для биллинг-менеджеров
    providers = None
    if request.user.has_role('billing_manager') and not request.user.has_role('system_admin'):
        # TODO: Получить список учреждений, за которые отвечает биллинг-менеджер
        # providers = get_billing_manager_providers(request.user)
        pass
    
    # Получаем данные отчёта
    cancellations = BookingReportService.get_cancellations_report(
        start_date, end_date, providers, request.user
    )
    
    # Получаем статистику
    statistics = BookingReportService.get_cancellation_statistics(
        start_date, end_date, providers
    )
    
    context = {
        'cancellations': cancellations,
        'statistics': statistics,
        'start_date': start_date,
        'end_date': end_date,
        'is_system_admin': request.user.has_role('system_admin'),
    }
    
    return render(request, 'booking/cancellations_report.html', context)


@login_required
@user_passes_test(lambda u: is_billing_manager(u) or is_system_admin(u))
def cancellations_report_csv(request):
    """Экспорт отчёта по отменам в CSV"""
    
    # Получаем параметры фильтрации
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    # По умолчанию - последние 30 дней
    if not start_date_str:
        start_date = datetime.now().date() - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    
    if not end_date_str:
        end_date = datetime.now().date()
    else:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    # Ограничиваем доступ по учреждениям для биллинг-менеджеров
    providers = None
    if request.user.has_role('billing_manager') and not request.user.has_role('system_admin'):
        # TODO: Получить список учреждений, за которые отвечает биллинг-менеджер
        pass
    
    # Получаем данные отчёта
    cancellations = BookingReportService.get_cancellations_report(
        start_date, end_date, providers, request.user
    )
    
    # Создаем CSV файл
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="cancellations_report_{start_date}_{end_date}.csv"'
    
    # Добавляем BOM для корректного отображения кириллицы в Excel
    response.write('\ufeff')
    
    writer = csv.writer(response, delimiter=';')
    
    # Заголовки
    writer.writerow([
        _('Cancellation Date'),
        _('Provider'),
        _('Service'),
        _('Service Type'),
        _('Cancelled By'),
        _('Client'),
        _('Cancellation Time'),
        _('Cancellation Reason')
    ])
    
    # Данные
    for cancellation in cancellations:
        writer.writerow([
            cancellation.cancelled_at.strftime('%Y-%m-%d'),
            cancellation.provider.name,
            cancellation.service.name,
            cancellation.service.service_type.name if cancellation.service.service_type else '',
            _('Client') if cancellation.status.name == 'cancelled_by_client' else _('Provider'),
            _("{} {}").format(cancellation.user.first_name, cancellation.user.last_name).strip() or cancellation.user.username,
            cancellation.cancelled_at.strftime('%Y-%m-%d %H:%M:%S'),
            cancellation.cancellation_reason or ''
        ])
    
    return response


@login_required
@user_passes_test(lambda u: is_billing_manager(u) or is_system_admin(u))
def cancellations_statistics_api(request):
    """API для получения статистики по отменам"""
    
    # Получаем параметры фильтрации
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    # По умолчанию - последние 30 дней
    if not start_date_str:
        start_date = datetime.now().date() - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    
    if not end_date_str:
        end_date = datetime.now().date()
    else:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    # Ограничиваем доступ по учреждениям для биллинг-менеджеров
    providers = None
    if request.user.has_role('billing_manager') and not request.user.has_role('system_admin'):
        # TODO: Получить список учреждений, за которые отвечает биллинг-менеджер
        pass
    
    # Получаем статистику
    statistics = BookingReportService.get_cancellation_statistics(
        start_date, end_date, providers
    )
    
    return JsonResponse(statistics) 