"""
Сериализаторы для моделей бронирования.

Этот модуль содержит сериализаторы для:
1. Бронирования
2. Статуса бронирования
3. Временного слота
4. Платежа бронирования
5. Отзыва бронирования
"""

from rest_framework import serializers
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .models import (
    Booking,
    BookingStatus,
    TimeSlot,
    BookingPayment,
    BookingReview
)
from providers.serializers import EmployeeSerializer, ProviderSerializer
from catalog.serializers import ServiceSerializer
from users.serializers import UserSerializer
from pets.serializers import PetSerializer
from pets.models import Pet


class BookingStatusSerializer(serializers.ModelSerializer):
    """Сериализатор для статуса бронирования."""
    
    class Meta:
        model = BookingStatus
        fields = ['id', 'name', 'description']


class TimeSlotSerializer(serializers.ModelSerializer):
    """Сериализатор для временного слота."""
    
    employee = EmployeeSerializer(read_only=True)
    provider = ProviderSerializer(read_only=True)
    
    class Meta:
        model = TimeSlot
        fields = [
            'id',
            'start_time',
            'end_time',
            'employee',
            'provider',
            'is_available'
        ]


class BookingPaymentSerializer(serializers.ModelSerializer):
    """Сериализатор для платежа бронирования."""
    
    class Meta:
        model = BookingPayment
        fields = [
            'id',
            'amount',
            'payment_method',
            'transaction_id',
            'created_at'
        ]


class BookingReviewSerializer(serializers.ModelSerializer):
    """Сериализатор для отзыва бронирования."""
    
    class Meta:
        model = BookingReview
        fields = [
            'id',
            'rating',
            'comment',
            'created_at'
        ]


class BookingSerializer(serializers.ModelSerializer):
    """Сериализатор для бронирования."""
    
    user = UserSerializer(read_only=True)
    pet = PetSerializer(read_only=True)
    provider = ProviderSerializer(read_only=True)
    employee = EmployeeSerializer(read_only=True)
    service = ServiceSerializer(read_only=True)
    status = BookingStatusSerializer(read_only=True)
    payment = BookingPaymentSerializer(read_only=True)
    review = BookingReviewSerializer(read_only=True)
    
    class Meta:
        model = Booking
        fields = [
            'id',
            'code',
            'user',
            'pet',
            'provider',
            'employee',
            'service',
            'status',
            'start_time',
            'end_time',
            'notes',
            'price',
            'payment',
            'review',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['code', 'created_at', 'updated_at']


class BookingCreateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания бронирования."""
    
    class Meta:
        model = Booking
        fields = [
            'pet',
            'provider',
            'employee',
            'service',
            'start_time',
            'end_time',
            'notes'
        ]


class BookingUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для обновления бронирования."""
    
    class Meta:
        model = Booking
        fields = ['notes']


class BookingStatusUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для обновления статуса бронирования."""
    
    class Meta:
        model = Booking
        fields = ['status']


class TimeSlotSearchSerializer(serializers.Serializer):
    """
    Сериализатор для поиска временных слотов.
    """
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
    employee = serializers.IntegerField(required=False)
    provider = serializers.IntegerField(required=False)


class BookingPaymentCreateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания платежа.
    """
    class Meta:
        model = BookingPayment
        fields = ['amount', 'payment_method', 'transaction_id']


class BookingReviewCreateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания отзыва.
    """
    class Meta:
        model = BookingReview
        fields = ['rating', 'comment']


class BookingCreateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания бронирований.
    """
    class Meta:
        model = Booking
        fields = [
            'pet',
            'service',
            'provider',
            'employee',
            'start_time',
            'end_time',
            'notes'
        ]

    def validate(self, data):
        """
        Валидация данных при создании бронирования.
        """
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError(
                {'start_time': _('Start time must be before end time')}
            )
            
        employee = data.get('employee')
        provider = data.get('provider')
        if employee.provider != provider:
            raise serializers.ValidationError(
                {'employee': _('Employee does not belong to this provider')}
            )
            
        return data 