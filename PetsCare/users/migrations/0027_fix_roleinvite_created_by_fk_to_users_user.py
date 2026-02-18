# Исправление FK created_by и accepted_by у RoleInvite: в БД ограничения могли ссылаться на auth_user,
# тогда как AUTH_USER_MODEL = 'users.User' (таблица users_user). Пересоздаём FK на users_user.

from django.db import migrations


def fix_roleinvite_user_fks(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        # Удаляем все FK с users_roleinvite, ссылающиеся на auth_user (created_by, accepted_by)
        cursor.execute("""
            DO $$
            DECLARE
                r RECORD;
            BEGIN
                FOR r IN (
                    SELECT c.conname
                    FROM pg_constraint c
                    JOIN pg_class t ON c.conrelid = t.oid
                    JOIN pg_namespace n ON t.relnamespace = n.oid
                    WHERE t.relname = 'users_roleinvite'
                    AND n.nspname = 'public'
                    AND c.contype = 'f'
                    AND (
                        c.conname LIKE '%created_by%'
                        OR c.conname LIKE '%accepted_by%'
                    )
                ) LOOP
                    EXECUTE format('ALTER TABLE users_roleinvite DROP CONSTRAINT IF EXISTS %I', r.conname);
                END LOOP;
            END $$;
        """)
        cursor.execute("""
            ALTER TABLE users_roleinvite
            ADD CONSTRAINT users_roleinvite_created_by_id_fk_users_user
            FOREIGN KEY (created_by_id) REFERENCES users_user(id) ON DELETE CASCADE;
        """)
        cursor.execute("""
            ALTER TABLE users_roleinvite
            ADD CONSTRAINT users_roleinvite_accepted_by_id_fk_users_user
            FOREIGN KEY (accepted_by_id) REFERENCES users_user(id) ON DELETE SET NULL;
        """)


def reverse_fix(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            ALTER TABLE users_roleinvite
            DROP CONSTRAINT IF EXISTS users_roleinvite_created_by_id_fk_users_user;
        """)
        cursor.execute("""
            ALTER TABLE users_roleinvite
            DROP CONSTRAINT IF EXISTS users_roleinvite_accepted_by_id_fk_users_user;
        """)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0026_drop_provideradmin_user_provider_uniq"),
    ]

    operations = [
        migrations.RunPython(fix_roleinvite_user_fks, reverse_fix),
    ]
