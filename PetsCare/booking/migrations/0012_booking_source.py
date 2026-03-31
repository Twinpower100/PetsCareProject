from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('booking', '0011_booking_visit_record'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='source',
            field=models.CharField(
                choices=[
                    ('booking_service', 'Booking service'),
                    ('manual_entry', 'Manual entry'),
                ],
                default='booking_service',
                help_text='How the booking was created',
                max_length=32,
                verbose_name='Source',
            ),
        ),
    ]
