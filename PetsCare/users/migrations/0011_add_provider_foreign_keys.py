# Generated manually to fix circular dependency

from django.db import migrations, models
import django.db.models.deletion


def check_and_add_provider_fields(apps, schema_editor):
    """
    Проверяет существование полей provider и добавляет их только если их нет.
    """
    with schema_editor.connection.cursor() as cursor:
        # Проверяем RoleInvite
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users_roleinvite' AND column_name='provider_id'
        """)
        if not cursor.fetchone():
            # Поле не существует, добавляем
            cursor.execute("""
                ALTER TABLE users_roleinvite 
                ADD COLUMN provider_id INTEGER REFERENCES providers_provider(id) ON DELETE CASCADE
            """)
        
        # Проверяем ProviderAdmin
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users_provideradmin' AND column_name='provider_id'
        """)
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE users_provideradmin 
                ADD COLUMN provider_id INTEGER REFERENCES providers_provider(id) ON DELETE CASCADE
            """)


def reverse_check_and_add_provider_fields(apps, schema_editor):
    """
    Обратная операция - удаляем поля если они были добавлены.
    """
    pass  # Не удаляем, так как это может быть опасно


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0010_make_provider_email_required'),
        ('providers', '0001_initial'),  # Теперь Provider уже создан
    ]

    operations = [
        # Используем RunPython для условного добавления полей
        migrations.RunPython(
            check_and_add_provider_fields,
            reverse_check_and_add_provider_fields,
        ),
        # Добавляем индекс для role и provider в RoleInvite (если еще нет)
        migrations.RunSQL(
            """
            CREATE INDEX IF NOT EXISTS users_rolei_role_b6af1b_idx 
            ON users_roleinvite (role, provider_id);
            """,
            reverse_sql="DROP INDEX IF EXISTS users_rolei_role_b6af1b_idx;"
        ),
        # Добавляем unique_together для user и provider в ProviderAdmin
        migrations.RunSQL(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint 
                    WHERE conname = 'users_provideradmin_user_id_provider_id_uniq'
                ) THEN
                    ALTER TABLE users_provideradmin 
                    ADD CONSTRAINT users_provideradmin_user_id_provider_id_uniq 
                    UNIQUE (user_id, provider_id);
                END IF;
            END $$;
            """,
            reverse_sql="""
            ALTER TABLE users_provideradmin 
            DROP CONSTRAINT IF EXISTS users_provideradmin_user_id_provider_id_uniq;
            """
        ),
    ]

