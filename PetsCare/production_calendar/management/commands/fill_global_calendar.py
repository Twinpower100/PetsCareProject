"""
Команда заполнения глобального производственного календаря на год.

Записей с is_manually_corrected=True не перезаписываем.
"""
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction

from production_calendar.models import ProductionCalendar
from production_calendar.calendar_provider import CalendarProvider, SUPPORTED_COUNTRIES as PROVIDER_COUNTRIES


def iter_dates_for_year(year: int):
    """Генератор всех дат года."""
    from datetime import timedelta
    d = date(year, 1, 1)
    end = date(year, 12, 31)
    while d <= end:
        yield d
        d += timedelta(days=1)


class Command(BaseCommand):
    help = 'Fill global production calendar for a year. Skips records with is_manually_corrected=True.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            required=True,
            help='Year to fill (e.g. 2026).',
        )
        parser.add_argument(
            '--country',
            type=str,
            default=None,
            help='Optional: fill only this country (ISO 3166-1 alpha-2).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Do not write to DB, only report what would be done.',
        )

    def handle(self, *args, **options):
        year = options['year']
        country_filter = (options['country'] or '').upper()[:2]
        dry_run = options['dry_run']

        if year < 2000 or year > 2100:
            self.stderr.write(self.style.ERROR('Year must be between 2000 and 2100.'))
            return

        countries = [c for c in PROVIDER_COUNTRIES if not country_filter or c == country_filter]
        if not countries:
            self.stderr.write(self.style.ERROR(f'No supported country for filter: {country_filter or "all"}'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run — no changes will be saved.'))

        created = 0
        updated = 0
        skipped = 0

        with transaction.atomic():
            for d in iter_dates_for_year(year):
                for country in countries:
                    existing = ProductionCalendar.objects.filter(
                        date=d,
                        country=country,
                    ).first()
                    if existing and existing.is_manually_corrected:
                        skipped += 1
                        continue
                    info = CalendarProvider.get_day_info(country, d)
                    if not dry_run:
                        obj, was_created = ProductionCalendar.objects.update_or_create(
                            date=d,
                            country=country,
                            defaults={
                                'day_type': info['day_type'],
                                'description': (info.get('description') or '')[:255],
                                'is_transfer': info.get('is_transfer', False),
                            },
                        )
                        if was_created:
                            created += 1
                        else:
                            updated += 1
                    else:
                        if existing:
                            updated += 1
                        else:
                            created += 1

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                f'Year {year}: created={created}, updated={updated}, skipped (manual)={skipped}'
            )
        )
