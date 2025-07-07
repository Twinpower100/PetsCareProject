"""
Команда для массовой валидации адресов.

Использование:
python manage.py validate_addresses [--all] [--invalid-only] [--pending-only] [--limit N]
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from geolocation.models import Address
from geolocation.services import AddressValidationService


class Command(BaseCommand):
    """
    Команда для массовой валидации адресов.
    
    Поддерживает:
    - Валидацию всех адресов
    - Валидацию только невалидных адресов
    - Валидацию только ожидающих адресов
    - Ограничение количества обрабатываемых адресов
    """
    
    help = 'Валидирует адреса через Google Maps API'
    
    def add_arguments(self, parser):
        """
        Добавляет аргументы командной строки.
        
        Args:
            parser: Парсер аргументов
        """
        parser.add_argument(
            '--all',
            action='store_true',
            help='Validate all addresses',
        )
        parser.add_argument(
            '--invalid-only',
            action='store_true',
            help='Validate only invalid addresses',
        )
        parser.add_argument(
            '--pending-only',
            action='store_true',
            help='Validate only pending addresses',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit the number of processed addresses',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
    
    def handle(self, *args, **options):
        """
        Выполняет валидацию адресов.
        
        Args:
            *args: Позиционные аргументы
            **options: Опции командной строки
        """
        # Определяем фильтр для адресов
        queryset = Address.objects.all()
        
        if options['invalid_only']:
            queryset = queryset.filter(validation_status='invalid')
        elif options['pending_only']:
            queryset = queryset.filter(validation_status='pending')
        elif not options['all']:
            # По умолчанию валидируем только невалидные и ожидающие
            queryset = queryset.filter(validation_status__in=['invalid', 'pending'])
        
        # Применяем ограничение
        if options['limit']:
            queryset = queryset[:options['limit']]
        
        total_addresses = queryset.count()
        
        if total_addresses == 0:
            self.stdout.write(
                self.style.WARNING('No addresses to validate')
            )
            return
        
        self.stdout.write(
            f'Found {total_addresses} addresses to validate'
        )
        
        if options['dry_run']:
            self.stdout.write(
                self.style.SUCCESS('Dry-run mode: changes will not be saved')
            )
            return
        
        # Execute validation
        validation_service = AddressValidationService()
        success_count = 0
        error_count = 0
        
        for i, address in enumerate(queryset, 1):
            try:
                self.stdout.write(f'Validating address {i}/{total_addresses}: {address}')
                
                with transaction.atomic():
                    validation_result = validation_service.validate_address(address)
                    
                    if validation_result.is_valid:
                        address.formatted_address = validation_result.formatted_address
                        address.latitude = validation_result.latitude
                        address.longitude = validation_result.longitude
                        address.is_validated = True
                        address.validation_status = 'valid'
                        address.save(update_fields=[
                            'formatted_address', 'latitude', 'longitude',
                            'is_validated', 'validation_status', 'updated_at'
                        ])
                        
                        self.stdout.write(
                            self.style.SUCCESS(f'✓ Address validated: {validation_result.formatted_address}')
                        )
                        success_count += 1
                    else:
                        address.validation_status = 'invalid'
                        address.save(update_fields=['validation_status', 'updated_at'])
                        
                        self.stdout.write(
                            self.style.ERROR(f'✗ Address invalid: {address}')
                        )
                        error_count += 1
                        
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Validation error for address {address}: {e}')
                )
                error_count += 1
        
        # Output final statistics
        self.stdout.write('\n' + '='*50)
        self.stdout.write('VALIDATION RESULTS:')
        self.stdout.write(f'Total processed: {total_addresses}')
        self.stdout.write(f'Successfully validated: {success_count}')
        self.stdout.write(f'Errors: {error_count}')
        self.stdout.write('='*50) 