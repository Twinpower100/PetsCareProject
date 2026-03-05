# Generated manually: allow unknown (null) birth date

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0012_seed_chronic_conditions'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pet',
            name='birth_date',
            field=models.DateField(
                blank=True,
                help_text='Pet birth date. Null = unknown (e.g. adopted without papers).',
                null=True,
                verbose_name='Birth Date'
            ),
        ),
    ]
