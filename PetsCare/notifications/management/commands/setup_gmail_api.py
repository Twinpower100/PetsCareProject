"""
Команда управления для настройки Gmail API.

Эта команда помогает настроить Gmail API с OAuth2 аутентификацией
для отправки email через Gmail API вместо SMTP.
"""

import os
import json
import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Команда для настройки Gmail API.
    
    Эта команда:
    1. Проверяет наличие необходимых файлов
    2. Тестирует подключение к Gmail API
    3. Помогает настроить OAuth2 аутентификацию
    """
    
    help = _('Setup Gmail API for email sending')
    
    def add_arguments(self, parser):
        """Добавление аргументов команды."""
        parser.add_argument(
            '--test',
            action='store_true',
            help=_('Test Gmail API connection')
        )
        parser.add_argument(
            '--check-files',
            action='store_true',
            help=_('Check if required files exist')
        )
        parser.add_argument(
            '--create-credentials-template',
            action='store_true',
            help=_('Create credentials.json template')
        )
    
    def handle(self, *args, **options):
        """Обработка команды."""
        if options['test']:
            self.test_connection()
        elif options['check_files']:
            self.check_files()
        elif options['create_credentials_template']:
            self.create_credentials_template()
        else:
            self.setup_gmail_api()
    
    def setup_gmail_api(self):
        """Основная настройка Gmail API."""
        self.stdout.write(
            self.style.SUCCESS(_('Setting up Gmail API for email sending...'))
        )
        
        # Проверяем файлы
        self.check_files()
        
        # Тестируем подключение
        if self.test_connection():
            self.stdout.write(
                self.style.SUCCESS(_('Gmail API setup completed successfully!'))
            )
        else:
            self.stdout.write(
                self.style.ERROR(_('Gmail API setup failed. Please check the configuration.'))
            )
    
    def check_files(self):
        """Проверка наличия необходимых файлов."""
        self.stdout.write(_('Checking required files...'))
        
        # Проверяем файл с учетными данными
        credentials_file = getattr(settings, 'GMAIL_CREDENTIALS_FILE', 'credentials.json')
        if os.path.exists(credentials_file):
            self.stdout.write(
                self.style.SUCCESS(f'✓ Credentials file found: {credentials_file}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'✗ Credentials file not found: {credentials_file}')
            )
            self.stdout.write(
                self.style.WARNING(_('Please download credentials.json from Google Cloud Console'))
            )
        
        # Проверяем файл с токеном
        token_file = getattr(settings, 'GMAIL_TOKEN_FILE', 'token.json')
        if os.path.exists(token_file):
            self.stdout.write(
                self.style.SUCCESS(f'✓ Token file found: {token_file}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'✗ Token file not found: {token_file}')
            )
            self.stdout.write(
                self.style.WARNING(_('Token file will be created automatically on first use'))
            )
        
        # Проверяем настройки
        self.stdout.write(_('Checking settings...'))
        
        use_gmail_api = getattr(settings, 'USE_GMAIL_API', True)
        self.stdout.write(
            self.style.SUCCESS(f'✓ USE_GMAIL_API: {use_gmail_api}')
        )
        
        fallback_to_smtp = getattr(settings, 'GMAIL_API_FALLBACK_TO_SMTP', True)
        self.stdout.write(
            self.style.SUCCESS(f'✓ GMAIL_API_FALLBACK_TO_SMTP: {fallback_to_smtp}')
        )
        
        email_backend = getattr(settings, 'EMAIL_BACKEND', '')
        self.stdout.write(
            self.style.SUCCESS(f'✓ EMAIL_BACKEND: {email_backend}')
        )
    
    def test_connection(self):
        """Тестирование подключения к Gmail API."""
        self.stdout.write(_('Testing Gmail API connection...'))
        
        try:
            from notifications.gmail_api_service import get_gmail_service
            
            service = get_gmail_service()
            if not service:
                self.stdout.write(
                    self.style.ERROR(_('✗ Gmail API service not available'))
                )
                return False
            
            if service.test_connection():
                self.stdout.write(
                    self.style.SUCCESS(_('✓ Gmail API connection test successful'))
                )
                return True
            else:
                self.stdout.write(
                    self.style.ERROR(_('✗ Gmail API connection test failed'))
                )
                return False
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'✗ Error testing Gmail API connection: {str(e)}')
            )
            return False
    
    def create_credentials_template(self):
        """Создание шаблона файла credentials.json."""
        self.stdout.write(_('Creating credentials.json template...'))
        
        template = {
            "installed": {
                "client_id": "your-client-id.apps.googleusercontent.com",
                "project_id": "your-project-id",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": "your-client-secret",
                "redirect_uris": ["http://localhost"]
            }
        }
        
        credentials_file = getattr(settings, 'GMAIL_CREDENTIALS_FILE', 'credentials.json')
        
        if os.path.exists(credentials_file):
            self.stdout.write(
                self.style.WARNING(f'File {credentials_file} already exists. Skipping...')
            )
        else:
            try:
                with open(credentials_file, 'w') as f:
                    json.dump(template, f, indent=2)
                
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created {credentials_file} template')
                )
                self.stdout.write(
                    self.style.WARNING(_('Please replace placeholder values with your actual Google Cloud credentials'))
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Error creating template: {str(e)}')
                )
    
    def print_setup_instructions(self):
        """Вывод инструкций по настройке."""
        self.stdout.write(_('\nGmail API Setup Instructions:'))
        self.stdout.write(_('1. Go to Google Cloud Console: https://console.cloud.google.com/'))
        self.stdout.write(_('2. Create a new project or select existing one'))
        self.stdout.write(_('3. Enable Gmail API'))
        self.stdout.write(_('4. Create OAuth 2.0 credentials'))
        self.stdout.write(_('5. Download credentials.json'))
        self.stdout.write(_('6. Place credentials.json in your project root'))
        self.stdout.write(_('7. Run: python manage.py setup_gmail_api --test'))
        self.stdout.write(_('\nFor detailed instructions, see: https://developers.google.com/gmail/api/quickstart/python')) 