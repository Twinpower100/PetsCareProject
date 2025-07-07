"""
Команда для отправки тестовых уведомлений.

Эта команда позволяет администратору отправлять тестовые уведомления
пользователям для проверки работы системы уведомлений.
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _
from notifications.services import NotificationService
from notifications.models import Notification

User = get_user_model()


class Command(BaseCommand):
    """
    Команда для отправки тестовых уведомлений.
    """
    help = 'Send test notifications to users'

    def add_arguments(self, parser):
        """
        Добавляет аргументы командной строки.
        
        Args:
            parser: Парсер аргументов
        """
        parser.add_argument(
            '--user-id',
            type=int,
            help='Send notification to specific user by ID'
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Send notification to user by email'
        )
        parser.add_argument(
            '--all-users',
            action='store_true',
            help='Send notification to all active users'
        )
        parser.add_argument(
            '--notification-type',
            type=str,
            default='system',
            choices=['system', 'booking', 'cancellation', 'pet_sitting', 'appointment', 'reminder'],
            help='Type of notification to send'
        )
        parser.add_argument(
            '--title',
            type=str,
            default='Test Notification',
            help='Notification title'
        )
        parser.add_argument(
            '--message',
            type=str,
            default='This is a test notification from the PetCare system',
            help='Notification message'
        )
        parser.add_argument(
            '--priority',
            type=str,
            default='low',
            choices=['low', 'medium', 'high'],
            help='Notification priority'
        )
        parser.add_argument(
            '--channels',
            nargs='+',
            default=['email', 'push', 'in_app'],
            choices=['email', 'push', 'in_app', 'all'],
            help='Channels to send notification through'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending'
        )

    def handle(self, *args, **options):
        """
        Выполняет команду.
        
        Args:
            *args: Позиционные аргументы
            **options: Опции командной строки
        """
        try:
            # Определяем пользователей для отправки
            users = self._get_users(options)
            
            if not users:
                raise CommandError('No users found to send notifications to')
            
            # Проверяем режим dry-run
            if options['dry_run']:
                self._show_dry_run(users, options)
                return
            
            # Отправляем уведомления
            self._send_notifications(users, options)
            
        except Exception as e:
            raise CommandError(f'Failed to send test notifications: {e}')

    def _get_users(self, options):
        """
        Получает список пользователей для отправки уведомлений.
        
        Args:
            options: Опции командной строки
            
        Returns:
            QuerySet: Список пользователей
        """
        if options['user_id']:
            try:
                user = User.objects.get(id=options['user_id'])
                return [user]
            except User.DoesNotExist:
                raise CommandError(f'User with ID {options["user_id"]} not found')
        
        elif options['email']:
            try:
                user = User.objects.get(email=options['email'])
                return [user]
            except User.DoesNotExist:
                raise CommandError(f'User with email {options["email"]} not found')
        
        elif options['all_users']:
            return User.objects.filter(is_active=True)
        
        else:
            raise CommandError('Please specify --user-id, --email, or --all-users')

    def _show_dry_run(self, users, options):
        """
        Показывает, что будет отправлено в режиме dry-run.
        
        Args:
            users: Список пользователей
            options: Опции командной строки
        """
        self.stdout.write(
            self.style.WARNING('DRY RUN - No notifications will be sent')
        )
        
        self.stdout.write(f'Would send notification to {len(users)} users:')
        for user in users:
            self.stdout.write(f'  - {user.email} (ID: {user.id})')
        
        self.stdout.write(f'\nNotification details:')
        self.stdout.write(f'  Type: {options["notification_type"]}')
        self.stdout.write(f'  Title: {options["title"]}')
        self.stdout.write(f'  Message: {options["message"]}')
        self.stdout.write(f'  Priority: {options["priority"]}')
        self.stdout.write(f'  Channels: {", ".join(options["channels"])}')

    def _send_notifications(self, users, options):
        """
        Отправляет уведомления пользователям.
        
        Args:
            users: Список пользователей
            options: Опции командной строки
        """
        notification_service = NotificationService()
        sent_count = 0
        failed_count = 0
        
        self.stdout.write(f'Sending notifications to {len(users)} users...')
        
        for user in users:
            try:
                notification = notification_service.send_notification(
                    user=user,
                    notification_type=options['notification_type'],
                    title=options['title'],
                    message=options['message'],
                    channels=options['channels'],
                    priority=options['priority'],
                    data={'test': True, 'sent_by': 'admin_command'}
                )
                
                sent_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Sent to {user.email} (ID: {user.id})')
                )
                
            except Exception as e:
                failed_count += 1
                self.stdout.write(
                    self.style.ERROR(f'✗ Failed to send to {user.email}: {e}')
                )
        
        # Выводим итоговую статистику
        self.stdout.write('\n' + '='*50)
        self.stdout.write('NOTIFICATION SENDING COMPLETED')
        self.stdout.write('='*50)
        self.stdout.write(f'Total users: {len(users)}')
        self.stdout.write(f'Successfully sent: {sent_count}')
        self.stdout.write(f'Failed: {failed_count}')
        
        if sent_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'\nSuccessfully sent {sent_count} test notifications!')
            )
        
        if failed_count > 0:
            self.stdout.write(
                self.style.WARNING(f'\nFailed to send {failed_count} notifications. Check logs for details.')
            ) 