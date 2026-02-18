# Migration: add EmployeeLocationService (employee + location + service), migrate data, remove Employee.services M2M

from django.db import migrations, models
import django.db.models.deletion


def migrate_employee_services_to_location_services(apps, schema_editor):
    """Перенос: для каждого сотрудника в каждой его локации создаём записи по его текущим услугам."""
    Employee = apps.get_model('providers', 'Employee')
    EmployeeLocationService = apps.get_model('providers', 'EmployeeLocationService')
    to_create = []
    for emp in Employee.objects.prefetch_related('locations', 'services').iterator(chunk_size=500):
        loc_ids = list(emp.locations.values_list('id', flat=True))
        svc_ids = list(emp.services.values_list('id', flat=True))
        for loc_id in loc_ids:
            for svc_id in svc_ids:
                to_create.append(
                    EmployeeLocationService(
                        employee_id=emp.id,
                        provider_location_id=loc_id,
                        service_id=svc_id,
                    )
                )
    if to_create:
        EmployeeLocationService.objects.bulk_create(to_create)


def noop_reverse(apps, schema_editor):
    """Обратная миграция не восстанавливает M2M employee.services (данные остаются в EmployeeLocationService)."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0032_fix_employee_user_fk_to_users_user'),
        ('catalog', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmployeeLocationService',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='location_services', to='providers.employee', verbose_name='Employee')),
                ('provider_location', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='employee_services', to='providers.providerlocation', verbose_name='Location')),
                ('service', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='catalog.service', verbose_name='Service')),
            ],
            options={
                'verbose_name': 'Employee location service',
                'verbose_name_plural': 'Employee location services',
            },
        ),
        migrations.AddConstraint(
            model_name='employeelocationservice',
            constraint=models.UniqueConstraint(fields=('employee', 'provider_location', 'service'), name='providers_employeelocationservice_employee_location_service_uniq'),
        ),
        migrations.AddIndex(
            model_name='employeelocationservice',
            index=models.Index(fields=['provider_location', 'service'], name='prov_emplocsvc_loc_svc_idx'),
        ),
        migrations.RunPython(migrate_employee_services_to_location_services, noop_reverse),
        migrations.RemoveField(
            model_name='employee',
            name='services',
        ),
    ]
