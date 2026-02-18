# Generated manually to add provider_location to SchedulePattern

from django.db import migrations, models
import django.db.models.deletion


def delete_all_schedule_patterns(apps, schema_editor):
    """
    Удаляет все записи SchedulePattern перед добавлением обязательного поля provider_location.
    """
    SchedulePattern = apps.get_model('providers', 'SchedulePattern')
    SchedulePattern.objects.all().delete()


def reverse_delete_all_schedule_patterns(apps, schema_editor):
    """
    Обратная операция - не требуется, так как мы просто удаляем записи.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0009_add_employee_locations_and_schedule_location'),
    ]

    operations = [
        # Удаляем все SchedulePattern перед добавлением обязательного поля
        migrations.RunPython(
            delete_all_schedule_patterns,
            reverse_delete_all_schedule_patterns,
        ),
        
        # Добавляем ForeignKey provider_location в SchedulePattern как nullable
        migrations.AddField(
            model_name='schedulepattern',
            name='provider_location',
            field=models.ForeignKey(
                null=True,  # Временно nullable
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='schedule_patterns',
                to='providers.providerlocation',
                verbose_name='Provider Location',
                help_text='Location this schedule pattern belongs to'
            ),
        ),
        
        # Делаем поле обязательным (так как все SchedulePattern удалены, это безопасно)
        migrations.AlterField(
            model_name='schedulepattern',
            name='provider_location',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='schedule_patterns',
                to='providers.providerlocation',
                verbose_name='Provider Location',
                help_text='Location this schedule pattern belongs to'
            ),
        ),
        
        # Обновляем индексы
        migrations.AlterIndexTogether(
            name='schedulepattern',
            index_together=set(),
        ),
        
        # Добавляем новые индексы
        migrations.AddIndex(
            model_name='schedulepattern',
            index=models.Index(fields=['provider_location', 'name'], name='providers_s_provide_123abc_idx'),
        ),
    ]

