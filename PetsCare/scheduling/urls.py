from django.urls import path
from . import api_views

app_name = 'scheduling'

urlpatterns = [
    path('employees/<int:employee_id>/vacations/', api_views.VacationCreateAPIView.as_view(), name='vacation-create'),
    path('employees/<int:employee_id>/sick-leaves/', api_views.SickLeaveCreateAPIView.as_view(), name='sick-leave-create'),
    path('vacations/<int:pk>/', api_views.VacationDetailAPIView.as_view(), name='vacation-detail'),
    path('sick-leaves/<int:pk>/', api_views.SickLeaveDetailAPIView.as_view(), name='sick-leave-detail'),
    path('provider-locations/<int:location_id>/aggregated-schedule/', api_views.LocationAggregatedScheduleAPIView.as_view(), name='location-aggregated-schedule'),
]
