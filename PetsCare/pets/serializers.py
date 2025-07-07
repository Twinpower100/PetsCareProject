"""
Сериализаторы для API модуля питомцев.

Этот модуль содержит сериализаторы для:
1. Питомца
2. Создания/обновления питомца
3. Поиска питомцев
4. Медицинских записей
5. Записей в карте питомца
6. Доступа к карте питомца
"""

from rest_framework import serializers
from .models import Pet, MedicalRecord, PetRecord, PetAccess, PetRecordFile, PetType, Breed, PetOwnershipInvite, DocumentType
from users.models import User
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class MedicalRecordSerializer(serializers.ModelSerializer):
    """
    Сериализатор для медицинских записей.
    
    Особенности:
    - Валидация даты
    - Защита от будущих дат
    """
    class Meta:
        model = MedicalRecord
        fields = [
            'id',
            'pet',
            'date',
            'diagnosis',
            'treatment',
            'prescription',
            'notes',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        """Проверяет корректность даты"""
        if data.get('date') and data['date'] > timezone.now().date():
            raise serializers.ValidationError(
                {'date': _('Date cannot be in the future')}
            )
        return data


class PetRecordSerializer(serializers.ModelSerializer):
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

    class Meta:
        model = PetRecord
        fields = [
            'id',
            'pet',
            'service_category',
            'provider',
            'service',
            'employee',
            'date',
            'next_date',
            'description',
            'results',
            'recommendations',
            'notes',
            'serial_number',
            'files',
            'created_by',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


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
            raise serializers.ValidationError(
                _('Invalid permissions: {}').format(', '.join(invalid_permissions))
            )
        return value


class PetSerializer(serializers.ModelSerializer):
    """
    Сериализатор для питомца.
    
    Особенности:
    - Валидация полей
    - Обработка JSON-полей
    - Расчет возраста
    - Связь с медицинскими записями
    - Управление доступом
    """
    owner = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        default=serializers.CurrentUserDefault()
    )
    age = serializers.SerializerMethodField()
    medical_records = MedicalRecordSerializer(many=True, read_only=True)
    records = PetRecordSerializer(many=True, read_only=True)
    access_list = PetAccessSerializer(many=True, read_only=True)

    class Meta:
        model = Pet
        fields = [
            'id',
            'owner',
            'name',
            'pet_type',
            'breed',
            'birth_date',
            'age',
            'weight',
            'description',
            'special_needs',
            'medical_conditions',
            'photo',
            'medical_records',
            'records',
            'access_list',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_age(self, obj):
        """Возвращает возраст питомца"""
        return obj.get_age()

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


class PetRecordFileSerializer(serializers.ModelSerializer):
    """
    Сериализатор для документов питомца.
    
    Особенности:
    - Загрузка файлов
    - Метаданные документа (даты, номер, орган выдачи)
    - Связь с типом документа
    - Аудит (кто загрузил, дата загрузки)
    - Связи с записями
    """
    uploaded_by = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        default=serializers.CurrentUserDefault()
    )
    document_type_name = serializers.CharField(source='document_type.name', read_only=True)
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    days_until_expiry = serializers.IntegerField(read_only=True)

    class Meta:
        model = PetRecordFile
        fields = [
            'id', 'file', 'name', 'description',
            'pet', 'pet_name', 'document_type', 'document_type_name',
            'medical_record', 'pet_record',
            'issue_date', 'expiry_date', 'document_number', 'issuing_authority',
            'uploaded_by', 'uploaded_at',
            'is_expired', 'days_until_expiry',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'uploaded_at', 'created_at', 'updated_at',
            'document_type_name', 'pet_name', 'is_expired', 'days_until_expiry'
        ]

    def validate(self, data):
        """Проверяет корректность данных"""
        # Проверяем, что документ привязан к питомцу
        if not data.get('pet'):
            raise serializers.ValidationError(_('Document must be attached to a pet'))
        
        # Проверяем, что документ привязан только к одной записи
        record_count = sum([
            1 if data.get('medical_record') else 0,
            1 if data.get('pet_record') else 0
        ])
        if record_count > 1:
            raise serializers.ValidationError(_('Document can only be attached to one record'))
        
        # Проверяем требования типа документа
        document_type = data.get('document_type')
        if document_type:
            if document_type.requires_issue_date and not data.get('issue_date'):
                raise serializers.ValidationError(
                    _('Issue date is required for this document type')
                )
            
            if document_type.requires_expiry_date and not data.get('expiry_date'):
                raise serializers.ValidationError(
                    _('Expiry date is required for this document type')
                )
            
            if document_type.requires_issuing_authority and not data.get('issuing_authority'):
                raise serializers.ValidationError(
                    _('Issuing authority is required for this document type')
                )
            
            if document_type.requires_document_number and not data.get('document_number'):
                raise serializers.ValidationError(
                    _('Document number is required for this document type')
                )
        
        # Проверяем даты
        if data.get('issue_date') and data.get('expiry_date'):
            if data['issue_date'] > data['expiry_date']:
                raise serializers.ValidationError(
                    _('Issue date cannot be after expiry date')
                )
        
        return data


class PetTypeSerializer(serializers.ModelSerializer):
    """
    Сериализатор для типа питомца.
    """
    class Meta:
        model = PetType
        fields = ['id', 'code', 'name', 'description']
        read_only_fields = ['id']


class DocumentTypeSerializer(serializers.ModelSerializer):
    """
    Сериализатор для типа документа питомца.
    
    Особенности:
    - Валидация технического кода
    - Связь с категориями услуг
    - Настройка обязательных полей
    """
    class Meta:
        model = DocumentType
        fields = [
            'id', 'name', 'code', 'description', 'service_categories',
            'requires_issue_date', 'requires_expiry_date', 
            'requires_issuing_authority', 'requires_document_number',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_code(self, value):
        """Проверяет уникальность кода"""
        if DocumentType.objects.filter(code=value).exists():
            raise serializers.ValidationError(_('Document type code must be unique'))
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
    """
    class Meta:
        model = Breed
        fields = ['id', 'code', 'name', 'description', 'pet_type']
        read_only_fields = ['id']


class PetOwnershipInviteSerializer(serializers.ModelSerializer):
    """
    Сериализатор для инвайта на добавление совладельца или передачу прав основного владельца.
    """
    class Meta:
        model = PetOwnershipInvite
        fields = [
            'id', 'pet', 'email', 'token', 'expires_at', 'type', 'invited_by', 'is_used', 'created_at'
        ]
        read_only_fields = ['id', 'token', 'invited_by', 'is_used', 'created_at'] 