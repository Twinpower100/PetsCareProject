# Удаление устаревшей модели BlockingRule (L1/L2/L3, mass rules) и отдельная RegionalBlockingPolicy.

from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def copy_regional_policies_and_seed(apps, schema_editor):
    RegionalBlockingPolicy = apps.get_model('billing', 'RegionalBlockingPolicy')
    BlockingRule = apps.get_model('billing', 'BlockingRule')
    Currency = apps.get_model('billing', 'Currency')

    qs = BlockingRule.objects.exclude(blocking_policy_region_code__isnull=True).exclude(
        blocking_policy_region_code=''
    )
    for br in qs:
        if not br.policy_currency_id:
            continue
        RegionalBlockingPolicy.objects.update_or_create(
            region_code=(br.blocking_policy_region_code or '').strip().upper(),
            defaults={
                'currency_id': br.policy_currency_id,
                'tolerance_amount': br.tolerance_amount,
                'overdue_days_l2_from': br.overdue_days_l2_from,
                'overdue_days_l3_from': br.overdue_days_l3_from,
                'is_active': br.is_active,
                'notes': (getattr(br, 'description', None) or '')[:5000],
            },
        )

    if not RegionalBlockingPolicy.objects.exists():
        eur = Currency.objects.filter(code='EUR').first()
        if eur:
            RegionalBlockingPolicy.objects.create(
                region_code='DEFAULT',
                currency_id=eur.id,
                tolerance_amount=Decimal('5.00'),
                overdue_days_l2_from=60,
                overdue_days_l3_from=90,
                is_active=True,
                notes='Seeded default: B2B-oriented fallback (edit per market).',
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('billing', '0028_merge_regionalblockingpolicy_into_blockingrule'),
    ]

    operations = [
        migrations.CreateModel(
            name='RegionalBlockingPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('region_code', models.CharField(db_index=True, help_text='DEFAULT — если для вычисленного кода провайдера нет своей строки. EU — все страны ЕС. Иначе ISO 3166-1 alpha-2 (RU, ME, DE, …).', max_length=32, unique=True, verbose_name='Region / country code')),
                ('tolerance_amount', models.DecimalField(decimal_places=2, help_text='Overdue debt at or below this amount (after conversion to provider invoice currency) does not advance blocking levels.', max_digits=12, verbose_name='Tolerance amount')),
                ('overdue_days_l2_from', models.PositiveIntegerField(help_text='Minimum calendar days overdue to reach level 2 (marketplace restrictions), when overdue debt exceeds tolerance.', verbose_name='Overdue days for level 2 (from)')),
                ('overdue_days_l3_from', models.PositiveIntegerField(help_text='Minimum calendar days overdue to reach level 3 (billing-only), when overdue debt exceeds tolerance.', verbose_name='Overdue days for level 3 (from)')),
                ('is_active', models.BooleanField(default=True, verbose_name='Is active')),
                ('notes', models.TextField(blank=True, verbose_name='Notes')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('currency', models.ForeignKey(help_text='Currency in which tolerance_amount is defined; converted to provider invoice currency.', on_delete=django.db.models.deletion.PROTECT, related_name='regional_blocking_policies', to='billing.currency', verbose_name='Policy currency')),
            ],
            options={
                'verbose_name': 'Regional blocking policy',
                'verbose_name_plural': 'Regional blocking policies',
                'ordering': ['region_code'],
            },
        ),
        migrations.RunPython(copy_regional_policies_and_seed, noop_reverse),
        migrations.RemoveField(
            model_name='providerblocking',
            name='blocking_rule',
        ),
        migrations.DeleteModel(
            name='BlockingRule',
        ),
    ]
