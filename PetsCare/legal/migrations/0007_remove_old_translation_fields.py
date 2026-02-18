# Generated manually to remove old translation fields that are no longer in models

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('legal', '0006_add_ckeditor_to_content'),
    ]

    operations = [
        # Удаляем старые поля перевода из LegalDocument
        # Эти поля были добавлены в 0002, но потом удалены из модели,
        # так как теперь используется DocumentTranslation
        migrations.RemoveField(
            model_name='legaldocument',
            name='title_de',
        ),
        migrations.RemoveField(
            model_name='legaldocument',
            name='title_en',
        ),
        migrations.RemoveField(
            model_name='legaldocument',
            name='title_ru',
        ),
        migrations.RemoveField(
            model_name='legaldocument',
            name='title_sr',
        ),
        # Удаляем старые поля перевода из LegalDocumentType
        migrations.RemoveField(
            model_name='legaldocumenttype',
            name='description_de',
        ),
        migrations.RemoveField(
            model_name='legaldocumenttype',
            name='description_en',
        ),
        migrations.RemoveField(
            model_name='legaldocumenttype',
            name='description_ru',
        ),
        migrations.RemoveField(
            model_name='legaldocumenttype',
            name='description_sr',
        ),
        migrations.RemoveField(
            model_name='legaldocumenttype',
            name='name_de',
        ),
        migrations.RemoveField(
            model_name='legaldocumenttype',
            name='name_en',
        ),
        migrations.RemoveField(
            model_name='legaldocumenttype',
            name='name_ru',
        ),
        migrations.RemoveField(
            model_name='legaldocumenttype',
            name='name_sr',
        ),
    ]
