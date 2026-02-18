# Generated manually to handle SchedulePattern and Schedule changes

from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


def remove_provider_from_schedulepattern(apps, schema_editor):
    """
    Удаляет поле provider из SchedulePattern, если оно существует.
    Теперь используется provider_location.
    """
    with schema_editor.connection.cursor() as cursor:
        # Проверяем, существует ли поле provider_id
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='providers_schedulepattern' AND column_name='provider_id'
        """)
        if cursor.fetchone():
            # Удаляем поле
            cursor.execute("""
                ALTER TABLE providers_schedulepattern 
                DROP COLUMN provider_id
            """)


def reverse_remove_provider_from_schedulepattern(apps, schema_editor):
    """
    Обратная операция - не восстанавливаем поле provider, так как оно больше не используется.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0010_add_provider_location_to_schedulepattern'),
    ]

    operations = [
        # Удаляем поле provider из SchedulePattern
        # Используем SeparateDatabaseAndState, чтобы безопасно обработать случай, когда поле уже удалено
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    remove_provider_from_schedulepattern,
                    reverse_remove_provider_from_schedulepattern,
                ),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name='schedulepattern',
                    name='provider',
                ),
            ],
        ),
        # Обновляем Meta опции для Schedule
        migrations.AlterModelOptions(
            name='schedule',
            options={'ordering': ['employee', 'provider_location', 'day_of_week'], 'verbose_name': 'Schedule', 'verbose_name_plural': 'Schedules'},
        ),
        # Обновляем Meta опции для SchedulePattern
        migrations.AlterModelOptions(
            name='schedulepattern',
            options={'ordering': ['provider_location', 'name'], 'verbose_name': 'Schedule Pattern', 'verbose_name_plural': 'Schedule Patterns'},
        ),
        # Индексы будут синхронизированы следующей миграцией Django
        # Не добавляем их здесь, чтобы Django мог правильно определить, какие индексы нужны
        # Обновляем поля tax_id и registration_number в Provider
        # Изменения в валидаторах не требуют изменений в БД, но Django их обнаруживает
        # Используем SeparateDatabaseAndState для синхронизации состояния без изменений в БД
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # Нет изменений в БД для валидаторов
            state_operations=[
                migrations.AlterField(
                    model_name='provider',
                    name='tax_id',
                    field=models.CharField(
                        blank=True,
                        help_text='Tax identification number / INN (unique, required for approval). Format: letters, digits, spaces, hyphens. Minimum 3 characters.',
                        max_length=50,
                        null=True,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                message='Tax ID can only contain letters, digits, spaces, and hyphens.',
                                regex='^[a-zA-Zа-яА-ЯёЁ0-9\\s-]+$'
                            ),
                            django.core.validators.MinLengthValidator(3, message='Tax ID must be at least 3 characters long.')
                        ],
                        verbose_name='Tax ID / INN'
                    ),
                ),
                migrations.AlterField(
                    model_name='provider',
                    name='registration_number',
                    field=models.CharField(
                        blank=True,
                        help_text='Registration number (unique, required for approval). Format: letters, digits, spaces, hyphens. Minimum 3 characters.',
                        max_length=100,
                        null=True,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                message='Registration number can only contain letters, digits, spaces, and hyphens.',
                                regex='^[a-zA-Zа-яА-ЯёЁ0-9\\s-]+$'
                            ),
                            django.core.validators.MinLengthValidator(3, message='Registration number must be at least 3 characters long.')
                        ],
                        verbose_name='Registration Number'
                    ),
                ),
            ],
        ),
    ]

