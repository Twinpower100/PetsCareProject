# Remove Employee.services M2M; use EmployeeLocationService only.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0034_add_employeelocationrole'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='employee',
            name='services',
        ),
    ]
