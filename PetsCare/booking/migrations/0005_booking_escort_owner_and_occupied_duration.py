from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0004_fix_booking_user_foreign_keys'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='escort_owner',
            field=models.ForeignKey(
                blank=True,
                help_text='Owner escorting the pet to the booking',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='escorted_bookings',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Escort Owner',
            ),
        ),
        migrations.AddField(
            model_name='booking',
            name='occupied_duration_minutes',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Immutable occupied duration snapshot stored at booking creation time',
                verbose_name='Occupied Duration Minutes',
            ),
        ),
        migrations.AddIndex(
            model_name='booking',
            index=models.Index(fields=['escort_owner', 'start_time'], name='booking_boo_escort__81a957_idx'),
        ),
        migrations.AddIndex(
            model_name='booking',
            index=models.Index(fields=['pet', 'start_time'], name='booking_boo_pet_id_d734c0_idx'),
        ),
        migrations.AddIndex(
            model_name='booking',
            index=models.Index(fields=['employee', 'start_time'], name='booking_boo_employe_50007e_idx'),
        ),
    ]
