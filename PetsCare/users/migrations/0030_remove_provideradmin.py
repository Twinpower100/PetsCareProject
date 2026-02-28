# Удаление модели ProviderAdmin. Роли провайдера хранятся в providers.EmployeeProvider.
# Перед применением должна быть применена миграция providers.0039_provider_admin_to_employee_provider.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0029_ensure_provider_staff_user_types'),
        ('providers', '0039_provider_admin_to_employee_provider'),
    ]

    operations = [
        migrations.DeleteModel(name='ProviderAdmin'),
    ]
