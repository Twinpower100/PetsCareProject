# Перенос данных из ProviderAdmin (users) в EmployeeProvider.
# После применения удалить модель ProviderAdmin в users.

from django.db import migrations
from django.utils import timezone


def provider_admin_to_employee_provider(apps, schema_editor):
    ProviderAdmin = apps.get_model('users', 'ProviderAdmin')
    User = apps.get_model('users', 'User')
    Employee = apps.get_model('providers', 'Employee')
    EmployeeProvider = apps.get_model('providers', 'EmployeeProvider')
    today = timezone.now().date()
    for pa in ProviderAdmin.objects.all():
        user = pa.user
        provider = pa.provider
        role = pa.role
        employee, _ = Employee.objects.get_or_create(user=user)
        start_date = pa.created_at.date() if pa.created_at else today
        end_date = None if pa.is_active else today
        ep, created = EmployeeProvider.objects.get_or_create(
            employee=employee,
            provider=provider,
            role=role,
            start_date=start_date,
            defaults={'end_date': end_date},
        )
        if not created and ep.end_date != end_date:
            ep.end_date = end_date
            ep.save(update_fields=['end_date'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0038_add_employee_provider_role'),
        ('users', '0029_ensure_provider_staff_user_types'),
    ]

    operations = [
        migrations.RunPython(provider_admin_to_employee_provider, noop),
    ]
