"""
Админка для системы рейтингов и жалоб.

Этот модуль содержит:
1. Админку для рейтингов
2. Админку для отзывов
3. Админку для жалоб
4. Админку для подозрительной активности
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.safestring import mark_safe
from .models import (
    Rating, Review, Complaint, ComplaintResponse, 
    RatingHistory, SuspiciousActivity
)
from .services import (
    RatingCalculationService, ComplaintProcessingService,
    SuspiciousActivityDetectionService, GooglePerspectiveModerationService
)


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    """
    Админка для рейтингов.
    """
    list_display = [
        'content_object', 'current_rating', 'total_reviews', 
        'total_complaints', 'is_suspended', 'last_calculated_at'
    ]
    list_filter = [
        'is_suspended', 'current_rating', 'content_type'
    ]
    search_fields = [
        'content_type__model', 'object_id'
    ]
    readonly_fields = [
        'content_type', 'object_id', 'current_rating', 
        'total_reviews', 'total_complaints', 'resolved_complaints',
        'last_calculated_at', 'created_at', 'updated_at'
    ]
    actions = ['recalculate_rating', 'suspend_rating', 'unsuspend_rating']
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('content_type', 'object_id', 'current_rating')
        }),
        (_('Statistics'), {
            'fields': ('total_reviews', 'total_complaints', 'resolved_complaints')
        }),
        (_('Weights'), {
            'fields': ('reviews_weight', 'complaints_weight', 'cancellations_weight', 'no_show_weight')
        }),
        (_('Status'), {
            'fields': ('is_suspended', 'suspension_reason')
        }),
        (_('Timestamps'), {
            'fields': ('last_calculated_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def recalculate_rating(self, request, queryset):
        """
        Пересчитывает рейтинг для выбранных объектов.
        """
        service = RatingCalculationService()
        count = 0
        
        for rating in queryset:
            try:
                service.calculate_rating(rating.content_object)
                count += 1
            except Exception as e:
                messages.error(request, _("Error recalculating rating for {rating}: {error}").format(rating=rating, error=e))
        
        messages.success(request, _("Successfully recalculated {count} ratings.").format(count=count))
    
    recalculate_rating.short_description = _("Recalculate rating")
    
    def suspend_rating(self, request, queryset):
        """
        Приостанавливает рейтинг.
        """
        queryset.update(is_suspended=True)
        messages.success(request, _("Suspended {count} ratings.").format(count=queryset.count()))
    
    suspend_rating.short_description = _("Suspend rating")
    
    def unsuspend_rating(self, request, queryset):
        """
        Возобновляет рейтинг.
        """
        queryset.update(is_suspended=False, suspension_reason='')
        messages.success(request, _("Unsuspended {count} ratings.").format(count=queryset.count()))
    
    unsuspend_rating.short_description = _("Unsuspend rating")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """
    Админка для отзывов.
    """
    list_display = [
        'author', 'content_object', 'rating', 'title', 
        'is_approved', 'is_suspicious', 'moderation_reason', 'created_at'
    ]
    list_filter = [
        'rating', 'is_approved', 'is_suspicious', 'created_at', 'content_type'
    ]
    search_fields = [
        'author__email', 'author__first_name', 'author__last_name',
        'title', 'text'
    ]
    readonly_fields = [
        'content_type', 'object_id', 'author', 'moderation_reason', 
        'toxicity_scores', 'created_at', 'updated_at'
    ]
    actions = ['approve_reviews', 'reject_reviews', 'mark_suspicious', 'moderate_reviews']
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('content_type', 'object_id', 'author', 'rating', 'title', 'text')
        }),
        (_('Status'), {
            'fields': ('is_approved', 'is_suspicious')
        }),
        (_('Moderation'), {
            'fields': ('moderation_reason', 'toxicity_scores'),
            'classes': ('collapse',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def approve_reviews(self, request, queryset):
        """
        Одобряет выбранные отзывы.
        """
        queryset.update(is_approved=True, is_suspicious=False)
        messages.success(request, _("Approved {count} reviews.").format(count=queryset.count()))
    
    approve_reviews.short_description = _("Approve selected reviews")
    
    def reject_reviews(self, request, queryset):
        """
        Отклоняет выбранные отзывы.
        """
        queryset.update(is_approved=False)
        messages.success(request, _("Rejected {count} reviews.").format(count=queryset.count()))
    
    reject_reviews.short_description = _("Reject selected reviews")
    
    def mark_suspicious(self, request, queryset):
        """
        Помечает отзывы как подозрительные.
        """
        queryset.update(is_suspicious=True, is_approved=False)
        messages.success(request, _("Marked {count} reviews as suspicious.").format(count=queryset.count()))
    
    mark_suspicious.short_description = _("Mark as suspicious")
    
    def moderate_reviews(self, request, queryset):
        """
        Модерирует выбранные отзывы.
        """
        service = GooglePerspectiveModerationService()
        count = 0
        
        for review in queryset:
            try:
                service.moderate_review(review)
                count += 1
            except Exception as e:
                messages.error(request, _("Error moderating review {id}: {error}").format(id=review.id, error=e))
        
        messages.success(request, _("Moderated {count} reviews.").format(count=count))
    
    moderate_reviews.short_description = _("Moderate selected reviews")


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    """
    Админка для жалоб.
    """
    list_display = [
        'author', 'content_object', 'complaint_type', 'status', 
        'is_justified', 'created_at'
    ]
    list_filter = [
        'complaint_type', 'status', 'is_justified', 'created_at', 'content_type'
    ]
    search_fields = [
        'author__email', 'author__first_name', 'author__last_name',
        'title', 'description'
    ]
    readonly_fields = [
        'content_type', 'object_id', 'author', 'created_at', 'updated_at'
    ]
    actions = ['mark_justified', 'mark_unjustified', 'resolve_complaints']
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('content_type', 'object_id', 'author', 'complaint_type', 'title', 'description')
        }),
        (_('Status'), {
            'fields': ('status', 'is_justified', 'assigned_to')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def mark_justified(self, request, queryset):
        """
        Отмечает жалобы как обоснованные.
        """
        queryset.update(is_justified=True)
        messages.success(request, _("Marked {count} complaints as justified.").format(count=queryset.count()))
    
    mark_justified.short_description = _("Mark as justified")
    
    def mark_unjustified(self, request, queryset):
        """
        Отмечает жалобы как необоснованные.
        """
        queryset.update(is_justified=False)
        messages.success(request, _("Marked {count} complaints as unjustified.").format(count=queryset.count()))
    
    mark_unjustified.short_description = _("Mark as unjustified")
    
    def resolve_complaints(self, request, queryset):
        """
        Разрешает жалобы.
        """
        from django.utils import timezone
        queryset.update(status='resolved', resolved_at=timezone.now())
        messages.success(request, _("Resolved {count} complaints.").format(count=queryset.count()))
    
    resolve_complaints.short_description = _("Resolve complaints")


@admin.register(ComplaintResponse)
class ComplaintResponseAdmin(admin.ModelAdmin):
    """
    Админка для ответов на жалобы.
    """
    list_display = [
        'complaint', 'author', 'created_at'
    ]
    list_filter = [
        'created_at', 'author'
    ]
    search_fields = [
        'complaint__title', 'author__email', 'text'
    ]
    readonly_fields = [
        'complaint', 'author', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        (_('Response Information'), {
            'fields': ('complaint', 'author', 'text', 'is_internal')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(RatingHistory)
class RatingHistoryAdmin(admin.ModelAdmin):
    """
    Админка для истории изменений рейтинга.
    """
    list_display = [
        'rating', 'old_rating', 'new_rating', 'change_reason', 
        'changed_by', 'created_at'
    ]
    list_filter = [
        'change_reason', 'created_at'
    ]
    search_fields = [
        'change_reason', 'change_description', 'changed_by__email'
    ]
    readonly_fields = [
        'rating', 'old_rating', 'new_rating', 'change_reason',
        'change_description', 'changed_by', 'created_at'
    ]
    
    fieldsets = (
        (_('Change Information'), {
            'fields': ('rating', 'old_rating', 'new_rating', 'change_reason', 'change_description', 'changed_by')
        }),
        (_('Timestamps'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(SuspiciousActivity)
class SuspiciousActivityAdmin(admin.ModelAdmin):
    """
    Админка для подозрительной активности.
    """
    list_display = [
        'user', 'activity_type', 'status', 'created_at'
    ]
    list_filter = [
        'activity_type', 'status', 'created_at'
    ]
    search_fields = [
        'user__email', 'user__first_name', 'user__last_name',
        'description'
    ]
    readonly_fields = [
        'user', 'activity_type', 'description', 'evidence',
        'created_at', 'updated_at'
    ]
    actions = ['mark_investigating', 'mark_resolved', 'mark_false_positive']
    
    fieldsets = (
        (_('Activity Information'), {
            'fields': ('user', 'activity_type', 'description', 'evidence')
        }),
        (_('Status'), {
            'fields': ('status', 'assigned_to')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def mark_investigating(self, request, queryset):
        """
        Отмечает активность как находящуюся в расследовании.
        """
        queryset.update(status='investigating', assigned_to=request.user)
        messages.success(request, _("Marked {count} activities as investigating.").format(count=queryset.count()))
    
    mark_investigating.short_description = _("Mark as investigating")
    
    def mark_resolved(self, request, queryset):
        """
        Отмечает активность как разрешенную.
        """
        queryset.update(status='resolved')
        messages.success(request, _("Marked {count} activities as resolved.").format(count=queryset.count()))
    
    mark_resolved.short_description = _("Mark as resolved")
    
    def mark_false_positive(self, request, queryset):
        """
        Отмечает активность как ложное срабатывание.
        """
        queryset.update(status='false_positive')
        messages.success(request, _("Marked {count} activities as false positives.").format(count=queryset.count()))
    
    mark_false_positive.short_description = _("Mark as false positive")


class RatingAdminActions:
    """
    Дополнительные действия для админки рейтингов.
    """
    
    def detect_suspicious_activity(self, request, queryset):
        """
        Запускает обнаружение подозрительной активности.
        """
        service = SuspiciousActivityDetectionService()
        count = 0
        
        for rating in queryset:
            try:
                activities = service.detect_suspicious_activity(rating.content_object)
                count += len(activities)
            except Exception as e:
                messages.error(request, _("Error detecting suspicious activity for {rating}: {error}").format(rating=rating, error=e))
        
        messages.success(request, _("Detected {count} suspicious activities.").format(count=count))
    
    detect_suspicious_activity.short_description = _("Detect suspicious activity") 