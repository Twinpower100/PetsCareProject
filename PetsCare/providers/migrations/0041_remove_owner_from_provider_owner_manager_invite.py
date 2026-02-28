# Удаляем инвайты с ролью owner: владелец больше не приглашается через инвайт.
# В модели ROLE_CHOICES оставлен только provider_manager (изменено в models.py).

from django.db import migrations


def delete_owner_invites(apps, schema_editor):
    """Удаляем все инвайты с ролью owner — они больше не принимаются."""
    ProviderOwnerManagerInvite = apps.get_model('providers', 'ProviderOwnerManagerInvite')
    ProviderOwnerManagerInvite.objects.filter(role='owner').delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0040_employeeprovider_roles_and_remove_confirmation'),
    ]

    operations = [
        migrations.RunPython(delete_owner_invites, noop),
    ]
