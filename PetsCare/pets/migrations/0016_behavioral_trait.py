# Create BehavioralTrait reference model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0015_seed_chronic_i18n_physical_features'),
    ]

    operations = [
        migrations.CreateModel(
            name='BehavioralTrait',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(help_text='Unique code (e.g. traitFlightRisk, traitWaterFear)', max_length=50, unique=True, verbose_name='Code')),
                ('name', models.CharField(help_text='Default display name', max_length=100, verbose_name='Name')),
                ('name_en', models.CharField(blank=True, max_length=100, verbose_name='Name (English)')),
                ('name_ru', models.CharField(blank=True, max_length=100, verbose_name='Name (Russian)')),
                ('name_de', models.CharField(blank=True, max_length=100, verbose_name='Name (German)')),
                ('name_me', models.CharField(blank=True, max_length=100, verbose_name='Name (Montenegrin)')),
                ('order', models.PositiveSmallIntegerField(default=0, verbose_name='Order')),
            ],
            options={
                'verbose_name': 'Behavioral Trait',
                'verbose_name_plural': 'Behavioral Traits',
                'ordering': ['order', 'code'],
            },
        ),
    ]
