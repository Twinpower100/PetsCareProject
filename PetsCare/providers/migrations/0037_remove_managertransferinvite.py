# Миграция: удаление модели ManagerTransferInvite.
# Оставлен один поток приглашений — Provider owner/manager invites (по email с 6-значным кодом).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0036_add_provider_owner_manager_invite'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ManagerTransferInvite',
        ),
    ]
