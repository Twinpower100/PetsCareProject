# Generated migration: add diagnosis, anamnesis; make employee optional

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0005_petrecord_provider_location_alter_petrecord_provider'),
    ]

    operations = [
        migrations.AddField(
            model_name='petrecord',
            name='diagnosis',
            field=models.TextField(blank=True, help_text='Diagnosis (optional, can be empty for vaccinations)', null=True, verbose_name='Diagnosis'),
        ),
        migrations.AddField(
            model_name='petrecord',
            name='anamnesis',
            field=models.TextField(blank=True, help_text='Anamnesis / medical history note (optional)', null=True, verbose_name='Anamnesis'),
        ),
        migrations.AlterField(
            model_name='petrecord',
            name='employee',
            field=models.ForeignKey(blank=True, help_text='Employee who performed the procedure; empty when record is added by owner', null=True, on_delete=models.PROTECT, related_name='pet_records', to='providers.employee', verbose_name='Employee'),
        ),
        migrations.AlterField(
            model_name='petrecord',
            name='description',
            field=models.TextField(blank=True, help_text='Description of what was done', verbose_name='Description'),
        ),
    ]
