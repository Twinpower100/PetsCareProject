from django.core.management.base import BaseCommand
from django.utils import timezone
from notifications.tasks import send_price_change_notification_task
from catalog.models import Service
from booking.models import Booking
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send price change notifications to users who used specific services'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending',
        )
        parser.add_argument(
            '--service-id',
            type=int,
            help='Specific service ID to process',
        )
        parser.add_argument(
            '--min-change-percent',
            type=float,
            default=5.0,
            help='Minimum price change percentage to notify (default: 5.0)',
        )
        parser.add_argument(
            '--days-since-change',
            type=int,
            default=1,
            help='Days since price change to send notification (default: 1)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        service_id = options['service_id']
        min_change_percent = options['min_change_percent']
        days_since_change = options['days_since_change']
        
        cutoff_date = timezone.now() - timezone.timedelta(days=days_since_change)
        
        # Получаем услуги с измененными ценами
        if service_id:
            services = Service.objects.filter(id=service_id)
        else:
            services = Service.objects.filter(
                updated_at__gte=cutoff_date
            ).exclude(price_history__isnull=True)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Found {services.count()} services to process for price changes'
            )
        )
        
        sent_count = 0
        error_count = 0
        
        for service in services:
            try:
                # Получаем историю цен
                price_history = service.price_history
                if not price_history or len(price_history) < 2:
                    continue
                
                # Получаем последние две цены
                current_price = price_history[-1]['price']
                previous_price = price_history[-2]['price']
                
                # Вычисляем процент изменения
                change_percent = abs((current_price - previous_price) / previous_price) * 100
                
                if change_percent < min_change_percent:
                    continue
                
                # Получаем количество пользователей, которые использовали эту услугу
                user_count = Booking.objects.filter(service=service).values('user').distinct().count()
                
                if dry_run:
                    self.stdout.write(
                        f'[DRY RUN] Would send price change notification for service "{service.name}" '
                        f'(change: {change_percent:.1f}%, users: {user_count})'
                    )
                else:
                    # Отправляем задачу на уведомление
                    send_price_change_notification_task.delay(
                        service_id=service.id,
                        old_price=previous_price,
                        new_price=current_price,
                        currency=service.currency or 'EUR'
                    )
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Sent price change notification for service "{service.name}" '
                            f'(change: {change_percent:.1f}%, users: {user_count})'
                        )
                    )
                
                sent_count += 1
                
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'Failed to process price change for service {service.id}: {e}'
                    )
                )
                logger.error(f'Failed to process price change for service {service.id}: {e}')
        
        # Выводим итоговую статистику
        self.stdout.write('\n' + '='*50)
        self.stdout.write(
            self.style.SUCCESS(
                f'Price change notifications processing completed:\n'
                f'- Total services processed: {services.count()}\n'
                f'- Notifications sent: {sent_count}\n'
                f'- Errors: {error_count}'
            )
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('This was a dry run - no actual notifications were sent')
            ) 