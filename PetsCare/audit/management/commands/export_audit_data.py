import json
import csv
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.utils.translation import gettext as _
from datetime import datetime, timedelta

from audit.models import UserAction, SecurityAudit


class Command(BaseCommand):
    """
    Команда для экспорта данных аудита и логирования.
    
    Экспортирует логи действий и записи аудита безопасности
    в различные форматы (JSON, CSV) для анализа и архивирования.
    """
    
    help = _('Exports audit and logging data to files')
    
    def add_arguments(self, parser):
        """Добавляет аргументы командной строки"""
        parser.add_argument(
            '--format',
            choices=['json', 'csv'],
            default='json',
            help=_('Export format (json or csv)')
        )
        parser.add_argument(
            '--start-date',
            type=str,
            help=_('Start date in YYYY-MM-DD format')
        )
        parser.add_argument(
            '--end-date',
            type=str,
            help=_('End date in YYYY-MM-DD format')
        )
        parser.add_argument(
            '--output-dir',
            type=str,
            default='audit_exports',
            help=_('Directory to save files')
        )
        parser.add_argument(
            '--include-logs',
            action='store_true',
            help=_('Include user actions in export')
        )
        parser.add_argument(
            '--include-audits',
            action='store_true',
            help=_('Include security audits in export')
        )
    
    def handle(self, *args, **options):
        """Основной метод выполнения команды"""
        import os
        
        # Создаем директорию для экспорта
        output_dir = options['output_dir']
        os.makedirs(output_dir, exist_ok=True)
        
        # Парсим даты
        start_date = self._parse_date(options['start_date'])
        end_date = self._parse_date(options['end_date'])
        
        # Определяем что экспортировать
        include_logs = options['include_logs'] or not options['include_audits']
        include_audits = options['include_audits'] or not options['include_logs']
        
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        
        # Экспортируем логи действий
        if include_logs:
            self._export_user_actions(
                output_dir, timestamp, options['format'], start_date, end_date
            )
        
        # Экспортируем аудит безопасности
        if include_audits:
            self._export_security_audits(
                output_dir, timestamp, options['format'], start_date, end_date
            )
        
        self.stdout.write(
            self.style.SUCCESS(_('Export completed. Files saved in {}').format(output_dir))
        )
    
    def _parse_date(self, date_str):
        """Парсит дату из строки"""
        if not date_str:
            return None
        
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            self.stdout.write(
                self.style.ERROR(_('Invalid date format: {}').format(date_str))
            )
            return None
    
    def _export_user_actions(self, output_dir, timestamp, format_type, start_date, end_date):
        """Экспортирует логи действий пользователей"""
        # Формируем queryset с фильтрацией по датам
        queryset = UserAction.objects.select_related('user', 'content_type')
        
        if start_date:
            queryset = queryset.filter(timestamp__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__date__lte=end_date)
        
        # Получаем данные
        actions = list(queryset.values(
            'id', 'user__email', 'action_type', 'timestamp',
            'ip_address', 'http_method', 'url', 'status_code',
            'execution_time', 'details'
        ))
        
        filename = f"{output_dir}/user_actions_{timestamp}.{format_type}"
        
        if format_type == 'json':
            self._export_to_json(actions, filename)
        else:
            self._export_to_csv(actions, filename, [
                'id', 'user__email', 'action_type', 'timestamp',
                'ip_address', 'http_method', 'url', 'status_code',
                'execution_time', 'details'
            ])
        
        self.stdout.write(_('Exported user actions: {}').format(len(actions)))
    
    def _export_security_audits(self, output_dir, timestamp, format_type, start_date, end_date):
        """Экспортирует записи аудита безопасности"""
        # Формируем queryset с фильтрацией по датам
        queryset = SecurityAudit.objects.select_related('user', 'content_type', 'reviewed_by')
        
        if start_date:
            queryset = queryset.filter(timestamp__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__date__lte=end_date)
        
        # Получаем данные
        audits = list(queryset.values(
            'id', 'user__email', 'audit_type', 'timestamp',
            'is_critical', 'review_status', 'reviewed_by__email',
            'reason', 'old_values', 'new_values', 'details'
        ))
        
        filename = f"{output_dir}/security_audits_{timestamp}.{format_type}"
        
        if format_type == 'json':
            self._export_to_json(audits, filename)
        else:
            self._export_to_csv(audits, filename, [
                'id', 'user__email', 'audit_type', 'timestamp',
                'is_critical', 'review_status', 'reviewed_by__email',
                'reason', 'old_values', 'new_values', 'details'
            ])
        
        self.stdout.write(_('Exported security audits: {}').format(len(audits)))
    
    def _export_to_json(self, data, filename):
        """Экспортирует данные в JSON формат"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    
    def _export_to_csv(self, data, filename, fieldnames):
        """Экспортирует данные в CSV формат"""
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for item in data:
                # Преобразуем JSON поля в строки
                if 'details' in item and item['details']:
                    item['details'] = json.dumps(item['details'], ensure_ascii=False)
                if 'old_values' in item and item['old_values']:
                    item['old_values'] = json.dumps(item['old_values'], ensure_ascii=False)
                if 'new_values' in item and item['new_values']:
                    item['new_values'] = json.dumps(item['new_values'], ensure_ascii=False)
                
                writer.writerow(item) 