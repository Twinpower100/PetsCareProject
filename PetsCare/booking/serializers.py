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
from providers.models import Provider, Employee, ProviderLocation
from providers.serializers import EmployeeSerializer, ProviderSerializer
from catalog.models import Service
from catalog.serializers import ServiceSerializer
from users.models import User
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


class BookingUserCompactSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name']


class BookingPetListSerializer(serializers.ModelSerializer):
    pet_type_name = serializers.CharField(source='pet_type.name', read_only=True)
    breed_name = serializers.CharField(source='breed.name', read_only=True)

    class Meta:
        model = Pet
        fields = [
            'id',
            'name',
            'photo',
            'pet_type',
            'pet_type_name',
            'breed',
            'breed_name',
            'birth_date',
        ]


class BookingProviderListSerializer(serializers.ModelSerializer):
    full_address = serializers.SerializerMethodField()

    class Meta:
        model = Provider
        fields = [
            'id',
            'name',
            'phone_number',
            'email',
            'logo',
            'website',
            'is_active',
            'full_address',
        ]

    def get_full_address(self, obj):
        if obj.structured_address:
            return obj.structured_address.formatted_address or str(obj.structured_address)
        return None


class BookingProviderLocationListSerializer(serializers.ModelSerializer):
    full_address = serializers.SerializerMethodField()

    class Meta:
        model = ProviderLocation
        fields = [
            'id',
            'name',
            'phone_number',
            'email',
            'is_active',
            'full_address',
        ]

    def get_full_address(self, obj):
        if obj.structured_address:
            return obj.structured_address.formatted_address or str(obj.structured_address)
        return None


class BookingEmployeeListSerializer(serializers.ModelSerializer):
    user = BookingUserCompactSerializer(read_only=True)

    class Meta:
        model = Employee
        fields = ['id', 'user', 'is_active']


class BookingServiceListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ['id', 'name']


class BookingListSerializer(serializers.ModelSerializer):
    user = BookingUserCompactSerializer(read_only=True)
    escort_owner = BookingUserCompactSerializer(read_only=True)
    pet = BookingPetListSerializer(read_only=True)
    provider = BookingProviderListSerializer(read_only=True)
    provider_location = BookingProviderLocationListSerializer(read_only=True)
    employee = BookingEmployeeListSerializer(read_only=True)
    service = BookingServiceListSerializer(read_only=True)
    status = BookingStatusSerializer(read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id',
            'code',
            'user',
            'escort_owner',
            'pet',
            'provider',
            'provider_location',
            'employee',
            'service',
            'status',
            'start_time',
            'end_time',
            'occupied_duration_minutes',
            'notes',
            'price',
            'created_at',
            'updated_at'
        ]


class BookingSerializer(serializers.ModelSerializer):
    """Сериализатор для бронирования."""
    
    user = UserSerializer(read_only=True)
    escort_owner = UserSerializer(read_only=True)
    pet = PetSerializer(read_only=True)
    provider = ProviderSerializer(read_only=True)
    provider_location = BookingProviderLocationListSerializer(read_only=True)
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
            'escort_owner',
            'pet',
            'provider',
            'provider_location',
            'employee',
            'service',
            'status',
            'start_time',
            'end_time',
            'occupied_duration_minutes',
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
            'provider',
            'provider_location',
            'employee',
            'service',
            'start_time',
            'escort_owner',
            'notes'
        ]

    def validate(self, data):
        """
        Валидация данных при создании бронирования.
        """
        if data.get('escort_owner') and not data['pet'].owners.filter(id=data['escort_owner'].id).exists():
            raise serializers.ValidationError(
                {'escort_owner': _('Escort owner must be one of the pet owners')}
            )
        return data 
