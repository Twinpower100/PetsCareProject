import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0010_remove_booking_pet_record'),
        ('pets', '0021_remove_petrecordfile_medical_record_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='booking',
            name='visit_record',
            field=models.ForeignKey(blank=True, help_text='Structured visit record linked to this completed booking', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='source_bookings', to='pets.visitrecord', verbose_name='Visit Record'),
        ),
    ]
