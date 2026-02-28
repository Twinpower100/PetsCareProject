# Удаление модели EmployeeJoinRequest: в продукте только инвайты, сценарий
# «пользователь просится в организацию» исключён из требований.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0041_remove_owner_from_provider_owner_manager_invite'),
    ]

    operations = [
        migrations.DeleteModel(name='EmployeeJoinRequest'),
    ]
