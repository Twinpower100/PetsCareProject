"""
Команда для обновления иерархического порядка всех услуг.

Эта команда:
1. Обновляет поле hierarchy_order для всех существующих услуг
2. Пересчитывает правильный иерархический порядок
3. Сохраняет изменения в базе данных
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from catalog.models import Service


class Command(BaseCommand):
    help = _('Updates hierarchical order for all services')

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help=_('Show what will be changed without saving'),
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(_('Dry-run mode: changes will not be saved'))
            )
        
        # Получаем все услуги
        services = Service.objects.all().order_by('id')
        
        if not services.exists():
            self.stdout.write(
                self.style.WARNING(_('No services to update'))
            )
            return
        
        updated_count = 0
        
        with transaction.atomic():
            for service in services:
                old_order = service.hierarchy_order
                new_order = service.calculate_hierarchy_order()
                
                if old_order != new_order:
                    if dry_run:
                        self.stdout.write(
                            f'{_("Will be updated")}: {service.name} ({old_order} -> {new_order})'
                        )
                    else:
                        service.hierarchy_order = new_order
                        service.save(update_fields=['hierarchy_order'])
                        self.stdout.write(
                            f'{_("Updated")}: {service.name} ({old_order} -> {new_order})'
                        )
                    updated_count += 1
                else:
                    self.stdout.write(
                        f'{_("No changes")}: {service.name} ({old_order})'
                    )
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(_('Will be updated {} records').format(updated_count))
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(_('Updated {} records').format(updated_count))
            )
        
        # Показываем итоговую иерархию
        self.stdout.write(f'\n{_("Current hierarchy")}:')
        self.show_hierarchy()

    def show_hierarchy(self):
        """Shows current services hierarchy."""
        services = Service.objects.all().order_by('hierarchy_order', 'name')
        
        for service in services:
            indent = "  " * service.level
            icon = "📁" if service.level == 0 else "📂" if service.children.exists() else "📄"
            self.stdout.write(
                f'{indent}{icon} {service.name} ({_("order")}: {service.hierarchy_order})'
            )
