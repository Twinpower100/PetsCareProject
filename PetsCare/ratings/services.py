"""
Сервисы для системы рейтингов и жалоб.

Этот модуль содержит:
1. Сервис расчета рейтингов
2. Сервис обработки жалоб
3. Сервис обнаружения подозрительной активности
4. Сервис модерации отзывов
"""

from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError, PermissionDenied
from decimal import Decimal
from datetime import timedelta
from .models import Rating, Review, Complaint, SuspiciousActivity
from booking.models import Booking
from sitters.models import PetSitting
from pets.models import Pet


class RatingCalculationService:
    """
    Сервис для расчета рейтингов.
    
    Основные функции:
    - Расчет рейтинга на основе отзывов
    - Учет жалоб в рейтинге
    - Учет отмен и no-show
    - Взвешенный расчет
    """
    
    def calculate_rating(self, obj):
        """
        Рассчитывает рейтинг для объекта.
        
        Args:
            obj: Объект (Provider, Employee, SitterProfile)
            
        Returns:
            Decimal: Рассчитанный рейтинг
        """
        # Получаем или создаем объект рейтинга
        content_type = ContentType.objects.get_for_model(obj)
        rating_obj, created = Rating.objects.get_or_create(
            content_type=content_type,
            object_id=obj.id
        )
        
        # Рассчитываем компоненты рейтинга
        reviews_score = self._calculate_reviews_score(obj)
        complaints_score = self._calculate_complaints_score(obj)
        cancellations_score = self._calculate_cancellations_score(obj)
        no_show_score = self._calculate_no_show_score(obj)
        
        # Взвешенный расчет
        total_rating = (
            reviews_score * rating_obj.reviews_weight +
            complaints_score * rating_obj.complaints_weight +
            cancellations_score * rating_obj.cancellations_weight +
            no_show_score * rating_obj.no_show_weight
        )
        
        # Ограничиваем рейтинг от 0 до 5
        total_rating = max(Decimal('0.00'), min(Decimal('5.00'), total_rating))
        
        return total_rating
    
    def _calculate_reviews_score(self, obj):
        """
        Рассчитывает оценку на основе отзывов.
        
        Args:
            obj: Объект для расчета
            
        Returns:
            Decimal: Оценка отзывов
        """
        content_type = ContentType.objects.get_for_model(obj)
        reviews = Review.objects.filter(
            content_type=content_type,
            object_id=obj.id,
            is_approved=True,
            is_suspicious=False
        )
        
        if not reviews.exists():
            return Decimal('3.00')  # Нейтральная оценка при отсутствии отзывов
        
        # Средняя оценка отзывов
        avg_rating = reviews.aggregate(
            avg_rating=models.Avg('rating')
        )['avg_rating']
        
        return Decimal(str(avg_rating))
    
    def _calculate_complaints_score(self, obj):
        """
        Рассчитывает оценку на основе жалоб.
        
        Args:
            obj: Объект для расчета
            
        Returns:
            Decimal: Оценка жалоб
        """
        content_type = ContentType.objects.get_for_model(obj)
        complaints = Complaint.objects.filter(
            content_type=content_type,
            object_id=obj.id
        )
        
        if not complaints.exists():
            return Decimal('5.00')  # Максимальная оценка при отсутствии жалоб
        
        total_complaints = complaints.count()
        justified_complaints = complaints.filter(is_justified=True).count()
        
        # Если все жалобы несправедливы, возвращаем максимальную оценку
        if justified_complaints == 0:
            return Decimal('5.00')
        
        # Рассчитываем штраф за жалобы
        complaint_penalty = (justified_complaints / total_complaints) * 2.0
        
        return max(Decimal('0.00'), Decimal('5.00') - Decimal(str(complaint_penalty)))
    
    def _calculate_cancellations_score(self, obj):
        """
        Рассчитывает оценку на основе отмен.
        
        Args:
            obj: Объект для расчета
            
        Returns:
            Decimal: Оценка отмен
        """
        # Определяем тип объекта и получаем соответствующие бронирования
        if hasattr(obj, 'bookings'):
            # Для Employee
            bookings = obj.bookings.all()
        elif hasattr(obj, 'provider'):
            # Для Provider
            bookings = obj.bookings.all()
        else:
            # Для других объектов
            return Decimal('5.00')
        
        if not bookings.exists():
            return Decimal('5.00')
        
        total_bookings = bookings.count()
        cancelled_by_provider = bookings.filter(
            status__name='cancelled_by_provider'
        ).count()
        
        # Рассчитываем штраф за отмены
        cancellation_rate = cancelled_by_provider / total_bookings
        cancellation_penalty = cancellation_rate * 1.5
        
        return max(Decimal('0.00'), Decimal('5.00') - Decimal(str(cancellation_penalty)))
    
    def _calculate_no_show_score(self, obj):
        """
        Рассчитывает оценку на основе no-show.
        
        Args:
            obj: Объект для расчета
            
        Returns:
            Decimal: Оценка no-show
        """
        # Определяем тип объекта и получаем соответствующие бронирования
        if hasattr(obj, 'bookings'):
            # Для Employee
            bookings = obj.bookings.all()
        elif hasattr(obj, 'provider'):
            # Для Provider
            bookings = obj.bookings.all()
        else:
            # Для других объектов
            return Decimal('5.00')
        
        if not bookings.exists():
            return Decimal('5.00')
        
        total_bookings = bookings.count()
        no_show_by_provider = bookings.filter(
            status__name='no_show_by_provider'
        ).count()
        
        # Рассчитываем штраф за no-show
        no_show_rate = no_show_by_provider / total_bookings
        no_show_penalty = no_show_rate * 2.0
        
        return max(Decimal('0.00'), Decimal('5.00') - Decimal(str(no_show_penalty)))


class ReviewService:
    """
    Сервис для работы с отзывами.
    
    Основные функции:
    - Создание отзывов с проверкой доступа
    - Валидация отзывов
    - Модерация отзывов
    """
    
    @transaction.atomic
    def create_review(self, obj, author, rating, title, text):
        """
        Создает новый отзыв с проверкой доступа.
        
        Args:
            obj: Объект отзыва (Provider, Employee, SitterProfile)
            author: Автор отзыва
            rating: Оценка (1-5)
            title: Заголовок отзыва
            text: Текст отзыва
            
        Returns:
            Review: Созданный отзыв
            
        Raises:
            PermissionDenied: Если у пользователя нет доступа к объекту
            ValidationError: Если отзыв уже существует
        """
        # Проверяем доступ к объекту
        self._check_access_to_object(obj, author)
        
        # Проверяем, что отзыв еще не оставлен
        content_type = ContentType.objects.get_for_model(obj)
        if Review.objects.filter(
            content_type=content_type,
            object_id=obj.id,
            author=author
        ).exists():
            raise ValidationError(_("You have already left a review for this object."))
        
        # Создаем отзыв
        review = Review.objects.create(
            content_type=content_type,
            object_id=obj.id,
            author=author,
            rating=rating,
            title=title,
            text=text
        )
        
        # Запускаем модерацию
        moderation_service = ReviewModerationService()
        moderation_service.moderate_review(review)
        
        # Пересчитываем рейтинг объекта
        rating_service = RatingCalculationService()
        rating_service.calculate_rating(obj)
        
        # Проверяем подозрительную активность
        detection_service = SuspiciousActivityDetectionService()
        detection_service.detect_suspicious_activity(author)
        
        return review
    
    def _check_access_to_object(self, obj, user):
        """
        Проверяет доступ пользователя к объекту для оставления отзыва.
        
        Args:
            obj: Объект для проверки
            user: Пользователь
            
        Raises:
            PermissionDenied: Если у пользователя нет доступа
        """
        # Для учреждений - доступ есть у всех пользователей
        if hasattr(obj, 'name') and hasattr(obj, 'address'):
            return  # Provider
        
        # Для сотрудников - проверяем через бронирования
        if hasattr(obj, 'user') and hasattr(obj, 'bookings'):
            # Employee - проверяем, что пользователь бронировал услуги у этого сотрудника
            user_bookings = Booking.objects.filter(
                user=user,
                employee=obj,
                status__name__in=['completed', 'active']
            )
            if not user_bookings.exists():
                raise PermissionDenied(_("You can only review employees you have booked services from."))
            return
        
        # Для пэт-ситтеров - проверяем через передержки
        if hasattr(obj, 'user') and hasattr(obj, 'sittings'):
            # SitterProfile - проверяем, что пользователь пользовался услугами этого ситтера
            user_sittings = PetSitting.objects.filter(
                ad__owner=user,
                sitter=obj,
                status='completed'
            )
            if not user_sittings.exists():
                raise PermissionDenied(_("You can only review pet sitters you have used services from."))
            return
        
        # Для других объектов - проверяем через питомцев
        if hasattr(obj, 'pet'):
            # Проверяем, что пользователь является владельцем питомца
            pet = obj.pet
            if not (pet.main_owner == user or pet.owners.filter(id=user.id).exists()):
                raise PermissionDenied(_("You can only review services related to your pets."))
            return
        
        # Если не удалось определить тип объекта
        raise PermissionDenied(_("Access denied for this object."))


class ComplaintProcessingService:
    """
    Сервис для обработки жалоб.
    
    Основные функции:
    - Создание жалоб
    - Обработка ответов на жалобы
    - Рассмотрение жалоб
    - Уведомления о жалобах
    """
    
    @transaction.atomic
    def create_complaint(self, obj, author, complaint_type, title, description):
        """
        Создает новую жалобу с проверкой доступа.
        
        Args:
            obj: Объект жалобы (Provider, Employee, SitterProfile)
            author: Автор жалобы
            complaint_type: Тип жалобы
            title: Заголовок жалобы
            description: Описание жалобы
            
        Returns:
            Complaint: Созданная жалоба
        """
        # Проверяем доступ к объекту
        review_service = ReviewService()
        review_service._check_access_to_object(obj, author)
        
        content_type = ContentType.objects.get_for_model(obj)
        
        complaint = Complaint.objects.create(
            content_type=content_type,
            object_id=obj.id,
            author=author,
            complaint_type=complaint_type,
            title=title,
            description=description
        )
        
        # Пересчитываем рейтинг объекта
        rating_service = RatingCalculationService()
        rating_service.calculate_rating(obj)
        
        # Отправляем уведомления
        self._send_complaint_notifications(complaint)
        
        return complaint
    
    @transaction.atomic
    def respond_to_complaint(self, complaint, author, response_text):
        """
        Добавляет ответ на жалобу.
        
        Args:
            complaint: Жалоба
            author: Автор ответа
            response_text: Текст ответа
            
        Returns:
            ComplaintResponse: Созданный ответ
        """
        from .models import ComplaintResponse
        
        response = ComplaintResponse.objects.create(
            complaint=complaint,
            author=author,
            text=response_text
        )
        
        # Обновляем статус жалобы
        if complaint.status == 'pending':
            complaint.status = 'in_progress'
            complaint.save()
        
        # Отправляем уведомления
        self._send_response_notifications(response)
        
        return response
    
    @transaction.atomic
    def resolve_complaint(self, complaint, resolved_by, resolution, is_justified):
        """
        Разрешает жалобу.
        
        Args:
            complaint: Жалоба
            resolved_by: Кто разрешил жалобу
            resolution: Решение по жалобе
            is_justified: Справедлива ли жалоба
            
        Returns:
            Complaint: Обновленная жалоба
        """
        complaint.status = 'resolved'
        complaint.resolution = resolution
        complaint.resolved_by = resolved_by
        complaint.resolved_at = timezone.now()
        complaint.is_justified = is_justified
        complaint.save()
        
        # Пересчитываем рейтинги
        rating_service = RatingCalculationService()
        rating_service.calculate_rating(complaint.content_object)
        
        # Если жалоба несправедлива, корректируем рейтинг автора
        if not is_justified:
            self._adjust_author_rating(complaint.author)
        
        # Отправляем уведомления
        self._send_resolution_notifications(complaint)
        
        return complaint
    
    def _send_complaint_notifications(self, complaint):
        """
        Отправляет уведомления о новой жалобе.
        
        Args:
            complaint: Жалоба
        """
        # TODO: Интеграция с системой уведомлений
        pass
    
    def _send_response_notifications(self, response):
        """
        Отправляет уведомления об ответе на жалобу.
        
        Args:
            response: Ответ на жалобу
        """
        # TODO: Интеграция с системой уведомлений
        pass
    
    def _send_resolution_notifications(self, complaint):
        """
        Отправляет уведомления о разрешении жалобы.
        
        Args:
            complaint: Жалоба
        """
        # TODO: Интеграция с системой уведомлений
        pass
    
    def _adjust_author_rating(self, author):
        """
        Корректирует рейтинг автора несправедливой жалобы.
        
        Args:
            author: Автор жалобы
        """
        # TODO: Реализовать корректировку рейтинга автора
        pass


class SuspiciousActivityDetectionService:
    """
    Сервис для обнаружения подозрительной активности.
    
    Основные функции:
    - Обнаружение массовых отзывов
    - Обнаружение фальшивых жалоб
    - Обнаружение манипуляций с рейтингами
    - Анализ подозрительных паттернов
    """
    
    def detect_suspicious_activity(self, user):
        """
        Обнаруживает подозрительную активность пользователя.
        
        Args:
            user: Пользователь для проверки
            
        Returns:
            list: Список обнаруженных подозрительных активностей
        """
        activities = []
        
        # Проверяем массовые отзывы
        if self._check_mass_reviews(user):
            activities.append(self._create_suspicious_activity(
                user, 'mass_reviews', 'Mass reviews detected'
            ))
        
        # Проверяем фальшивые жалобы
        if self._check_fake_complaints(user):
            activities.append(self._create_suspicious_activity(
                user, 'fake_complaints', 'Fake complaints detected'
            ))
        
        # Проверяем манипуляции с рейтингами
        if self._check_rating_manipulation(user):
            activities.append(self._create_suspicious_activity(
                user, 'rating_manipulation', 'Rating manipulation detected'
            ))
        
        return activities
    
    def _check_mass_reviews(self, user):
        """
        Проверяет массовые отзывы пользователя.
        
        Args:
            user: Пользователь для проверки
            
        Returns:
            bool: True если обнаружены массовые отзывы
        """
        # Проверяем количество отзывов за последние 24 часа
        yesterday = timezone.now() - timedelta(days=1)
        recent_reviews = Review.objects.filter(
            author=user,
            created_at__gte=yesterday
        ).count()
        
        return recent_reviews > 5  # Более 5 отзывов за день подозрительно
    
    def _check_fake_complaints(self, user):
        """
        Проверяет фальшивые жалобы пользователя.
        
        Args:
            user: Пользователь для проверки
            
        Returns:
            bool: True если обнаружены фальшивые жалобы
        """
        # Проверяем количество отклоненных жалоб
        rejected_complaints = Complaint.objects.filter(
            author=user,
            is_justified=False
        ).count()
        
        total_complaints = Complaint.objects.filter(author=user).count()
        
        if total_complaints == 0:
            return False
        
        # Если более 80% жалоб отклонены, это подозрительно
        rejection_rate = rejected_complaints / total_complaints
        return rejection_rate > 0.8
    
    def _check_rating_manipulation(self, user):
        """
        Проверяет манипуляции с рейтингами.
        
        Args:
            user: Пользователь для проверки
            
        Returns:
            bool: True если обнаружены манипуляции
        """
        # Проверяем паттерны отзывов (все 5 звезд или все 1 звезда)
        reviews = Review.objects.filter(author=user)
        
        if reviews.count() < 3:
            return False
        
        ratings = list(reviews.values_list('rating', flat=True))
        
        # Если все отзывы одинаковые, это подозрительно
        if len(set(ratings)) == 1:
            return True
        
        # Если все отзывы крайние (1 или 5), это подозрительно
        extreme_ratings = [r for r in ratings if r in [1, 5]]
        if len(extreme_ratings) / len(ratings) > 0.9:
            return True
        
        return False
    
    def _create_suspicious_activity(self, user, activity_type, description):
        """
        Создает запись о подозрительной активности.
        
        Args:
            user: Пользователь
            activity_type: Тип активности
            description: Описание активности
            
        Returns:
            SuspiciousActivity: Созданная запись
        """
        return SuspiciousActivity.objects.create(
            user=user,
            activity_type=activity_type,
            description=description,
            evidence={
                'detected_at': timezone.now().isoformat(),
                'user_id': user.id,
                'activity_type': activity_type
            }
        )


class ReviewModerationService:
    """
    Сервис для модерации отзывов.
    
    Основные функции:
    - Автоматическая модерация отзывов
    - Проверка подозрительных отзывов
    - Управление статусом отзывов
    """
    
    def moderate_review(self, review):
        """
        Модерирует отзыв.
        
        Args:
            review: Отзыв для модерации
            
        Returns:
            Review: Обновленный отзыв
        """
        # Проверяем подозрительность отзыва
        is_suspicious = self._check_review_suspicious(review)
        
        if is_suspicious:
            review.is_suspicious = True
            review.is_approved = False
            review.save()
            
            # Создаем запись о подозрительной активности
            detection_service = SuspiciousActivityDetectionService()
            detection_service._create_suspicious_activity(
                review.author,
                'suspicious_patterns',
                f'Suspicious review detected: {review.id}'
            )
        else:
            review.is_approved = True
            review.is_suspicious = False
            review.save()
        
        return review
    
    def _check_review_suspicious(self, review):
        """
        Проверяет подозрительность отзыва.
        
        Args:
            review: Отзыв для проверки
            
        Returns:
            bool: True если отзыв подозрительный
        """
        # Проверяем длину текста
        if len(review.text) < 10 and review.rating in [1, 5]:
            return True
        
        # Проверяем повторяющиеся символы
        if self._has_repeating_characters(review.text):
            return True
        
        # Проверяем капс
        if self._is_all_caps(review.text):
            return True
        
        return False
    
    def _has_repeating_characters(self, text):
        """
        Проверяет наличие повторяющихся символов.
        
        Args:
            text: Текст для проверки
            
        Returns:
            bool: True если есть повторяющиеся символы
        """
        if len(text) < 3:
            return False
        
        for i in range(len(text) - 2):
            if text[i] == text[i+1] == text[i+2]:
                return True
        
        return False
    
    def _is_all_caps(self, text):
        """
        Проверяет, написан ли текст заглавными буквами.
        
        Args:
            text: Текст для проверки
            
        Returns:
            bool: True если текст заглавными буквами
        """
        if not text:
            return False
        
        return text.isupper() and len(text) > 10 