"""
API views для системы рейтингов и жалоб.

Этот модуль содержит:
1. API для создания и получения отзывов
2. API для создания и обработки жалоб
3. API для получения рейтингов
4. API для статистики
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import timedelta
from django.utils.translation import gettext_lazy as _
from django.db import transaction

from .models import Rating, Review, Complaint, ComplaintResponse, SuspiciousActivity
from .services import (
    RatingCalculationService, ComplaintProcessingService,
    SuspiciousActivityDetectionService, GooglePerspectiveModerationService,
    ReviewService
)
from .serializers import (
    RatingSerializer, ReviewSerializer, ComplaintSerializer,
    ComplaintResponseSerializer, SuspiciousActivitySerializer
)


class RatingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для рейтингов.
    
    Предоставляет:
    - Получение рейтингов
    - Статистику рейтингов
    - Пересчет рейтингов
    """
    queryset = Rating.objects.all()
    serializer_class = RatingSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Фильтрует queryset по параметрам запроса.
        """
        queryset = Rating.objects.all()
        
        # Фильтр по типу контента
        content_type = self.request.query_params.get('content_type')
        if content_type:
            queryset = queryset.filter(content_type__model=content_type)
        
        # Фильтр по минимальному рейтингу
        min_rating = self.request.query_params.get('min_rating')
        if min_rating:
            queryset = queryset.filter(current_rating__gte=min_rating)
        
        # Фильтр по статусу приостановки
        is_suspended = self.request.query_params.get('is_suspended')
        if is_suspended is not None:
            queryset = queryset.filter(is_suspended=is_suspended.lower() == 'true')
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def recalculate(self, request, pk=None):
        """
        Пересчитывает рейтинг для объекта.
        """
        rating = self.get_object()
        service = RatingCalculationService()
        
        try:
            new_rating = service.calculate_rating(rating.content_object)
            return Response({
                'message': 'Rating recalculated successfully',
                'new_rating': new_rating
            })
        except Exception as e:
            return Response({
                'error': f'Error recalculating rating: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Возвращает статистику рейтингов.
        """
        # Общая статистика
        total_ratings = Rating.objects.count()
        avg_rating = Rating.objects.aggregate(avg=Avg('current_rating'))['avg'] or 0
        suspended_ratings = Rating.objects.filter(is_suspended=True).count()
        
        # Статистика по типам
        provider_ratings = Rating.objects.filter(content_type__model='provider')
        employee_ratings = Rating.objects.filter(content_type__model='employee')
        sitter_ratings = Rating.objects.filter(content_type__model='sitterprofile')
        
        stats = {
            'total_ratings': total_ratings,
            'average_rating': avg_rating,
            'suspended_ratings': suspended_ratings,
            'by_type': {
                'providers': {
                    'count': provider_ratings.count(),
                    'avg_rating': provider_ratings.aggregate(avg=Avg('current_rating'))['avg'] or 0
                },
                'employees': {
                    'count': employee_ratings.count(),
                    'avg_rating': employee_ratings.aggregate(avg=Avg('current_rating'))['avg'] or 0
                },
                'sitters': {
                    'count': sitter_ratings.count(),
                    'avg_rating': sitter_ratings.aggregate(avg=Avg('current_rating'))['avg'] or 0
                }
            }
        }
        
        return Response(stats)


class ReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet для отзывов.
    
    Предоставляет:
    - Создание отзывов
    - Получение отзывов
    - Модерацию отзывов
    """
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Фильтрует queryset по параметрам запроса.
        """
        queryset = Review.objects.all()
        
        # Фильтр по типу контента
        content_type = self.request.query_params.get('content_type')
        if content_type:
            queryset = queryset.filter(content_type__model=content_type)
        
        # Фильтр по объекту
        object_id = self.request.query_params.get('object_id')
        if object_id:
            queryset = queryset.filter(object_id=object_id)
        
        # Фильтр по автору
        author = self.request.query_params.get('author')
        if author:
            queryset = queryset.filter(author_id=author)
        
        # Фильтр по рейтингу
        rating = self.request.query_params.get('rating')
        if rating:
            queryset = queryset.filter(rating=rating)
        
        # Фильтр по статусу одобрения
        is_approved = self.request.query_params.get('is_approved')
        if is_approved is not None:
            queryset = queryset.filter(is_approved=is_approved.lower() == 'true')
        
        # Фильтр по подозрительности
        is_suspicious = self.request.query_params.get('is_suspicious')
        if is_suspicious is not None:
            queryset = queryset.filter(is_suspicious=is_suspicious.lower() == 'true')
        
        return queryset
    
    def perform_create(self, serializer):
        """
        Создает отзыв и запускает модерацию.
        """
        review = serializer.save(author=self.request.user)
        
        # Запускаем модерацию
        service = GooglePerspectiveModerationService()
        service.moderate_review(review)
        
        # Проверяем подозрительную активность
        detection_service = SuspiciousActivityDetectionService()
        detection_service.detect_suspicious_activity(self.request.user)
    
    @action(detail=True, methods=['post'])
    def moderate(self, request, pk=None):
        """
        Модерирует отзыв.
        """
        review = self.get_object()
        service = GooglePerspectiveModerationService()
        
        try:
            moderated_review = service.moderate_review(review)
            return Response({
                'message': 'Review moderated successfully',
                'is_approved': moderated_review.is_approved,
                'is_suspicious': moderated_review.is_suspicious
            })
        except Exception as e:
            return Response({
                'error': f'Error moderating review: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Возвращает статистику отзывов.
        """
        # Общая статистика
        total_reviews = Review.objects.count()
        approved_reviews = Review.objects.filter(is_approved=True).count()
        suspicious_reviews = Review.objects.filter(is_suspicious=True).count()
        
        # Статистика по рейтингам
        rating_stats = Review.objects.values('rating').annotate(
            count=Count('id')
        ).order_by('rating')
        
        # Статистика по времени
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        recent_reviews = Review.objects.filter(created_at__date__gte=week_ago).count()
        monthly_reviews = Review.objects.filter(created_at__date__gte=month_ago).count()
        
        stats = {
            'total_reviews': total_reviews,
            'approved_reviews': approved_reviews,
            'suspicious_reviews': suspicious_reviews,
            'approval_rate': (approved_reviews / total_reviews * 100) if total_reviews > 0 else 0,
            'rating_distribution': list(rating_stats),
            'recent_activity': {
                'week': recent_reviews,
                'month': monthly_reviews
            }
        }
        
        return Response(stats)


class ComplaintViewSet(viewsets.ModelViewSet):
    """
    ViewSet для жалоб.
    
    Предоставляет:
    - Создание жалоб
    - Получение жалоб
    - Обработку жалоб
    """
    queryset = Complaint.objects.all()
    serializer_class = ComplaintSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Фильтрует queryset по параметрам запроса.
        """
        queryset = Complaint.objects.all()
        
        # Фильтр по типу контента
        content_type = self.request.query_params.get('content_type')
        if content_type:
            queryset = queryset.filter(content_type__model=content_type)
        
        # Фильтр по объекту
        object_id = self.request.query_params.get('object_id')
        if object_id:
            queryset = queryset.filter(object_id=object_id)
        
        # Фильтр по автору
        author = self.request.query_params.get('author')
        if author:
            queryset = queryset.filter(author_id=author)
        
        # Фильтр по типу жалобы
        complaint_type = self.request.query_params.get('complaint_type')
        if complaint_type:
            queryset = queryset.filter(complaint_type=complaint_type)
        
        # Фильтр по статусу
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Фильтр по справедливости
        is_justified = self.request.query_params.get('is_justified')
        if is_justified is not None:
            queryset = queryset.filter(is_justified=is_justified.lower() == 'true')
        
        return queryset
    
    def perform_create(self, serializer):
        """
        Создает жалобу.
        """
        serializer.save(author=self.request.user)
    
    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        """
        Добавляет ответ на жалобу.
        """
        complaint = self.get_object()
        response_text = request.data.get('text')
        
        if not response_text:
            return Response({
                'error': 'Response text is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        service = ComplaintProcessingService()
        
        try:
            response = service.respond_to_complaint(
                complaint, 
                request.user, 
                response_text
            )
            return Response({
                'message': 'Response added successfully',
                'response_id': response.id
            })
        except Exception as e:
            return Response({
                'error': f'Error adding response: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """
        Разрешает жалобу.
        """
        complaint = self.get_object()
        resolution = request.data.get('resolution', '')
        is_justified = request.data.get('is_justified', True)
        
        service = ComplaintProcessingService()
        
        try:
            resolved_complaint = service.resolve_complaint(
                complaint,
                request.user,
                resolution,
                is_justified
            )
            return Response({
                'message': _('Complaint resolved successfully'),
                'status': resolved_complaint.status
            })
        except Exception as e:
            return Response({
                'error': _('Error resolving complaint: {error}').format(error=str(e))
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Возвращает статистику жалоб.
        """
        # Общая статистика
        total_complaints = Complaint.objects.count()
        pending_complaints = Complaint.objects.filter(status='pending').count()
        resolved_complaints = Complaint.objects.filter(status='resolved').count()
        justified_complaints = Complaint.objects.filter(is_justified=True).count()
        
        # Статистика по типам жалоб
        type_stats = Complaint.objects.values('complaint_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Статистика по времени
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        recent_complaints = Complaint.objects.filter(created_at__date__gte=week_ago).count()
        monthly_complaints = Complaint.objects.filter(created_at__date__gte=month_ago).count()
        
        # Среднее время разрешения
        resolved_complaints_with_time = Complaint.objects.filter(
            status='resolved',
            resolved_at__isnull=False
        )
        
        avg_resolution_time = None
        if resolved_complaints_with_time.exists():
            total_time = sum([
                (complaint.resolved_at - complaint.created_at).total_seconds()
                for complaint in resolved_complaints_with_time
            ])
            avg_resolution_time = total_time / resolved_complaints_with_time.count()
        
        stats = {
            'total_complaints': total_complaints,
            'pending_complaints': pending_complaints,
            'resolved_complaints': resolved_complaints,
            'justified_complaints': justified_complaints,
            'resolution_rate': (resolved_complaints / total_complaints * 100) if total_complaints > 0 else 0,
            'justification_rate': (justified_complaints / total_complaints * 100) if total_complaints > 0 else 0,
            'by_type': list(type_stats),
            'recent_activity': {
                'week': recent_complaints,
                'month': monthly_complaints
            },
            'avg_resolution_time_hours': avg_resolution_time / 3600 if avg_resolution_time else None
        }
        
        return Response(stats)


class ComplaintResponseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для ответов на жалобы.
    
    Предоставляет:
    - Получение ответов на жалобы
    """
    queryset = ComplaintResponse.objects.all()
    serializer_class = ComplaintResponseSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Фильтрует queryset по параметрам запроса.
        """
        queryset = ComplaintResponse.objects.all()
        
        # Фильтр по жалобе
        complaint = self.request.query_params.get('complaint')
        if complaint:
            queryset = queryset.filter(complaint_id=complaint)
        
        # Фильтр по автору
        author = self.request.query_params.get('author')
        if author:
            queryset = queryset.filter(author_id=author)
        
        return queryset


class SuspiciousActivityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для подозрительной активности.
    
    Предоставляет:
    - Получение подозрительной активности
    - Статистику подозрительной активности
    """
    queryset = SuspiciousActivity.objects.all()
    serializer_class = SuspiciousActivitySerializer
    permission_classes = [permissions.IsAdminUser]  # Только для админов
    
    def get_queryset(self):
        """
        Фильтрует queryset по параметрам запроса.
        """
        queryset = SuspiciousActivity.objects.all()
        
        # Фильтр по пользователю
        user = self.request.query_params.get('user')
        if user:
            queryset = queryset.filter(user_id=user)
        
        # Фильтр по типу активности
        activity_type = self.request.query_params.get('activity_type')
        if activity_type:
            queryset = queryset.filter(activity_type=activity_type)
        
        # Фильтр по статусу
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Возвращает статистику подозрительной активности.
        """
        # Общая статистика
        total_activities = SuspiciousActivity.objects.count()
        detected_activities = SuspiciousActivity.objects.filter(status='detected').count()
        investigating_activities = SuspiciousActivity.objects.filter(status='investigating').count()
        resolved_activities = SuspiciousActivity.objects.filter(status='resolved').count()
        false_positives = SuspiciousActivity.objects.filter(status='false_positive').count()
        
        # Статистика по типам активности
        type_stats = SuspiciousActivity.objects.values('activity_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Статистика по времени
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        recent_activities = SuspiciousActivity.objects.filter(created_at__date__gte=week_ago).count()
        monthly_activities = SuspiciousActivity.objects.filter(created_at__date__gte=month_ago).count()
        
        stats = {
            'total_activities': total_activities,
            'detected_activities': detected_activities,
            'investigating_activities': investigating_activities,
            'resolved_activities': resolved_activities,
            'false_positives': false_positives,
            'false_positive_rate': (false_positives / total_activities * 100) if total_activities > 0 else 0,
            'by_type': list(type_stats),
            'recent_activity': {
                'week': recent_activities,
                'month': monthly_activities
            }
        }
        
        return Response(stats)
    
    @action(detail=True, methods=['post'])
    def mark_investigating(self, request, pk=None):
        """
        Помечает активность как исследуемую.
        """
        activity = self.get_object()
        activity.status = 'investigating'
        activity.save()
        
        return Response({
            'message': _('Activity marked as investigating')
        })
    
    @action(detail=True, methods=['post'])
    def mark_resolved(self, request, pk=None):
        """
        Помечает активность как разрешенную.
        """
        activity = self.get_object()
        resolution = request.data.get('resolution', '')
        
        activity.status = 'resolved'
        activity.resolution = resolution
        activity.resolved_by = request.user
        activity.resolved_at = timezone.now()
        activity.save()
        
        return Response({
            'message': _('Activity marked as resolved')
        })
    
    @action(detail=True, methods=['post'])
    def mark_false_positive(self, request, pk=None):
        """
        Помечает активность как ложное срабатывание.
        """
        activity = self.get_object()
        resolution = request.data.get('resolution', '')
        
        activity.status = 'false_positive'
        activity.resolution = resolution
        activity.resolved_by = request.user
        activity.resolved_at = timezone.now()
        activity.save()
        
        return Response({
            'message': _('Activity marked as false positive')
        })

    @action(detail=False, methods=['post'])
    def detect(self, request):
        """
        Запускает обнаружение подозрительной активности.
        """
        service = SuspiciousActivityDetectionService()
        
        try:
            activities = service.detect_suspicious_activity()
            return Response({
                'message': _('Suspicious activity detection completed'),
                'detected_count': len(activities)
            })
        except Exception as e:
            return Response({
                'error': _('Error detecting suspicious activity: {error}').format(error=str(e))
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """
        Отмечает активность как проверенную.
        """
        activity = self.get_object()
        notes = request.data.get('notes', '')
        
        try:
            activity.is_reviewed = True
            activity.reviewed_by = request.user
            activity.review_notes = notes
            activity.save()
            
            return Response({
                'message': _('Activity marked as reviewed')
            })
        except Exception as e:
            return Response({
                'error': _('Error reviewing activity: {error}').format(error=str(e))
            }, status=status.HTTP_400_BAD_REQUEST) 