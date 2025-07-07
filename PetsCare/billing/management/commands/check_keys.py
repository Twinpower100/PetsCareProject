from django.core.management.base import BaseCommand
from django.conf import settings
import requests
import logging
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """
    Проверяет доступность и валидность внешних API ключей
    """
    help = 'Check availability and validity of external API keys'

    def handle(self, *args, **options):
        self.stdout.write('Checking external API keys...')
        
        # Проверка Google Maps API
        try:
            if hasattr(settings, 'GOOGLE_MAPS_API_KEY'):
                response = requests.get(
                    f'https://maps.googleapis.com/maps/api/geocode/json?address=test&key={settings.GOOGLE_MAPS_API_KEY}'
                )
                if response.status_code == 200:
                    self.stdout.write(self.style.SUCCESS('✓ Google Maps API key is valid'))
                else:
                    self.stdout.write(self.style.ERROR('✗ Google Maps API key is invalid'))
            else:
                self.stdout.write(self.style.WARNING('⚠ Google Maps API key not found in settings'))
        except Exception as e:
            logger.error(f'Error checking Google Maps API: {str(e)}')
            self.stdout.write(self.style.ERROR('✗ Error checking Google Maps API'))

        self.stdout.write(self.style.SUCCESS('Key check completed')) 