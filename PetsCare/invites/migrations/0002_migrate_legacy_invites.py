# Data migration: legacy invite data can be migrated here if needed.
# Currently no-op (skeletal) as per UNIFIED_INVITE_PROMPT: "миграция может быть пустой".

from django.db import migrations


def migrate_legacy_invites(apps, schema_editor):
    """При необходимости перенести данные из старых таблиц — реализовать здесь."""
    pass


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('invites', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(migrate_legacy_invites, noop),
    ]
