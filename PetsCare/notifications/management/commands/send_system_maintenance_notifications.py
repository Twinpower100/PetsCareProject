from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from notifications.tasks import send_system_maintenance_notification_task
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Send system maintenance notifications to users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending',
        )
        parser.add_argument(
            '--message',
            type=str,
            required=True,
            help='Maintenance message to send',
        )
        parser.add_argument(
            '--user-ids',
            nargs='+',
            type=int,
            help='Specific user IDs to notify (if not provided, notifies all active users)',
        )
        parser.add_argument(
            '--user-type',
            type=str,
            choices=['all', 'owners', 'providers', 'sitters'],
            default='all',
            help='User type to notify (default: all)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        message = options['message']
        user_ids = options['user_ids']
        user_type = options['user_type']
        
        # Определяем queryset пользователей
        if user_ids:
            users = User.objects.filter(id__in=user_ids, is_active=True)
        else:
            users = User.objects.filter(is_active=True)
            
            # Фильтруем по типу пользователя
            if user_type == 'owners':
                users = users.filter(user_type='owner')
            elif user_type == 'providers':
                users = users.filter(user_type='provider')
            elif user_type == 'sitters':
                users = users.filter(user_type='sitter')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Found {users.count()} users to notify about system maintenance'
            )
        )
        
        if dry_run:
            self.stdout.write(f'[DRY RUN] Message: "{message}"')
            self.stdout.write(f'[DRY RUN] Would send to {users.count()} users')
            
            # Показываем первые 10 пользователей
            for user in users[:10]:
                self.stdout.write(f'[DRY RUN] Would notify: {user.email} ({user.get_full_name()})')
            
            if users.count() > 10:
                self.stdout.write(f'[DRY RUN] ... and {users.count() - 10} more users')
        else:
            try:
                # Отправляем задачу на уведомление
                user_id_list = list(users.values_list('id', flat=True))
                
                send_system_maintenance_notification_task.delay(
                    message=message,
                    user_ids=user_id_list
                )
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'System maintenance notification task queued for {users.count()} users'
                    )
                )
                
                logger.info(f'System maintenance notification queued for {users.count()} users')
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Failed to queue system maintenance notification: {e}')
                )
                logger.error(f'Failed to queue system maintenance notification: {e}')
        
        # Выводим итоговую статистику
        self.stdout.write('\n' + '='*50)
        self.stdout.write(
            self.style.SUCCESS(
                f'System maintenance notification processing completed:\n'
                f'- Users to notify: {users.count()}\n'
                f'- User type: {user_type}\n'
                f'- Message: "{message}"'
            )
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('This was a dry run - no actual notifications were sent')
            ) 