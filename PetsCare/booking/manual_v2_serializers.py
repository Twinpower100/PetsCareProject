"""Сериализаторы для Manual Booking V2."""

from __future__ import annotations

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from booking.manual_v2_models import ManualBooking, ManualVisitProtocol
from booking.serializers import (
    BookingCancellationReasonSerializer,
    BookingEmployeeListSerializer,
    BookingProviderLocationListSerializer,
    BookingProviderListSerializer,
    BookingServiceListSerializer,
)


class ManualBookingUserSnapshotSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.CharField(allow_blank=True)
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    phone_number = serializers.CharField(allow_blank=True)


class ManualBookingPetSnapshotSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    pet_type = serializers.IntegerField()
    pet_type_name = serializers.CharField()
    breed = serializers.IntegerField()
    breed_name = serializers.CharField()


class ManualBookingStatusSerializer(serializers.Serializer):
    id = serializers.IntegerField(default=0)
    name = serializers.CharField()
    display_name = serializers.CharField()
    description = serializers.CharField(allow_blank=True, default='')


class ManualVisitProtocolSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManualVisitProtocol
        fields = [
            'id',
            'protocol_family',
            'date',
            'next_date',
            'description',
            'diagnosis',
            'anamnesis',
            'results',
            'recommendations',
            'notes',
            'serial_number',
            'created_at',
            'updated_at',
        ]


class ManualBookingListSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()
    escort_owner = serializers.SerializerMethodField()
    pet = serializers.SerializerMethodField()
    provider = serializers.SerializerMethodField()
    provider_location = BookingProviderLocationListSerializer(read_only=True)
    employee = BookingEmployeeListSerializer(read_only=True)
    service = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    status_code = serializers.CharField(source='status', read_only=True)
    status_display = serializers.SerializerMethodField()
    ui_status = serializers.SerializerMethodField()
    source = serializers.CharField(read_only=True)
    manual_entry = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    cancelled_by = serializers.CharField(read_only=True)
    cancellation_reason = BookingCancellationReasonSerializer(read_only=True)

    class Meta:
        model = ManualBooking
        fields = [
            'id',
            'kind',
            'code',
            'user',
            'escort_owner',
            'pet',
            'provider',
            'provider_location',
            'employee',
            'service',
            'status',
            'status_code',
            'status_display',
            'ui_status',
            'source',
            'manual_entry',
            'is_overdue',
            'cancelled_by',
            'cancellation_reason',
            'cancellation_reason_text',
            'completed_at',
            'start_time',
            'end_time',
            'occupied_duration_minutes',
            'notes',
            'price',
            'created_at',
            'updated_at',
        ]

    def get_kind(self, obj):
        return 'manual'

    def get_user(self, obj):
        return {
            'id': obj.lead_id,
            'email': obj.owner_email,
            'first_name': obj.owner_first_name,
            'last_name': obj.owner_last_name,
            'phone_number': str(obj.owner_phone_number),
        }

    def get_escort_owner(self, obj):
        return self.get_user(obj)

    def get_pet(self, obj):
        return {
            'id': obj.id,
            'name': obj.pet_name,
            'pet_type': obj.pet_type_id,
            'pet_type_name': obj.pet_type.get_localized_name(),
            'breed': obj.breed_id,
            'breed_name': obj.breed.get_localized_name(),
        }

    def get_provider(self, obj):
        return BookingProviderListSerializer(obj.provider, context=self.context).data

    def get_service(self, obj):
        payload = BookingServiceListSerializer(obj.service, context=self.context).data
        payload['protocol_family'] = obj.service.resolve_protocol_family()
        payload['emergency_capable'] = obj.service.resolve_emergency_capable()
        return payload

    def get_status(self, obj):
        return {
            'id': 0,
            'name': obj.status,
            'display_name': self.get_status_display(obj),
            'description': '',
        }

    def get_status_display(self, obj):
        labels = {
            'active': str(_('Active')),
            'completed': str(_('Completed')),
            'cancelled': str(_('Cancelled')),
        }
        return labels.get(obj.status, obj.status)

    def get_ui_status(self, obj):
        if obj.is_overdue:
            return {'code': 'overdue', 'label': str(_('Overdue'))}
        if obj.status == 'cancelled' and obj.cancelled_by == 'provider':
            return {'code': 'cancelled_by_provider', 'label': str(_('Cancelled by provider'))}
        return {'code': obj.status, 'label': self.get_status_display(obj)}

    def get_manual_entry(self, obj):
        return {
            'is_guest': True,
            'guest_client_name': f'{obj.owner_first_name} {obj.owner_last_name}'.strip(),
            'guest_client_phone': str(obj.owner_phone_number),
            'guest_pet_name': obj.pet_name,
            'guest_pet_species': obj.pet_type.get_localized_name(),
            'guest_pet_type_id': obj.pet_type_id,
            'size_code': obj.size_code,
            'protocol_family': obj.protocol_family,
            'emergency_capable': obj.service.resolve_emergency_capable(),
        }


class ManualBookingDetailSerializer(ManualBookingListSerializer):
    manual_visit_protocol = serializers.SerializerMethodField()
    requires_protocol = serializers.BooleanField(read_only=True)
    protocol_family = serializers.CharField(read_only=True)

    class Meta(ManualBookingListSerializer.Meta):
        fields = ManualBookingListSerializer.Meta.fields + [
            'manual_visit_protocol',
            'requires_protocol',
            'protocol_family',
        ]

    def get_manual_visit_protocol(self, obj):
        protocol = getattr(obj, 'manual_visit_protocol', None)
        if protocol is None:
            return None
        return ManualVisitProtocolSerializer(protocol, context=self.context).data


class ManualBookingCreateUpdateSerializer(serializers.Serializer):
    provider_id = serializers.IntegerField()
    provider_location_id = serializers.IntegerField(required=False, allow_null=True)
    employee_id = serializers.IntegerField(required=False, allow_null=True)
    service_id = serializers.IntegerField()
    pet_type_id = serializers.IntegerField()
    breed_id = serializers.IntegerField()
    size_code = serializers.CharField(max_length=10)
    owner_first_name = serializers.CharField(max_length=100)
    owner_last_name = serializers.CharField(max_length=100)
    owner_phone_number = serializers.CharField(max_length=64)
    owner_email = serializers.EmailField(required=False, allow_blank=True)
    pet_name = serializers.CharField(max_length=100)
    start_time = serializers.DateTimeField()
    is_emergency = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class ManualBookingProtocolUpsertSerializer(serializers.Serializer):
    description = serializers.CharField(required=False, allow_blank=True)
    diagnosis = serializers.CharField(required=False, allow_blank=True)
    anamnesis = serializers.CharField(required=False, allow_blank=True)
    results = serializers.CharField(required=False, allow_blank=True)
    recommendations = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    serial_number = serializers.CharField(required=False, allow_blank=True)
    next_date = serializers.DateField(required=False, allow_null=True)


class ManualBookingCancelSerializer(serializers.Serializer):
    cancellation_reason_id = serializers.IntegerField(required=False, allow_null=True)
    cancellation_reason_text = serializers.CharField(required=False, allow_blank=True)


class ManualBookingResolveConflictSerializer(ManualBookingCreateUpdateSerializer):
    resolution_action = serializers.ChoiceField(choices=['cancel_conflict', 'move_conflict', 'abort'])
    conflict_kind = serializers.ChoiceField(choices=['booking', 'manual'])
    conflict_id = serializers.IntegerField()
    move_start_time = serializers.DateTimeField(required=False)
