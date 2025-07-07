"""
Команда Django для обнаружения подозрительной активности.

Использование:
python manage.py detect_suspicious_activity
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from ratings.services import SuspiciousActivityDetectionService
from ratings.models import Review, Complaint, SuspiciousActivity

User = get_user_model()


class Command(BaseCommand):
    """
    Команда для обнаружения подозрительной активности.
    """
    help = _('Detect suspicious activity in ratings and reviews')
    
    def add_arguments(self, parser):
        """
        Добавляет аргументы командной строки.
        """
        parser.add_argument(
            '--users',
            type=str,
            help='Comma-separated list of user IDs to check (optional)'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help=_('Number of days to analyze (default: 30)')
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help=_('Run without saving suspicious activity records')
        )
        parser.add_argument(
            '--threshold',
            type=float,
            default=0.8,
            help=_('Suspicious activity threshold (0.0-1.0, default: 0.8)')
        )
    
    def handle(self, *args, **options):
        """
        Выполняет команду.
        """
        self.stdout.write(_('Starting suspicious activity detection...'))
        
        # Получаем пользователей для проверки
        if options['users']:
            user_ids = [int(uid.strip()) for uid in options['users'].split(',')]
            users = User.objects.filter(id__in=user_ids)
        else:
            # Проверяем всех пользователей с отзывами или жалобами
            users_with_reviews = User.objects.filter(reviews__isnull=False).distinct()
            users_with_complaints = User.objects.filter(complaints__isnull=False).distinct()
            users = (users_with_reviews | users_with_complaints).distinct()
        
        self.stdout.write(f'Checking {users.count()} users...')
        
        # Создаем сервис для обнаружения подозрительной активности
        detection_service = SuspiciousActivityDetectionService()
        
        # Получаем дату начала анализа
        start_date = timezone.now() - timezone.timedelta(days=options['days'])
        
        self.stdout.write(
            _('Analyzing activity from {date} to {now}').format(
                date=start_date.strftime('%Y-%m-%d'),
                now=timezone.now().strftime('%Y-%m-%d')
            )
        )
        
        # Обнаруживаем подозрительную активность
        suspicious_activities = detection_service.detect_suspicious_activity(
            start_date=start_date,
            threshold=options['threshold']
        )
        
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING(
                    _('[DRY RUN] Found {count} suspicious activities').format(
                        count=len(suspicious_activities)
                    )
                )
            )
        else:
            # Сохраняем обнаруженную подозрительную активность
            saved_count = 0
            for activity_data in suspicious_activities:
                try:
                    activity = SuspiciousActivity.objects.create(
                        activity_type=activity_data['activity_type'],
                        user=activity_data['user'],
                        content_type=activity_data['content_type'],
                        object_id=activity_data['object_id'],
                        confidence_score=activity_data['confidence_score'],
                        details=activity_data['details'],
                        detected_at=timezone.now()
                    )
                    saved_count += 1
                    
                    self.stdout.write(
                        _('Detected: {type} by user {user} (confidence: {score:.2f})').format(
                            type=activity_data['activity_type'],
                            user=activity_data['user'].username,
                            score=activity_data['confidence_score']
                        )
                    )
                
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            _('Error saving suspicious activity: {error}').format(error=e)
                        )
                    )
            
            self.stdout.write(
                self.style.SUCCESS(
                    _('Detection completed. Saved {saved} suspicious activities.').format(
                        saved=saved_count
                    )
                )
            ) 