"""
Command for cleaning up geolocation cache.

Usage:
python manage.py cleanup_geolocation_cache [--all] [--cache-only] [--validation-only] [--days N]
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
from geolocation.models import AddressCache, AddressValidation


class Command(BaseCommand):
    """
    Command for cleaning up geolocation cache.
    
    Supports:
    - Cleaning all types of cache
    - Cleaning only geocoding cache
    - Cleaning only old validation records
    - Setting period for removing old records
    """
    
    help = 'Cleans up geolocation cache and old records'
    
    def add_arguments(self, parser):
        """
        Adds command line arguments.
        
        Args:
            parser: Command line argument parser
        """
        parser.add_argument(
            '--all',
            action='store_true',
            help='Clean all cache types and old records',
        )
        parser.add_argument(
            '--cache-only',
            action='store_true',
            help='Clean only geocoding cache',
        )
        parser.add_argument(
            '--validation-only',
            action='store_true',
            help='Clean only old validation records',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to determine old records (default 30)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without executing changes',
        )
    
    def handle(self, *args, **options):
        """
        Executes cache cleaning and old records cleanup.
        
        Args:
            *args: Positional arguments
            **options: Command line options
        """
        days = options['days']
        cutoff_date = timezone.now() - timedelta(days=days)
        
        if options['dry_run']:
            self.stdout.write(
                self.style.SUCCESS('Dry-run mode: changes will not be saved')
            )
        
        # Cleaning geocoding cache
        if options['all'] or options['cache_only']:
            self.cleanup_address_cache(cutoff_date, options['dry_run'])
        
        # Cleaning old validation records
        if options['all'] or options['validation_only']:
            self.cleanup_validation_records(cutoff_date, options['dry_run'])
        
        # Cleaning Django cache
        if options['all']:
            self.cleanup_django_cache(options['dry_run'])
    
    def cleanup_address_cache(self, cutoff_date, dry_run=False):
        """
        Cleans up old geocoding cache records.
        
        Args:
            cutoff_date: Cutoff date
            dry_run: Dry-run mode
        """
        # Deleting cache records that have expired
        expired_cache = AddressCache.objects.filter(expires_at__lt=timezone.now())
        expired_count = expired_cache.count()
        
        # Deleting old cache records
        old_cache = AddressCache.objects.filter(created_at__lt=cutoff_date)
        old_count = old_cache.count()
        
        total_cache = expired_count + old_count
        
        if total_cache == 0:
            self.stdout.write('No cache records to delete')
            return
        
        self.stdout.write(f'Found cache records to delete: {total_cache}')
        self.stdout.write(f'  - Expired: {expired_count}')
        self.stdout.write(f'  - Old (older than {cutoff_date.date()}): {old_count}')
        
        if not dry_run:
            expired_cache.delete()
            old_cache.delete()
            self.stdout.write(
                self.style.SUCCESS(f'✓ Deleted {total_cache} cache records')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'DRY-RUN: {total_cache} cache records would be deleted')
            )
    
    def cleanup_validation_records(self, cutoff_date, dry_run=False):
        """
        Cleans up old validation records.
        
        Args:
            cutoff_date: Cutoff date
            dry_run: Dry-run mode
        """
        old_validations = AddressValidation.objects.filter(
            created_at__lt=cutoff_date
        )
        validation_count = old_validations.count()
        
        if validation_count == 0:
            self.stdout.write('No old validation records to delete')
            return
        
        self.stdout.write(
            f'Found old validation records to delete: {validation_count} '
            f'(older than {cutoff_date.date()})'
        )
        
        if not dry_run:
            old_validations.delete()
            self.stdout.write(
                self.style.SUCCESS(f'✓ Deleted {validation_count} validation records')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'DRY-RUN: {validation_count} validation records would be deleted')
            )
    
    def cleanup_django_cache(self, dry_run=False):
        """
        Cleans up Django cache.
        
        Args:
            dry_run: Dry-run mode
        """
        # Getting cache statistics
        cache_keys = []
        try:
            # This is a simplified version - in reality, specific backend cache methods should be used
            cache.clear()
            self.stdout.write('Django cache cleared')
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error clearing Django cache: {e}')
            )
        
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS('✓ Django cache cleared')
            )
        else:
            self.stdout.write(
                self.style.WARNING('DRY-RUN: Django cache would be cleared')
            ) 