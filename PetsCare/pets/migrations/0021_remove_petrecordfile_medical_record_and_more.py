import os

import django.db.models.deletion
from django.db import migrations, models


def migrate_legacy_documents(apps, schema_editor):
    MedicalRecord = apps.get_model('pets', 'MedicalRecord')
    PetOwner = apps.get_model('pets', 'PetOwner')
    PetRecordFile = apps.get_model('pets', 'PetRecordFile')
    PetRecordFilesM2M = PetRecordFile.records.through
    User = apps.get_model('users', 'User')

    for document in PetRecordFile.objects.all().iterator():
        if document.pet_record_id:
            continue
        relation = (
            PetRecordFilesM2M.objects
            .filter(petrecordfile_id=document.pk)
            .order_by('petrecord_id')
            .first()
        )
        if relation is not None:
            PetRecordFile.objects.filter(pk=document.pk).update(pet_record_id=relation.petrecord_id)

    fallback_user_id = User.objects.order_by('id').values_list('id', flat=True).first()

    for record in MedicalRecord.objects.exclude(attachments='').exclude(attachments__isnull=True).iterator():
        attachment_name = record.attachments.name
        if not attachment_name:
            continue
        if PetRecordFile.objects.filter(medical_record_id=record.pk, file=attachment_name).exists():
            continue

        owner_id = (
            PetOwner.objects.filter(pet_id=record.pet_id, role='main')
            .values_list('user_id', flat=True)
            .first()
        )
        if owner_id is None:
            owner_id = (
                PetOwner.objects.filter(pet_id=record.pet_id)
                .order_by('id')
                .values_list('user_id', flat=True)
                .first()
            )
        if owner_id is None:
            owner_id = fallback_user_id
        if owner_id is None:
            continue

        name = (record.title or '').strip() or os.path.basename(attachment_name) or f'health-note-{record.pk}'
        PetRecordFile.objects.create(
            file=attachment_name,
            name=name[:255],
            description=record.description or '',
            pet_id=record.pet_id,
            medical_record_id=record.pk,
            uploaded_by_id=owner_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0010_remove_booking_pet_record'),
        ('pets', '0020_alter_medicalrecord_options_alter_petrecord_options_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_legacy_documents, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameModel('MedicalRecord', 'PetHealthNote'),
                migrations.AlterModelTable('pethealthnote', 'pets_medicalrecord'),
                migrations.RenameModel('PetRecord', 'VisitRecord'),
                migrations.AlterModelTable('visitrecord', 'pets_petrecord'),
                migrations.RenameModel('PetRecordFile', 'PetDocument'),
                migrations.AlterModelTable('petdocument', 'pets_petrecordfile'),
            ],
        ),
        migrations.RenameField(
            model_name='petdocument',
            old_name='medical_record',
            new_name='health_note',
        ),
        migrations.RenameField(
            model_name='petdocument',
            old_name='pet_record',
            new_name='visit_record',
        ),
        migrations.AlterModelOptions(
            name='pethealthnote',
            options={
                'ordering': ['-date', '-created_at'],
                'verbose_name': 'Pet Health Note',
                'verbose_name_plural': 'Pet Health Notes',
            },
        ),
        migrations.AlterModelOptions(
            name='visitrecord',
            options={
                'ordering': ['-date'],
                'verbose_name': 'Visit Record',
                'verbose_name_plural': 'Visit Records',
            },
        ),
        migrations.AlterModelOptions(
            name='petdocument',
            options={
                'ordering': ['-uploaded_at'],
                'verbose_name': 'Pet Document',
                'verbose_name_plural': 'Pet Documents',
            },
        ),
        migrations.AlterField(
            model_name='pethealthnote',
            name='date',
            field=models.DateField(
                help_text='Date of the note',
                verbose_name='Date',
            ),
        ),
        migrations.AlterField(
            model_name='pethealthnote',
            name='title',
            field=models.CharField(
                help_text='Short title of the note',
                max_length=200,
                verbose_name='Title',
            ),
        ),
        migrations.AlterField(
            model_name='pethealthnote',
            name='description',
            field=models.TextField(
                help_text='Description of the note',
                verbose_name='Description',
            ),
        ),
        migrations.AlterField(
            model_name='pethealthnote',
            name='pet',
            field=models.ForeignKey(
                help_text='Pet to which this note belongs',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='health_notes',
                to='pets.pet',
                verbose_name='Pet',
            ),
        ),
        migrations.AlterField(
            model_name='visitrecord',
            name='provider',
            field=models.ForeignKey(
                blank=True,
                help_text='Legacy field - use provider_location instead',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='visit_records',
                to='providers.provider',
                verbose_name='Provider (Legacy)',
            ),
        ),
        migrations.AlterField(
            model_name='visitrecord',
            name='provider_location',
            field=models.ForeignKey(
                blank=True,
                help_text='Location where the service was provided',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='visit_records',
                to='providers.providerlocation',
                verbose_name='Provider Location',
            ),
        ),
        migrations.AlterField(
            model_name='visitrecord',
            name='service',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='visit_records',
                to='catalog.service',
                verbose_name='Service',
            ),
        ),
        migrations.AlterField(
            model_name='visitrecord',
            name='employee',
            field=models.ForeignKey(
                blank=True,
                help_text='Employee who performed the procedure; empty when record is added by owner',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='visit_records',
                to='providers.employee',
                verbose_name='Employee',
            ),
        ),
        migrations.AlterField(
            model_name='petdocument',
            name='health_note',
            field=models.ForeignKey(
                blank=True,
                help_text='Health note to which the document is attached',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='documents',
                to='pets.pethealthnote',
                verbose_name='Health Note',
            ),
        ),
        migrations.AlterField(
            model_name='petdocument',
            name='visit_record',
            field=models.ForeignKey(
                blank=True,
                help_text='Visit record to which the document is attached',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='documents',
                to='pets.visitrecord',
                verbose_name='Visit Record',
            ),
        ),
        migrations.AlterField(
            model_name='visitrecordaddendum',
            name='visit_record',
            field=models.ForeignKey(
                help_text='Visit protocol to which this addendum belongs',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='addenda',
                to='pets.visitrecord',
                verbose_name='Visit Record',
            ),
        ),
        migrations.RemoveField(
            model_name='visitrecord',
            name='files',
        ),
        migrations.RemoveField(
            model_name='pethealthnote',
            name='attachments',
        ),
        migrations.RemoveField(
            model_name='pethealthnote',
            name='title_en',
        ),
        migrations.RemoveField(
            model_name='pethealthnote',
            name='title_ru',
        ),
        migrations.RemoveField(
            model_name='pethealthnote',
            name='title_me',
        ),
        migrations.RemoveField(
            model_name='pethealthnote',
            name='title_de',
        ),
        migrations.RemoveField(
            model_name='pethealthnote',
            name='description_en',
        ),
        migrations.RemoveField(
            model_name='pethealthnote',
            name='description_ru',
        ),
        migrations.RemoveField(
            model_name='pethealthnote',
            name='description_me',
        ),
        migrations.RemoveField(
            model_name='pethealthnote',
            name='description_de',
        ),
    ]
