from django.urls import path
from . import api_views

app_name = 'reports'

urlpatterns = [
    # API endpoints для отчетов
    path('api/income/', api_views.income_report, name='income_report'),
    path('api/workload/', api_views.employee_workload_report, name='workload_report'),
    path('api/debt/', api_views.debt_report, name='debt_report'),
    path('api/activity/', api_views.activity_report, name='activity_report'),
    path('api/payment/', api_views.payment_report, name='payment_report'),
    path('api/cancellation/', api_views.cancellation_report, name='cancellation_report'),
] 