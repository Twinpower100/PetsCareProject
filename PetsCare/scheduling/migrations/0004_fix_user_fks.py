
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0003_alter_servicepriority_unique_together_and_more'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DO $$
            DECLARE
                r RECORD;
            BEGIN
                -- Fix Vacation
                FOR r IN (
                    SELECT c.conname
                    FROM pg_constraint c
                    JOIN pg_class t ON c.conrelid = t.oid
                    JOIN pg_namespace n ON t.relnamespace = n.oid
                    WHERE t.relname = 'scheduling_vacation'
                    AND n.nspname = 'public'
                    AND c.contype = 'f'
                    AND pg_get_constraintdef(c.oid) LIKE '%auth_user%'
                ) LOOP
                    EXECUTE format('ALTER TABLE scheduling_vacation DROP CONSTRAINT IF EXISTS %I', r.conname);
                END LOOP;
                
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'scheduling_vacation_approved_by_user_id_fk') THEN
                    ALTER TABLE scheduling_vacation
                    ADD CONSTRAINT scheduling_vacation_approved_by_user_id_fk
                    FOREIGN KEY (approved_by_id) REFERENCES users_user(id) ON DELETE SET NULL;
                END IF;

                -- Fix SickLeave
                FOR r IN (
                    SELECT c.conname
                    FROM pg_constraint c
                    JOIN pg_class t ON c.conrelid = t.oid
                    JOIN pg_namespace n ON t.relnamespace = n.oid
                    WHERE t.relname = 'scheduling_sickleave'
                    AND n.nspname = 'public'
                    AND c.contype = 'f'
                    AND pg_get_constraintdef(c.oid) LIKE '%auth_user%'
                ) LOOP
                    EXECUTE format('ALTER TABLE scheduling_sickleave DROP CONSTRAINT IF EXISTS %I', r.conname);
                END LOOP;
                
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'scheduling_sickleave_confirmed_by_user_id_fk') THEN
                    ALTER TABLE scheduling_sickleave
                    ADD CONSTRAINT scheduling_sickleave_confirmed_by_user_id_fk
                    FOREIGN KEY (confirmed_by_id) REFERENCES users_user(id) ON DELETE SET NULL;
                END IF;

                -- Fix DayOff
                FOR r IN (
                    SELECT c.conname
                    FROM pg_constraint c
                    JOIN pg_class t ON c.conrelid = t.oid
                    JOIN pg_namespace n ON t.relnamespace = n.oid
                    WHERE t.relname = 'scheduling_dayoff'
                    AND n.nspname = 'public'
                    AND c.contype = 'f'
                    AND pg_get_constraintdef(c.oid) LIKE '%auth_user%'
                ) LOOP
                    EXECUTE format('ALTER TABLE scheduling_dayoff DROP CONSTRAINT IF EXISTS %I', r.conname);
                END LOOP;
                
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'scheduling_dayoff_approved_by_user_id_fk') THEN
                    ALTER TABLE scheduling_dayoff
                    ADD CONSTRAINT scheduling_dayoff_approved_by_user_id_fk
                    FOREIGN KEY (approved_by_id) REFERENCES users_user(id) ON DELETE SET NULL;
                END IF;
            END $$;
            """,
            reverse_sql="""
            ALTER TABLE scheduling_vacation DROP CONSTRAINT IF EXISTS scheduling_vacation_approved_by_user_id_fk;
            ALTER TABLE scheduling_sickleave DROP CONSTRAINT IF EXISTS scheduling_sickleave_confirmed_by_user_id_fk;
            ALTER TABLE scheduling_dayoff DROP CONSTRAINT IF EXISTS scheduling_dayoff_approved_by_user_id_fk;
            """
        ),
    ]
