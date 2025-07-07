"""
Команда Django для пересчета рейтингов.

Использование:
python manage.py recalculate_ratings
"""

from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from ratings.services import RatingCalculationService
from ratings.models import Rating
from providers.models import Provider, Employee
from sitters.models import SitterProfile


class Command(BaseCommand):
    """
    Команда для пересчета рейтингов.
    """
    help = _('Recalculate ratings for all objects')
    
    def add_arguments(self, parser):
        """
        Добавляет аргументы командной строки.
        """
        parser.add_argument(
            '--type',
            type=str,
            choices=['provider', 'employee', 'sitter', 'all'],
            default='all',
            help=_('Type of objects to recalculate ratings for')
        )
        parser.add_argument(
            '--object-id',
            type=int,
            help=_('Specific object ID to recalculate (optional)')
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help=_('Run without saving changes')
        )
    
    def handle(self, *args, **options):
        """
        Выполняет команду.
        """
        self.stdout.write(_('Starting rating recalculation...'))
        
        # Создаем сервис для расчета рейтингов
        rating_service = RatingCalculationService()
        
        # Определяем типы объектов для пересчета
        object_types = []
        if options['type'] == 'all' or options['type'] == 'provider':
            object_types.append(('provider', Provider))
        if options['type'] == 'all' or options['type'] == 'employee':
            object_types.append(('employee', Employee))
        if options['type'] == 'all' or options['type'] == 'sitter':
            object_types.append(('sitter', SitterProfile))
        
        total_processed = 0
        total_updated = 0
        
        for type_name, model_class in object_types:
            self.stdout.write(_('Processing {type}s...').format(type=type_name))
            
            # Получаем объекты для пересчета
            if options['object_id']:
                objects = model_class.objects.filter(id=options['object_id'])
            else:
                objects = model_class.objects.all()
            
            for obj in objects:
                try:
                    # Получаем или создаем рейтинг
                    content_type = ContentType.objects.get_for_model(model_class)
                    rating, created = Rating.objects.get_or_create(
                        content_type=content_type,
                        object_id=obj.id
                    )
                    
                    # Сохраняем старый рейтинг
                    old_rating = rating.current_rating
                    
                    # Рассчитываем новый рейтинг
                    new_rating = rating_service.calculate_rating(obj)
                    
                    if options['dry_run']:
                        self.stdout.write(
                            _('[DRY RUN] {type} {id}: {old} → {new}').format(
                                type=type_name, id=obj.id, old=old_rating, new=new_rating
                            )
                        )
                    else:
                        # Обновляем рейтинг
                        rating.current_rating = new_rating
                        rating.last_calculated_at = timezone.now()
                        rating.save()
                        
                        self.stdout.write(
                            _('{type} {id}: {old} → {new}').format(
                                type=type_name, id=obj.id, old=old_rating, new=new_rating
                            )
                        )
                    
                    total_processed += 1
                    if old_rating != new_rating:
                        total_updated += 1
                
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            _('Error processing {type} {id}: {error}').format(
                                type=type_name, id=obj.id, error=e
                            )
                        )
                    )
        
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING(
                    _('[DRY RUN] Processed {processed} objects, would update {updated} ratings').format(
                        processed=total_processed, updated=total_updated
                    )
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    _('Recalculation completed. Processed {processed} objects, updated {updated} ratings.').format(
                        processed=total_processed, updated=total_updated
                    )
                )
            ) 