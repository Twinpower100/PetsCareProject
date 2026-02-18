# Generated manually to fix Employee.user_id FK pointing to auth_user instead of users_user.
# После смены AUTH_USER_MODEL на users.User в БД остался старый FK на auth_user.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0031_locationstaffinvite'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE providers_employee
            DROP CONSTRAINT IF EXISTS providers_employee_user_id_f436d7db_fk_auth_user_id;
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'providers_employee_user_id_f436d7db_fk_users_user_id') THEN
                    ALTER TABLE providers_employee
                    ADD CONSTRAINT providers_employee_user_id_f436d7db_fk_users_user_id
                    FOREIGN KEY (user_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
