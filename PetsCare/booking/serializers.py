"""
Сериализаторы для моделей бронирования.

Этот модуль содержит сериализаторы для:
1. Бронирования
2. Статуса бронирования
3. Временного слота
4. Платежа бронирования
5. Отзыва бронирования
"""

from datetime import timedelta

from rest_framework import serializers
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .models import (
    Booking,
    BookingCancellationReason,
    BookingServiceIssue,
    BookingStatus,
    TimeSlot,
    BookingPayment,
    BookingReview
)
from .constants import (
    BOOKING_SERVICE_ISSUE_REPORT_WINDOW_DAYS,
    BOOKING_STATUS_ACTIVE,
    BOOKING_STATUS_CANCELLED,
    CANCELLED_BY_CLIENT,
    CANCELLED_BY_PROVIDER,
    CANCELLATION_REASON_CLIENT_NO_SHOW,
    CLIENT_ATTENDANCE_CHOICES,
    CLIENT_ATTENDANCE_NO_SHOW,
    CLIENT_ATTENDANCE_UNKNOWN,
    ISSUE_STATUS_ACKNOWLEDGED,
    ISSUE_STATUS_OPEN,
    RESOLUTION_OUTCOME_CLIENT_CANCELLED,
    RESOLUTION_OUTCOME_COMPLETED,
    RESOLUTION_OUTCOME_CLAIM_REJECTED,
    RESOLUTION_OUTCOME_PROVIDER_CANCELLED,
)
from providers.models import Provider, Employee, ProviderLocation
from providers.serializers import EmployeeSerializer, ProviderSerializer
from catalog.models import Service
from users.models import User
from pets.models import ChronicCondition, Pet, PetHealthNote, VisitRecord
from pets.serializers import PetDocumentSummarySerializer, VisitRecordAddendumSerializer
from .manual_notes import replace_manual_booking_notes


def get_context_language_code(context):
    request = context.get('request')
    if request is None:
        return None

    language_code = None
    query_params = getattr(request, 'query_params', None)
    if query_params is not None:
        language_code = query_params.get('lang')
    elif hasattr(request, 'GET'):
        language_code = request.GET.get('lang')

    if not language_code:
        raw = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        language_code = raw.split(',')[0].split('-')[0].strip().lower() if raw else None

    if not language_code:
        return None

    language_code = language_code.split('-')[0].lower()
    return 'me' if language_code == 'cnr' else language_code


def build_manual_entry_payload(booking):
    """Собирает payload guest/manual metadata для API."""
    metadata = booking.get_manual_entry_metadata() or {}
    if booking.source != Booking.BookingSource.MANUAL_ENTRY and not metadata:
        return None

    return {
        'is_guest': bool(metadata.get('is_guest')),
        'is_emergency': bool(metadata.get('is_emergency')),
        'guest_client_name': metadata.get('guest_client_name'),
        'guest_client_phone': metadata.get('guest_client_phone'),
        'guest_pet_name': metadata.get('guest_pet_name'),
        'guest_pet_species': metadata.get('guest_pet_species'),
        'guest_pet_type_id': metadata.get('guest_pet_type_id'),
        'guest_pet_weight': metadata.get('guest_pet_weight'),
    }


class BookingStatusSerializer(serializers.ModelSerializer):
    """Сериализатор для статуса бронирования."""

    display_name = serializers.CharField(source='get_localized_name', read_only=True)

    class Meta:
        model = BookingStatus
        fields = ['id', 'name', 'display_name', 'description']


class BookingCancellationReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingCancellationReason
        fields = ['id', 'code', 'label', 'scope']


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
        fields = ['id', 'email', 'first_name', 'last_name', 'phone_number']


class BookingLifecycleFieldsMixin(serializers.ModelSerializer):
    status = BookingStatusSerializer(read_only=True)
    status_code = serializers.CharField(source='status.name', read_only=True)
    status_display = serializers.CharField(source='status.get_localized_name', read_only=True)
    ui_status = serializers.SerializerMethodField()
    source = serializers.CharField(read_only=True)
    notes = serializers.SerializerMethodField()
    manual_entry = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    has_open_service_issue = serializers.SerializerMethodField()
    latest_service_issue = serializers.SerializerMethodField()
    cancelled_by_user = BookingUserCompactSerializer(read_only=True)
    cancellation_reason = BookingCancellationReasonSerializer(read_only=True)
    completed_by_user = BookingUserCompactSerializer(read_only=True)

    def _get_cached_service_issues(self, obj):
        prefetched = getattr(obj, '_prefetched_objects_cache', {})
        issues = prefetched.get('service_issues')
        if issues is None:
            return None
        return sorted(list(issues), key=lambda issue: issue.created_at, reverse=True)

    def get_ui_status(self, obj):
        if obj.is_overdue:
            return {'code': 'overdue', 'label': str(_('Overdue'))}
        if obj.status.name == BOOKING_STATUS_CANCELLED:
            if obj.cancelled_by == CANCELLED_BY_CLIENT:
                return {'code': 'cancelled_by_client', 'label': str(_('Cancelled by client'))}
            if obj.cancelled_by == CANCELLED_BY_PROVIDER:
                return {'code': 'cancelled_by_provider', 'label': str(_('Cancelled by provider'))}
        return {'code': obj.status.name, 'label': obj.status.get_localized_name()}

    def get_notes(self, obj):
        return obj.display_notes

    def get_manual_entry(self, obj):
        return build_manual_entry_payload(obj)

    def get_has_open_service_issue(self, obj):
        issues = self._get_cached_service_issues(obj)
        if issues is not None:
            return any(issue.status in (ISSUE_STATUS_OPEN, ISSUE_STATUS_ACKNOWLEDGED) for issue in issues)
        return obj.has_open_service_issue

    def get_latest_service_issue(self, obj):
        issues = self._get_cached_service_issues(obj)
        latest_issue = issues[0] if issues else None
        if issues is None:
            latest_issue = obj.latest_service_issue
        if latest_issue is None:
            return None
        return BookingServiceIssueSummarySerializer(latest_issue, context=self.context).data


class BookingPetListSerializer(serializers.ModelSerializer):
    pet_type_name = serializers.SerializerMethodField()
    breed_name = serializers.SerializerMethodField()

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

    def get_pet_type_name(self, obj):
        if not obj.pet_type:
            return None
        return obj.pet_type.get_localized_name()

    def get_breed_name(self, obj):
        if not obj.breed:
            return None
        return obj.breed.get_localized_name()


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
    name_display = serializers.CharField(source='get_localized_name', read_only=True)
    root_category_code = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = ['id', 'name', 'name_display', 'code', 'root_category_code', 'is_client_facing']

    def get_root_category_code(self, obj):
        """Код корневой категории (veterinary, grooming и т.д.) для определения семейства услуги."""
        current = obj
        while current.parent_id:
            current = current.parent
        return current.code if current else None


class BookingChronicConditionSerializer(serializers.ModelSerializer):
    name_display = serializers.SerializerMethodField()

    class Meta:
        model = ChronicCondition
        fields = ['id', 'code', 'name', 'name_display']

    def get_name_display(self, obj):
        return obj.get_localized_name(get_context_language_code(self.context))


class BookingPetHealthNoteDetailSerializer(serializers.ModelSerializer):

    class Meta:
        model = PetHealthNote
        fields = [
            'id',
            'date',
            'title',
            'description',
            'next_visit',
            'created_at',
            'updated_at',
        ]


class BookingVisitRecordDetailSerializer(serializers.ModelSerializer):
    provider_location_name = serializers.CharField(source='provider_location.name', read_only=True)
    service_name = serializers.SerializerMethodField()
    employee_name = serializers.SerializerMethodField()
    documents = PetDocumentSummarySerializer(many=True, read_only=True)
    addenda = VisitRecordAddendumSerializer(many=True, read_only=True)
    booking_id = serializers.SerializerMethodField()

    class Meta:
        model = VisitRecord
        fields = [
            'id',
            'provider',
            'provider_location',
            'provider_location_name',
            'service',
            'service_name',
            'employee',
            'employee_name',
            'date',
            'next_date',
            'description',
            'diagnosis',
            'anamnesis',
            'results',
            'recommendations',
            'notes',
            'serial_number',
            'documents',
            'addenda',
            'booking_id',
            'created_at',
            'updated_at',
        ]

    def get_service_name(self, obj):
        if obj.service is None:
            return None
        return obj.service.get_localized_name(get_context_language_code(self.context))

    def get_employee_name(self, obj):
        if obj.employee is None or obj.employee.user is None:
            return None
        full_name = obj.employee.user.get_full_name().strip()
        return full_name or obj.employee.user.email

    def get_booking_id(self, obj):
        prefetched = getattr(obj, '_prefetched_objects_cache', {})
        source_bookings = prefetched.get('source_bookings')
        if source_bookings is not None:
            booking = source_bookings[0] if source_bookings else None
            return booking.id if booking else None
        return obj.source_bookings.values_list('id', flat=True).order_by('-created_at').first()


class BookingPetDetailSerializer(serializers.ModelSerializer):
    pet_type_name = serializers.SerializerMethodField()
    breed_name = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    chronic_conditions = BookingChronicConditionSerializer(many=True, read_only=True)
    health_notes = BookingPetHealthNoteDetailSerializer(many=True, read_only=True)
    medical_records = BookingPetHealthNoteDetailSerializer(source='health_notes', many=True, read_only=True)
    visit_records = BookingVisitRecordDetailSerializer(source='records', many=True, read_only=True)
    records = BookingVisitRecordDetailSerializer(many=True, read_only=True)
    documents = PetDocumentSummarySerializer(many=True, read_only=True)
    main_owner_name = serializers.SerializerMethodField()
    main_owner_email = serializers.SerializerMethodField()
    records_count = serializers.SerializerMethodField()
    last_visit_date = serializers.SerializerMethodField()

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
            'age',
            'weight',
            'gender',
            'is_neutered',
            'rabies_vaccination_expiry',
            'core_vaccination_expiry',
            'identifier',
            'description',
            'behavioral_traits',
            'special_needs',
            'medical_conditions',
            'chronic_conditions',
            'health_notes',
            'medical_records',
            'visit_records',
            'records',
            'documents',
            'main_owner_name',
            'main_owner_email',
            'records_count',
            'last_visit_date',
        ]

    def get_pet_type_name(self, obj):
        if obj.pet_type is None:
            return None
        return obj.pet_type.get_localized_name(get_context_language_code(self.context))

    def get_breed_name(self, obj):
        if obj.breed is None:
            return None
        return obj.breed.get_localized_name(get_context_language_code(self.context))

    def get_age(self, obj):
        return obj.get_age()

    def get_main_owner_name(self, obj):
        main_owner = obj.main_owner
        if main_owner is None:
            return None
        full_name = main_owner.get_full_name().strip()
        return full_name or main_owner.email

    def get_main_owner_email(self, obj):
        main_owner = obj.main_owner
        if main_owner is None:
            return None
        return main_owner.email

    def get_records_count(self, obj):
        prefetched = getattr(obj, '_prefetched_objects_cache', {})
        records = prefetched.get('records')
        if records is not None:
            return len(records)
        return obj.records.count()

    def get_last_visit_date(self, obj):
        prefetched = getattr(obj, '_prefetched_objects_cache', {})
        records = prefetched.get('records')
        if records is not None:
            latest_record = records[0] if records else None
        else:
            latest_record = obj.records.order_by('-date').only('date').first()
        return latest_record.date if latest_record is not None else None


class BookingListSerializer(BookingLifecycleFieldsMixin, serializers.ModelSerializer):
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
            'status_code',
            'status_display',
            'ui_status',
            'source',
            'manual_entry',
            'is_overdue',
            'has_open_service_issue',
            'latest_service_issue',
            'completed_at',
            'completed_by_actor',
            'completed_by_user',
            'completion_reason_code',
            'cancelled_by',
            'cancelled_by_user',
            'cancelled_at',
            'cancellation_reason',
            'cancellation_reason_text',
            'client_attendance',
            'start_time',
            'end_time',
            'occupied_duration_minutes',
            'notes',
            'price',
            'created_at',
            'updated_at'
        ]


class BookingSerializer(BookingLifecycleFieldsMixin, serializers.ModelSerializer):
    """Сериализатор для бронирования."""
    
    user = BookingUserCompactSerializer(read_only=True)
    escort_owner = BookingUserCompactSerializer(read_only=True)
    pet = BookingPetDetailSerializer(read_only=True)
    visit_record = BookingVisitRecordDetailSerializer(read_only=True)
    pet_record = BookingVisitRecordDetailSerializer(source='visit_record', read_only=True)
    provider = BookingProviderListSerializer(read_only=True)
    provider_location = BookingProviderLocationListSerializer(read_only=True)
    employee = BookingEmployeeListSerializer(read_only=True)
    service = BookingServiceListSerializer(read_only=True)
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
            'visit_record',
            'pet_record',
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
            'has_open_service_issue',
            'latest_service_issue',
            'completed_at',
            'completed_by_actor',
            'completed_by_user',
            'completion_reason_code',
            'cancelled_by',
            'cancelled_by_user',
            'cancelled_at',
            'cancellation_reason',
            'cancellation_reason_text',
            'client_attendance',
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


class BookingUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для обновления бронирования."""
    
    class Meta:
        model = Booking
        fields = ['notes']

    def update(self, instance, validated_data):
        """Обновляет заметки, сохраняя служебную metadata ручного бронирования."""
        if 'notes' in validated_data:
            instance.notes = replace_manual_booking_notes(instance.notes, validated_data['notes'])
        instance.save(update_fields=['notes', 'updated_at'])
        return instance


class BookingStatusUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для обновления статуса бронирования."""
    
    class Meta:
        model = Booking
        fields = ['status']


class BookingCompletionActionSerializer(serializers.Serializer):
    employee_comment = serializers.CharField(required=False, allow_blank=True)
    visit_record = serializers.DictField(required=False)

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            normalized_data = data.copy()
        else:
            normalized_data = dict(data)

        if 'visit_record' not in normalized_data and 'pet_record' in normalized_data:
            normalized_data['visit_record'] = normalized_data['pet_record']

        return super().to_internal_value(normalized_data)

    def _validate_visit_record_payload(self, value):
        allowed_fields = {
            'description',
            'diagnosis',
            'anamnesis',
            'results',
            'recommendations',
            'notes',
            'serial_number',
            'next_date',
        }
        extra_fields = sorted(set(value.keys()) - allowed_fields)
        if extra_fields:
            raise serializers.ValidationError(
                _('Unsupported visit record fields: {}').format(', '.join(extra_fields))
            )

        serializer = BookingCompletionVisitRecordSerializer(data=value)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def validate_visit_record(self, value):
        return self._validate_visit_record_payload(value)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        initial_data = getattr(self, 'initial_data', {})
        if 'pet_record' in initial_data and 'visit_record' in initial_data:
            raise serializers.ValidationError(
                {'pet_record': _('Use either pet_record or visit_record, not both.')}
            )
        return attrs


class BookingCompletionVisitRecordSerializer(serializers.Serializer):
    description = serializers.CharField(required=False, allow_blank=True)
    diagnosis = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    anamnesis = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    results = serializers.CharField(required=False, allow_blank=True)
    recommendations = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    serial_number = serializers.CharField(required=False, allow_blank=True)
    next_date = serializers.DateField(required=False, allow_null=True)


class BookingVisitRecordUpsertSerializer(BookingCompletionVisitRecordSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        has_meaningful_data = any(
            value not in (None, '', [], {})
            for value in attrs.values()
        )
        if not has_meaningful_data:
            raise serializers.ValidationError(
                {'non_field_errors': [_('Visit protocol cannot be empty.')]}
            )
        return attrs


class BookingCancellationActionSerializer(serializers.Serializer):
    reason_code = serializers.SlugRelatedField(
        slug_field='code',
        queryset=BookingCancellationReason.objects.filter(is_active=True),
        source='cancellation_reason',
    )
    reason_text = serializers.CharField(
        required=False,
        allow_blank=True,
        source='cancellation_reason_text',
    )
    client_attendance = serializers.ChoiceField(
        choices=CLIENT_ATTENDANCE_CHOICES,
        required=False,
        default=CLIENT_ATTENDANCE_UNKNOWN,
    )

    def validate(self, attrs):
        cancellation_reason = attrs['cancellation_reason']
        cancelled_by = self.context['cancelled_by']
        client_attendance = attrs.get('client_attendance', CLIENT_ATTENDANCE_UNKNOWN)

        if cancellation_reason.scope != cancelled_by:
            raise serializers.ValidationError({
                'reason_code': _('Reason is not available for this cancellation side.')
            })

        if cancellation_reason.code == CANCELLATION_REASON_CLIENT_NO_SHOW:
            if cancelled_by != CANCELLED_BY_PROVIDER:
                raise serializers.ValidationError({
                    'reason_code': _('client_no_show is provider-only.')
                })
            attrs['client_attendance'] = CLIENT_ATTENDANCE_NO_SHOW
        elif client_attendance == CLIENT_ATTENDANCE_NO_SHOW:
            raise serializers.ValidationError({
                'client_attendance': _('no_show attendance requires client_no_show reason.')
            })

        return attrs


class BookingNoShowActionSerializer(serializers.Serializer):
    reason_text = serializers.CharField(required=False, allow_blank=True)


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


class ManualBookingSearchSerializer(serializers.Serializer):
    """Параметры поиска клиента для ручного бронирования."""

    query = serializers.CharField(required=False, allow_blank=True)
    provider_location_id = serializers.IntegerField(required=False)


class ManualBookingCreateSerializer(serializers.Serializer):
    """Payload для ручного создания бронирования персоналом."""

    is_guest = serializers.BooleanField()
    guest_client_phone = serializers.CharField(required=False, allow_blank=True)
    guest_client_name = serializers.CharField(required=False, allow_blank=True)
    guest_pet_name = serializers.CharField(required=False, allow_blank=True)
    guest_pet_species = serializers.CharField(required=False, allow_blank=True)
    guest_pet_type_id = serializers.IntegerField(required=False)
    guest_pet_weight = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)
    user_id = serializers.IntegerField(required=False)
    pet_id = serializers.IntegerField(required=False)
    escort_owner_id = serializers.IntegerField(required=False)
    provider_location_id = serializers.IntegerField()
    employee_id = serializers.IntegerField()
    service_id = serializers.IntegerField()
    start_time = serializers.DateTimeField()
    notes = serializers.CharField(required=False, allow_blank=True)
    is_emergency = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        """Проверяет обязательные поля для guest и registered сценариев."""
        is_guest = attrs['is_guest']
        errors = {}

        if is_guest:
            required_guest_fields = (
                'guest_client_phone',
                'guest_client_name',
                'guest_pet_name',
            )
            for field_name in required_guest_fields:
                if not str(attrs.get(field_name, '')).strip():
                    errors[field_name] = _('This field is required for guest bookings.')
        else:
            required_registered_fields = ('user_id', 'pet_id')
            for field_name in required_registered_fields:
                if attrs.get(field_name) is None:
                    errors[field_name] = _('This field is required for registered bookings.')

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

class BookingServiceIssueSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingServiceIssue
        fields = [
            'id',
            'issue_type',
            'status',
            'resolution_outcome',
            'client_attendance_snapshot',
            'resolved_by_actor',
            'resolved_at',
            'created_at',
        ]


class BookingServiceIssueSerializer(serializers.ModelSerializer):
    reported_by_user = BookingUserCompactSerializer(read_only=True)
    resolved_by_user = BookingUserCompactSerializer(read_only=True)

    class Meta:
        model = BookingServiceIssue
        fields = [
            'id',
            'booking',
            'issue_type',
            'reported_by_user',
            'reported_by_side',
            'client_attendance_snapshot',
            'description',
            'status',
            'resolution_outcome',
            'resolved_by_user',
            'resolved_by_actor',
            'resolved_at',
            'resolution_note',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'booking',
            'issue_type',
            'reported_by_user',
            'reported_by_side',
            'status',
            'resolution_outcome',
            'resolved_by_user',
            'resolved_by_actor',
            'resolved_at',
            'created_at',
            'updated_at',
        ]


class BookingServiceIssueCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingServiceIssue
        fields = [
            'issue_type',
            'client_attendance_snapshot',
            'description',
        ]

    def validate(self, attrs):
        booking = self.context['booking']
        now = timezone.now()

        if booking.status.name != BOOKING_STATUS_ACTIVE:
            raise serializers.ValidationError(
                _('Service issues can only be reported for active bookings.')
            )

        if now < booking.start_time:
            raise serializers.ValidationError(
                _('Service issues can only be reported from the booking start time.')
            )

        if now > booking.end_time + timedelta(days=BOOKING_SERVICE_ISSUE_REPORT_WINDOW_DAYS):
            raise serializers.ValidationError(
                _('The service issue reporting window has expired.')
            )

        if attrs.get('client_attendance_snapshot') == CLIENT_ATTENDANCE_NO_SHOW:
            raise serializers.ValidationError({
                'client_attendance_snapshot': _(
                    'Use the provider no-show flow when the client did not arrive.'
                )
            })

        if booking.service_issues.filter(
            status__in=(ISSUE_STATUS_OPEN, ISSUE_STATUS_ACKNOWLEDGED)
        ).exists():
            raise serializers.ValidationError(
                _('An open service issue already exists for this booking.')
            )

        return attrs


class BookingServiceIssueResolveSerializer(serializers.Serializer):
    resolution_outcome = serializers.ChoiceField(
        choices=[
            RESOLUTION_OUTCOME_PROVIDER_CANCELLED,
            RESOLUTION_OUTCOME_COMPLETED,
            RESOLUTION_OUTCOME_CLIENT_CANCELLED,
            RESOLUTION_OUTCOME_CLAIM_REJECTED,
        ]
    )
    resolution_note = serializers.CharField(required=False, allow_blank=True)
    cancellation_reason = serializers.CharField(required=False, allow_blank=True, help_text=_('Required if resolution is a cancellation'))

    def validate(self, attrs):
        outcome = attrs['resolution_outcome']
        reason_code = (attrs.get('cancellation_reason') or '').strip()

        if outcome in (RESOLUTION_OUTCOME_PROVIDER_CANCELLED, RESOLUTION_OUTCOME_CLIENT_CANCELLED):
            if not reason_code:
                raise serializers.ValidationError({
                    'cancellation_reason': _('This field is required for cancellation resolutions.')
                })

            scope = (
                CANCELLED_BY_PROVIDER
                if outcome == RESOLUTION_OUTCOME_PROVIDER_CANCELLED
                else CANCELLED_BY_CLIENT
            )
            reason = BookingCancellationReason.objects.filter(
                code=reason_code,
                scope=scope,
                is_active=True,
            ).first()
            if reason is None:
                raise serializers.ValidationError({
                    'cancellation_reason': _('Invalid cancellation reason for this resolution outcome.')
                })
            attrs['cancellation_reason_obj'] = reason

        return attrs
