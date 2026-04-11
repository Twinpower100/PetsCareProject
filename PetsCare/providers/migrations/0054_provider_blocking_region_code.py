from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0053_providerservicepricing_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='provider',
            name='blocking_region_code',
            field=models.CharField(
                blank=True,
                help_text='Optional region code for billing blocking policy (EU, ME, …). If empty, region is derived from country (EU aggregate for EU members).',
                max_length=32,
                verbose_name='Blocking region override',
            ),
        ),
    ]
