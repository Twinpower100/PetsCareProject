"""
URL routes for the booking module.

Этот модуль содержит маршруты для:
1. Временных слотов
2. Бронирований
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views
from . import flow_views
from . import manual_v2_views

router = DefaultRouter()
router.register(r'bookings', api_views.BookingViewSet, basename='booking')
# router.register(r'booking-statuses', api_views.BookingStatusViewSet, basename='booking-status')  # не существует
router.register(r'booking-reviews', api_views.BookingReviewViewSet, basename='booking-review')

urlpatterns = [
    path('', include(router.urls)),
    
    # API для автоматического бронирования работника
    path('auto-book-employee/', api_views.auto_book_employee, name='auto_book_employee'),
    path('available-employees/', api_views.get_available_employees, name='get_available_employees'),
    
    # Новый Booking Flow UI: Поиск, Слоты, Создание
    path('booking/search/', flow_views.ProviderSearchAPIView.as_view(), name='search_providers'),
    path('booking/locations/<int:location_id>/slots/', flow_views.LocationSlotsAPIView.as_view(), name='location_slots'),
    path('booking/appointments/validate/', flow_views.BookingDraftValidationAPIView.as_view(), name='validate_appointment'),
    path('booking/appointments/', flow_views.CreateAppointmentAPIView.as_view(), name='create_appointment'),
    path('manual-booking/options/', manual_v2_views.ManualBookingOptionsAPIView.as_view(), name='manual-booking-v2-options'),
    path('manual-bookings/', manual_v2_views.ManualBookingListCreateAPIView.as_view(), name='manual-bookings-v2'),
    path('manual-bookings/resolve-conflict/', manual_v2_views.ManualBookingResolveConflictAPIView.as_view(), name='manual-bookings-v2-resolve-conflict'),
    path('manual-bookings/<int:booking_id>/', manual_v2_views.ManualBookingDetailAPIView.as_view(), name='manual-bookings-v2-detail'),
    path('manual-bookings/<int:booking_id>/visit-protocol/', manual_v2_views.ManualBookingProtocolAPIView.as_view(), name='manual-bookings-v2-protocol'),
    path('manual-bookings/<int:booking_id>/cancel/', manual_v2_views.ManualBookingCancelAPIView.as_view(), name='manual-bookings-v2-cancel'),
    path('manual-bookings/<int:booking_id>/complete/', manual_v2_views.ManualBookingCompleteAPIView.as_view(), name='manual-bookings-v2-complete'),
    path('manual-bookings/<int:booking_id>/print/', manual_v2_views.ManualBookingPrintAPIView.as_view(), name='manual-bookings-v2-print'),
    path('manual-bookings/<int:booking_id>/pdf/', manual_v2_views.ManualBookingPdfAPIView.as_view(), name='manual-bookings-v2-pdf'),
    
    # Существующие URL - восстановлены
    path('bookings/<int:booking_id>/cancel/', api_views.CancelBookingAPIView.as_view(), name='cancel_booking'),
    path('bookings/<int:booking_id>/complete/', api_views.CompleteBookingAPIView.as_view(), name='complete_booking'),
    path('bookings/<int:booking_id>/visit-protocol/print/', api_views.BookingVisitProtocolPrintAPIView.as_view(), name='booking_visit_protocol_print'),
    path('bookings/<int:booking_id>/visit-protocol/pdf/', api_views.BookingVisitProtocolPdfAPIView.as_view(), name='booking_visit_protocol_pdf'),
    path('bookings/<int:booking_id>/no-show/', api_views.MarkNoShowAPIView.as_view(), name='mark_no_show'),
    path('bookings/<int:booking_id>/time-slots/', api_views.GetAvailableTimeSlotsAPIView.as_view(), name='get_available_time_slots'),
] 
