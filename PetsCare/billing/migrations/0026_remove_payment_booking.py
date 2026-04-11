# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0025_alter_billingconfig_invoice_period_days_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='payment',
            name='booking',
        ),
    ]
