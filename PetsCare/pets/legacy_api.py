from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, permissions as drf_permissions, serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .medical_card_access import (
    can_manage_visit_record_as_provider,
    get_globally_accessible_visit_records_queryset,
    is_pet_owner,
)
from .document_type_catalog import (
    DOCUMENT_TYPE_ALLOWED_EXTENSIONS,
    DOCUMENT_TYPE_ALLOWED_MIME_TYPES,
    get_legacy_default_document_type_code,
)
from .models import DocumentType, PetDocument, PetHealthNote, VisitRecord
from .serializers import PetDocumentSerializer


DEPRECATION_WARNING = (
    '299 - "Deprecated medical-card endpoint. Use canonical /pets/{pet_id}/medical-card/, '
    '/pets/{pet_id}/health-notes/, /pets/{pet_id}/documents/, /visit-records/ and /pet-documents/ APIs."'
)


def _validate_legacy_attachment_file(file_obj):
    """Проверяет допустимость файла для deprecated upload-путей."""
    if file_obj.size > 10 * 1024 * 1024:
        raise serializers.ValidationError(
            {'attachments': _('File is too large (max 10MB)')}
        )

    file_name = file_obj.name.lower()
    if not any(file_name.endswith(ext) for ext in DOCUMENT_TYPE_ALLOWED_EXTENSIONS):
        raise serializers.ValidationError(
            {'attachments': _('Unsupported file type. Allowed: PDF and JPG/PNG images')}
        )

    content_type = getattr(file_obj, 'content_type', None)
    if content_type and content_type not in DOCUMENT_TYPE_ALLOWED_MIME_TYPES:
        raise serializers.ValidationError(
            {'attachments': _('Unsupported MIME type')}
        )


class DeprecatedEndpointMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Deprecation'] = 'true'
        response['Warning'] = DEPRECATION_WARNING
        return response


class LegacyPetDocumentSerializer(serializers.ModelSerializer):
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    document_type_name = serializers.CharField(source='document_type.name', read_only=True)
    medical_record = serializers.IntegerField(source='health_note_id', read_only=True)
    pet_record = serializers.IntegerField(source='visit_record_id', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    days_until_expiry = serializers.IntegerField(read_only=True)

    class Meta:
        model = PetDocument
        fields = [
            'id',
            'file',
            'name',
            'description',
            'pet',
            'pet_name',
            'document_type',
            'document_type_name',
            'medical_record',
            'pet_record',
            'issue_date',
            'expiry_date',
            'document_number',
            'issuing_authority',
            'uploaded_by',
            'uploaded_at',
            'is_expired',
            'days_until_expiry',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'pet_name',
            'document_type_name',
            'medical_record',
            'pet_record',
            'uploaded_at',
            'is_expired',
            'days_until_expiry',
            'created_at',
            'updated_at',
        ]


class LegacyMedicalRecordSerializer(serializers.ModelSerializer):
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = PetHealthNote
        fields = [
            'id',
            'pet',
            'date',
            'title',
            'description',
            'attachments',
            'next_visit',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        attachment = data.get('attachments') if hasattr(data, 'get') else None
        if attachment not in (None, ''):
            value['_attachment_file'] = attachment
        return value

    def validate(self, data):
        if data.get('date') and data['date'] > timezone.localdate():
            raise serializers.ValidationError({'date': _('Date cannot be in the future')})
        return data

    def get_attachments(self, obj):
        document = obj.documents.order_by('-uploaded_at', '-created_at').first()
        if document is None or not document.file:
            return None
        try:
            return document.file.url
        except ValueError:
            return document.file.name

    def create(self, validated_data):
        attachment_file = validated_data.pop('_attachment_file', None)
        note = PetHealthNote.objects.create(**validated_data)
        self._sync_attachment(note, attachment_file)
        return note

    def update(self, instance, validated_data):
        attachment_file = validated_data.pop('_attachment_file', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        self._sync_attachment(instance, attachment_file)
        return instance

    def _sync_attachment(self, note, attachment_file):
        if not attachment_file:
            return
        _validate_legacy_attachment_file(attachment_file)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            raise serializers.ValidationError({'attachments': _('Authenticated uploader is required')})

        default_document_type = DocumentType.objects.get(
            code=get_legacy_default_document_type_code()
        )
        existing = note.documents.order_by('-uploaded_at', '-created_at').first()
        if existing is not None:
            existing.file = attachment_file
            existing.name = ((note.title or attachment_file.name) or '').strip()[:255]
            existing.description = note.description or ''
            existing.uploaded_by = user
            if existing.document_type_id is None:
                existing.document_type = default_document_type
            if not existing.issue_date:
                existing.issue_date = note.date
            existing.save()
            return

        name = ((note.title or attachment_file.name) or '').strip()[:255] or attachment_file.name[:255]
        PetDocument.objects.create(
            file=attachment_file,
            name=name,
            description=note.description or '',
            pet=note.pet,
            document_type=default_document_type,
            health_note=note,
            issue_date=note.date,
            uploaded_by=user,
        )


class LegacyVisitRecordSerializer(serializers.ModelSerializer):
    service_name = serializers.SerializerMethodField()
    employee_name = serializers.SerializerMethodField()
    provider_location_name = serializers.CharField(source='provider_location.name', read_only=True)
    files = serializers.SerializerMethodField()

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
            'files',
            'created_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'files', 'created_by', 'created_at', 'updated_at']
        extra_kwargs = {
            'employee': {'required': False, 'allow_null': True},
            'provider': {'required': False, 'allow_null': True},
            'provider_location': {'required': False, 'allow_null': True},
            'description': {'required': False, 'allow_blank': True},
        }

    def get_service_name(self, obj):
        return obj.service.get_localized_name() if obj.service else None

    def get_employee_name(self, obj):
        if not obj.employee or not obj.employee.user:
            return None
        return obj.employee.user.get_full_name() or obj.employee.user.email

    def get_files(self, obj):
        return list(obj.documents.order_by('id').values_list('id', flat=True))


class LegacyMedicalRecordViewSet(DeprecatedEndpointMixin, viewsets.ModelViewSet):
    serializer_class = LegacyMedicalRecordSerializer
    permission_classes = [drf_permissions.IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return PetHealthNote._default_manager.none()
        queryset = PetHealthNote._default_manager.select_related('pet').prefetch_related('documents').order_by('-date', '-created_at')
        if not (self.request.user.is_superuser or self.request.user.is_system_admin()):
            queryset = queryset.filter(pet__owners=self.request.user)
        pet_id = self.request.query_params.get('pet')
        if pet_id:
            queryset = queryset.filter(pet_id=pet_id)
        return queryset

    def perform_create(self, serializer):
        pet = serializer.validated_data['pet']
        if not (self.request.user.is_superuser or self.request.user.is_system_admin() or is_pet_owner(self.request.user, pet)):
            raise PermissionDenied(_('You do not have permission to create medical records for this pet'))
        serializer.save()

    def perform_update(self, serializer):
        pet = serializer.instance.pet
        if not (self.request.user.is_superuser or self.request.user.is_system_admin() or is_pet_owner(self.request.user, pet)):
            raise PermissionDenied(_('You do not have permission to update medical records for this pet'))
        serializer.save()

    def perform_destroy(self, instance):
        if not (self.request.user.is_superuser or self.request.user.is_system_admin() or is_pet_owner(self.request.user, instance.pet)):
            raise PermissionDenied(_('You do not have permission to delete medical records for this pet'))
        instance.delete()


class LegacyVisitRecordViewSet(DeprecatedEndpointMixin, viewsets.ModelViewSet):
    serializer_class = LegacyVisitRecordSerializer
    permission_classes = [drf_permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return VisitRecord._default_manager.none()
        scoped_queryset = get_globally_accessible_visit_records_queryset(self.request.user)

        pet_id = self.request.query_params.get('pet')
        if pet_id:
            scoped_queryset = scoped_queryset.filter(pet_id=pet_id)
        return scoped_queryset

    def perform_create(self, serializer):
        pet = serializer.validated_data['pet']
        user = self.request.user
        is_owner_creator = is_pet_owner(user, pet)
        employee = serializer.validated_data.get('employee')
        is_employee_creator = bool(employee and employee.user_id == user.id)
        if not (user.is_superuser or user.is_system_admin() or is_owner_creator or is_employee_creator):
            raise PermissionDenied(_('You do not have permission to add records for this pet'))
        serializer.save(created_by=user)

    def perform_update(self, serializer):
        record = serializer.instance
        user = self.request.user
        can_edit = (
            user.is_superuser
            or user.is_system_admin()
            or is_pet_owner(user, record.pet)
            or can_manage_visit_record_as_provider(user, record)
        )
        if not can_edit:
            raise PermissionDenied(_('You do not have permission to update this pet record'))
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        can_delete = (
            user.is_superuser
            or user.is_system_admin()
            or is_pet_owner(user, instance.pet)
            or can_manage_visit_record_as_provider(user, instance)
        )
        if not can_delete:
            raise PermissionDenied(_('You do not have permission to delete this pet record'))
        instance.delete()


class LegacyVisitRecordListCreateAPIView(DeprecatedEndpointMixin, generics.ListCreateAPIView):
    serializer_class = LegacyVisitRecordSerializer
    permission_classes = [drf_permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return VisitRecord._default_manager.none()
        viewset = LegacyVisitRecordViewSet()
        viewset.request = self.request
        viewset.swagger_fake_view = getattr(self, 'swagger_fake_view', False)
        return viewset.get_queryset()

    def perform_create(self, serializer):
        viewset = LegacyVisitRecordViewSet()
        viewset.request = self.request
        return viewset.perform_create(serializer)


class LegacyVisitRecordRetrieveUpdateDestroyAPIView(DeprecatedEndpointMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LegacyVisitRecordSerializer
    permission_classes = [drf_permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return VisitRecord._default_manager.none()
        viewset = LegacyVisitRecordViewSet()
        viewset.request = self.request
        viewset.swagger_fake_view = getattr(self, 'swagger_fake_view', False)
        return viewset.get_queryset()

    def perform_update(self, serializer):
        viewset = LegacyVisitRecordViewSet()
        viewset.request = self.request
        return viewset.perform_update(serializer)

    def perform_destroy(self, instance):
        viewset = LegacyVisitRecordViewSet()
        viewset.request = self.request
        return viewset.perform_destroy(instance)


class LegacyVisitRecordFileUploadAPIView(DeprecatedEndpointMixin, APIView):
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [drf_permissions.IsAuthenticated]

    def post(self, request, record_id):
        record = get_object_or_404(VisitRecord, pk=record_id)
        user = request.user
        can_upload = (
            user.is_superuser
            or user.is_system_admin()
            or can_manage_visit_record_as_provider(user, record)
        )
        if not can_upload:
            raise PermissionDenied(
                _('You do not have permission to upload documents to this record')
            )

        payload = request.data.copy()
        payload['visit_record'] = record.id
        if not payload.get('document_type'):
            payload['document_type'] = str(
                DocumentType.objects.only('id').get(
                    code=get_legacy_default_document_type_code()
                ).id
            )
            record_date = record.date.date() if hasattr(record.date, 'date') else record.date
            payload['issue_date'] = str(record_date or timezone.localdate())
        serializer = PetDocumentSerializer(
            data=payload,
            context={'request': request, 'pet': record.pet},
        )
        serializer.is_valid(raise_exception=True)
        document = serializer.save(
            pet=record.pet,
            uploaded_by=user,
        )
        return Response(
            LegacyPetDocumentSerializer(document, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )
