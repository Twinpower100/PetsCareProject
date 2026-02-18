"""
Management команда для проверки всех типов документов и их настроек.

Использование:
    python manage.py check_all_document_types
"""

from django.core.management.base import BaseCommand
from legal.models import LegalDocumentType


class Command(BaseCommand):
    help = 'Проверяет все типы документов и их настройки'

    def handle(self, *args, **options):
        # Ожидаемые типы документов и их правильные настройки
        EXPECTED_TYPES = {
            'global_offer': {
                'name': 'Global Offer',
                'requires_billing_config': True,
                'requires_region_code': False,
                'requires_addendum_type': False,
                'allows_variables': True,
                'is_required_for_all_countries': True,
                'is_multiple_allowed': False,
                'requires_provider': False,
                'allows_financial_terms': False,
            },
            'regional_addendum': {
                'name': 'Regional Addendum',
                'requires_billing_config': False,
                'requires_region_code': True,
                'requires_addendum_type': True,
                'allows_variables': True,
                'is_required_for_all_countries': False,
                'is_multiple_allowed': True,
                'requires_provider': False,
                'allows_financial_terms': False,
            },
            'privacy_policy': {
                'name': 'Privacy Policy',
                'requires_billing_config': False,
                'requires_region_code': False,
                'requires_addendum_type': False,
                'allows_variables': False,
                'is_required_for_all_countries': True,
                'is_multiple_allowed': False,
                'requires_provider': False,
                'allows_financial_terms': False,
            },
            'terms_of_service': {
                'name': 'Terms of Service',
                'requires_billing_config': False,
                'requires_region_code': False,
                'requires_addendum_type': False,
                'allows_variables': False,
                'is_required_for_all_countries': True,
                'is_multiple_allowed': False,
                'requires_provider': False,
                'allows_financial_terms': False,
            },
            'cookie_policy': {
                'name': 'Cookie Policy',
                'requires_billing_config': False,
                'requires_region_code': False,
                'requires_addendum_type': False,
                'allows_variables': False,
                'is_required_for_all_countries': True,
                'is_multiple_allowed': False,
                'requires_provider': False,
                'allows_financial_terms': False,
            },
            'side_letter': {
                'name': 'Side Letter',
                'requires_billing_config': False,
                'requires_region_code': False,
                'requires_addendum_type': False,
                'allows_variables': True,
                'is_required_for_all_countries': False,
                'is_multiple_allowed': True,
                'requires_provider': True,
                'allows_financial_terms': True,
            },
        }

        self.stdout.write(self.style.SUCCESS('\n=== Проверка типов документов ===\n'))

        # Получаем все существующие типы
        existing_types = {dt.code: dt for dt in LegalDocumentType.objects.all()}

        # Проверяем каждый ожидаемый тип
        errors = []
        warnings = []
        correct = []

        for code, expected in EXPECTED_TYPES.items():
            self.stdout.write(f'\n--- {code.upper()} ({expected["name"]}) ---')
            
            if code not in existing_types:
                errors.append(f'❌ Тип {code} НЕ НАЙДЕН в базе данных!')
                self.stdout.write(self.style.ERROR(f'  ❌ Тип {code} не найден'))
                continue

            dt = existing_types[code]
            issues = []

            # Проверяем каждое поле
            checks = [
                ('requires_billing_config', expected['requires_billing_config']),
                ('requires_region_code', expected['requires_region_code']),
                ('requires_addendum_type', expected['requires_addendum_type']),
                ('allows_variables', expected['allows_variables']),
                ('is_required_for_all_countries', expected['is_required_for_all_countries']),
                ('is_multiple_allowed', expected['is_multiple_allowed']),
                ('requires_provider', expected['requires_provider']),
                ('allows_financial_terms', expected['allows_financial_terms']),
            ]

            for field, expected_value in checks:
                actual_value = getattr(dt, field)
                if actual_value != expected_value:
                    issues.append(f'  ❌ {field}: ожидается {expected_value}, фактически {actual_value}')
                else:
                    self.stdout.write(f'  ✅ {field}: {actual_value}')

            if issues:
                errors.extend([f'❌ {code}: {issue}' for issue in issues])
                for issue in issues:
                    self.stdout.write(self.style.ERROR(issue))
            else:
                correct.append(code)
                self.stdout.write(self.style.SUCCESS(f'  ✅ Все настройки корректны'))

            # Проверяем дополнительные поля
            if not dt.is_active:
                warnings.append(f'⚠️ {code}: is_active = False (тип неактивен)')
                self.stdout.write(self.style.WARNING(f'  ⚠️ is_active = False'))

        # Проверяем неожиданные типы
        unexpected = set(existing_types.keys()) - set(EXPECTED_TYPES.keys())
        if unexpected:
            self.stdout.write(self.style.WARNING(f'\n⚠️ Найдены неожиданные типы: {", ".join(unexpected)}'))
            for code in unexpected:
                dt = existing_types[code]
                self.stdout.write(self.style.WARNING(f'  ⚠️ {code} ({dt.name}) - is_active={dt.is_active}'))
                warnings.append(f'⚠️ Неожиданный тип: {code} ({dt.name})')
        
        # Показываем полный список всех типов в базе
        self.stdout.write(self.style.SUCCESS(f'\n=== ВСЕ ТИПЫ В БАЗЕ ДАННЫХ ==='))
        for code, dt in sorted(existing_types.items()):
            status = '✅' if code in EXPECTED_TYPES else '⚠️'
            self.stdout.write(f'{status} {code} ({dt.name}) - is_active={dt.is_active}')

        # Итоги
        self.stdout.write(self.style.SUCCESS(f'\n=== ИТОГИ ==='))
        self.stdout.write(f'✅ Корректных типов: {len(correct)}/{len(EXPECTED_TYPES)}')
        self.stdout.write(f'❌ Ошибок: {len(errors)}')
        self.stdout.write(f'⚠️ Предупреждений: {len(warnings)}')

        if errors:
            self.stdout.write(self.style.ERROR('\n❌ ОШИБКИ:'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f'  {error}'))

        if warnings:
            self.stdout.write(self.style.WARNING('\n⚠️ ПРЕДУПРЕЖДЕНИЯ:'))
            for warning in warnings:
                self.stdout.write(self.style.WARNING(f'  {warning}'))

        if not errors and not warnings:
            self.stdout.write(self.style.SUCCESS('\n✅ Все типы документов настроены корректно!'))

        return len(errors)
