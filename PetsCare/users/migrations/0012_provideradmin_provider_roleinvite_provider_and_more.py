# Generated manually to handle provider fields properly

from django.db import migrations, models
import django.db.models.deletion


def ensure_provider_fields_not_null(apps, schema_editor):
    """
    Убеждается, что поля provider в ProviderAdmin и RoleInvite являются не-nullable.
    Так как записей нет, можно безопасно изменить поля.
    """
    with schema_editor.connection.cursor() as cursor:
        # Проверяем ProviderAdmin
        cursor.execute("""
            SELECT is_nullable 
            FROM information_schema.columns 
            WHERE table_name='users_provideradmin' AND column_name='provider_id'
        """)
        result = cursor.fetchone()
        if result:
            if result[0] == 'YES':
                # Поле существует и является nullable, делаем его не-nullable
                cursor.execute("""
                    ALTER TABLE users_provideradmin 
                    ALTER COLUMN provider_id SET NOT NULL
                """)
        # Если поля нет, Django AddField добавит его
        
        # Проверяем RoleInvite
        cursor.execute("""
            SELECT is_nullable 
            FROM information_schema.columns 
            WHERE table_name='users_roleinvite' AND column_name='provider_id'
        """)
        result = cursor.fetchone()
        if result:
            if result[0] == 'YES':
                # Поле существует и является nullable, делаем его не-nullable
                cursor.execute("""
                    ALTER TABLE users_roleinvite 
                    ALTER COLUMN provider_id SET NOT NULL
                """)
        # Если поля нет, Django AddField добавит его


def reverse_ensure_provider_fields_not_null(apps, schema_editor):
    """
    Обратная операция - делаем поля nullable (на случай отката).
    Проверяем существование полей перед изменением.
    """
    with schema_editor.connection.cursor() as cursor:
        # Проверяем ProviderAdmin
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users_provideradmin' AND column_name='provider_id'
        """)
        if cursor.fetchone():
            cursor.execute("""
                ALTER TABLE users_provideradmin 
                ALTER COLUMN provider_id DROP NOT NULL
            """)
        
        # Проверяем RoleInvite
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users_roleinvite' AND column_name='provider_id'
        """)
        if cursor.fetchone():
            cursor.execute("""
                ALTER TABLE users_roleinvite 
                ALTER COLUMN provider_id DROP NOT NULL
            """)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0011_add_provider_foreign_keys'),
        ('providers', '0010_add_provider_location_to_schedulepattern'),
    ]

    operations = [
        # Сначала проверяем и добавляем поля, если их нет, или делаем их не-nullable, если они есть
        migrations.RunPython(
            ensure_provider_fields_not_null,
            reverse_ensure_provider_fields_not_null,
        ),
        # Добавляем поля через Django ORM для правильной синхронизации
        # Если поле уже существует (добавлено через миграцию 0011), Django пропустит это
        migrations.RunSQL(
            """
            DO $$
            BEGIN
                -- Добавляем поле provider в ProviderAdmin, если его нет
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='users_provideradmin' AND column_name='provider_id'
                ) THEN
                    ALTER TABLE users_provideradmin 
                    ADD COLUMN provider_id INTEGER NOT NULL REFERENCES providers_provider(id) ON DELETE CASCADE;
                END IF;
                
                -- Добавляем поле provider в RoleInvite, если его нет
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='users_roleinvite' AND column_name='provider_id'
                ) THEN
                    ALTER TABLE users_roleinvite 
                    ADD COLUMN provider_id INTEGER NOT NULL REFERENCES providers_provider(id) ON DELETE CASCADE;
                END IF;
            END $$;
            """,
            reverse_sql="""
            ALTER TABLE users_provideradmin DROP COLUMN IF EXISTS provider_id;
            ALTER TABLE users_roleinvite DROP COLUMN IF EXISTS provider_id;
            """
        ),
        # Обновляем unique_together для ProviderAdmin (если еще не установлено)
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
        # Добавляем индекс для RoleInvite (если еще не существует)
        migrations.RunSQL(
            """
            CREATE INDEX IF NOT EXISTS users_rolei_role_b6af1b_idx 
            ON users_roleinvite (role, provider_id);
            """,
            reverse_sql="DROP INDEX IF EXISTS users_rolei_role_b6af1b_idx;"
        ),
        # Синхронизируем состояние Django для полей provider
        # Используем SeparateDatabaseAndState, так как изменения в БД уже сделаны через RunSQL
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # Операции в БД уже выполнены выше
            state_operations=[
                # Добавляем поле provider в ProviderAdmin в состояние Django
                migrations.AddField(
                    model_name='provideradmin',
                    name='provider',
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='admins',
                        to='providers.provider',
                        verbose_name='Provider'
                    ),
                ),
                # Добавляем поле provider в RoleInvite в состояние Django
                migrations.AddField(
                    model_name='roleinvite',
                    name='provider',
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='providers.provider',
                        verbose_name='Provider',
                        help_text='Provider for employee role or project for billing manager'
                    ),
                ),
                # Обновляем unique_together для ProviderAdmin в состоянии Django
                migrations.AlterUniqueTogether(
                    name='provideradmin',
                    unique_together={('user', 'provider')},
                ),
                # Добавляем индекс для RoleInvite в состояние Django
                migrations.AddIndex(
                    model_name='roleinvite',
                    index=models.Index(fields=['role', 'provider'], name='users_rolei_role_b6af1b_idx'),
                ),
            ],
        ),
    ]

