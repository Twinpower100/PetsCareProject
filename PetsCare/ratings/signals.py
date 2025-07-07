"""
Сигналы для системы рейтингов и жалоб.

Этот модуль содержит:
1. Сигналы для автоматического создания рейтингов
2. Сигналы для обновления рейтингов при изменении объектов
3. Сигналы для обнаружения подозрительной активности
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from .models import Rating, Review, Complaint, SuspiciousActivity
from providers.models import Provider, Employee
from sitters.models import SitterProfile
from .services import RatingCalculationService, SuspiciousActivityDetectionService


@receiver(post_save, sender=Provider)
def create_provider_rating(sender, instance, created, **kwargs):
    """
    Создает рейтинг для нового учреждения.
    """
    if created:
        content_type = ContentType.objects.get_for_model(Provider)
        Rating.objects.get_or_create(
            content_type=content_type,
            object_id=instance.id
        )


@receiver(post_save, sender=Employee)
def create_employee_rating(sender, instance, created, **kwargs):
    """
    Создает рейтинг для нового сотрудника.
    """
    if created:
        content_type = ContentType.objects.get_for_model(Employee)
        Rating.objects.get_or_create(
            content_type=content_type,
            object_id=instance.id
        )


@receiver(post_save, sender=SitterProfile)
def create_sitter_rating(sender, instance, created, **kwargs):
    """
    Создает рейтинг для нового пэт-ситтера.
    """
    if created:
        content_type = ContentType.objects.get_for_model(SitterProfile)
        Rating.objects.get_or_create(
            content_type=content_type,
            object_id=instance.id
        )


@receiver(post_save, sender=Review)
def update_rating_on_review_change(sender, instance, created, **kwargs):
    """
    Обновляет рейтинг при изменении отзыва.
    """
    if instance.is_approved and not instance.is_suspicious:
        rating_service = RatingCalculationService()
        rating_service.calculate_rating(instance.content_object)


@receiver(post_save, sender=Complaint)
def update_rating_on_complaint_change(sender, instance, created, **kwargs):
    """
    Обновляет рейтинг при изменении жалобы.
    """
    rating_service = RatingCalculationService()
    rating_service.calculate_rating(instance.content_object)


@receiver(post_save, sender=Review)
def detect_suspicious_activity_on_review(sender, instance, created, **kwargs):
    """
    Обнаруживает подозрительную активность при создании отзыва.
    """
    if created:
        detection_service = SuspiciousActivityDetectionService()
        detection_service.detect_suspicious_activity(instance.author)


@receiver(post_save, sender=Complaint)
def detect_suspicious_activity_on_complaint(sender, instance, created, **kwargs):
    """
    Обнаруживает подозрительную активность при создании жалобы.
    """
    if created:
        detection_service = SuspiciousActivityDetectionService()
        detection_service.detect_suspicious_activity(instance.author) 