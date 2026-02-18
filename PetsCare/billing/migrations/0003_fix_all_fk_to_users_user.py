# Generated manually to fix all foreign key constraints pointing to auth_user

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_fix_billingmanagerprovider_fk'),
    ]

    operations = [
        # Исправляем все внешние ключи в billing, ссылающиеся на auth_user
        migrations.RunSQL(
            sql="""
            ALTER TABLE billing_blockingrule
            DROP CONSTRAINT IF EXISTS billing_blockingrule_created_by_id_473bc0b3_fk_auth_user_id;
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'billing_blockingrule_created_by_id_473bc0b3_fk_users_use_id') THEN
                    ALTER TABLE billing_blockingrule
                    ADD CONSTRAINT billing_blockingrule_created_by_id_473bc0b3_fk_users_use_id
                    FOREIGN KEY (created_by_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE billing_blockingsystemsettings
            DROP CONSTRAINT IF EXISTS billing_blockingsyst_updated_by_id_0f544fad_fk_auth_user;
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'billing_blockingsyst_updated_by_id_0f544fad_fk_users_use') THEN
                    ALTER TABLE billing_blockingsystemsettings
                    ADD CONSTRAINT billing_blockingsyst_updated_by_id_0f544fad_fk_users_use
                    FOREIGN KEY (updated_by_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE billing_blockingtemplate
            DROP CONSTRAINT IF EXISTS billing_blockingtemplate_created_by_id_ec704707_fk_auth_user_id;
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'billing_blockingtemplate_created_by_id_ec704707_fk_users_use_id') THEN
                    ALTER TABLE billing_blockingtemplate
                    ADD CONSTRAINT billing_blockingtemplate_created_by_id_ec704707_fk_users_use_id
                    FOREIGN KEY (created_by_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE billing_blockingtemplatehistory
            DROP CONSTRAINT IF EXISTS billing_blockingtemp_changed_by_id_dfabe60c_fk_auth_user;
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'billing_blockingtemp_changed_by_id_dfabe60c_fk_users_use') THEN
                    ALTER TABLE billing_blockingtemplatehistory
                    ADD CONSTRAINT billing_blockingtemp_changed_by_id_dfabe60c_fk_users_use
                    FOREIGN KEY (changed_by_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE billing_contract
            DROP CONSTRAINT IF EXISTS billing_contract_approved_by_id_2302a4de_fk_auth_user_id;
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'billing_contract_approved_by_id_2302a4de_fk_users_use_id') THEN
                    ALTER TABLE billing_contract
                    ADD CONSTRAINT billing_contract_approved_by_id_2302a4de_fk_users_use_id
                    FOREIGN KEY (approved_by_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE billing_contract
            DROP CONSTRAINT IF EXISTS billing_contract_created_by_id_d31b643f_fk_auth_user_id;
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'billing_contract_created_by_id_d31b643f_fk_users_use_id') THEN
                    ALTER TABLE billing_contract
                    ADD CONSTRAINT billing_contract_created_by_id_d31b643f_fk_users_use_id
                    FOREIGN KEY (created_by_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE billing_contractapprovalhistory
            DROP CONSTRAINT IF EXISTS billing_contractappr_user_id_592979bd_fk_auth_user;
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'billing_contractappr_user_id_592979bd_fk_users_use') THEN
                    ALTER TABLE billing_contractapprovalhistory
                    ADD CONSTRAINT billing_contractappr_user_id_592979bd_fk_users_use
                    FOREIGN KEY (user_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
            ALTER TABLE billing_providerblocking
            DROP CONSTRAINT IF EXISTS billing_providerbloc_resolved_by_id_d91dbb98_fk_auth_user;
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'billing_providerbloc_resolved_by_id_d91dbb98_fk_users_use') THEN
                    ALTER TABLE billing_providerblocking
                    ADD CONSTRAINT billing_providerbloc_resolved_by_id_d91dbb98_fk_users_use
                    FOREIGN KEY (resolved_by_id) REFERENCES users_user(id) DEFERRABLE INITIALLY DEFERRED;
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
