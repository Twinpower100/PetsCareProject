# Remove UserScopeRole: rights = user_types (what), ProviderAdmin/Employee = where.
# No code changes required; keep existing ProviderAdmin, EmployeeLocationRole, manager.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0024_add_userscoperole'),
    ]

    operations = [
        migrations.DeleteModel(name='UserScopeRole'),
    ]
