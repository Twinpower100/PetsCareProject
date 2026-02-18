# Удаляем старый уникальный ключ (user_id, provider_id), чтобы действовал
# unique_together (user, provider, role) — один пользователь может иметь несколько ролей у одного провайдера.

from django.db import migrations


def drop_old_uniq(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            ALTER TABLE users_provideradmin
            DROP CONSTRAINT IF EXISTS users_provideradmin_user_id_provider_id_uniq;
        """)


def add_old_uniq(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            ALTER TABLE users_provideradmin
            ADD CONSTRAINT users_provideradmin_user_id_provider_id_uniq
            UNIQUE (user_id, provider_id);
        """)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0025_remove_userscoperole'),
    ]

    operations = [
        migrations.RunPython(drop_old_uniq, add_old_uniq),
    ]
