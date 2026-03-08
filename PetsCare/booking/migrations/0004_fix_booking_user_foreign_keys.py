from django.conf import settings
from django.db import connection, migrations


BOOKING_USER_FOREIGN_KEYS = [
    (
        'booking_booking',
        'booking_booking_user_id_e1eb6912_fk_auth_user_id',
        'user_id',
        'booking_booking_user_id_e1eb6912_fk_users_user_id',
        'CASCADE',
    ),
    (
        'booking_booking',
        'booking_booking_cancelled_by_id_bb79d48c_fk_auth_user_id',
        'cancelled_by_id',
        'booking_booking_cancelled_by_id_bb79d48c_fk_users_user_id',
        'SET NULL',
    ),
    (
        'booking_booking',
        'booking_booking_completed_by_id_963a4ec9_fk_auth_user_id',
        'completed_by_id',
        'booking_booking_completed_by_id_963a4ec9_fk_users_user_id',
        'SET NULL',
    ),
    (
        'booking_bookingcancellation',
        'booking_bookingcance_cancelled_by_id_852aa2db_fk_auth_user',
        'cancelled_by_id',
        'booking_bookingcance_cancelled_by_id_852aa2db_fk_users_user',
        'NO ACTION',
    ),
    (
        'booking_bookingnote',
        'booking_bookingnote_created_by_id_962bb941_fk_auth_user_id',
        'created_by_id',
        'booking_bookingnote_created_by_id_962bb941_fk_users_user_id',
        'SET NULL',
    ),
]


def _get_constraint_target(cursor, constraint_name):
    cursor.execute(
        """
        SELECT target.relname
        FROM pg_constraint con
        JOIN pg_class target ON target.oid = con.confrelid
        WHERE con.conname = %s
        """,
        [constraint_name],
    )
    row = cursor.fetchone()
    return row[0] if row else None


def _constraint_exists(cursor, constraint_name):
    cursor.execute(
        """
        SELECT 1
        FROM pg_constraint
        WHERE conname = %s
        """,
        [constraint_name],
    )
    return cursor.fetchone() is not None


def repair_booking_user_foreign_keys(apps, schema_editor):
    if connection.vendor != 'postgresql':
        return

    custom_user_table = apps.get_model('users', 'User')._meta.db_table

    with connection.cursor() as cursor:
        for table_name, old_constraint, column_name, new_constraint, on_delete in BOOKING_USER_FOREIGN_KEYS:
            if _constraint_exists(cursor, new_constraint):
                continue

            target_table = _get_constraint_target(cursor, old_constraint)
            if target_table == custom_user_table:
                continue

            if _constraint_exists(cursor, old_constraint):
                schema_editor.execute(
                    f'ALTER TABLE "{table_name}" DROP CONSTRAINT "{old_constraint}"'
                )

            schema_editor.execute(
                f'''
                ALTER TABLE "{table_name}"
                ADD CONSTRAINT "{new_constraint}"
                FOREIGN KEY ("{column_name}")
                REFERENCES "{custom_user_table}" ("id")
                ON DELETE {on_delete}
                DEFERRABLE INITIALLY DEFERRED
                '''
            )


class Migration(migrations.Migration):

    dependencies = [
        ('booking', '0003_booking_provider_location_timeslot_provider_location_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(repair_booking_user_foreign_keys, migrations.RunPython.noop),
    ]
