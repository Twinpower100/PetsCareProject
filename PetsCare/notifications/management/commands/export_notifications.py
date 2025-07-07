"""
Команда для экспорта уведомлений.

Эта команда позволяет администратору экспортировать уведомления
в различные форматы для анализа и отчетности.
"""

import csv
import json
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Q
from notifications.models import Notification
from django.utils.translation import gettext as _


class Command(BaseCommand):
    """
    Команда для экспорта уведомлений.
    """
    help = 'Export notifications to CSV or JSON format'

    def add_arguments(self, parser):
        """
        Добавляет аргументы командной строки.
        
        Args:
            parser: Парсер аргументов
        """
        parser.add_argument(
            '--format',
            type=str,
            choices=['csv', 'json'],
            default='csv',
            help='Export format (default: csv)'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output file path (default: notifications_YYYY-MM-DD_HH-MM.format)'
        )
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date for filtering (YYYY-MM-DD)'
        )
        parser.add_argument(
            '--end-date',
            type=str,
            help='End date for filtering (YYYY-MM-DD)'
        )
        parser.add_argument(
            '--notification-type',
            type=str,
            help='Filter by notification type'
        )
        parser.add_argument(
            '--priority',
            type=str,
            choices=['low', 'medium', 'high'],
            help='Filter by priority'
        )
        parser.add_argument(
            '--read-status',
            type=str,
            choices=['read', 'unread', 'all'],
            default='all',
            help='Filter by read status (default: all)'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Filter by specific user ID'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of records to export'
        )

    def handle(self, *args, **options):
        """
        Выполняет команду.
        
        Args:
            *args: Позиционные аргументы
            **options: Опции командной строки
        """
        try:
            # Получаем уведомления для экспорта
            notifications = self._get_notifications(options)
            
            if not notifications.exists():
                self.stdout.write(
                    self.style.WARNING('No notifications found matching the criteria')
                )
                return
            
            # Определяем путь к файлу
            output_file = self._get_output_file(options)
            
            # Экспортируем данные
            if options['format'] == 'csv':
                self._export_to_csv(notifications, output_file)
            else:
                self._export_to_json(notifications, output_file)
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully exported {notifications.count()} notifications to {output_file}')
            )
            
        except Exception as e:
            raise CommandError(f'Failed to export notifications: {e}')

    def _get_notifications(self, options):
        """
        Получает уведомления для экспорта по критериям.
        
        Args:
            options: Опции командной строки
            
        Returns:
            QuerySet: Уведомления для экспорта
        """
        queryset = Notification.objects.all()
        
        # Фильтр по датам
        if options['start_date']:
            try:
                start_date = datetime.strptime(options['start_date'], '%Y-%m-%d').date()
                queryset = queryset.filter(created_at__date__gte=start_date)
            except ValueError:
                raise CommandError('Invalid start date format. Use YYYY-MM-DD')
        
        if options['end_date']:
            try:
                end_date = datetime.strptime(options['end_date'], '%Y-%m-%d').date()
                queryset = queryset.filter(created_at__date__lte=end_date)
            except ValueError:
                raise CommandError('Invalid end date format. Use YYYY-MM-DD')
        
        # Фильтр по типу уведомления
        if options['notification_type']:
            queryset = queryset.filter(notification_type=options['notification_type'])
        
        # Фильтр по приоритету
        if options['priority']:
            queryset = queryset.filter(priority=options['priority'])
        
        # Фильтр по статусу прочтения
        if options['read_status'] == 'read':
            queryset = queryset.filter(is_read=True)
        elif options['read_status'] == 'unread':
            queryset = queryset.filter(is_read=False)
        
        # Фильтр по пользователю
        if options['user_id']:
            queryset = queryset.filter(user_id=options['user_id'])
        
        # Ограничение количества записей
        if options['limit']:
            queryset = queryset[:options['limit']]
        
        return queryset.select_related('user', 'pet')

    def _get_output_file(self, options):
        """
        Определяет путь к файлу для экспорта.
        
        Args:
            options: Опции командной строки
            
        Returns:
            str: Путь к файлу
        """
        if options['output']:
            return options['output']
        
        # Генерируем имя файла по умолчанию
        timestamp = timezone.now().strftime('%Y-%m-%d_%H-%M')
        format_ext = options['format']
        return f'notifications_{timestamp}.{format_ext}'

    def _export_to_csv(self, notifications, output_file):
        """
        Экспортирует уведомления в CSV формат.
        
        Args:
            notifications: Уведомления для экспорта
            output_file: Путь к файлу
        """
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'id', 'user_id', 'user_email', 'pet_id', 'pet_name',
                'notification_type', 'title', 'message', 'priority',
                'channel', 'is_read', 'created_at', 'scheduled_for',
                'sent_at', 'data'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for notification in notifications:
                writer.writerow({
                    'id': notification.id,
                    'user_id': notification.user.id if notification.user else None,
                    'user_email': notification.user.email if notification.user else None,
                    'pet_id': notification.pet.id if notification.pet else None,
                    'pet_name': notification.pet.name if notification.pet else None,
                    'notification_type': notification.notification_type,
                    'title': notification.title,
                    'message': notification.message,
                    'priority': notification.priority,
                    'channel': notification.channel,
                    'is_read': notification.is_read,
                    'created_at': notification.created_at.isoformat() if notification.created_at else None,
                    'scheduled_for': notification.scheduled_for.isoformat() if notification.scheduled_for else None,
                    'sent_at': notification.sent_at.isoformat() if notification.sent_at else None,
                    'data': json.dumps(notification.data) if notification.data else None,
                })

    def _export_to_json(self, notifications, output_file):
        """
        Экспортирует уведомления в JSON формат.
        
        Args:
            notifications: Уведомления для экспорта
            output_file: Путь к файлу
        """
        data = []
        
        for notification in notifications:
            notification_data = {
                'id': notification.id,
                'user': {
                    'id': notification.user.id if notification.user else None,
                    'email': notification.user.email if notification.user else None,
                } if notification.user else None,
                'pet': {
                    'id': notification.pet.id if notification.pet else None,
                    'name': notification.pet.name if notification.pet else None,
                } if notification.pet else None,
                'notification_type': notification.notification_type,
                'title': notification.title,
                'message': notification.message,
                'priority': notification.priority,
                'channel': notification.channel,
                'is_read': notification.is_read,
                'created_at': notification.created_at.isoformat() if notification.created_at else None,
                'scheduled_for': notification.scheduled_for.isoformat() if notification.scheduled_for else None,
                'sent_at': notification.sent_at.isoformat() if notification.sent_at else None,
                'data': notification.data,
            }
            data.append(notification_data)
        
        with open(output_file, 'w', encoding='utf-8') as jsonfile:
            json.dump(data, jsonfile, indent=2, ensure_ascii=False) 