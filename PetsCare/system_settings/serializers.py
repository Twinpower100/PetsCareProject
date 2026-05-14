"""
Сериализаторы для системных настроек и обращений в поддержку.
"""

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from .models import SupportRequest


class SupportRequestCreateSerializer(serializers.ModelSerializer):
    """Сериализатор публичного создания обращения в поддержку."""

    class Meta:
        model = SupportRequest
        fields = (
            'id',
            'author_name',
            'author_email',
            'author_phone',
            'subject',
            'message',
            'language',
            'page_url',
            'created_at',
        )
        read_only_fields = ('id', 'created_at')
        extra_kwargs = {
            'author_name': {'required': True, 'allow_blank': False},
            'author_email': {'required': True, 'allow_blank': False},
            'subject': {'required': True, 'allow_blank': False},
            'message': {'required': True, 'allow_blank': False},
        }

    def validate_subject(self, value):
        """Проверяет, что тема обращения не пустая."""
        clean_value = value.strip()
        if not clean_value:
            raise serializers.ValidationError(_('Subject is required'))
        return clean_value

    def validate_message(self, value):
        """Проверяет, что текст обращения не пустой."""
        clean_value = value.strip()
        if not clean_value:
            raise serializers.ValidationError(_('Message is required'))
        return clean_value

    def validate_author_email(self, value):
        """Проверяет обязательный email автора обращения."""
        clean_value = value.strip()
        if not clean_value:
            raise serializers.ValidationError(_('Email is required'))
        return clean_value

    def validate_author_name(self, value):
        """Нормализует имя автора обращения."""
        clean_value = value.strip()
        if not clean_value:
            raise serializers.ValidationError(_('Name is required'))
        return clean_value

    def validate_author_phone(self, value):
        """Нормализует телефон автора обращения."""
        return value.strip()

    def create(self, validated_data):
        """Создает обращение из публичной формы контактов."""
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        if user and user.is_authenticated:
            validated_data['author'] = user

        validated_data['source'] = SupportRequest.SOURCE_CONTACT_FORM
        validated_data['status'] = SupportRequest.STATUS_NEW
        validated_data['priority'] = SupportRequest.PRIORITY_NORMAL

        return SupportRequest.objects.create(**validated_data)
