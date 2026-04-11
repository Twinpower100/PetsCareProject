"""
Сериализаторы для API модуля питомцев.

Этот модуль содержит сериализаторы для:
1. Питомца
2. Создания/обновления питомца
3. Поиска питомцев
4. Медицинских записей
5. Записей в карте питомца
6. Доступа к карте питомца
7. Канонического lifecycle-контракта документов питомца
"""

from rest_framework import serializers
from django.urls import reverse
import os
from .models import (
    Pet,
    PetHealthNote,
    VisitRecord,
    PetAccess,
    PetDocument,
    PetType,
    Breed,
    DocumentType,
    ChronicCondition,
    PhysicalFeature,
    BehavioralTrait,
    PetOwner,
    VisitRecordAddendum,
)
from users.models import User
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from .medical_card_access import (
    can_manage_visit_record_as_provider,
    can_deactivate_pet_document,
    can_update_pet_document,
    can_view_pet_document,
    can_withdraw_pet_document,
    can_view_health_notes,
    get_accessible_documents_queryset,
    get_accessible_visit_records_queryset,
    is_pet_owner,
)
from .document_type_catalog import (
    DOCUMENT_TYPE_ALLOWED_EXTENSIONS,
    DOCUMENT_TYPE_ALLOWED_MIME_TYPES,
    PROVIDER_VISIT_DOCUMENT_CONTEXT,
    get_document_type_definition_by_name,
    get_document_type_codes_for_context,
)

from .models import PetOwnerIncapacity, PetIncapacityNotification
from .constants import (
    PET_PHOTO_MAX_SIZE_BYTES,
    PET_PHOTO_MAX_SIZE_MB,
    PET_PHOTO_MAX_WIDTH,
    PET_PHOTO_MAX_HEIGHT,
    PET_PHOTO_ALLOWED_CONTENT_TYPES,
)


class PetHealthNoteSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()

    class Meta:
        model = PetHealthNote
        fields = [
            'id',
            'pet',
            'date',
            'title',
            'description',
            'next_visit',
            'kind',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'pet', 'created_at', 'updated_at']

    def get_kind(self, obj):
        return 'health_note'

    def validate(self, data):
        if data.get('date') and data['date'] > timezone.localdate():
            raise serializers.ValidationError(
                {'date': _('Date cannot be in the future')}
            )
        return data


class VisitRecordAddendumSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta:
        model = VisitRecordAddendum
        fields = [
            'id',
            'visit_record',
            'author',
            'author_name',
            'content',
            'documents',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'visit_record',
            'author',
            'author_name',
            'documents',
            'created_at',
            'updated_at',
        ]

    def get_author_name(self, obj):
        return obj.author.get_full_name() or obj.author.email

    def get_documents(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        queryset = getattr(obj, 'documents', PetDocument._default_manager.none())
        if hasattr(queryset, 'all'):
            queryset = queryset.all()
        accessible = [document for document in queryset if user and can_view_pet_document(user, document)]
        return PetDocumentSummarySerializer(
            accessible,
            many=True,
            context=self.context,
        ).data


class PetDocumentSummarySerializer(serializers.ModelSerializer):
    """Каноническое чтение документа с lifecycle- и permission-метаданными."""

    document_type_name = serializers.SerializerMethodField()
    document_type_code = serializers.SerializerMethodField()
    visit_record = serializers.IntegerField(source='visit_record_id', read_only=True)
    visit_record_addendum = serializers.IntegerField(source='visit_record_addendum_id', read_only=True)
    health_note = serializers.IntegerField(source='health_note_id', read_only=True)
    uploaded_by_name = serializers.SerializerMethodField()
    deactivated_by = serializers.IntegerField(source='deactivated_by_id', read_only=True)
    deactivated_by_name = serializers.SerializerMethodField()
    withdrawn_by = serializers.IntegerField(source='withdrawn_by_id', read_only=True)
    withdrawn_by_name = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    management_context = serializers.CharField(read_only=True)
    can_update = serializers.SerializerMethodField()
    can_deactivate = serializers.SerializerMethodField()
    can_withdraw = serializers.SerializerMethodField()
    days_until_expiry = serializers.IntegerField(read_only=True)
    download_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()

    class Meta:
        model = PetDocument
        fields = [
            'id',
            'file',
            'name',
            'description',
            'document_type',
            'document_type_code',
            'document_type_name',
            'pet',
            'visit_record',
            'visit_record_addendum',
            'health_note',
            'issue_date',
            'expiry_date',
            'document_number',
            'issuing_authority',
            'uploaded_by',
            'uploaded_by_name',
            'uploaded_at',
            'version',
            'management_context',
            'lifecycle_status',
            'lifecycle_reason_code',
            'lifecycle_reason_comment',
            'deactivated_at',
            'deactivated_by',
            'deactivated_by_name',
            'withdrawn_at',
            'withdrawn_by',
            'withdrawn_by_name',
            'is_expired',
            'is_active',
            'can_update',
            'can_deactivate',
            'can_withdraw',
            'days_until_expiry',
            'download_url',
            'preview_url',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'pet',
            'uploaded_by',
            'uploaded_by_name',
            'uploaded_at',
            'version',
            'management_context',
            'lifecycle_status',
            'lifecycle_reason_code',
            'lifecycle_reason_comment',
            'deactivated_at',
            'deactivated_by',
            'deactivated_by_name',
            'withdrawn_at',
            'withdrawn_by',
            'withdrawn_by_name',
            'is_expired',
            'is_active',
            'can_update',
            'can_deactivate',
            'can_withdraw',
            'days_until_expiry',
            'download_url',
            'preview_url',
            'created_at',
            'updated_at',
        ]

    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.get_full_name() or obj.uploaded_by.email

    def get_document_type_code(self, obj):
        if not obj.document_type:
            return None
        return obj.document_type.code

    def get_document_type_name(self, obj):
        if not obj.document_type:
            return None
        request = self.context.get('request')
        lang = request.GET.get('lang') if request else None
        if not lang and request and request.META.get('HTTP_ACCEPT_LANGUAGE'):
            raw = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
            lang = raw.split(',')[0].split('-')[0].strip().lower() if raw else None
        return obj.document_type.get_localized_name(lang) if lang else obj.document_type.get_localized_name()

    def _build_url(self, obj, route_name):
        request = self.context.get('request')
        url = reverse(route_name, kwargs={'document_id': obj.id})
        return request.build_absolute_uri(url) if request else url

    def get_download_url(self, obj):
        return self._build_url(obj, 'pets:document-download')

    def get_preview_url(self, obj):
        return self._build_url(obj, 'pets:document-preview')

    def get_deactivated_by_name(self, obj):
        if not obj.deactivated_by:
            return None
        return obj.deactivated_by.get_full_name() or obj.deactivated_by.email

    def get_withdrawn_by_name(self, obj):
        if not obj.withdrawn_by:
            return None
        return obj.withdrawn_by.get_full_name() or obj.withdrawn_by.email

    def _get_request_user(self):
        request = self.context.get('request')
        return getattr(request, 'user', None)

    def get_can_update(self, obj):
        user = self._get_request_user()
        return bool(user and can_update_pet_document(user, obj))

    def get_can_deactivate(self, obj):
        user = self._get_request_user()
        return bool(user and can_deactivate_pet_document(user, obj))

    def get_can_withdraw(self, obj):
        user = self._get_request_user()
        return bool(user and can_withdraw_pet_document(user, obj))


class PetDocumentSerializer(PetDocumentSummarySerializer):
    """Legacy-совместимый сериализатор создания документа."""

    visit_record = serializers.PrimaryKeyRelatedField(
        queryset=VisitRecord._default_manager.all(),
        required=False,
        allow_null=True,
    )
    visit_record_addendum = serializers.PrimaryKeyRelatedField(
        queryset=VisitRecordAddendum._default_manager.all(),
        required=False,
        allow_null=True,
    )
    health_note = serializers.PrimaryKeyRelatedField(
        queryset=PetHealthNote._default_manager.all(),
        required=False,
        allow_null=True,
    )

    def validate_file(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError(_('File is too large (max 10MB)'))

        file_name = value.name.lower()
        if not any(file_name.endswith(ext) for ext in DOCUMENT_TYPE_ALLOWED_EXTENSIONS):
            raise serializers.ValidationError(
                _('Unsupported file type. Allowed: PDF and JPG/PNG images')
            )

        content_type = getattr(value, 'content_type', None)
        if content_type and content_type not in DOCUMENT_TYPE_ALLOWED_MIME_TYPES:
            raise serializers.ValidationError(_('Unsupported MIME type'))

        return value

    def validate(self, data):
        pet = self.context.get('pet')
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        visit_record = data.get('visit_record')
        visit_record_addendum = data.get('visit_record_addendum')
        health_note = data.get('health_note')

        if pet is None:
            raise serializers.ValidationError({'pet': _('Pet is required')})

        if visit_record and visit_record.pet_id != pet.id:
            raise serializers.ValidationError({'visit_record': _('Visit record belongs to another pet')})

        if (
            visit_record_addendum
            and visit_record_addendum.visit_record.pet_id != pet.id
        ):
            raise serializers.ValidationError(
                {'visit_record_addendum': _('Visit addendum belongs to another pet')}
            )

        if health_note and health_note.pet_id != pet.id:
            raise serializers.ValidationError(
                {'health_note': _('Health note belongs to another pet')}
            )

        record_count = sum([
            1 if visit_record else 0,
            1 if data.get('visit_record_addendum') else 0,
            1 if health_note else 0,
        ])
        if record_count > 1:
            raise serializers.ValidationError(_('Document can only be attached to one record'))

        document_type = data.get('document_type')
        if document_type is None:
            raise serializers.ValidationError(
                {'document_type': _('Document type is required')}
            )

        is_owner_upload = bool(user and is_pet_owner(user, pet))
        is_system_upload = bool(user and (user.is_superuser or user.is_system_admin()))
        provider_context_record = visit_record
        if provider_context_record is None and visit_record_addendum is not None:
            provider_context_record = visit_record_addendum.visit_record
        acts_as_provider = bool(
            provider_context_record
            and user
            and not is_system_upload
            and can_manage_visit_record_as_provider(user, provider_context_record)
        )

        if provider_context_record is None:
            if not (is_owner_upload or is_system_upload):
                raise serializers.ValidationError(
                    {'visit_record': _('Provider staff can upload documents only for a specific visit record')}
                )
        elif not (acts_as_provider or is_system_upload):
            if is_owner_upload:
                raise serializers.ValidationError(
                    {'visit_record': _('Owners can upload documents only in pet-card context')}
                )
            raise serializers.ValidationError(
                {'visit_record': _('You do not have permission to upload documents for this visit record')}
            )

        if acts_as_provider:
            allowed_codes = set(
                get_document_type_codes_for_context(PROVIDER_VISIT_DOCUMENT_CONTEXT) or ()
            )
            if document_type.code not in allowed_codes:
                raise serializers.ValidationError(
                    {'document_type': _('This document type is not allowed in provider visit context')}
                )

        if health_note and not (is_owner_upload or is_system_upload):
            raise serializers.ValidationError(
                {'health_note': _('Only pet owners can attach documents to health notes')}
            )

        if document_type.requires_issue_date and not data.get('issue_date'):
            raise serializers.ValidationError(
                {'issue_date': _('Issue date is required for this document type')}
            )
        if document_type.requires_expiry_date and not data.get('expiry_date'):
            raise serializers.ValidationError(
                {'expiry_date': _('Expiry date is required for this document type')}
            )
        if document_type.requires_issuing_authority and not data.get('issuing_authority'):
            raise serializers.ValidationError(
                {'issuing_authority': _('Issuing authority is required for this document type')}
            )
        if document_type.requires_document_number and not data.get('document_number'):
            raise serializers.ValidationError(
                {'document_number': _('Document number is required for this document type')}
            )

        if data.get('issue_date') and data.get('expiry_date') and data['issue_date'] > data['expiry_date']:
            raise serializers.ValidationError(
                {'expiry_date': _('Issue date cannot be after expiry date')}
            )

        return data


class CanonicalPetDocumentCreateSerializer(serializers.ModelSerializer):
    """Строгий сериализатор канонического create-контракта документов."""

    file = serializers.FileField(required=True)
    name = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    document_type = serializers.PrimaryKeyRelatedField(
        queryset=DocumentType._default_manager.filter(is_active=True),
        required=True,
        allow_null=False,
    )
    visit_record = serializers.PrimaryKeyRelatedField(
        queryset=VisitRecord._default_manager.all(),
        required=False,
        allow_null=True,
    )
    visit_record_addendum = serializers.PrimaryKeyRelatedField(
        queryset=VisitRecordAddendum._default_manager.all(),
        required=False,
        allow_null=True,
    )
    health_note = serializers.PrimaryKeyRelatedField(
        queryset=PetHealthNote._default_manager.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = PetDocument
        fields = [
            'id',
            'file',
            'name',
            'description',
            'document_type',
            'visit_record',
            'visit_record_addendum',
            'health_note',
            'issue_date',
            'expiry_date',
            'document_number',
            'issuing_authority',
        ]
        read_only_fields = ['id']

    def validate_file(self, value):
        """Проверяет допустимость формата файла для v1."""
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError(_('File is too large (max 10MB)'))

        file_name = value.name.lower()
        if not any(file_name.endswith(ext) for ext in DOCUMENT_TYPE_ALLOWED_EXTENSIONS):
            raise serializers.ValidationError(
                _('Unsupported file type. Allowed: PDF and JPG/PNG images')
            )

        content_type = getattr(value, 'content_type', None)
        if content_type and content_type not in DOCUMENT_TYPE_ALLOWED_MIME_TYPES:
            raise serializers.ValidationError(_('Unsupported MIME type'))

        return value

    def _validate_document_type_requirements(self, document_type, data):
        """Проверяет обязательные метаданные для выбранного типа документа."""
        if document_type.requires_issue_date and not data.get('issue_date'):
            raise serializers.ValidationError(
                {'issue_date': _('Issue date is required for this document type')}
            )

        if document_type.requires_expiry_date and not data.get('expiry_date'):
            raise serializers.ValidationError(
                {'expiry_date': _('Expiry date is required for this document type')}
            )

        if document_type.requires_issuing_authority and not data.get('issuing_authority'):
            raise serializers.ValidationError(
                {'issuing_authority': _('Issuing authority is required for this document type')}
            )

        if document_type.requires_document_number and not data.get('document_number'):
            raise serializers.ValidationError(
                {'document_number': _('Document number is required for this document type')}
            )

    def validate(self, data):
        """Валидирует строгий owner/provider контракт создания."""
        pet = self.context.get('pet')
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        visit_record = data.get('visit_record')
        visit_record_addendum = data.get('visit_record_addendum')
        health_note = data.get('health_note')
        document_type = data.get('document_type')

        if pet is None:
            raise serializers.ValidationError({'pet': _('Pet is required')})

        if visit_record and visit_record.pet_id != pet.id:
            raise serializers.ValidationError(
                {'visit_record': _('Visit record belongs to another pet')}
            )

        if (
            visit_record_addendum
            and visit_record_addendum.visit_record.pet_id != pet.id
        ):
            raise serializers.ValidationError(
                {'visit_record_addendum': _('Visit addendum belongs to another pet')}
            )

        if health_note and health_note.pet_id != pet.id:
            raise serializers.ValidationError(
                {'health_note': _('Health note belongs to another pet')}
            )

        record_count = sum([
            1 if visit_record else 0,
            1 if visit_record_addendum else 0,
            1 if health_note else 0,
        ])
        if record_count > 1:
            raise serializers.ValidationError(
                _('Document can only be attached to one record')
            )

        if document_type is None:
            raise serializers.ValidationError(
                {'document_type': _('Document type is required')}
            )

        is_owner_upload = bool(user and is_pet_owner(user, pet))
        is_system_upload = bool(user and (user.is_superuser or user.is_system_admin()))
        provider_context_record = visit_record
        if provider_context_record is None and visit_record_addendum is not None:
            provider_context_record = visit_record_addendum.visit_record
        acts_as_provider = bool(
            provider_context_record
            and user
            and not is_system_upload
            and can_manage_visit_record_as_provider(user, provider_context_record)
        )

        if provider_context_record is None:
            if not (is_owner_upload or is_system_upload):
                raise serializers.ValidationError(
                    {'visit_record': _('Provider staff can create documents only for a specific visit record')}
                )
        elif not (acts_as_provider or is_system_upload):
            if is_owner_upload:
                raise serializers.ValidationError(
                    {'visit_record': _('Owners can create documents only in pet-card context')}
                )
            raise serializers.ValidationError(
                {'visit_record': _('You do not have permission to manage documents for this visit record')}
            )

        if acts_as_provider:
            if health_note:
                raise serializers.ValidationError(
                    {'health_note': _('Provider staff cannot attach documents to owner health notes')}
                )
            allowed_codes = set(
                get_document_type_codes_for_context(PROVIDER_VISIT_DOCUMENT_CONTEXT) or ()
            )
            if document_type.code not in allowed_codes:
                raise serializers.ValidationError(
                    {'document_type': _('This document type is not allowed in provider visit context')}
                )

        self._validate_document_type_requirements(document_type, data)

        if data.get('issue_date') and data.get('expiry_date') and data['issue_date'] > data['expiry_date']:
            raise serializers.ValidationError(
                {'expiry_date': _('Issue date cannot be after expiry date')}
            )

        return data

    def create(self, validated_data):
        """Создаёт документ, подставляя имя файла по умолчанию."""
        if not validated_data.get('name'):
            validated_data['name'] = os.path.basename(validated_data['file'].name)
        return super().create(validated_data)


class CanonicalPetDocumentUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор канонического PATCH для метаданных документа."""

    file = serializers.FileField(write_only=True, required=False)
    document_type = serializers.PrimaryKeyRelatedField(
        queryset=DocumentType._default_manager.filter(is_active=True),
        required=False,
        allow_null=False,
    )

    class Meta:
        model = PetDocument
        fields = [
            'file',
            'name',
            'description',
            'document_type',
            'issue_date',
            'expiry_date',
            'document_number',
            'issuing_authority',
        ]
        extra_kwargs = {
            'name': {'required': False},
            'description': {'required': False, 'allow_blank': True},
            'document_number': {'required': False, 'allow_blank': True},
            'issuing_authority': {'required': False, 'allow_blank': True},
        }

    def validate_file(self, value):
        """Явно запрещает замену файла в v1."""
        raise serializers.ValidationError(
            _('File replacement is not supported for pet documents in v1')
        )

    def validate(self, attrs):
        """Проверяет допустимость частичного обновления метаданных."""
        document = self.instance
        document_type = attrs.get('document_type') or document.document_type

        if not document.is_active:
            raise serializers.ValidationError(
                _('Only active documents can be updated')
            )

        if document_type is None:
            raise serializers.ValidationError(
                {'document_type': _('Document type is required')}
            )

        if document.provider_context_visit_record_id:
            allowed_codes = set(
                get_document_type_codes_for_context(PROVIDER_VISIT_DOCUMENT_CONTEXT) or ()
            )
            if document_type.code not in allowed_codes:
                raise serializers.ValidationError(
                    {'document_type': _('This document type is not allowed in provider visit context')}
                )

        merged = {
            'issue_date': attrs.get('issue_date', document.issue_date),
            'expiry_date': attrs.get('expiry_date', document.expiry_date),
            'issuing_authority': attrs.get('issuing_authority', document.issuing_authority),
            'document_number': attrs.get('document_number', document.document_number),
        }

        if document_type.requires_issue_date and not merged['issue_date']:
            raise serializers.ValidationError(
                {'issue_date': _('Issue date is required for this document type')}
            )

        if document_type.requires_expiry_date and not merged['expiry_date']:
            raise serializers.ValidationError(
                {'expiry_date': _('Expiry date is required for this document type')}
            )

        if document_type.requires_issuing_authority and not merged['issuing_authority']:
            raise serializers.ValidationError(
                {'issuing_authority': _('Issuing authority is required for this document type')}
            )

        if document_type.requires_document_number and not merged['document_number']:
            raise serializers.ValidationError(
                {'document_number': _('Document number is required for this document type')}
            )

        if merged['issue_date'] and merged['expiry_date'] and merged['issue_date'] > merged['expiry_date']:
            raise serializers.ValidationError(
                {'expiry_date': _('Issue date cannot be after expiry date')}
            )

        return attrs


class PetDocumentLifecycleActionSerializer(serializers.Serializer):
    """Сериализатор payload для deactivate/withdraw действий."""

    reason_code = serializers.CharField(required=False, allow_blank=True, max_length=100)
    reason_comment = serializers.CharField(required=False, allow_blank=True)


class VisitRecordSerializer(serializers.ModelSerializer):
    """
    Сериализатор для записей в карте питомца.
    
    Особенности:
    - Автоматическое определение создателя
    - Связь с услугами
    - Управление файлами
    """
    created_by = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        default=serializers.CurrentUserDefault()
    )
    service_name = serializers.SerializerMethodField()
    employee_name = serializers.SerializerMethodField()
    provider_location_name = serializers.CharField(source='provider_location.name', read_only=True)

    class Meta:
        model = VisitRecord
        fields = [
            'id',
            'pet',
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
            'created_by',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']
        extra_kwargs = {
            'employee': {'required': False, 'allow_null': True},
            'description': {'required': False, 'allow_blank': True},
            'provider_location': {'required': False, 'allow_null': True},
        }

    def get_service_name(self, obj):
        if not obj.service:
            return None
        return obj.service.get_localized_name()

    def get_employee_name(self, obj):
        if not obj.employee or not obj.employee.user:
            return None
        return obj.employee.user.get_full_name() or obj.employee.user.email


class VisitRecordDetailSerializer(VisitRecordSerializer):
    documents = PetDocumentSummarySerializer(many=True, read_only=True)
    addenda = VisitRecordAddendumSerializer(many=True, read_only=True)
    booking_id = serializers.SerializerMethodField()

    class Meta(VisitRecordSerializer.Meta):
        fields = VisitRecordSerializer.Meta.fields + ['documents', 'addenda', 'booking_id']

    def get_booking_id(self, obj):
        prefetched = getattr(obj, '_prefetched_objects_cache', {})
        source_bookings = prefetched.get('source_bookings')
        if source_bookings is not None:
            booking = source_bookings[0] if source_bookings else None
            return booking.id if booking else None
        booking_id = obj.source_bookings.values_list('id', flat=True).order_by('-created_at').first()
        return booking_id


class PetAccessSerializer(serializers.ModelSerializer):
    """
    Сериализатор для доступа к карте питомца.
    
    Особенности:
    - Управление разрешениями
    - Валидация срока действия
    - Автоматическое определение выдавшего доступ
    """
    granted_by = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        default=serializers.CurrentUserDefault()
    )

    class Meta:
        model = PetAccess
        fields = [
            'id',
            'pet',
            'granted_to',
            'granted_by',
            'permissions',
            'expires_at',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'granted_by', 'created_at', 'updated_at']
        ref_name = 'PetsPetAccess'

    def validate(self, data):
        """Проверяет корректность данных"""
        if data.get('expires_at') and data['expires_at'] <= timezone.now():
            raise serializers.ValidationError(
                {'expires_at': _('Expiration date must be in the future')}
            )
        return data

    def validate_permissions(self, value):
        """Проверяет корректность разрешений"""
        valid_permissions = {'read', 'write', 'book'}
        invalid_permissions = set(value.keys()) - valid_permissions
        if invalid_permissions:
            message = str(_('Invalid permissions: {}')).format(', '.join(invalid_permissions))
            raise serializers.ValidationError(
                message
            )
        return value


class ChronicConditionSerializer(serializers.ModelSerializer):
    """Справочник хронических заболеваний. name_display — по языку запроса (Accept-Language или ?lang=)."""
    name_display = serializers.SerializerMethodField()

    class Meta:
        model = ChronicCondition
        fields = ['id', 'code', 'name', 'name_display', 'name_en', 'name_ru', 'name_de', 'name_me', 'category', 'order']
        read_only_fields = ['id', 'code', 'name', 'name_en', 'name_ru', 'name_de', 'name_me', 'category', 'order']

    def get_name_display(self, obj):
        request = self.context.get('request')
        lang = request.GET.get('lang') if request else None
        if not lang and request and request.META.get('HTTP_ACCEPT_LANGUAGE'):
            raw = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
            lang = raw.split(',')[0].split('-')[0].strip().lower() if raw else None
        return obj.get_localized_name(lang) if lang else obj.get_localized_name()


class PhysicalFeatureSerializer(serializers.ModelSerializer):
    """Справочник физических особенностей. name_display — по языку запроса."""
    name_display = serializers.SerializerMethodField()

    class Meta:
        model = PhysicalFeature
        fields = ['id', 'code', 'name', 'name_display', 'name_en', 'name_ru', 'name_de', 'name_me', 'order']
        read_only_fields = ['id', 'code', 'name', 'name_en', 'name_ru', 'name_de', 'name_me', 'order']

    def get_name_display(self, obj):
        request = self.context.get('request')
        lang = request.GET.get('lang') if request else None
        if not lang and request and request.META.get('HTTP_ACCEPT_LANGUAGE'):
            raw = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
            lang = raw.split(',')[0].split('-')[0].strip().lower() if raw else None
        return obj.get_localized_name(lang) if lang else obj.get_localized_name()


class BehavioralTraitSerializer(serializers.ModelSerializer):
    """Справочник поведенческих особенностей. name_display — по языку запроса."""
    name_display = serializers.SerializerMethodField()

    class Meta:
        model = BehavioralTrait
        fields = ['id', 'code', 'name', 'name_display', 'name_en', 'name_ru', 'name_de', 'name_me', 'order']
        read_only_fields = ['id', 'code', 'name', 'name_en', 'name_ru', 'name_de', 'name_me', 'order']

    def get_name_display(self, obj):
        request = self.context.get('request')
        lang = request.GET.get('lang') if request else None
        if not lang and request and request.META.get('HTTP_ACCEPT_LANGUAGE'):
            raw = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
            lang = raw.split(',')[0].split('-')[0].strip().lower() if raw else None
        return obj.get_localized_name(lang) if lang else obj.get_localized_name()


class PetOwnerSerializer(serializers.ModelSerializer):
    """Сериализатор для PetOwner through-модели."""
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = PetOwner
        fields = ['id', 'user', 'user_email', 'user_name', 'role', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email


class PetSerializer(serializers.ModelSerializer):
    """
    Сериализатор для питомца.
    
    Особенности:
    - Валидация полей
    - Обработка JSON-полей
    - Расчет возраста
    - Связь с медицинскими записями
    - Управление доступом
    - Поддержка расширенного поиска
    """
    # Backward-compatible input alias: external clients send `owner` (user PK)
    owner = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
        write_only=True
    )
    # Выходные поля для владельцев
    main_owner = serializers.SerializerMethodField()
    main_owner_id = serializers.SerializerMethodField()
    owners = PetOwnerSerializer(source='petowner_set', many=True, read_only=True)
    chronic_conditions = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=ChronicCondition._default_manager.all(),
        required=False
    )
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
    age = serializers.SerializerMethodField()
    access_list = PetAccessSerializer(source='accesses', many=True, read_only=True)
    
    # Дополнительные поля для поиска
    pet_type_name = serializers.SerializerMethodField()
    breed_name = serializers.SerializerMethodField()
    main_owner_name = serializers.SerializerMethodField()
    main_owner_email = serializers.SerializerMethodField()
    records_count = serializers.SerializerMethodField()
    last_visit_date = serializers.SerializerMethodField()
    has_medical_conditions = serializers.SerializerMethodField()
    has_special_needs = serializers.SerializerMethodField()

    class Meta:
        model = Pet
        fields = [
            'id',
            'owner',
            'main_owner',
            'main_owner_id',
            'owners',
            'name',
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
            'photo',
            'access_list',
            'main_owner_name',
            'main_owner_email',
            'records_count',
            'last_visit_date',
            'has_medical_conditions',
            'has_special_needs',
            'is_active',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id', 'main_owner', 'main_owner_id', 'owners', 'created_at', 'updated_at', 'pet_type_name', 'breed_name',
            'main_owner_name', 'main_owner_email', 'records_count', 'last_visit_date',
            'has_medical_conditions', 'has_special_needs'
        ]
        extra_kwargs = {
            'special_needs': {'required': False},
            'medical_conditions': {'required': False},
            'behavioral_traits': {'required': False},
            'chronic_conditions': {'required': False},
        }

    def get_main_owner(self, obj):
        """Возвращает данные основного владельца."""
        mo = obj.main_owner
        if mo:
            return {'id': mo.id, 'email': mo.email, 'name': mo.get_full_name() or mo.email}
        return None

    def get_main_owner_id(self, obj):
        return obj.main_owner_id

    def get_main_owner_name(self, obj):
        mo = obj.main_owner
        return mo.get_full_name() if mo else None

    def get_main_owner_email(self, obj):
        mo = obj.main_owner
        return mo.email if mo else None

    def get_pet_type_name(self, obj):
        if not obj.pet_type:
            return None
        return obj.pet_type.get_localized_name()

    def get_breed_name(self, obj):
        if not obj.breed:
            return None
        return obj.breed.get_localized_name()

    def get_age(self, obj):
        """Возвращает возраст питомца"""
        return obj.get_age()
    
    def get_records_count(self, obj):
        """Возвращает количество записей питомца"""
        context = self.context
        if context.get('include_records_count', False):
            return obj.records.count()
        return None
    
    def get_last_visit_date(self, obj):
        """Возвращает дату последнего посещения"""
        last_record = obj.records.order_by('-date').first()
        return last_record.date if last_record else None
    
    def get_has_medical_conditions(self, obj):
        """Возвращает True если у питомца есть медицинские условия"""
        return bool(obj.medical_conditions and obj.medical_conditions != {})
    
    def get_has_special_needs(self, obj):
        """Возвращает True если у питомца есть особые потребности"""
        return bool(obj.special_needs and obj.special_needs != {})

    def create(self, validated_data):
        """
        Создаёт питомца и привязывает основного владельца через PetOwner.
        `owner` (входной PK) извлекается из validated_data.
        M2M chronic_conditions задаётся после создания.
        """
        request = self.context.get('request')
        # owner — write_only, не маппится на model field
        main_owner = validated_data.pop('owner', None) or getattr(request, 'user', None)
        if not main_owner:
            raise serializers.ValidationError({'owner': _('Owner is required')})

        chronic_conditions = validated_data.pop('chronic_conditions', [])

        with transaction.atomic():
            pet = Pet.objects.create(**validated_data)
            PetOwner.objects.create(pet=pet, user=main_owner, role='main')
            if chronic_conditions is not None:
                pet.chronic_conditions.set(chronic_conditions)
        return pet

    def update(self, instance, validated_data):
        """
        Обновляет питомца.
        Смена основного владельца через owner:
        - старый main → coowner
        - новый → main
        """
        new_main_owner = validated_data.pop('owner', None)
        chronic_conditions = validated_data.pop('chronic_conditions', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if chronic_conditions is not None:
            instance.chronic_conditions.set(chronic_conditions)

        if new_main_owner is not None and new_main_owner != instance.main_owner:
            with transaction.atomic():
                # Понижаем текущего main → coowner
                PetOwner.objects.filter(
                    pet=instance, role='main'
                ).update(role='coowner')
                # Повышаем нового или создаём
                po, created = PetOwner.objects.get_or_create(
                    pet=instance, user=new_main_owner,
                    defaults={'role': 'main'},
                )
                if not created:
                    po.role = 'main'
                    PetOwner.objects.filter(pk=po.pk).update(role='main')

        return instance

    def validate_description(self, value):
        """Пустое значение и null приводим к пустой строке."""
        return value or ''

    def validate_photo(self, value):
        """Проверка размера, типа и разрешения загружаемого фото питомца."""
        if not value:
            return value
        if value.size > PET_PHOTO_MAX_SIZE_BYTES:
            raise serializers.ValidationError(
                _('Photo size must not exceed %(max_mb)s MB.')
                % {'max_mb': PET_PHOTO_MAX_SIZE_MB}
            )
        content_type = getattr(value, 'content_type', None) or ''
        if content_type and content_type.lower() not in [t.lower() for t in PET_PHOTO_ALLOWED_CONTENT_TYPES]:
            raise serializers.ValidationError(
                _('Allowed formats: JPEG, PNG, WebP.')
            )
        try:
            from PIL import Image
            img = Image.open(value)
            img.verify()
        except Exception:
            raise serializers.ValidationError(_('Invalid or unsupported image file.'))
        value.seek(0)
        img = Image.open(value)
        w, h = img.size
        if w > PET_PHOTO_MAX_WIDTH or h > PET_PHOTO_MAX_HEIGHT:
            raise serializers.ValidationError(
                _('Photo resolution must not exceed %(max_w)s×%(max_h)s px.')
                % {'max_w': PET_PHOTO_MAX_WIDTH, 'max_h': PET_PHOTO_MAX_HEIGHT}
            )
        value.seek(0)
        return value

    def validate(self, data):
        """Проверяет корректность данных"""
        if data.get('birth_date') and data['birth_date'] > timezone.now().date():
            raise serializers.ValidationError(
                {'birth_date': _('Birth date cannot be in the future')}
            )
        
        if data.get('weight') and data['weight'] <= 0:
            raise serializers.ValidationError(
                {'weight': _('Weight must be positive')}
            )
        
        return data


class PetMedicalCardSerializer(PetSerializer):
    visit_records = serializers.SerializerMethodField()
    health_notes = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta(PetSerializer.Meta):
        fields = [
            field
            for field in PetSerializer.Meta.fields
            if field != 'access_list'
        ] + [
            'visit_records',
            'health_notes',
            'documents',
        ]
        read_only_fields = list(PetSerializer.Meta.read_only_fields) + [
            'visit_records',
            'health_notes',
            'documents',
        ]

    def get_visit_records(self, obj):
        request = self.context.get('request')
        queryset = get_accessible_visit_records_queryset(request.user, obj)
        return VisitRecordDetailSerializer(queryset, many=True, context=self.context).data

    def get_health_notes(self, obj):
        request = self.context.get('request')
        if not can_view_health_notes(request.user, obj):
            return []
        queryset = obj.health_notes.order_by('-date', '-created_at')
        return PetHealthNoteSerializer(queryset, many=True, context=self.context).data

    def get_documents(self, obj):
        request = self.context.get('request')
        queryset = get_accessible_documents_queryset(request.user, obj)
        return PetDocumentSummarySerializer(queryset, many=True, context=self.context).data


class PetTypeSerializer(serializers.ModelSerializer):
    """
    Сериализатор для типа питомца.
    Поле name_display — локализованное название по языку запроса (Accept-Language или ?lang=).
    """
    name_display = serializers.SerializerMethodField()

    class Meta:
        model = PetType
        fields = ['id', 'code', 'name', 'name_display', 'name_ru', 'name_en', 'name_de', 'name_me', 'description']
        read_only_fields = ['id']
        ref_name = 'PetsPetType'

    def get_name_display(self, obj):
        request = self.context.get('request')
        lang = request.GET.get('lang') if request else None
        if not lang and request and request.META.get('HTTP_ACCEPT_LANGUAGE'):
            raw = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
            lang = raw.split(',')[0].split('-')[0].strip().lower() if raw else None
        return obj.get_localized_name(lang) if lang else obj.get_localized_name()


class DocumentTypeSerializer(serializers.ModelSerializer):
    """
    Сериализатор для типа документа питомца.

    Особенности:
    - Возвращает локализованное отображаемое имя
    - Разрешает только согласованные типы документов
    - Не принимает ручное редактирование технического кода и служебных полей
    """
    name_display = serializers.SerializerMethodField()

    class Meta:
        model = DocumentType
        fields = [
            'id', 'name', 'name_display', 'code', 'description',
            'name_en', 'name_ru', 'name_me', 'name_de',
            'requires_issue_date', 'requires_expiry_date', 
            'requires_issuing_authority', 'requires_document_number',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id',
            'name_display',
            'code',
            'description',
            'name_en',
            'name_ru',
            'name_me',
            'name_de',
            'requires_issue_date',
            'requires_expiry_date',
            'requires_issuing_authority',
            'requires_document_number',
            'created_at',
            'updated_at',
        ]

    def get_name_display(self, obj):
        request = self.context.get('request')
        lang = request.GET.get('lang') if request else None
        if not lang and request and request.META.get('HTTP_ACCEPT_LANGUAGE'):
            raw = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
            lang = raw.split(',')[0].split('-')[0].strip().lower() if raw else None
        return obj.get_localized_name(lang) if lang else obj.get_localized_name()

    def validate_name(self, value):
        """Проверяет, что имя принадлежит согласованному каталогу."""
        definition = get_document_type_definition_by_name(value)
        if definition is None:
            raise serializers.ValidationError(
                _('Document type name must be selected from the approved catalog')
            )

        queryset = DocumentType._default_manager.exclude(pk=getattr(self.instance, 'pk', None))
        if queryset.filter(code=definition.code).exists():
            raise serializers.ValidationError(_('Document type already exists'))
        return value

    def validate(self, data):
        """Проверяет корректность данных"""
        if data.get('requires_expiry_date') and not data.get('requires_issue_date'):
            raise serializers.ValidationError(
                _('Issue date is required if expiry date is required')
            )
        return data


class BreedSerializer(serializers.ModelSerializer):
    """
    Сериализатор для породы питомца.
    Поле name_display — локализованное название по языку запроса (Accept-Language или ?lang=).
    """
    name_display = serializers.SerializerMethodField()

    class Meta:
        model = Breed
        fields = ['id', 'code', 'name', 'name_display', 'name_ru', 'name_en', 'name_de', 'name_me', 'description', 'pet_type']
        read_only_fields = ['id']

    def get_name_display(self, obj):
        request = self.context.get('request')
        lang = request.GET.get('lang') if request else None
        if not lang and request and request.META.get('HTTP_ACCEPT_LANGUAGE'):
            raw = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
            lang = raw.split(',')[0].split('-')[0].strip().lower() if raw else None
        return obj.get_localized_name(lang) if lang else obj.get_localized_name()


class PetOwnerIncapacitySerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели PetOwnerIncapacity.
    """
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    main_owner_name = serializers.CharField(source='main_owner.get_full_name', read_only=True)
    main_owner_email = serializers.CharField(source='main_owner.email', read_only=True)
    reported_by_name = serializers.CharField(source='reported_by.get_full_name', read_only=True)
    reported_by_email = serializers.CharField(source='reported_by.email', read_only=True)
    new_main_owner_name = serializers.CharField(source='new_main_owner.get_full_name', read_only=True)
    new_main_owner_email = serializers.CharField(source='new_main_owner.email', read_only=True)
    
    class Meta:
        model = PetOwnerIncapacity
        fields = [
            'id', 'pet', 'pet_name', 'main_owner', 'main_owner_name', 'main_owner_email',
            'reported_by', 'reported_by_name', 'reported_by_email', 'status', 'flow_type',
            'incapacity_reason', 'created_at', 'confirmation_deadline', 'resolved_at',
            'auto_action_taken', 'new_main_owner', 'new_main_owner_name', 'new_main_owner_email',
            'notifications_sent', 'notes'
        ]
        read_only_fields = [
            'id', 'pet_name', 'main_owner_name', 'main_owner_email', 'reported_by_name', 
            'reported_by_email', 'created_at', 'confirmation_deadline', 'resolved_at',
            'auto_action_taken', 'new_main_owner_name', 'new_main_owner_email', 
            'notifications_sent'
        ]


class PetIncapacityNotificationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели PetIncapacityNotification.
    """
    recipient_name = serializers.CharField(source='recipient.get_full_name', read_only=True)
    recipient_email = serializers.CharField(source='recipient.email', read_only=True)
    
    class Meta:
        model = PetIncapacityNotification
        fields = [
            'id', 'incapacity_record', 'notification_type', 'status', 'recipient',
            'recipient_name', 'recipient_email', 'subject', 'message', 'sent_at',
            'error_message', 'created_at'
        ]
        read_only_fields = [
            'id', 'recipient_name', 'recipient_email', 'subject', 'message', 'sent_at',
            'error_message', 'created_at'
        ] 
