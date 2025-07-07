from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.utils.translation import gettext as _
from datetime import timedelta

from audit.models import UserAction, SecurityAudit, AuditSettings


class Command(BaseCommand):
    """
    Команда для очистки старых логов и записей аудита.
    
    Удаляет записи, которые превышают срок хранения,
    установленный в настройках аудита.
    """
    
    help = _('Cleans up old logs and audit records according to retention settings')
    
    def add_arguments(self, parser):
        """Добавляет аргументы командной строки"""
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help=_('Show what will be deleted without actually deleting')
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help=_('Force cleanup without confirmation')
        )
    
    def handle(self, *args, **options):
        """Основной метод выполнения команды"""
        # Получаем настройки аудита
        settings = AuditSettings.get_settings()
        
        if not settings.auto_cleanup_enabled:
            self.stdout.write(
                self.style.WARNING(_('Automatic cleanup is disabled in settings'))
            )
            return
        
        # Вычисляем даты для очистки
        log_retention_date = timezone.now() - timedelta(days=settings.log_retention_days)
        audit_retention_date = timezone.now() - timedelta(days=settings.security_audit_retention_days)
        
        # Получаем количество записей для удаления
        old_logs_count = UserAction.objects.filter(
            timestamp__lt=log_retention_date
        ).count()
        
        old_audits_count = SecurityAudit.objects.filter(
            timestamp__lt=audit_retention_date
        ).count()
        
        if old_logs_count == 0 and old_audits_count == 0:
            self.stdout.write(
                self.style.SUCCESS(_('No old records to clean up'))
            )
            return
        
        # Показываем статистику
        self.stdout.write(_('Found records to delete:'))
        self.stdout.write(_('  - User actions: {}').format(old_logs_count))
        self.stdout.write(_('  - Security audits: {}').format(old_audits_count))
        self.stdout.write(_('Log cutoff date: {}').format(log_retention_date))
        self.stdout.write(_('Audit cutoff date: {}').format(audit_retention_date))
        
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING(_('Dry-run mode: records will not be deleted'))
            )
            return
        
        # Запрашиваем подтверждение
        if not options['force']:
            confirm = input(_('Continue deletion? (y/N): '))
            if confirm.lower() != 'y':
                self.stdout.write(_('Operation cancelled'))
                return
        
        # Выполняем очистку в транзакции
        with transaction.atomic():
            # Удаляем старые логи
            if old_logs_count > 0:
                deleted_logs = UserAction.objects.filter(
                    timestamp__lt=log_retention_date
                ).delete()
                self.stdout.write(
                    self.style.SUCCESS(_('Deleted logs: {}').format(deleted_logs[0]))
                )
            
            # Удаляем старые записи аудита
            if old_audits_count > 0:
                deleted_audits = SecurityAudit.objects.filter(
                    timestamp__lt=audit_retention_date
                ).delete()
                self.stdout.write(
                    self.style.SUCCESS(_('Deleted audit records: {}').format(deleted_audits[0]))
                )
        
        self.stdout.write(
            self.style.SUCCESS(_('Cleanup completed successfully'))
        ) 