"""
Сериализаторы для модуля каталога услуг.
"""

from rest_framework import serializers
from .models import Service

class ServiceSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели Service.
    """
    class Meta:
        model = Service
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, data):
        if data.get('is_periodic') and not data.get('period_days'):
            raise serializers.ValidationError(
                "Для периодической услуги необходимо указать период"
            )
        if data.get('send_reminders') and not data.get('reminder_days_before'):
            raise serializers.ValidationError(
                "Для отправки напоминаний необходимо указать количество дней"
            )
        return data
