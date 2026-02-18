"""
Сериализаторы для API юридических документов.
"""

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import (
    LegalDocumentType,
    LegalDocument,
    DocumentTranslation,
    CountryLegalConfig,
    DocumentAcceptance
)


class LegalDocumentTypeSerializer(serializers.ModelSerializer):
    """Сериализатор для типов документов"""
    
    class Meta:
        model = LegalDocumentType
        fields = [
            'id', 'code', 'name', 'description',
            'requires_billing_config', 'requires_region_code',
            'requires_addendum_type', 'allows_variables',
            'is_required_for_all_countries', 'is_multiple_allowed',
            'is_active', 'display_order'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DocumentTranslationSerializer(serializers.ModelSerializer):
    """Сериализатор для переводов документов"""
    
    class Meta:
        model = DocumentTranslation
        fields = [
            'id', 'document', 'language', 'content', 'content_docx_file',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LegalDocumentSerializer(serializers.ModelSerializer):
    """Сериализатор для юридических документов"""
    document_type = LegalDocumentTypeSerializer(read_only=True)
    document_type_id = serializers.PrimaryKeyRelatedField(
        queryset=LegalDocumentType.objects.all(),
        source='document_type',
        write_only=True
    )
    translations = DocumentTranslationSerializer(many=True, read_only=True)
    
    class Meta:
        model = LegalDocument
        fields = [
            'id', 'document_type', 'document_type_id', 'version', 'title',
            'billing_config', 'region_code', 'addendum_type', 'variables',
            'effective_date', 'is_active', 'change_notification_days',
            'notification_sent_at', 'translations', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'notification_sent_at']


class LegalDocumentListSerializer(serializers.ModelSerializer):
    """Упрощенный сериализатор для списка документов"""
    document_type_name = serializers.CharField(source='document_type.name', read_only=True)
    
    class Meta:
        model = LegalDocument
        fields = [
            'id', 'title', 'version', 'document_type_name',
            'is_active', 'effective_date'
        ]


class CountryLegalConfigSerializer(serializers.ModelSerializer):
    """Сериализатор для конфигурации стран"""
    global_offer = LegalDocumentListSerializer(read_only=True)
    regional_addendums = LegalDocumentListSerializer(many=True, read_only=True)
    privacy_policy = LegalDocumentListSerializer(read_only=True)
    terms_of_service = LegalDocumentListSerializer(read_only=True)
    cookie_policy = LegalDocumentListSerializer(read_only=True)
    
    class Meta:
        model = CountryLegalConfig
        fields = [
            'country', 'global_offer', 'regional_addendums',
            'privacy_policy', 'terms_of_service', 'cookie_policy',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class DocumentAcceptanceSerializer(serializers.ModelSerializer):
    """Сериализатор для принятия документов"""
    document = LegalDocumentListSerializer(read_only=True)
    ip_address = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    class Meta:
        model = DocumentAcceptance
        fields = [
            'id', 'document', 'document_version', 'user', 'provider',
            'accepted_at', 'ip_address', 'user_agent', 'is_active'
        ]
        read_only_fields = ['id', 'accepted_at']


class DocumentAcceptanceCreateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания принятия документа"""
    ip_address = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    class Meta:
        model = DocumentAcceptance
        fields = [
            'document', 'document_version', 'ip_address', 'user_agent'
        ]
