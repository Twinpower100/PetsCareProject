from django.db import migrations


EXCLUDED_TABLES = {
    'auth_user_groups',
    'auth_user_user_permissions',
}

DELETE_ACTION_SQL = {
    'a': '',
    'r': ' ON DELETE RESTRICT',
    'c': ' ON DELETE CASCADE',
    'n': ' ON DELETE SET NULL',
    'd': ' ON DELETE SET DEFAULT',
}


def fix_project_auth_user_fks(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                t.relname AS table_name,
                c.conname AS constraint_name,
                array_agg(a.attname ORDER BY cols.ordinality) AS column_names,
                c.confdeltype AS delete_action
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            JOIN pg_class rt ON c.confrelid = rt.oid
            JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS cols(attnum, ordinality) ON TRUE
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = cols.attnum
            WHERE n.nspname = 'public'
              AND c.contype = 'f'
              AND rt.relname = 'auth_user'
            GROUP BY t.relname, c.conname, c.confdeltype
            ORDER BY t.relname, c.conname
            """
        )

        for table_name, constraint_name, column_names, delete_action in cursor.fetchall():
            if table_name in EXCLUDED_TABLES or not column_names:
                continue

            quoted_columns = ', '.join(column_names)
            on_delete_sql = DELETE_ACTION_SQL.get(delete_action, '')

            cursor.execute(f'ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS "{constraint_name}"')
            cursor.execute(
                f"""
                ALTER TABLE {table_name}
                ADD CONSTRAINT "{constraint_name}"
                FOREIGN KEY ({quoted_columns}) REFERENCES users_user(id){on_delete_sql}
                DEFERRABLE INITIALLY DEFERRED
                """
            )


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0032_remove_legacy_invite_models'),
        ('access', '0001_initial'),
        ('account', '0005_emailaddress_idx_upper_email'),
        ('notifications', '0002_notificationtemplate_body_de_and_more'),
        ('pets', '0019_fix_user_fks_to_users_user'),
        ('push_notifications', '0010_alter_apnsdevice_id_alter_gcmdevice_id_and_more'),
        ('ratings', '0001_initial'),
        ('reports', '0001_initial'),
        ('security', '0001_initial'),
        ('socialaccount', '0006_alter_socialaccount_extra_data'),
    ]

    operations = [
        migrations.RunPython(fix_project_auth_user_fks, migrations.RunPython.noop),
    ]
