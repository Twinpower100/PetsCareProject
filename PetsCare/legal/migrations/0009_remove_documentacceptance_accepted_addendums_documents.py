# One DocumentAcceptance per document; M2M accepted_addendums_documents removed.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('legal', '0008_fix_legaldocument_unique_constraint'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='documentacceptance',
            name='accepted_addendums_documents',
        ),
    ]
