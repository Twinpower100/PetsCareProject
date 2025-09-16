"""
URL routes for the booking module.

Этот модуль содержит маршруты для:
1. Временных слотов
2. Бронирований
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views

router = DefaultRouter()
router.register(r'bookings', api_views.BookingViewSet, basename='booking')
# router.register(r'booking-statuses', api_views.BookingStatusViewSet, basename='booking-status')  # не существует
router.register(r'booking-reviews', api_views.BookingReviewViewSet, basename='booking-review')

urlpatterns = [
    path('api/', include(router.urls)),
    
    # API для автоматического бронирования работника
    path('api/auto-book-employee/', api_views.auto_book_employee, name='auto_book_employee'),
    path('api/available-employees/', api_views.get_available_employees, name='get_available_employees'),
    
    # Существующие URL (временно отключены - функции не существуют)
    # path('api/bookings/<int:booking_id>/cancel/', api_views.cancel_booking, name='cancel_booking'),
    # path('api/bookings/<int:booking_id>/complete/', api_views.complete_booking, name='complete_booking'),
    # path('api/bookings/<int:booking_id>/no-show/', api_views.mark_no_show, name='mark_no_show'),
    # path('api/bookings/<int:booking_id>/time-slots/', api_views.get_available_time_slots, name='get_available_time_slots'),
] 