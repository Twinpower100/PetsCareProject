from django.db import migrations, models


def copy_location_pet_types_to_provider(apps, schema_editor):
    Provider = apps.get_model('providers', 'Provider')
    PetType = apps.get_model('pets', 'PetType')

    for provider in Provider.objects.all():
        pet_type_ids = list(
            PetType.objects.filter(provider_locations_served__provider=provider)
            .values_list('id', flat=True)
            .distinct()
        )
        if pet_type_ids:
            provider.served_pet_types.set(pet_type_ids)


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0025_petdocument_addendum_and_type_contract'),
        ('providers', '0054_provider_blocking_region_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='provider',
            name='served_pet_types',
            field=models.ManyToManyField(
                blank=True,
                help_text='Pet types that can be priced at the organization level and used as the allowed scope for branches in unified pricing mode.',
                related_name='providers_served',
                to='pets.pettype',
                verbose_name='Organization served pet types',
            ),
        ),
        migrations.RunPython(copy_location_pet_types_to_provider, noop_reverse),
    ]
