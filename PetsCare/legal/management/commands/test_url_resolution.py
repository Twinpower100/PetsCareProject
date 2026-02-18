"""
Management command для проверки разрешения URL
"""
from django.core.management.base import BaseCommand
from django.urls import resolve
from django.urls.exceptions import Resolver404


class Command(BaseCommand):
    help = 'Test URL resolution for legal API'

    def handle(self, *args, **options):
        urls_to_test = [
            '/api/v1/legal/documents/terms_of_service/',
            '/api/v1/legal/documents/privacy_policy/',
            '/api/v1/legal/documents/global_offer/',
        ]

        self.stdout.write("Testing URL resolution:")
        self.stdout.write("=" * 80)

        for url in urls_to_test:
            try:
                match = resolve(url)
                self.stdout.write(self.style.SUCCESS(f"✓ {url}"))
                self.stdout.write(f"  -> url_name: {match.url_name}")
                self.stdout.write(f"  -> namespace: {match.namespace}")
                self.stdout.write(f"  -> view: {match.func.__module__}.{match.func.__name__}")
                self.stdout.write("")
            except Resolver404 as e:
                self.stdout.write(self.style.ERROR(f"✗ {url}"))
                self.stdout.write(f"  -> 404: {e}")
                self.stdout.write("")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"✗ {url}"))
                self.stdout.write(f"  -> Error: {type(e).__name__}: {e}")
                self.stdout.write("")
