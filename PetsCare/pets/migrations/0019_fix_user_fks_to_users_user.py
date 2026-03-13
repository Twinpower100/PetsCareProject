from django.db import migrations


PETS_USER_FKS = (
    {
        'table': 'pets_petaccess',
        'column': 'granted_by_id',
        'constraint': 'pets_petaccess_granted_by_id_fk_users_user',
        'on_delete': 'CASCADE',
    },
    {
        'table': 'pets_petaccess',
        'column': 'granted_to_id',
        'constraint': 'pets_petaccess_granted_to_id_fk_users_user',
        'on_delete': 'CASCADE',
    },
    {
        'table': 'pets_petrecord',
        'column': 'created_by_id',
        'constraint': 'pets_petrecord_created_by_id_fk_users_user',
        'on_delete': '',
    },
    {
        'table': 'pets_petrecordfile',
        'column': 'uploaded_by_id',
        'constraint': 'pets_petrecordfile_uploaded_by_id_fk_users_user',
        'on_delete': '',
    },
)


def fix_pets_user_fks(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        for fk in PETS_USER_FKS:
            cursor.execute(
                """
                SELECT c.conname
                FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                JOIN pg_namespace n ON t.relnamespace = n.oid
                JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey)
                WHERE t.relname = %s
                  AND n.nspname = 'public'
                  AND c.contype = 'f'
                  AND a.attname = %s
                """,
                [fk['table'], fk['column']],
            )
            for (constraint_name,) in cursor.fetchall():
                cursor.execute(f'ALTER TABLE {fk["table"]} DROP CONSTRAINT IF EXISTS "{constraint_name}"')

            cursor.execute(
                "SELECT 1 FROM pg_constraint WHERE conname = %s",
                [fk['constraint']],
            )
            if cursor.fetchone():
                continue

            on_delete_clause = f" ON DELETE {fk['on_delete']}" if fk['on_delete'] else ""
            cursor.execute(
                f"""
                ALTER TABLE {fk["table"]}
                ADD CONSTRAINT {fk["constraint"]}
                FOREIGN KEY ({fk["column"]}) REFERENCES users_user(id){on_delete_clause}
                DEFERRABLE INITIALLY DEFERRED
                """
            )


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0018_add_petowner_through_model'),
    ]

    operations = [
        migrations.RunPython(fix_pets_user_fks, migrations.RunPython.noop),
    ]
