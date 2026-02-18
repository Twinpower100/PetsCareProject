# Generated manually for Service.is_client_facing (technical services)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0007_service_description_de_service_description_me_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='service',
            name='is_client_facing',
            field=models.BooleanField(
                default=True,
                help_text='If False, this is a technical/internal service (e.g. cleaning) not bookable by clients.',
                verbose_name='Is client facing',
            ),
        ),
    ]
