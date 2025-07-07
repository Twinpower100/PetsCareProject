"""
Команда для очистки старых уведомлений.

Эта команда позволяет администратору очищать старые уведомления
из базы данных для оптимизации производительности.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from notifications.models import Notification
from django.utils.translation import gettext as _


class Command(BaseCommand):
    """
    Команда для очистки старых уведомлений.
    """
    help = 'Clean up old notifications from database'

    def add_arguments(self, parser):
        """
        Добавляет аргументы командной строки.
        
        Args:
            parser: Парсер аргументов
        """
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Delete notifications older than specified days (default: 30)'
        )
        parser.add_argument(
            '--read-only',
            action='store_true',
            help='Delete only read notifications'
        )
        parser.add_argument(
            '--unread-only',
            action='store_true',
            help='Delete only unread notifications'
        )
        parser.add_argument(
            '--notification-type',
            type=str,
            help='Delete only notifications of specific type'
        )
        parser.add_argument(
            '--priority',
            type=str,
            choices=['low', 'medium', 'high'],
            help='Delete only notifications of specific priority'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force deletion without confirmation'
        )

    def handle(self, *args, **options):
        """
        Выполняет команду.
        
        Args:
            *args: Позиционные аргументы
            **options: Опции командной строки
        """
        try:
            # Получаем критерии для удаления
            criteria = self._build_criteria(options)
            
            # Получаем уведомления для удаления
            notifications_to_delete = self._get_notifications_to_delete(criteria)
            
            if not notifications_to_delete.exists():
                self.stdout.write(
                    self.style.WARNING('No notifications found matching the criteria')
                )
                return
            
            # Показываем статистику
            self._show_statistics(notifications_to_delete, options)
            
            # Проверяем режим dry-run
            if options['dry_run']:
                self._show_dry_run(notifications_to_delete)
                return
            
            # Запрашиваем подтверждение
            if not options['force'] and not self._confirm_deletion(notifications_to_delete):
                self.stdout.write('Operation cancelled.')
                return
            
            # Выполняем удаление
            self._perform_deletion(notifications_to_delete)
            
        except Exception as e:
            raise CommandError(f'Failed to cleanup notifications: {e}')

    def _build_criteria(self, options):
        """
        Строит критерии для удаления уведомлений.
        
        Args:
            options: Опции командной строки
            
        Returns:
            dict: Критерии для удаления
        """
        criteria = {}
        
        # Возраст уведомлений
        days = options['days']
        cutoff_date = timezone.now() - timedelta(days=days)
        criteria['created_at__lt'] = cutoff_date
        
        # Статус прочтения
        if options['read_only']:
            criteria['is_read'] = True
        elif options['unread_only']:
            criteria['is_read'] = False
        
        # Тип уведомления
        if options['notification_type']:
            criteria['notification_type'] = options['notification_type']
        
        # Приоритет
        if options['priority']:
            criteria['priority'] = options['priority']
        
        return criteria

    def _get_notifications_to_delete(self, criteria):
        """
        Получает уведомления для удаления по критериям.
        
        Args:
            criteria: Критерии для удаления
            
        Returns:
            QuerySet: Уведомления для удаления
        """
        return Notification.objects.filter(**criteria)

    def _show_statistics(self, notifications, options):
        """
        Показывает статистику уведомлений для удаления.
        
        Args:
            notifications: Уведомления для удаления
            options: Опции командной строки
        """
        total_count = notifications.count()
        
        self.stdout.write('='*60)
        self.stdout.write('NOTIFICATION CLEANUP STATISTICS')
        self.stdout.write('='*60)
        
        self.stdout.write(f'Total notifications to delete: {total_count}')
        self.stdout.write(f'Older than: {options["days"]} days')
        
        if options['read_only']:
            self.stdout.write('Filter: Read notifications only')
        elif options['unread_only']:
            self.stdout.write('Filter: Unread notifications only')
        
        if options['notification_type']:
            self.stdout.write(f'Type: {options["notification_type"]}')
        
        if options['priority']:
            self.stdout.write(f'Priority: {options["priority"]}')
        
        # Статистика по типам
        type_stats = notifications.values('notification_type').annotate(
            count=models.Count('id')
        )
        if type_stats:
            self.stdout.write('\nBy notification type:')
            for stat in type_stats:
                self.stdout.write(f'  {stat["notification_type"]}: {stat["count"]}')
        
        # Статистика по приоритетам
        priority_stats = notifications.values('priority').annotate(
            count=models.Count('id')
        )
        if priority_stats:
            self.stdout.write('\nBy priority:')
            for stat in priority_stats:
                self.stdout.write(f'  {stat["priority"]}: {stat["count"]}')
        
        # Статистика по статусу прочтения
        read_stats = notifications.values('is_read').annotate(
            count=models.Count('id')
        )
        if read_stats:
            self.stdout.write('\nBy read status:')
            for stat in read_stats:
                status = 'Read' if stat['is_read'] else 'Unread'
                self.stdout.write(f'  {status}: {stat["count"]}')
        
        self.stdout.write('='*60)

    def _show_dry_run(self, notifications):
        """
        Показывает, что будет удалено в режиме dry-run.
        
        Args:
            notifications: Уведомления для удаления
        """
        self.stdout.write(
            self.style.WARNING('\nDRY RUN - No notifications will be deleted')
        )
        
        self.stdout.write(f'Would delete {notifications.count()} notifications')
        
        # Показываем примеры уведомлений
        sample_notifications = notifications[:5]
        if sample_notifications:
            self.stdout.write('\nSample notifications to be deleted:')
            for notification in sample_notifications:
                self.stdout.write(
                    f'  - ID: {notification.id}, Type: {notification.notification_type}, '
                    f'Title: {notification.title[:50]}..., '
                    f'Created: {notification.created_at.strftime("%Y-%m-%d %H:%M")}'
                )

    def _confirm_deletion(self, notifications):
        """
        Запрашивает подтверждение удаления.
        
        Args:
            notifications: Уведомления для удаления
            
        Returns:
            bool: True если пользователь подтвердил удаление
        """
        count = notifications.count()
        
        self.stdout.write(
            self.style.WARNING(f'\nWARNING: This will permanently delete {count} notifications!')
        )
        
        while True:
            response = input('\nAre you sure you want to proceed? (yes/no): ').lower().strip()
            
            if response in ['yes', 'y']:
                return True
            elif response in ['no', 'n']:
                return False
            else:
                self.stdout.write('Please enter "yes" or "no"')

    def _perform_deletion(self, notifications):
        """
        Выполняет удаление уведомлений.
        
        Args:
            notifications: Уведомления для удаления
        """
        try:
            with transaction.atomic():
                count = notifications.count()
                notifications.delete()
                
                self.stdout.write(
                    self.style.SUCCESS(f'\nSuccessfully deleted {count} notifications!')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\nFailed to delete notifications: {e}')
            )
            raise 