from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Count, Q
from django.utils.translation import gettext as _
from datetime import timedelta

from audit.models import UserAction, SecurityAudit, AuditSettings


class Command(BaseCommand):
    """
    Команда для вывода статистики аудита и логирования.
    
    Показывает различные метрики и статистику по логам действий
    и записям аудита безопасности.
    """
    
    help = _('Shows audit and logging statistics')
    
    def add_arguments(self, parser):
        """Добавляет аргументы командной строки"""
        parser.add_argument(
            '--period',
            choices=['today', 'week', 'month', 'year'],
            default='week',
            help=_('Statistics period')
        )
        parser.add_argument(
            '--detailed',
            action='store_true',
            help=_('Show detailed statistics')
        )
    
    def handle(self, *args, **options):
        """Основной метод выполнения команды"""
        # Определяем период
        period = options['period']
        start_date = self._get_start_date(period)
        
        self.stdout.write(_('Audit Statistics for period: {}').format(period))
        self.stdout.write(_('Period: {} - {}').format(start_date, timezone.now()))
        self.stdout.write('=' * 50)
        
        # Общая статистика
        self._show_general_statistics(start_date)
        
        # Статистика по типам действий
        self._show_action_statistics(start_date)
        
        # Статистика по пользователям
        self._show_user_statistics(start_date)
        
        # Статистика аудита безопасности
        self._show_security_audit_statistics(start_date)
        
        # Детальная статистика
        if options['detailed']:
            self._show_detailed_statistics(start_date)
    
    def _get_start_date(self, period):
        """Получает дату начала периода"""
        now = timezone.now()
        
        if period == 'today':
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'week':
            return now - timedelta(days=7)
        elif period == 'month':
            return now - timedelta(days=30)
        elif period == 'year':
            return now - timedelta(days=365)
        
        return now - timedelta(days=7)
    
    def _show_general_statistics(self, start_date):
        """Показывает общую статистику"""
        self.stdout.write(_('\nGeneral Statistics:'))
        
        # Общее количество записей
        total_actions = UserAction.objects.count()
        total_audits = SecurityAudit.objects.count()
        
        # Записи за период
        period_actions = UserAction.objects.filter(timestamp__gte=start_date).count()
        period_audits = SecurityAudit.objects.filter(timestamp__gte=start_date).count()
        
        self.stdout.write(_('Total user actions: {}').format(total_actions))
        self.stdout.write(_('Total security audits: {}').format(total_audits))
        self.stdout.write(_('Actions in period: {}').format(period_actions))
        self.stdout.write(_('Audits in period: {}').format(period_audits))
    
    def _show_action_statistics(self, start_date):
        """Показывает статистику по типам действий"""
        self.stdout.write(_('\nAction Type Statistics:'))
        
        # Топ типов действий за период
        action_types = UserAction.objects.filter(
            timestamp__gte=start_date
        ).values('action_type').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        for action_type in action_types:
            self.stdout.write(
                _('  {}: {}').format(action_type['action_type'], action_type['count'])
            )
    
    def _show_user_statistics(self, start_date):
        """Показывает статистику по пользователям"""
        self.stdout.write(_('\nTop Users (by actions):'))
        
        # Топ пользователей по количеству действий
        top_users = UserAction.objects.filter(
            timestamp__gte=start_date,
            user__isnull=False
        ).values('user__email').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        for user in top_users:
            self.stdout.write(
                _('  {}: {} actions').format(user['user__email'], user['count'])
            )
    
    def _show_security_audit_statistics(self, start_date):
        """Показывает статистику аудита безопасности"""
        self.stdout.write(_('\nSecurity Audit Statistics:'))
        
        # Статистика по типам аудита
        audit_types = SecurityAudit.objects.filter(
            timestamp__gte=start_date
        ).values('audit_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        for audit_type in audit_types:
            self.stdout.write(
                _('  {}: {}').format(audit_type['audit_type'], audit_type['count'])
            )
        
        # Критические операции
        critical_count = SecurityAudit.objects.filter(
            timestamp__gte=start_date,
            is_critical=True
        ).count()
        
        self.stdout.write(_('Critical operations: {}').format(critical_count))
        
        # Статус проверки
        pending_count = SecurityAudit.objects.filter(
            timestamp__gte=start_date,
            review_status='pending'
        ).count()
        
        self.stdout.write(_('Pending reviews: {}').format(pending_count))
    
    def _show_detailed_statistics(self, start_date):
        """Показывает детальную статистику"""
        self.stdout.write(_('\nDetailed Statistics:'))
        
        # Статистика по часам
        self.stdout.write(_('\nHourly Distribution:'))
        hourly_stats = UserAction.objects.filter(
            timestamp__gte=start_date
        ).extra(
            select={'hour': "EXTRACT(hour FROM timestamp)"}
        ).values('hour').annotate(
            count=Count('id')
        ).order_by('hour')
        
        for hour_stat in hourly_stats:
            self.stdout.write(
                _('  Hour {}: {} actions').format(hour_stat['hour'], hour_stat['count'])
            )
        
        # Статистика по IP адресам
        self.stdout.write(_('\nTop IP Addresses:'))
        top_ips = UserAction.objects.filter(
            timestamp__gte=start_date,
            ip_address__isnull=False
        ).values('ip_address').annotate(
            count=Count('id')
        ).order_by('-count')[:5]
        
        for ip_stat in top_ips:
            self.stdout.write(
                _('  {}: {} actions').format(ip_stat['ip_address'], ip_stat['count'])
            )
        
        # Статистика по HTTP методам
        self.stdout.write(_('\nHTTP Methods:'))
        http_methods = UserAction.objects.filter(
            timestamp__gte=start_date,
            http_method__isnull=False
        ).values('http_method').annotate(
            count=Count('id')
        ).order_by('-count')
        
        for method in http_methods:
            self.stdout.write(
                _('  {}: {} requests').format(method['http_method'], method['count'])
            ) 