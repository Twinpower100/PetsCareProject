from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0004_fix_user_fks'),
    ]

    operations = [
        migrations.DeleteModel(
            name='EmployeeSchedule',
        ),
        migrations.DeleteModel(
            name='ServicePriority',
        ),
        migrations.DeleteModel(
            name='StaffingRequirement',
        ),
        migrations.DeleteModel(
            name='WorkplaceAllowedServices',
        ),
        migrations.DeleteModel(
            name='Workplace',
        ),
    ]
