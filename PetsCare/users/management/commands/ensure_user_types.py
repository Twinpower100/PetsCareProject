"""
Проверка и заполнение UserType по справочнику ROLE_PERMISSION_SETS.

Режимы:
  --check  — только показать текущие типы и их права (без изменений).
  без флагов — создать/обновить типы по permissions.ROLE_PERMISSION_SETS.

Использование:
  python manage.py ensure_user_types --check
  python manage.py ensure_user_types
"""

from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _
from users.models import UserType
from users.permissions import ROLE_PERMISSION_SETS, get_role_permissions


# Локализованные названия для ролей (опционально)
ROLE_DISPLAY_NAMES = {
    'basic_user': {'en': 'Basic user', 'ru': 'Базовый пользователь', 'de': 'Basisbenutzer', 'me': 'Osnovni korisnik'},
    'system_admin': {'en': 'System administrator', 'ru': 'Администратор системы', 'de': 'Systemadministrator', 'me': 'Sistemski administrator'},
    'owner': {'en': 'Owner', 'ru': 'Владелец провайдера', 'de': 'Inhaber', 'me': 'Vlasnik pružaoca'},
    'provider_admin': {'en': 'Provider administrator', 'ru': 'Админ провайдера', 'de': 'Anbieter-Administrator', 'me': 'Administrator pružaoca'},
    'provider_manager': {'en': 'Provider manager', 'ru': 'Менеджер провайдера', 'de': 'Anbieter-Manager', 'me': 'Menadžer pružaoca'},
    'branch_manager': {'en': 'Branch manager', 'ru': 'Руководитель филиала', 'de': 'Filialleiter', 'me': 'Menadžer filijale'},
    'specialist': {'en': 'Specialist', 'ru': 'Специалист (сервис/техработник)', 'de': 'Spezialist', 'me': 'Stručnjak'},
    'billing_manager': {'en': 'Billing manager', 'ru': 'Менеджер по биллингу', 'de': 'Abrechnungsmanager', 'me': 'Menadžer naplate'},
    'booking_manager': {'en': 'Booking manager', 'ru': 'Менеджер бронирований', 'de': 'Buchungsmanager', 'me': 'Menadžer rezervacija'},
    'employee': {'en': 'Employee', 'ru': 'Сотрудник', 'de': 'Mitarbeiter', 'me': 'Zaposleni'},
    'pet_owner': {'en': 'Pet owner', 'ru': 'Владелец питомца', 'de': 'Haustierbesitzer', 'me': 'Vlasnik ljubimca'},
    'pet_sitter': {'en': 'Pet sitter', 'ru': 'Передержка', 'de': 'Tiersitter', 'me': 'Čuvanje ljubimaca'},
}


class Command(BaseCommand):
    help = 'Show current user types and their permissions (--check) or ensure all roles from ROLE_PERMISSION_SETS exist.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check',
            action='store_true',
            help='Only list existing user types and their permissions; do not create or update.',
        )

    def handle(self, *args, **options):
        if options['check']:
            self._show_current()
        else:
            self._ensure_user_types()

    def _show_current(self):
        """Вывести текущие UserType и их права доступа."""
        self.stdout.write(self.style.MIGRATE_HEADING('Current UserType records and permissions'))
        self.stdout.write('')
        qs = UserType.objects.all().order_by('name')
        if not qs.exists():
            self.stdout.write(self.style.WARNING('No UserType records found.'))
            return
        for ut in qs:
            self.stdout.write(self.style.HTTP_INFO(f'  [{ut.name}] active={ut.is_active}'))
            self.stdout.write(f'    name_en={ut.name_en or "(empty)"} name_ru={ut.name_ru or "(empty)"}')
            self.stdout.write(f'    description: {(ut.description or "")[:80]}...' if ut.description and len(ut.description or '') > 80 else f'    description: {ut.description or "(empty)"}')
            perms = ut.permissions or []
            if perms:
                # Совпадение: сначала проверяем роль с тем же name, иначе любой ключ из справочника
                matched = None
                if ut.name in ROLE_PERMISSION_SETS and set(get_role_permissions(ut.name)) == set(perms):
                    matched = ut.name
                else:
                    for key in ROLE_PERMISSION_SETS:
                        if set(get_role_permissions(key)) == set(perms):
                            matched = key
                            break
                if matched:
                    self.stdout.write(self.style.SUCCESS(f'    permissions: SET:{matched} ({len(perms)} permissions)'))
                else:
                    self.stdout.write(f'    permissions: {len(perms)} items (custom)')
                    for p in perms[:10]:
                        self.stdout.write(f'      - {p}')
                    if len(perms) > 10:
                        self.stdout.write(f'      ... and {len(perms) - 10} more')
            else:
                self.stdout.write(self.style.WARNING('    permissions: (empty)'))
            self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Reference: ROLE_PERMISSION_SETS keys'))
        self.stdout.write('  ' + ', '.join(ROLE_PERMISSION_SETS.keys()))

    def _ensure_user_types(self):
        """Создать или обновить UserType для каждого ключа из ROLE_PERMISSION_SETS."""
        self.stdout.write(self.style.MIGRATE_HEADING('Ensuring user types from ROLE_PERMISSION_SETS'))
        created = 0
        updated = 0
        for role_key, role_data in ROLE_PERMISSION_SETS.items():
            names = ROLE_DISPLAY_NAMES.get(role_key, {})
            name_en = names.get('en') or (str(role_data.get('name', '')) if role_data.get('name') else role_key)
            ut, was_created = UserType.objects.get_or_create(
                name=role_key,
                defaults={
                    'name_en': name_en or role_key,
                    'name_ru': names.get('ru', ''),
                    'name_de': names.get('de', ''),
                    'name_me': names.get('me', ''),
                    'description': role_data.get('description', ''),
                    'permissions': [f'SET:{role_key}'],
                    'is_active': True,
                },
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'  Created: {role_key}'))
            else:
                # Обновить права и названия, если изменились
                need_save = False
                if (ut.permissions or []) != [f'SET:{role_key}']:
                    ut.permissions = [f'SET:{role_key}']
                    need_save = True
                if ut.name_en != (name_en or role_key):
                    ut.name_en = name_en or role_key
                    need_save = True
                if names.get('ru') and ut.name_ru != names['ru']:
                    ut.name_ru = names['ru']
                    need_save = True
                if names.get('de') and ut.name_de != names['de']:
                    ut.name_de = names['de']
                    need_save = True
                if names.get('me') and ut.name_me != names['me']:
                    ut.name_me = names['me']
                    need_save = True
                if role_data.get('description') and ut.description != role_data['description']:
                    ut.description = role_data['description']
                    need_save = True
                if need_save:
                    ut.save()
                    updated += 1
                    self.stdout.write(self.style.WARNING(f'  Updated: {role_key}'))
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Done. Created: {created}, Updated: {updated}.'))
