"""
Management команда для управления расписанием проверки блокировок учреждений.

Команды:
- show: Показать текущие настройки расписания
- reset: Сбросить настройки к значениям по умолчанию
- update: Обновить расписание в Celery Beat
- next-run: Показать время следующего запуска
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import logging

from settings.services import BlockingScheduleService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = _('Manage blocking schedule settings')
    
    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['show', 'reset', 'update', 'next-run'],
            help=_('Action to perform')
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help=_('Force action without confirmation')
        )
    
    def handle(self, *args, **options):
        action = options['action']
        force = options['force']
        
        service = BlockingScheduleService()
        
        if action == 'show':
            self.show_schedule(service)
        elif action == 'reset':
            self.reset_schedule(service, force)
        elif action == 'update':
            self.update_schedule(service)
        elif action == 'next-run':
            self.show_next_run(service)
    
    def show_schedule(self, service):
        """Показать текущие настройки расписания."""
        try:
            settings = service.get_current_schedule()
            info = service.get_schedule_info()
            
            self.stdout.write(
                self.style.SUCCESS(_('Current Blocking Schedule Settings:'))
            )
            self.stdout.write(f"  {_('Frequency')}: {info['frequency_display']}")
            self.stdout.write(f"  {_('Check Time')}: {info['check_time']}")
            self.stdout.write(f"  {_('Description')}: {info['schedule_description']}")
            self.stdout.write(f"  {_('Status')}: {'Active' if info['is_active'] else 'Inactive'}")
            self.stdout.write(f"  {_('Last Updated')}: {info['last_updated']}")
            self.stdout.write(f"  {_('Updated By')}: {info['updated_by'] or 'System'}")
            self.stdout.write(f"  {_('Celery Schedule')}: {info['celery_schedule']}")
            
        except Exception as e:
            raise CommandError(f"Failed to show schedule: {e}")
    
    def reset_schedule(self, service, force):
        """Сбросить настройки к значениям по умолчанию."""
        if not force:
            confirm = input(_('Are you sure you want to reset schedule settings to defaults? (y/N): '))
            if confirm.lower() != 'y':
                self.stdout.write(_('Operation cancelled.'))
                return
        
        try:
            success = service.reset_to_defaults()
            
            if success:
                self.stdout.write(
                    self.style.SUCCESS(_('Schedule settings reset to defaults successfully.'))
                )
                self.show_schedule(service)
            else:
                raise CommandError(_('Failed to reset schedule settings.'))
                
        except Exception as e:
            raise CommandError(f"Failed to reset schedule: {e}")
    
    def update_schedule(self, service):
        """Обновить расписание в Celery Beat."""
        try:
            success = service.update_celery_schedule()
            
            if success:
                self.stdout.write(
                    self.style.SUCCESS(_('Celery schedule updated successfully.'))
                )
            else:
                raise CommandError(_('Failed to update Celery schedule.'))
                
        except Exception as e:
            raise CommandError(f"Failed to update schedule: {e}")
    
    def show_next_run(self, service):
        """Показать время следующего запуска."""
        try:
            next_run = service.get_next_run_time()
            now = timezone.now()
            
            self.stdout.write(
                self.style.SUCCESS(_('Next Run Information:'))
            )
            self.stdout.write(f"  {_('Current Time')}: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            self.stdout.write(f"  {_('Next Run')}: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Вычисляем разницу
            time_diff = next_run - now
            hours = int(time_diff.total_seconds() // 3600)
            minutes = int((time_diff.total_seconds() % 3600) // 60)
            
            if hours > 0:
                self.stdout.write(f"  {_('Time Until Next Run')}: {hours}h {minutes}m")
            else:
                self.stdout.write(f"  {_('Time Until Next Run')}: {minutes}m")
                
        except Exception as e:
            raise CommandError(f"Failed to show next run: {e}") 