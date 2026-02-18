from django.urls import path
from . import api_views

app_name = 'reports'

urlpatterns = [
    # API endpoints для отчетов
    path('income/', api_views.income_report, name='income_report'),
    path('workload/', api_views.employee_workload_report, name='workload_report'),
    path('debt/', api_views.debt_report, name='debt_report'),
    path('activity/', api_views.activity_report, name='activity_report'),
    path('payment/', api_views.payment_report, name='payment_report'),
    path('cancellation/', api_views.cancellation_report, name='cancellation_report'),
] 