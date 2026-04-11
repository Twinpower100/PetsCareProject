# Перенос RegionalBlockingPolicy в BlockingRule и удаление отдельной таблицы

from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def migrate_regional_rows(apps, schema_editor):
    RegionalBlockingPolicy = apps.get_model('billing', 'RegionalBlockingPolicy')
    BlockingRule = apps.get_model('billing', 'BlockingRule')
    for rp in RegionalBlockingPolicy.objects.all():
        code = (rp.region_code or 'DEFAULT').strip().upper()
        BlockingRule.objects.update_or_create(
            blocking_policy_region_code=code,
            defaults={
                'name': f'Regional blocking policy {code}',
                'description': rp.notes or '',
                'debt_amount_threshold': Decimal('0'),
                'overdue_days_threshold': 0,
                'is_mass_rule': False,
                'regions': [],
                'service_types': [],
                'priority': 0,
                'is_active': rp.is_active,
                'policy_currency_id': rp.currency_id,
                'tolerance_amount': rp.tolerance_amount,
                'overdue_days_l2_from': rp.overdue_days_l2_from,
                'overdue_days_l3_from': rp.overdue_days_l3_from,
            },
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    # PostgreSQL: отложенные триггеры на billing_blockingrule мешают CREATE INDEX в одной транзакции.
    atomic = False

    dependencies = [
        ('billing', '0027_regionalblockingpolicy'),
    ]

    operations = [
        migrations.AddField(
            model_name='blockingrule',
            name='blocking_policy_region_code',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='If set, this row is the platform regional policy for that code (tolerance / L2 / L3 days). Leave empty for mass or auto-generated rules.',
                max_length=32,
                null=True,
                unique=True,
                verbose_name='Blocking policy region code',
            ),
        ),
        migrations.AddField(
            model_name='blockingrule',
            name='overdue_days_l2_from',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Regional policy: minimum overdue days for level 2 when debt exceeds tolerance.',
                null=True,
                verbose_name='Overdue days for level 2 (from)',
            ),
        ),
        migrations.AddField(
            model_name='blockingrule',
            name='overdue_days_l3_from',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Regional policy: minimum overdue days for level 3 when debt exceeds tolerance.',
                null=True,
                verbose_name='Overdue days for level 3 (from)',
            ),
        ),
        migrations.AddField(
            model_name='blockingrule',
            name='policy_currency',
            field=models.ForeignKey(
                blank=True,
                help_text='Currency of tolerance_amount for regional policy rows; ignored otherwise.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='blocking_rules_regional_policy',
                to='billing.currency',
                verbose_name='Policy currency',
            ),
        ),
        migrations.AddField(
            model_name='blockingrule',
            name='tolerance_amount',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Regional policy: overdue debt at or below this amount (converted to provider invoice currency) does not advance blocking levels.',
                max_digits=12,
                null=True,
                verbose_name='Tolerance amount',
            ),
        ),
        migrations.RunPython(migrate_regional_rows, noop_reverse),
        migrations.DeleteModel(name='RegionalBlockingPolicy'),
    ]
