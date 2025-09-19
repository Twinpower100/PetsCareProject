"""
Сериализаторы для модуля каталога услуг.
"""

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import Service
from pets.models import PetType

class PetTypeSerializer(serializers.ModelSerializer):
    """
    Сериализатор для типов животных (для вложенного отображения).
    """
    class Meta:
        model = PetType
        fields = ['id', 'name', 'code']
        ref_name = 'CatalogPetType'


class ServiceSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели Service.
    """
    allowed_pet_types = PetTypeSerializer(many=True, read_only=True)
    allowed_pet_type_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=PetType.objects.all(),
        source='allowed_pet_types',
        write_only=True,
        required=False
    )
    
    class Meta:
        model = Service
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'level']

    def validate(self, data):
        if data.get('is_periodic') and not data.get('period_days'):
            raise serializers.ValidationError(
                _("Period must be specified for periodic service")
            )
        if data.get('send_reminders') and not data.get('reminder_days_before'):
            raise serializers.ValidationError(
                _("Number of days must be specified for sending reminders")
            )
        return data
    
    def to_representation(self, instance):
        """
        Добавляем информацию о совместимости с типами животных.
        """
        data = super().to_representation(instance)
        
        # Добавляем информацию о доступности для всех типов
        if not instance.allowed_pet_types.exists():
            data['is_available_for_all_types'] = True
        else:
            data['is_available_for_all_types'] = False
            
        return data


class ServiceCompatibilitySerializer(serializers.Serializer):
    """
    Сериализатор для проверки совместимости услуг с типами животных.
    """
    service_id = serializers.IntegerField()
    pet_type_id = serializers.IntegerField()
    
    def validate(self, data):
        try:
            service = Service.objects.get(id=data['service_id'])
            pet_type = PetType.objects.get(id=data['pet_type_id'])
        except (Service.DoesNotExist, PetType.DoesNotExist):
            raise serializers.ValidationError(_("Service or pet type not found"))
        
        data['service'] = service
        data['pet_type'] = pet_type
        return data
    
    def to_representation(self, instance):
        """
        Возвращает информацию о совместимости.
        """
        service = instance['service']
        pet_type = instance['pet_type']
        
        compatibility_info = service.get_periodic_info_for_pet_type(pet_type)
        
        return {
            'service_id': service.id,
            'service_name': service.name,
            'pet_type_id': pet_type.id,
            'pet_type_name': pet_type.name,
            'is_compatible': compatibility_info['is_available'],
            'periodic_info': compatibility_info
        }
