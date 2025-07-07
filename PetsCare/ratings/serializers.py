"""
Сериализаторы для системы рейтингов и жалоб.

Этот модуль содержит:
1. Сериализаторы для рейтингов
2. Сериализаторы для отзывов
3. Сериализаторы для жалоб
4. Сериализаторы для подозрительной активности
"""

from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import (
    Rating, Review, Complaint, ComplaintResponse, 
    RatingHistory, SuspiciousActivity
)


class ContentTypeSerializer(serializers.ModelSerializer):
    """
    Сериализатор для ContentType.
    """
    class Meta:
        model = ContentType
        fields = ['id', 'app_label', 'model']


class RatingSerializer(serializers.ModelSerializer):
    """
    Сериализатор для рейтингов.
    """
    content_type = ContentTypeSerializer(read_only=True)
    content_type_name = serializers.CharField(source='content_type.model', read_only=True)
    object_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Rating
        fields = [
            'id', 'content_type', 'object_id', 'content_type_name', 'object_name',
            'current_rating', 'total_reviews', 'total_complaints', 
            'resolved_complaints', 'reviews_weight', 'complaints_weight',
            'cancellations_weight', 'no_show_weight', 'is_suspended',
            'suspension_reason', 'last_calculated_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'content_type', 'object_id', 'current_rating',
            'total_reviews', 'total_complaints', 'resolved_complaints',
            'last_calculated_at', 'created_at', 'updated_at'
        ]
    
    def get_object_name(self, obj):
        """
        Возвращает название объекта.
        """
        try:
            return str(obj.content_object)
        except:
            return 'Unknown object'


class ReviewSerializer(serializers.ModelSerializer):
    """
    Сериализатор для отзывов.
    """
    content_type = ContentTypeSerializer(read_only=True)
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)
    author_email = serializers.CharField(source='author.email', read_only=True)
    content_object_info = serializers.SerializerMethodField()
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    service_name = serializers.CharField(source='service.service_type.name', read_only=True)
    
    class Meta:
        model = Review
        fields = [
            'id', 'content_type', 'object_id', 'content_object_info',
            'author', 'author_name', 'author_email', 'rating', 'title', 'text',
            'is_approved', 'is_suspicious', 'created_at', 'updated_at',
            'user', 'user_name', 'pet', 'pet_name', 'service', 'service_name'
        ]
        read_only_fields = [
            'id', 'content_type', 'object_id', 'author', 'author_name', 
            'author_email', 'is_approved', 'is_suspicious', 'created_at', 'updated_at',
            'user', 'user_name', 'pet', 'pet_name', 'service', 'service_name'
        ]
    
    def get_content_object_info(self, obj):
        """
        Возвращает информацию об объекте отзыва.
        """
        if obj.content_object:
            if hasattr(obj.content_object, 'name'):
                return {
                    'id': obj.content_object.id,
                    'name': obj.content_object.name,
                    'type': obj.content_type.model
                }
            elif hasattr(obj.content_object, 'user'):
                return {
                    'id': obj.content_object.id,
                    'name': obj.content_object.user.get_full_name(),
                    'type': obj.content_type.model
                }
        return None
    
    def validate_rating(self, value):
        """
        Валидация рейтинга.
        """
        if value < 1 or value > 5:
            raise serializers.ValidationError('Rating must be between 1 and 5')
        return value
    
    def validate(self, data):
        """
        Валидация данных отзыва.
        """
        # Проверяем, что пользователь является владельцем питомца
        pet = data.get('pet')
        user = self.context['request'].user
        
        if not pet.owners.filter(id=user.id).exists():
            raise serializers.ValidationError('You can only review services for your own pets')
        
        # Проверяем, что услуга завершена
        service = data.get('service')
        if not service.is_completed:
            raise serializers.ValidationError('Can only review completed services')
        
        # Проверяем, что отзыв еще не оставлен
        if Review.objects.filter(user=user, pet=pet, service=service).exists():
            raise serializers.ValidationError('You have already reviewed this service')
        
        return data


class ComplaintSerializer(serializers.ModelSerializer):
    """
    Сериализатор для жалоб.
    """
    content_type = ContentTypeSerializer(read_only=True)
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)
    author_email = serializers.CharField(source='author.email', read_only=True)
    content_object_info = serializers.SerializerMethodField()
    responses_count = serializers.SerializerMethodField()
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    service_name = serializers.CharField(source='service.service_type.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    complaint_type_display = serializers.CharField(source='get_complaint_type_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    
    class Meta:
        model = Complaint
        fields = [
            'id', 'content_type', 'object_id', 'content_object_info',
            'author', 'author_name', 'author_email', 'complaint_type',
            'complaint_type_display', 'title', 'description', 'status', 'status_display',
            'priority', 'priority_display', 'assigned_to', 'responses_count', 'created_at', 'updated_at',
            'user', 'user_name', 'service', 'service_name'
        ]
        read_only_fields = [
            'id', 'content_type', 'object_id', 'author', 'author_name',
            'author_email', 'status', 'assigned_to', 'responses_count', 'created_at', 'updated_at',
            'user', 'user_name', 'service', 'service_name'
        ]
    
    def get_content_object_info(self, obj):
        """
        Возвращает информацию об объекте жалобы.
        """
        if obj.content_object:
            if hasattr(obj.content_object, 'name'):
                return {
                    'id': obj.content_object.id,
                    'name': obj.content_object.name,
                    'type': obj.content_type.model
                }
            elif hasattr(obj.content_object, 'user'):
                return {
                    'id': obj.content_object.id,
                    'name': obj.content_object.user.get_full_name(),
                    'type': obj.content_type.model
                }
        return None
    
    def get_responses_count(self, obj):
        """
        Возвращает количество ответов на жалобу.
        """
        return obj.responses.count()
    
    def validate_title(self, value):
        """
        Валидация заголовка жалобы.
        """
        if len(value.strip()) < 5:
            raise serializers.ValidationError('Title must be at least 5 characters long')
        return value
    
    def validate_description(self, value):
        """
        Валидация описания жалобы.
        """
        if len(value.strip()) < 20:
            raise serializers.ValidationError('Description must be at least 20 characters long')
        return value
    
    def validate(self, data):
        """
        Валидация данных жалобы.
        """
        # Проверяем, что пользователь имеет доступ к услуге
        service = data.get('service')
        user = self.context['request'].user
        
        if not service.pet.owners.filter(id=user.id).exists():
            raise serializers.ValidationError('You can only file complaints for services involving your pets')
        
        # Проверяем, что жалоба еще не подана
        if Complaint.objects.filter(user=user, service=service).exists():
            raise serializers.ValidationError('You have already filed a complaint for this service')
        
        return data


class ComplaintResponseSerializer(serializers.ModelSerializer):
    """
    Сериализатор для ответов на жалобы.
    """
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)
    author_email = serializers.CharField(source='author.email', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = ComplaintResponse
        fields = [
            'id', 'complaint', 'author', 'author_name', 'author_email',
            'user', 'user_name', 'response', 'is_internal', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'complaint', 'author', 'author_name', 'author_email',
            'user', 'user_name', 'created_at', 'updated_at'
        ]
    
    def validate_response(self, value):
        """
        Валидация ответа.
        """
        if len(value.strip()) < 10:
            raise serializers.ValidationError('Response must be at least 10 characters long')
        return value


class RatingHistorySerializer(serializers.ModelSerializer):
    """
    Сериализатор для истории изменений рейтинга.
    """
    changed_by_name = serializers.CharField(source='changed_by.get_full_name', read_only=True)
    changed_by_email = serializers.CharField(source='changed_by.email', read_only=True)
    
    class Meta:
        model = RatingHistory
        fields = [
            'id', 'rating', 'old_rating', 'new_rating', 'change_reason',
            'change_description', 'changed_by', 'changed_by_name',
            'changed_by_email', 'created_at'
        ]
        read_only_fields = [
            'id', 'rating', 'old_rating', 'new_rating', 'change_reason',
            'change_description', 'changed_by', 'changed_by_name',
            'changed_by_email', 'created_at'
        ]


class SuspiciousActivitySerializer(serializers.ModelSerializer):
    """
    Сериализатор для подозрительной активности.
    """
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    resolved_by_name = serializers.CharField(source='resolved_by.get_full_name', read_only=True)
    resolved_by_email = serializers.CharField(source='resolved_by.email', read_only=True)
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)
    
    class Meta:
        model = SuspiciousActivity
        fields = [
            'id', 'user', 'user_name', 'user_email', 'activity_type',
            'activity_type_display', 'description', 'evidence', 'status', 'resolution',
            'resolved_by', 'resolved_by_name', 'resolved_by_email',
            'resolved_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'user_name', 'user_email', 'activity_type',
            'activity_type_display', 'description', 'evidence', 'status', 'resolution',
            'resolved_by', 'resolved_by_name', 'resolved_by_email',
            'resolved_at', 'created_at', 'updated_at'
        ]
    
    def validate_confidence_score(self, value):
        """
        Валидация уровня уверенности.
        """
        if value < 0 or value > 1:
            raise serializers.ValidationError('Confidence score must be between 0 and 1')
        return value


# Сериализаторы для создания объектов
class CreateReviewSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания отзывов.
    """
    content_type_id = serializers.IntegerField(write_only=True)
    object_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = Review
        fields = [
            'content_type_id', 'object_id', 'rating', 'title', 'text'
        ]
    
    def validate(self, data):
        """
        Валидирует данные для создания отзыва.
        """
        content_type_id = data.get('content_type_id')
        object_id = data.get('object_id')
        
        try:
            content_type = ContentType.objects.get(id=content_type_id)
            model_class = content_type.model_class()
            obj = model_class.objects.get(id=object_id)
            data['content_object'] = obj
        except (ContentType.DoesNotExist, model_class.DoesNotExist):
            raise serializers.ValidationError("Invalid content type or object ID.")
        
        return data


class CreateComplaintSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания жалоб.
    """
    content_type_id = serializers.IntegerField(write_only=True)
    object_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = Complaint
        fields = [
            'content_type_id', 'object_id', 'complaint_type', 'title', 'description'
        ]
    
    def validate(self, data):
        """
        Валидирует данные для создания жалобы.
        """
        content_type_id = data.get('content_type_id')
        object_id = data.get('object_id')
        
        try:
            content_type = ContentType.objects.get(id=content_type_id)
            model_class = content_type.model_class()
            obj = model_class.objects.get(id=object_id)
            data['content_object'] = obj
        except (ContentType.DoesNotExist, model_class.DoesNotExist):
            raise serializers.ValidationError("Invalid content type or object ID.")
        
        return data


# Сериализаторы для статистики
class RatingStatisticsSerializer(serializers.Serializer):
    """
    Сериализатор для статистики рейтингов.
    """
    total_ratings = serializers.IntegerField()
    average_rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    suspended_ratings = serializers.IntegerField()
    by_type = serializers.DictField()


class ReviewStatisticsSerializer(serializers.Serializer):
    """
    Сериализатор для статистики отзывов.
    """
    total_reviews = serializers.IntegerField()
    approved_reviews = serializers.IntegerField()
    suspicious_reviews = serializers.IntegerField()
    approval_rate = serializers.FloatField()
    rating_distribution = serializers.ListField()
    recent_activity = serializers.DictField()


class ComplaintStatisticsSerializer(serializers.Serializer):
    """
    Сериализатор для статистики жалоб.
    """
    total_complaints = serializers.IntegerField()
    pending_complaints = serializers.IntegerField()
    resolved_complaints = serializers.IntegerField()
    justified_complaints = serializers.IntegerField()
    resolution_rate = serializers.FloatField()
    justification_rate = serializers.FloatField()
    by_type = serializers.ListField()
    recent_activity = serializers.DictField()
    avg_resolution_time_hours = serializers.FloatField(allow_null=True)


class SuspiciousActivityStatisticsSerializer(serializers.Serializer):
    """
    Сериализатор для статистики подозрительной активности.
    """
    total_activities = serializers.IntegerField()
    detected_activities = serializers.IntegerField()
    investigating_activities = serializers.IntegerField()
    resolved_activities = serializers.IntegerField()
    false_positives = serializers.IntegerField()
    false_positive_rate = serializers.FloatField()
    by_type = serializers.ListField()
    recent_activity = serializers.DictField() 