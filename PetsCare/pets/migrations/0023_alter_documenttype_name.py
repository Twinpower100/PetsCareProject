from django.db import migrations, models


CATALOG_NAME_BY_CODE = {
    'passport_identification': 'Passport / identification',
    'veterinary_certificate': 'Veterinary certificate',
    'lab_results': 'Laboratory results',
    'diagnostics': 'Diagnostics',
    'discharge_doctor_orders': 'Discharge / doctor orders',
}


def sync_document_type_names_to_english(apps, schema_editor):
    """Переводит каноническое поле name на английский язык для всего каталога."""
    DocumentType = apps.get_model('pets', 'DocumentType')

    for code, english_name in CATALOG_NAME_BY_CODE.items():
        DocumentType.objects.filter(code=code).update(
            name=english_name,
            name_en=english_name,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0022_alter_documenttype_code_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documenttype',
            name='name',
            field=models.CharField(
                choices=[
                    ('Passport / identification', 'Passport / identification'),
                    ('Veterinary certificate', 'Veterinary certificate'),
                    ('Laboratory results', 'Laboratory results'),
                    ('Diagnostics', 'Diagnostics'),
                    ('Discharge / doctor orders', 'Discharge / doctor orders'),
                ],
                help_text='Select one of the approved document types.',
                max_length=100,
                verbose_name='Name',
            ),
        ),
        migrations.RunPython(sync_document_type_names_to_english, migrations.RunPython.noop),
    ]
