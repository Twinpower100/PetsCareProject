import django.db.models.deletion
from django.db import migrations, models


LEGACY_DEFAULT_DOCUMENT_TYPE_CODE = 'discharge_doctor_orders'


def backfill_petdocument_types(apps, schema_editor):
    """Заполняет legacy-документы согласованным fallback-типом перед ужесточением схемы."""
    document_type_model = apps.get_model('pets', 'DocumentType')
    pet_document_model = apps.get_model('pets', 'PetDocument')
    default_document_type = document_type_model.objects.get(
        code=LEGACY_DEFAULT_DOCUMENT_TYPE_CODE
    )
    pet_document_model.objects.filter(document_type__isnull=True).update(
        document_type=default_document_type
    )


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0024_petdocument_deactivated_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='petdocument',
            name='visit_record_addendum',
            field=models.ForeignKey(
                blank=True,
                help_text='Visit addendum to which the document is attached',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='documents',
                to='pets.visitrecordaddendum',
                verbose_name='Visit Record Addendum',
            ),
        ),
        migrations.RunPython(
            backfill_petdocument_types,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='petdocument',
            name='document_type',
            field=models.ForeignKey(
                help_text='Type of the document',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='documents',
                to='pets.documenttype',
                verbose_name='Document Type',
            ),
        ),
        migrations.AddIndex(
            model_name='petdocument',
            index=models.Index(
                fields=['visit_record_addendum', 'lifecycle_status'],
                name='pets_petrec_visit_r_10d72f_idx',
            ),
        ),
    ]
