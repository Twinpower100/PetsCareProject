# Generated manually for staff invite flow

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0030_providerlocationservice_meta_and_price'),
    ]

    operations = [
        migrations.CreateModel(
            name='LocationStaffInvite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(help_text='Email of the user to invite (must exist in the system)', max_length=254, verbose_name='Email')),
                ('token', models.CharField(help_text='6-digit activation code', max_length=6, unique=True, verbose_name='Token')),
                ('expires_at', models.DateTimeField(verbose_name='Expires at')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created at')),
                ('provider_location', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='staff_invites', to='providers.providerlocation', verbose_name='Provider location')),
            ],
            options={
                'verbose_name': 'Location staff invite',
                'verbose_name_plural': 'Location staff invites',
                'ordering': ['-created_at'],
                'unique_together': {('provider_location', 'email')},
            },
        ),
        migrations.AddIndex(
            model_name='locationstaffinvite',
            index=models.Index(fields=['token'], name='providers_l_token_8a2b12_idx'),
        ),
        migrations.AddIndex(
            model_name='locationstaffinvite',
            index=models.Index(fields=['expires_at'], name='providers_l_expires_3c4d56_idx'),
        ),
        migrations.AddIndex(
            model_name='locationstaffinvite',
            index=models.Index(fields=['provider_location', 'email'], name='providers_l_provide_9e8f01_idx'),
        ),
    ]
