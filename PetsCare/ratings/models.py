"""
Модели для системы рейтингов и жалоб.

Этот модуль содержит модели для:
1. Рейтингов учреждений, специалистов и пэт-ситтеров
2. Отзывов клиентов
3. Жалоб и их обработки
4. Истории изменений рейтингов
5. Подозрительной активности
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal
import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


class Rating(models.Model):
    """
    Модель рейтинга для учреждений, специалистов и пэт-ситтеров.
    
    Основные характеристики:
    - Универсальная модель для всех типов рейтингов
    - Автоматический расчет на основе отзывов и жалоб
    - История изменений рейтинга
    - Защита от манипуляций
    """
    # Связь с объектом рейтинга (учреждение, специалист, пэт-ситтер)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Основные поля рейтинга
    current_rating = models.DecimalField(
        _('Current Rating'),
        max_digits=3,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text=_('Current average rating (0-5)')
    )
    total_reviews = models.PositiveIntegerField(
        _('Total Reviews'),
        default=0,
        help_text=_('Total number of reviews')
    )
    total_complaints = models.PositiveIntegerField(
        _('Total Complaints'),
        default=0,
        help_text=_('Total number of complaints')
    )
    resolved_complaints = models.PositiveIntegerField(
        _('Resolved Complaints'),
        default=0,
        help_text=_('Number of resolved complaints')
    )
    
    # Взвешенные коэффициенты
    reviews_weight = models.DecimalField(
        _('Reviews Weight'),
        max_digits=3,
        decimal_places=2,
        default=0.60,
        help_text=_('Weight of reviews in rating calculation (0-1)')
    )
    complaints_weight = models.DecimalField(
        _('Complaints Weight'),
        max_digits=3,
        decimal_places=2,
        default=0.25,
        help_text=_('Weight of complaints in rating calculation (0-1)')
    )
    cancellations_weight = models.DecimalField(
        _('Cancellations Weight'),
        max_digits=3,
        decimal_places=2,
        default=0.10,
        help_text=_('Weight of cancellations in rating calculation (0-1)')
    )
    no_show_weight = models.DecimalField(
        _('No Show Weight'),
        max_digits=3,
        decimal_places=2,
        default=0.05,
        help_text=_('Weight of no-show in rating calculation (0-1)')
    )
    
    # Статус рейтинга
    is_suspended = models.BooleanField(
        _('Is Suspended'),
        default=False,
        help_text=_('Whether the rating is suspended due to suspicious activity')
    )
    suspension_reason = models.TextField(
        _('Suspension Reason'),
        blank=True,
        help_text=_('Reason for rating suspension')
    )
    
    # Временные метки
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    last_calculated_at = models.DateTimeField(
        _('Last Calculated At'),
        null=True,
        blank=True,
        help_text=_('When the rating was last calculated')
    )
    
    class Meta:
        verbose_name = _('Rating')
        verbose_name_plural = _('Ratings')
        unique_together = ['content_type', 'object_id']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['current_rating']),
            models.Index(fields=['is_suspended']),
        ]
    
    def __str__(self):
        return f"Rating for {self.content_object}: {self.current_rating}"
    
    def calculate_rating(self):
        """
        Пересчитывает рейтинг на основе всех факторов.
        
        Returns:
            Decimal: Новый рейтинг
        """
        from .services import RatingCalculationService
        
        service = RatingCalculationService()
        new_rating = service.calculate_rating(self.content_object)
        
        self.current_rating = new_rating
        self.last_calculated_at = timezone.now()
        self.save()
        
        return new_rating
    
    def get_rating_display(self):
        """
        Возвращает отображение рейтинга в виде строки.
        
        Returns:
            str: Строковое представление рейтинга
        """
        return f"{self.current_rating} stars"
    
    def is_high_rating(self):
        """
        Проверяет, является ли рейтинг высоким.
        
        Returns:
            bool: True если рейтинг >= 4.5
        """
        return self.current_rating >= Decimal('4.5')
    
    def is_low_rating(self):
        """
        Проверяет, является ли рейтинг низким.
        
        Returns:
            bool: True если рейтинг < 2.5
        """
        return self.current_rating < Decimal('2.5')

    def clean(self):
        """
        Валидация модели.
        """
        if self.current_rating < 0 or self.current_rating > 5:
            raise ValidationError(_('Rating must be between 0 and 5'))
        
        if self.total_reviews < 0:
            raise ValidationError(_('Total reviews cannot be negative'))
    
    def get_average_rating(self):
        """
        Возвращает средний рейтинг.
        """
        if self.total_reviews == 0:
            return 0.0
        return round(self.total_rating / self.total_reviews, 2)


class Review(models.Model):
    """
    Модель отзыва клиента.
    
    Основные характеристики:
    - Связь с бронированием или передержкой
    - Оценка и комментарий
    - Автоматическое влияние на рейтинг
    - Модерация отзывов
    """
    # Связь с объектом отзыва
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Автор отзыва
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name=_('Author')
    )
    
    # Основные поля отзыва
    rating = models.PositiveSmallIntegerField(
        _('Rating'),
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_('Rating from 1 to 5 stars')
    )
    title = models.CharField(
        _('Title'),
        max_length=200,
        blank=True,
        help_text=_('Review title')
    )
    text = models.TextField(
        _('Text'),
        blank=True,
        help_text=_('Review text')
    )
    
    # Статус отзыва
    is_approved = models.BooleanField(
        _('Is Approved'),
        default=True,
        help_text=_('Whether the review is approved by moderators')
    )
    is_suspicious = models.BooleanField(
        _('Is Suspicious'),
        default=False,
        help_text=_('Whether the review is marked as suspicious')
    )
    
    # Поля для Google Perspective API модерации
    moderation_reason = models.TextField(
        _('Moderation Reason'),
        blank=True,
        help_text=_('Reason for moderation decision')
    )
    toxicity_scores = models.JSONField(
        _('Toxicity Scores'),
        default=dict,
        help_text=_('Toxicity scores from Google Perspective API')
    )
    
    # Временные метки
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Review')
        verbose_name_plural = _('Reviews')
        unique_together = ['content_type', 'object_id', 'author']
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['author']),
            models.Index(fields=['rating']),
            models.Index(fields=['is_approved']),
            models.Index(fields=['is_suspicious']),
        ]
    
    def __str__(self):
        return f"Review by {self.author} for {self.content_object}: {self.rating} stars"
    
    def save(self, *args, **kwargs):
        """
        Сохраняет отзыв и пересчитывает рейтинг.
        """
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new and self.is_approved:
            # Пересчитываем рейтинг объекта
            rating_obj, created = Rating.objects.get_or_create(
                content_type=self.content_type,
                object_id=self.object_id
            )
            rating_obj.calculate_rating()
    
    def get_rating_display(self):
        """
        Возвращает отображение рейтинга в виде строки.
        
        Returns:
            str: Строковое представление рейтинга
        """
        return f"{self.rating} stars"

    def clean(self):
        """
        Валидация модели.
        """
        if self.rating < 1 or self.rating > 5:
            raise ValidationError(_('Rating must be between 1 and 5'))
        
        # Проверяем, что пользователь является владельцем питомца
        if not self.content_object.owners.filter(id=self.author.id).exists():
            raise ValidationError(_('User must be an owner of the pet'))
        
        # Проверяем, что услуга была оказана
        if not self.content_object.is_completed:
            raise ValidationError(_('Can only review completed services'))


class Complaint(models.Model):
    """
    Модель жалобы клиента.
    
    Основные характеристики:
    - Связь с бронированием или передержкой
    - Тип жалобы и описание
    - Процесс рассмотрения
    - Автоматическое влияние на рейтинг
    """
    COMPLAINT_TYPES = [
        ('service_quality', _('Service Quality')),
        ('employee_absence', _('Employee Absence')),
        ('staff_rudeness', _('Staff Rudeness')),
        ('sanitary_conditions', _('Sanitary Conditions')),
        ('other', _('Other')),
    ]
    
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('in_progress', _('In Progress')),
        ('resolved', _('Resolved')),
        ('rejected', _('Rejected')),
        ('closed', _('Closed')),
    ]
    
    # Связь с объектом жалобы
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Автор жалобы
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='complaints',
        verbose_name=_('Author')
    )
    
    # Основные поля жалобы
    complaint_type = models.CharField(
        _('Complaint Type'),
        max_length=50,
        choices=COMPLAINT_TYPES,
        help_text=_('Type of complaint')
    )
    title = models.CharField(
        _('Title'),
        max_length=200,
        help_text=_('Complaint title')
    )
    description = models.TextField(
        _('Description'),
        help_text=_('Detailed description of the complaint')
    )
    
    # Статус жалобы
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text=_('Current status of the complaint')
    )
    
    # Решение по жалобе
    resolution = models.TextField(
        _('Resolution'),
        blank=True,
        help_text=_('Resolution of the complaint')
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_complaints',
        verbose_name=_('Resolved By')
    )
    resolved_at = models.DateTimeField(
        _('Resolved At'),
        null=True,
        blank=True,
        help_text=_('When the complaint was resolved')
    )
    
    # Справедливость жалобы
    is_justified = models.BooleanField(
        _('Is Justified'),
        null=True,
        blank=True,
        help_text=_('Whether the complaint is justified')
    )
    
    # Временные метки
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Complaint')
        verbose_name_plural = _('Complaints')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['author']),
            models.Index(fields=['complaint_type']),
            models.Index(fields=['status']),
            models.Index(fields=['is_justified']),
        ]
    
    def __str__(self):
        return f"Complaint by {self.author} about {self.content_object}: {self.get_complaint_type_display()}"
    
    def save(self, *args, **kwargs):
        """
        Сохраняет жалобу и пересчитывает рейтинг.
        """
        is_new = self.pk is None
        old_status = None
        old_is_justified = None
        
        if not is_new:
            old_instance = Complaint.objects.get(pk=self.pk)
            old_status = old_instance.status
            old_is_justified = old_instance.is_justified
        
        super().save(*args, **kwargs)
        
        # Пересчитываем рейтинг при изменении статуса или справедливости
        if (is_new or 
            old_status != self.status or 
            old_is_justified != self.is_justified):
            
            rating_obj, created = Rating.objects.get_or_create(
                content_type=self.content_type,
                object_id=self.object_id
            )
            rating_obj.calculate_rating()

    def clean(self):
        """
        Валидация модели.
        """
        if self.status == 'resolved' and not self.resolved_at:
            self.resolved_at = timezone.now()


class ComplaintResponse(models.Model):
    """
    Модель ответа на жалобу.
    
    Основные характеристики:
    - Связь с жалобой
    - Автор ответа (провайдер, специалист)
    - Текст ответа
    - Временные ограничения
    """
    complaint = models.ForeignKey(
        Complaint,
        on_delete=models.CASCADE,
        related_name='responses',
        verbose_name=_('Complaint')
    )
    
    # Автор ответа
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='complaint_responses',
        verbose_name=_('Author')
    )
    
    # Текст ответа
    text = models.TextField(
        _('Response Text'),
        help_text=_('Response to the complaint')
    )
    
    # Временные метки
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Complaint Response')
        verbose_name_plural = _('Complaint Responses')
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['complaint']),
            models.Index(fields=['author']),
        ]
    
    def __str__(self):
        return f"Response by {self.author} to complaint {self.complaint.id}"


class RatingHistory(models.Model):
    """
    Модель истории изменений рейтинга.
    
    Основные характеристики:
    - Связь с рейтингом
    - Предыдущее и новое значение
    - Причина изменения
    - Автор изменения
    """
    rating = models.ForeignKey(
        Rating,
        on_delete=models.CASCADE,
        related_name='history',
        verbose_name=_('Rating')
    )
    
    # Значения рейтинга
    old_rating = models.DecimalField(
        _('Old Rating'),
        max_digits=3,
        decimal_places=2,
        help_text=_('Previous rating value')
    )
    new_rating = models.DecimalField(
        _('New Rating'),
        max_digits=3,
        decimal_places=2,
        help_text=_('New rating value')
    )
    
    # Причина изменения
    change_reason = models.CharField(
        _('Change Reason'),
        max_length=100,
        help_text=_('Reason for rating change')
    )
    change_description = models.TextField(
        _('Change Description'),
        blank=True,
        help_text=_('Detailed description of the change')
    )
    
    # Автор изменения
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rating_changes',
        verbose_name=_('Changed By')
    )
    
    # Временные метки
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('Rating History')
        verbose_name_plural = _('Rating Histories')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['rating']),
            models.Index(fields=['changed_by']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Rating change for {self.rating}: {self.old_rating} → {self.new_rating}"


class SuspiciousActivity(models.Model):
    """
    Модель подозрительной активности.
    
    Основные характеристики:
    - Тип подозрительной активности
    - Связь с пользователем
    - Детали активности
    - Статус обработки
    """
    ACTIVITY_TYPES = [
        ('mass_reviews', _('Mass Reviews')),
        ('fake_complaints', _('Fake Complaints')),
        ('rating_manipulation', _('Rating Manipulation')),
        ('suspicious_patterns', _('Suspicious Patterns')),
        ('other', _('Other')),
    ]
    
    STATUS_CHOICES = [
        ('detected', _('Detected')),
        ('investigating', _('Investigating')),
        ('resolved', _('Resolved')),
        ('false_positive', _('False Positive')),
    ]
    
    # Тип активности
    activity_type = models.CharField(
        _('Activity Type'),
        max_length=50,
        choices=ACTIVITY_TYPES,
        help_text=_('Type of suspicious activity')
    )
    
    # Связь с пользователем
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='suspicious_activities',
        verbose_name=_('User')
    )
    
    # Детали активности
    description = models.TextField(
        _('Description'),
        help_text=_('Description of the suspicious activity')
    )
    evidence = models.JSONField(
        _('Evidence'),
        default=dict,
        help_text=_('Evidence of suspicious activity')
    )
    
    # Статус обработки
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='detected',
        help_text=_('Current status of the investigation')
    )
    
    # Решение
    resolution = models.TextField(
        _('Resolution'),
        blank=True,
        help_text=_('Resolution of the investigation')
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_suspicious_activities',
        verbose_name=_('Resolved By')
    )
    resolved_at = models.DateTimeField(
        _('Resolved At'),
        null=True,
        blank=True,
        help_text=_('When the investigation was resolved')
    )
    
    # Временные метки
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Suspicious Activity')
        verbose_name_plural = _('Suspicious Activities')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['activity_type']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Suspicious activity by {self.user}: {self.get_activity_type_display()}"

    def clean(self):
        """
        Валидация модели.
        """
        if self.confidence_score < 0 or self.confidence_score > 1:
            raise ValidationError(_('Confidence score must be between 0 and 1')) 