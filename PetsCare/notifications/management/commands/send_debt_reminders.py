from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from notifications.tasks import send_debt_reminder_task
from billing.models import Debt
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Send debt reminders to users with outstanding payments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending',
        )
        parser.add_argument(
            '--min-amount',
            type=float,
            default=10.0,
            help='Minimum debt amount to send reminder (default: 10.0)',
        )
        parser.add_argument(
            '--days-overdue',
            type=int,
            default=7,
            help='Days overdue to send reminder (default: 7)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        min_amount = options['min_amount']
        days_overdue = options['days_overdue']
        
        cutoff_date = timezone.now() - timezone.timedelta(days=days_overdue)
        
        # Получаем задолженности, которые соответствуют критериям
        debts = Debt.objects.filter(
            amount__gte=min_amount,
            created_at__lte=cutoff_date,
            is_paid=False
        ).select_related('user')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Found {debts.count()} debts to process (min amount: {min_amount}, days overdue: {days_overdue})'
            )
        )
        
        sent_count = 0
        error_count = 0
        
        for debt in debts:
            try:
                if dry_run:
                    self.stdout.write(
                        f'[DRY RUN] Would send debt reminder to {debt.user.email} '
                        f'(amount: {debt.amount} {debt.currency})'
                    )
                else:
                    # Отправляем задачу на уведомление
                    send_debt_reminder_task.delay(
                        user_id=debt.user.id,
                        debt_amount=debt.amount,
                        currency=debt.currency or 'EUR'
                    )
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Sent debt reminder to {debt.user.email} '
                            f'(amount: {debt.amount} {debt.currency})'
                        )
                    )
                
                sent_count += 1
                
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'Failed to send debt reminder to {debt.user.email}: {e}'
                    )
                )
                logger.error(f'Failed to send debt reminder to user {debt.user.id}: {e}')
        
        # Выводим итоговую статистику
        self.stdout.write('\n' + '='*50)
        self.stdout.write(
            self.style.SUCCESS(
                f'Debt reminders processing completed:\n'
                f'- Total processed: {debts.count()}\n'
                f'- Successfully sent: {sent_count}\n'
                f'- Errors: {error_count}'
            )
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('This was a dry run - no actual notifications were sent')
            ) 