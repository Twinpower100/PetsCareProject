# Удаление legacy-полей is_valid и is_validated из Address.
# Каноническое поле состояния валидации — validation_status (см. ADDRESS_GEOLOCATION_AND_VALIDATION_SOLUTION.md).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('geolocation', '0007_remove_location_searchradius_locationhistory'),
    ]

    operations = [
        migrations.RemoveField(model_name='address', name='is_valid'),
        migrations.RemoveField(model_name='address', name='is_validated'),
    ]
