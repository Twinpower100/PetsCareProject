# Упрощение: одна таблица ProviderLocationService (location, service, pet_type, size_code)
# с ценой и длительностью. Удаление LocationServicePrice и ServiceVariant.

from django.db import migrations, models
import django.db.models.deletion


def fill_pet_type_and_size(apps, schema_editor):
    """Заполняем pet_type и size_code для существующих строк (если есть)."""
    ProviderLocationService = apps.get_model('providers', 'ProviderLocationService')
    PetType = apps.get_model('pets', 'PetType')
    first_pet_type = PetType.objects.order_by('id').first()
    if not first_pet_type:
        return
    ProviderLocationService.objects.filter(
        pet_type__isnull=True
    ).update(pet_type=first_pet_type, size_code='S')
    ProviderLocationService.objects.filter(
        size_code__isnull=True
    ).update(size_code='S')


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0007_weight_driven_pricing_sizerule_pet'),
        ('providers', '0027_add_served_pet_types_to_location'),
    ]

    operations = [
        migrations.AddField(
            model_name='providerlocationservice',
            name='pet_type',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='location_services',
                to='pets.pettype',
                verbose_name='Pet Type',
                help_text='Pet type (dog, cat, etc.) for this price row',
            ),
        ),
        migrations.AddField(
            model_name='providerlocationservice',
            name='size_code',
            field=models.CharField(
                null=True,
                max_length=10,
                choices=[('S', 'S'), ('M', 'M'), ('L', 'L'), ('XL', 'XL')],
                verbose_name='Size Code',
                help_text='Size category: S, M, L, XL (must match SizeRule)',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='providerlocationservice',
            unique_together=set(),
        ),
        migrations.RunPython(fill_pet_type_and_size, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='providerlocationservice',
            name='pet_type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='location_services',
                to='pets.pettype',
                verbose_name='Pet Type',
                help_text='Pet type (dog, cat, etc.) for this price row',
            ),
        ),
        migrations.AlterField(
            model_name='providerlocationservice',
            name='size_code',
            field=models.CharField(
                max_length=10,
                choices=[('S', 'S'), ('M', 'M'), ('L', 'L'), ('XL', 'XL')],
                verbose_name='Size Code',
                help_text='Size category: S, M, L, XL (must match SizeRule)',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='providerlocationservice',
            unique_together={('location', 'service', 'pet_type', 'size_code')},
        ),
        migrations.DeleteModel(
            name='ServiceVariant',
        ),
        migrations.DeleteModel(
            name='LocationServicePrice',
        ),
    ]
