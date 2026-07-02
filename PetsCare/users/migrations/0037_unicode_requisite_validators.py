from django.core.validators import MinLengthValidator
from django.db import migrations, models
import utils.validators


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0036_providerform_ownership_form'),
    ]

    operations = [
        migrations.AlterField(
            model_name='providerform',
            name='registration_number',
            field=models.CharField(
                blank=True,
                help_text='Registration number (required). Format: letters, digits, spaces, hyphens. Minimum 3 characters.',
                max_length=100,
                null=True,
                validators=[
                    utils.validators.LettersDigitsSpacesHyphensValidator(
                        message='Registration number can only contain letters, digits, spaces, and hyphens.'
                    ),
                    MinLengthValidator(3, message='Registration number must be at least 3 characters long.'),
                ],
                verbose_name='Registration Number',
            ),
        ),
        migrations.AlterField(
            model_name='providerform',
            name='tax_id',
            field=models.CharField(
                blank=True,
                help_text='Tax identification number / INN (required). Format: letters, digits, spaces, hyphens. Minimum 3 characters.',
                max_length=50,
                null=True,
                validators=[
                    utils.validators.LettersDigitsSpacesHyphensValidator(
                        message='Tax ID can only contain letters, digits, spaces, and hyphens.'
                    ),
                    MinLengthValidator(3, message='Tax ID must be at least 3 characters long.'),
                ],
                verbose_name='Tax ID / INN',
            ),
        ),
    ]
