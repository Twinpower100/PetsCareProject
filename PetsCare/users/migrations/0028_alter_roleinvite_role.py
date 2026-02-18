# Обновление choices для поля role в RoleInvite (добавлены owner, provider_manager, provider_admin).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0027_fix_roleinvite_created_by_fk_to_users_user"),
    ]

    operations = [
        migrations.AlterField(
            model_name="roleinvite",
            name="role",
            field=models.CharField(
                choices=[
                    ("employee", "Employee"),
                    ("billing_manager", "Billing Manager"),
                    ("owner", "Owner"),
                    ("provider_manager", "Provider manager"),
                    ("provider_admin", "Provider admin"),
                ],
                help_text="Role to assign",
                max_length=20,
                verbose_name="Role",
            ),
        ),
    ]
