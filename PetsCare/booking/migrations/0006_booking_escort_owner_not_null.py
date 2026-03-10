from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_escort_owner(apps, schema_editor):
    Booking = apps.get_model('booking', 'Booking')
    Booking.objects.filter(
        escort_owner__isnull=True,
        user__isnull=False,
    ).update(escort_owner=models.F('user'))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0005_booking_escort_owner_and_occupied_duration'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(backfill_escort_owner, noop),
        migrations.AlterField(
            model_name='booking',
            name='escort_owner',
            field=models.ForeignKey(
                blank=True,
                help_text='Owner escorting the pet to the booking',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='escorted_bookings',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Escort Owner',
            ),
        ),
    ]
