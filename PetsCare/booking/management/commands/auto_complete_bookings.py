"""
Команда для автоматического завершения "зависших" бронирований.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from booking.services import BookingCompletionService
from django.utils.translation import gettext_lazy as _
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Автоматическое завершение "зависших" бронирований'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help=_('Show which bookings will be completed without executing'),
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Принудительно запустить, даже если автозавершение отключено',
        )

    def handle(self, *args, **options):
        from booking.models import BookingAutoCompleteSettings
        
        settings = BookingAutoCompleteSettings.get_settings()
        
        if not settings.auto_complete_enabled and not options['force']:
            self.stdout.write(
                self.style.WARNING(
                    'Автоматическое завершение отключено в настройках. '
                    'Используйте --force для принудительного запуска.'
                )
            )
            return
        
        if options['dry_run']:
            self.stdout.write('Режим предварительного просмотра:')
            self._show_stale_bookings()
        else:
            self.stdout.write('Запуск автоматического завершения...')
            completed_count = BookingCompletionService.auto_complete_bookings()
            
            if completed_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Автоматически завершено {completed_count} бронирований'
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('Нет "зависших" бронирований для завершения')
                )
    
    def _show_stale_bookings(self):
        """Показать "зависшие" бронирования без их завершения"""
        from booking.models import Booking, BookingAutoCompleteSettings
        from datetime import timedelta
        
        settings = BookingAutoCompleteSettings.get_settings()
        
        # Вычисляем диапазон дат для проверки
        today = timezone.now().date()
        start_date = today - timedelta(days=settings.auto_complete_days)
        end_date = today - timedelta(days=1)  # Вчера включительно
        
        # Находим "зависшие" бронирования
        stale_bookings = Booking.objects.filter(
            status__name='confirmed',
            start_time__date__range=[start_date, end_date],
            completed_at__isnull=True,
            cancelled_at__isnull=True
        ).select_related('user', 'pet', 'provider', 'service')
        
        if stale_bookings.exists():
            self.stdout.write(f'Найдено {stale_bookings.count()} "зависших" бронирований:')
            self.stdout.write('')
            
            for booking in stale_bookings:
                self.stdout.write(
                    f'  - ID: {booking.id}, '
                    f'Клиент: {booking.user.username}, '
                    f'Питомец: {booking.pet.name}, '
                    f'Услуга: {booking.service.name}, '
                    f'Дата: {booking.start_time.date()}, '
                    f'Учреждение: {booking.provider.name}'
                )
        else:
            self.stdout.write('"Зависших" бронирований не найдено') 