# Удаление неиспользуемых моделей: Location, SearchRadius, LocationHistory.
# В продукте не используются; для позиции пользователя — UserLocation, для адресов — Address.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('geolocation', '0006_add_is_valid_to_address'),
    ]

    operations = [
        migrations.DeleteModel(name='Location'),
        migrations.DeleteModel(name='SearchRadius'),
        migrations.DeleteModel(name='LocationHistory'),
    ]
