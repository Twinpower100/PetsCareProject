# Ревизия User Types: обеспечить наличие ролей персонала провайдера (см. FunctionalDesign 1.2.4).
# Не удаляет и не меняет существующие типы; создаёт отсутствующие.

from django.db import migrations


PROVIDER_STAFF_ROLES = [
    ('owner', 'Owner'),
    ('provider_manager', 'Provider manager'),
    ('provider_admin', 'Provider admin'),
    ('branch_manager', 'Branch manager'),
    ('service_worker', 'Service worker'),
    ('technical_worker', 'Technical worker'),
]


def ensure_provider_staff_user_types(apps, schema_editor):
    UserType = apps.get_model('users', 'UserType')
    for name, _ in PROVIDER_STAFF_ROLES:
        UserType.objects.get_or_create(
            name=name,
            defaults={'is_active': True},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0028_alter_roleinvite_role'),
    ]

    operations = [
        migrations.RunPython(ensure_provider_staff_user_types, noop),
    ]
