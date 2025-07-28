"""
Сериализаторы для API модуля передержки питомцев.

Этот модуль содержит сериализаторы для:
1. Профиля передержки
2. Поиска передержек
3. Отзывов и рейтингов
"""

from rest_framework import serializers
from .models import SitterProfile, PetSittingAd, PetSittingResponse, Review, PetSitting
from users.models import User
from django.utils.translation import gettext_lazy as _
from .models import Message, Conversation


class SitterProfileSerializer(serializers.ModelSerializer):
    """
    Сериализатор для профиля передержки.
    
    Особенности:
    - Валидация полей
    - Обработка JSON-полей
    - Проверка доступности
    """
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        default=serializers.CurrentUserDefault()
    )
    rating = serializers.DecimalField(
        source='user.sitter_rating',
        max_digits=3,
        decimal_places=2,
        read_only=True
    )
    reviews_count = serializers.IntegerField(
        source='user.sitter_reviews_count',
        read_only=True
    )

    class Meta:
        model = SitterProfile
        fields = [
            'id',
            'user',
            'description',
            'experience_years',
            'pet_types',
            'max_pets',
            'available_from',
            'available_to',
            'max_distance_km',
            'compensation_type',
            'hourly_rate',
            'is_verified',
            'rating',
            'reviews_count',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        """Проверяет корректность данных"""
        if data.get('available_from') and data.get('available_to'):
            if data['available_from'] > data['available_to']:
                raise serializers.ValidationError(
                    {'available_to': _('End date must be after start date')}
                )
        
        if data.get('compensation_type') == 'paid' and not data.get('hourly_rate'):
            raise serializers.ValidationError(
                {'hourly_rate': _('Hourly rate is required for paid services')}
            )
        
        return data


class SitterSearchSerializer(serializers.Serializer):
    """
    Сериализатор для поиска передержек.
    
    Особенности:
    - Фильтрация по параметрам
    - Поиск по местоположению
    - Сортировка результатов
    """
    pet_type = serializers.CharField(required=False)
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)
    max_distance = serializers.IntegerField(required=False, default=5)
    compensation_type = serializers.ChoiceField(
        choices=['', 'paid', 'unpaid'],
        required=False
    )
    min_rating = serializers.DecimalField(
        max_digits=3,
        decimal_places=2,
        required=False,
        min_value=0,
        max_value=5
    )
    sort_by = serializers.ChoiceField(
        choices=['rating', 'distance', 'price'],
        required=False
    )

    def validate(self, data):
        """Проверяет корректность дат"""
        if data.get('start_date') and data.get('end_date'):
            if data['start_date'] > data['end_date']:
                raise serializers.ValidationError(
                    {'end_date': _('End date must be after start date')}
                )
        return data 


class PetSittingAdSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели объявления о передержке питомца.
    Позволяет создавать, просматривать и фильтровать объявления.
    """
    class Meta:
        model = PetSittingAd
        fields = [
            'id', 'pet', 'owner', 'start_date', 'end_date', 'description',
            'status', 'location', 'max_distance_km', 'compensation_type',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'owner']

    def validate(self, data):
        """
        Проверяет корректность дат и обязательных полей.
        """
        if data.get('start_date') and data.get('end_date'):
            if data['start_date'] > data['end_date']:
                raise serializers.ValidationError({'end_date': _('End date must be after start date')})
        return data


class PetSittingResponseSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели отклика на объявление о передержке.
    Позволяет ситтеру откликнуться на объявление владельца.
    """
    class Meta:
        model = PetSittingResponse
        fields = [
            'id', 'ad', 'sitter', 'message', 'status', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'status', 'sitter']


class PetSittingSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели PetSitting (передержка).
    Позволяет управлять процессом передержки, подтверждениями, статусами и отзывами.
    """
    class Meta:
        model = PetSitting
        fields = [
            'id', 'ad', 'response', 'sitter', 'pet', 'start_date', 'end_date',
            'status', 'owner_confirmed_start', 'sitter_confirmed_start',
            'owner_confirmed_end', 'sitter_confirmed_end', 'review_left',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'review_left']


class ReviewSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели отзыва о передержке.
    Позволяет оставлять и просматривать отзывы, связанные с PetSitting.
    """
    class Meta:
        model = Review
        fields = [
            'id', 'history', 'author', 'rating', 'text', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'author'] 


class MessageSerializer(serializers.ModelSerializer):
    """
    Сериализатор для сообщений в чате.
    """
    sender_name = serializers.CharField(source='sender.get_full_name', read_only=True)
    sender_avatar = serializers.CharField(source='sender.avatar', read_only=True)
    
    class Meta:
        model = Message
        fields = ['id', 'sender', 'sender_name', 'sender_avatar', 'text', 'created_at', 'is_read']
        read_only_fields = ['sender', 'created_at', 'is_read']

    def create(self, validated_data):
        """Автоматически устанавливает отправителя"""
        validated_data['sender'] = self.context['request'].user
        return super().create(validated_data)


class ConversationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для диалогов.
    """
    participants = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = ['id', 'participants', 'other_participant', 'last_message', 'unread_count', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['created_at', 'updated_at']

    def get_participants(self, obj):
        """Получает список участников"""
        return [
            {
                'id': user.id,
                'name': user.get_full_name(),
                'avatar': user.avatar
            }
            for user in obj.participants.all()
        ]

    def get_last_message(self, obj):
        """Получает последнее сообщение"""
        last_message = obj.messages.last()
        if last_message:
            return {
                'id': last_message.id,
                'text': last_message.text[:100] + '...' if len(last_message.text) > 100 else last_message.text,
                'sender_name': last_message.sender.get_full_name(),
                'created_at': last_message.created_at
            }
        return None

    def get_unread_count(self, obj):
        """Получает количество непрочитанных сообщений"""
        user = self.context['request'].user
        return obj.messages.filter(is_read=False).exclude(sender=user).count()

    def get_other_participant(self, obj):
        """Получает другого участника диалога"""
        user = self.context['request'].user
        other = obj.get_other_participant(user)
        if other:
            return {
                'id': other.id,
                'name': other.get_full_name(),
                'avatar': other.avatar
            }
        return None


class ConversationDetailSerializer(ConversationSerializer):
    """
    Детальный сериализатор для диалога с сообщениями.
    """
    messages = MessageSerializer(many=True, read_only=True)
    
    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ['messages'] 