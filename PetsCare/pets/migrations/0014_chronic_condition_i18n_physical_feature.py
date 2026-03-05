# ChronicCondition: add name_en, name_ru, name_de, name_me; create PhysicalFeature

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0013_allow_null_birth_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='chroniccondition',
            name='name_de',
            field=models.CharField(blank=True, help_text='Name in German', max_length=200, verbose_name='Name (German)'),
        ),
        migrations.AddField(
            model_name='chroniccondition',
            name='name_en',
            field=models.CharField(blank=True, help_text='Name in English', max_length=200, verbose_name='Name (English)'),
        ),
        migrations.AddField(
            model_name='chroniccondition',
            name='name_me',
            field=models.CharField(blank=True, help_text='Name in Montenegrin', max_length=200, verbose_name='Name (Montenegrin)'),
        ),
        migrations.AddField(
            model_name='chroniccondition',
            name='name_ru',
            field=models.CharField(blank=True, help_text='Name in Russian', max_length=200, verbose_name='Name (Russian)'),
        ),
        migrations.CreateModel(
            name='PhysicalFeature',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(help_text='Unique code (e.g. featureAmputee, featureBlindness)', max_length=50, unique=True, verbose_name='Code')),
                ('name', models.CharField(help_text='Default display name', max_length=100, verbose_name='Name')),
                ('name_en', models.CharField(blank=True, max_length=100, verbose_name='Name (English)')),
                ('name_ru', models.CharField(blank=True, max_length=100, verbose_name='Name (Russian)')),
                ('name_de', models.CharField(blank=True, max_length=100, verbose_name='Name (German)')),
                ('name_me', models.CharField(blank=True, max_length=100, verbose_name='Name (Montenegrin)')),
                ('order', models.PositiveSmallIntegerField(default=0, verbose_name='Order')),
            ],
            options={
                'verbose_name': 'Physical Feature',
                'verbose_name_plural': 'Physical Features',
                'ordering': ['order', 'code'],
            },
        ),
    ]
