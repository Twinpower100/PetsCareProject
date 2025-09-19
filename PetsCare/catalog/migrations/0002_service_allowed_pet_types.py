# Generated manually for adding allowed_pet_types field to Service model

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0001_initial'),
        ('pets', '0001_initial'),  # Assuming pets app has initial migration
    ]

    operations = [
        migrations.AddField(
            model_name='service',
            name='allowed_pet_types',
            field=models.ManyToManyField(
                blank=True,
                help_text='Pet types this service is available for. If empty, available for all types.',
                related_name='services',
                to='pets.pettype',
                verbose_name='Allowed Pet Types'
            ),
        ),
    ]
