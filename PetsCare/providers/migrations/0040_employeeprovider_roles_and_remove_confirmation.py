# EmployeeProvider: одна связь (employee, provider), роли как атрибуты.
# Удалены is_confirmed, confirmation_requested_at, confirmed_at.
# Добавлены is_owner, is_provider_manager, is_provider_admin.
# unique_together (employee, provider, start_date); объединение строк по (employee, provider).

from django.db import migrations, models


def backfill_role_flags(apps, schema_editor):
    """Заполняем is_owner, is_provider_manager, is_provider_admin из role."""
    EmployeeProvider = apps.get_model('providers', 'EmployeeProvider')
    ROLE_OWNER = 'owner'
    ROLE_PROVIDER_MANAGER = 'provider_manager'
    ROLE_PROVIDER_ADMIN = 'provider_admin'
    for ep in EmployeeProvider.objects.all():
        role = getattr(ep, 'role', None) or 'service_worker'
        ep.is_owner = (role == ROLE_OWNER)
        ep.is_provider_manager = (role == ROLE_PROVIDER_MANAGER)
        ep.is_provider_admin = (role == ROLE_PROVIDER_ADMIN)
        ep.is_manager = (role == ROLE_PROVIDER_MANAGER)
        ep.save(update_fields=['is_owner', 'is_provider_manager', 'is_provider_admin', 'is_manager'])


def merge_employee_provider_rows(apps, schema_editor):
    """Объединяем несколько записей (employee, provider) в одну с флагами ролей."""
    from collections import defaultdict
    EmployeeProvider = apps.get_model('providers', 'EmployeeProvider')
    by_key = defaultdict(list)
    for ep in EmployeeProvider.objects.order_by('start_date'):
        by_key[(ep.employee_id, ep.provider_id)].append(ep)
    to_delete = []
    for key, group in by_key.items():
        if len(group) <= 1:
            continue
        first = group[0]
        for other in group[1:]:
            first.is_owner = first.is_owner or other.is_owner
            first.is_provider_manager = first.is_provider_manager or other.is_provider_manager
            first.is_provider_admin = first.is_provider_admin or other.is_provider_admin
            first.is_manager = first.is_provider_manager
            if other.start_date and (not first.start_date or other.start_date < first.start_date):
                first.start_date = other.start_date
            if other.end_date and (not first.end_date or other.end_date > first.end_date):
                first.end_date = other.end_date
            to_delete.append(other.pk)
        first.save(update_fields=['is_owner', 'is_provider_manager', 'is_provider_admin', 'is_manager', 'start_date', 'end_date'])
    if to_delete:
        EmployeeProvider.objects.filter(pk__in=to_delete).delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0039_provider_admin_to_employee_provider'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeeprovider',
            name='is_owner',
            field=models.BooleanField(default=False, help_text='Owner of the organization', verbose_name='Is Owner'),
        ),
        migrations.AddField(
            model_name='employeeprovider',
            name='is_provider_admin',
            field=models.BooleanField(default=False, help_text='Provider admin (organization admin)', verbose_name='Is Provider Admin'),
        ),
        migrations.AddField(
            model_name='employeeprovider',
            name='is_provider_manager',
            field=models.BooleanField(default=False, help_text='Provider manager (organization manager)', verbose_name='Is Provider Manager'),
        ),
        migrations.RunPython(backfill_role_flags, noop),
        migrations.RemoveField(
            model_name='employeeprovider',
            name='is_confirmed',
        ),
        migrations.RemoveField(
            model_name='employeeprovider',
            name='confirmation_requested_at',
        ),
        migrations.RemoveField(
            model_name='employeeprovider',
            name='confirmed_at',
        ),
        migrations.RemoveIndex(
            model_name='employeeprovider',
            name='providers_e_is_conf_401368_idx',
        ),
        migrations.RunPython(merge_employee_provider_rows, noop),
        migrations.AlterUniqueTogether(
            name='employeeprovider',
            unique_together={('employee', 'provider', 'start_date')},
        ),
        migrations.RemoveIndex(
            model_name='employeeprovider',
            name='providers_e_provide_899f7a_idx',
        ),
        migrations.AddIndex(
            model_name='employeeprovider',
            index=models.Index(fields=['provider', 'is_owner'], name='providers_e_provide_owner_idx'),
        ),
        migrations.AddIndex(
            model_name='employeeprovider',
            index=models.Index(fields=['provider', 'is_provider_manager'], name='providers_e_provide_mgr_idx'),
        ),
        migrations.AddIndex(
            model_name='employeeprovider',
            index=models.Index(fields=['provider', 'is_provider_admin'], name='providers_e_provide_adm_idx'),
        ),
    ]
