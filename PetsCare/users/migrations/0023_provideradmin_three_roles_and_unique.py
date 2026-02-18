# Three provider-level roles: owner, provider_manager, provider_admin.
# One user can have several roles per provider (unique_together = user, provider, role).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0022_add_provideradmin_role'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='provideradmin',
            unique_together={('user', 'provider', 'role')},
        ),
    ]
