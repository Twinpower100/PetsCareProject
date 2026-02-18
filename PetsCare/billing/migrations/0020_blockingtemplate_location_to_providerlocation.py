# Замена FK location: geolocation.Location удалена, привязываем к providers.ProviderLocation

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0019_add_side_letter_fields'),
        ('providers', '0006_providerlocation_providerlocationservice_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='blockingtemplate',
            name='location',
        ),
        migrations.AddField(
            model_name='blockingtemplate',
            name='location',
            field=models.ForeignKey(
                blank=True,
                help_text='Provider location for precise geographic targeting',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='blocking_templates',
                to='providers.providerlocation',
                verbose_name='Location',
            ),
        ),
    ]
