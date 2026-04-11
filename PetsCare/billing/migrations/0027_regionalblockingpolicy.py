# Региональные политики блокировок и начальная запись DEFAULT

from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def seed_default_policy(apps, schema_editor):
    """Создаёт валюту EUR при необходимости и политику DEFAULT для расчёта блокировок."""
    Currency = apps.get_model('billing', 'Currency')
    RegionalBlockingPolicy = apps.get_model('billing', 'RegionalBlockingPolicy')

    eur, _ = Currency.objects.get_or_create(
        code='EUR',
        defaults={
            'name': 'Euro',
            'symbol': '€',
            'exchange_rate': Decimal('1.0000'),
            'is_active': True,
        },
    )
    RegionalBlockingPolicy.objects.get_or_create(
        region_code='DEFAULT',
        defaults={
            'currency_id': eur.id,
            'tolerance_amount': Decimal('5.00'),
            'overdue_days_l2_from': 60,
            'overdue_days_l3_from': 90,
            'is_active': True,
            'notes': 'Seeded default; adjust per environment.',
        },
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0026_remove_payment_booking'),
    ]

    operations = [
        migrations.CreateModel(
            name='RegionalBlockingPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('region_code', models.CharField(db_index=True, help_text='Stable code: EU, ME, RU, DEFAULT, ...', max_length=32, unique=True, verbose_name='Region code')),
                ('tolerance_amount', models.DecimalField(decimal_places=2, help_text='Overdue debt at or below this amount (after conversion to provider invoice currency) does not trigger blocking levels.', max_digits=12, verbose_name='Tolerance amount')),
                ('overdue_days_l2_from', models.PositiveIntegerField(help_text='Minimum calendar days of overdue to reach level 2 (marketplace restrictions), when overdue debt exceeds tolerance.', verbose_name='Overdue days for level 2 (from)')),
                ('overdue_days_l3_from', models.PositiveIntegerField(help_text='Minimum calendar days of overdue to reach level 3 (billing-only mode), when overdue debt exceeds tolerance.', verbose_name='Overdue days for level 3 (from)')),
                ('is_active', models.BooleanField(default=True, verbose_name='Is active')),
                ('notes', models.TextField(blank=True, verbose_name='Notes')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('currency', models.ForeignKey(help_text='Currency in which tolerance and amounts are defined', on_delete=django.db.models.deletion.PROTECT, related_name='regional_blocking_policies', to='billing.currency', verbose_name='Policy currency')),
            ],
            options={
                'verbose_name': 'Regional blocking policy',
                'verbose_name_plural': 'Regional blocking policies',
                'ordering': ['region_code'],
            },
        ),
        migrations.RunPython(seed_default_policy, noop_reverse),
    ]
