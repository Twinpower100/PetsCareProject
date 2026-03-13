from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0009_booking_pet_record_link'),
    ]

    operations = [
        migrations.RenameField(
            model_name='booking',
            old_name='pet_record',
            new_name='visit_record',
        ),
    ]
