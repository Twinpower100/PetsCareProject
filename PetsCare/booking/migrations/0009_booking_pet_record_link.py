from datetime import timedelta

import django.db.models.deletion
from django.db import migrations, models


def link_existing_pet_records(apps, schema_editor):
    Booking = apps.get_model('booking', 'Booking')
    PetRecord = apps.get_model('pets', 'PetRecord')

    completed_bookings = Booking.objects.filter(
        status__name='completed',
        completed_at__isnull=False,
        pet_record__isnull=True,
    ).iterator()

    for booking in completed_bookings:
        candidates = PetRecord.objects.filter(
            pet_id=booking.pet_id,
            service_id=booking.service_id,
            employee_id=booking.employee_id,
        )
        if booking.provider_location_id is not None:
            candidates = candidates.filter(provider_location_id=booking.provider_location_id)
        elif booking.provider_id is not None:
            candidates = candidates.filter(provider_id=booking.provider_id)

        exact_match = candidates.filter(date=booking.completed_at).order_by('-created_at').first()
        if exact_match is not None:
            Booking.objects.filter(pk=booking.pk).update(pet_record_id=exact_match.pk)
            continue

        nearby_match = candidates.filter(
            date__gte=booking.completed_at - timedelta(minutes=5),
            date__lte=booking.completed_at + timedelta(minutes=5),
        ).order_by('-created_at').first()
        if nearby_match is not None:
            Booking.objects.filter(pk=booking.pk).update(pet_record_id=nearby_match.pk)


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0019_fix_user_fks_to_users_user'),
        ('booking', '0008_bookingserviceissue'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='pet_record',
            field=models.ForeignKey(
                blank=True,
                help_text='Structured visit record linked to this completed booking',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='source_bookings',
                to='pets.petrecord',
                verbose_name='Pet Record',
            ),
        ),
        migrations.RunPython(link_existing_pet_records, migrations.RunPython.noop),
    ]
