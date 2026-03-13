from django.db import migrations, models
import django.core.validators
from django.utils.translation import gettext_lazy as _


CATALOG_TYPES = (
    {
        'code': 'passport_identification',
        'name': 'Паспорт / идентификация',
        'name_en': 'Passport / identification',
        'name_ru': 'Паспорт / идентификация',
        'name_me': 'Pasos / identifikacija',
        'name_de': 'Pass / Identifikation',
        'description': 'Passport, microchip and other pet identification documents.',
        'requires_issue_date': False,
        'requires_expiry_date': False,
        'requires_issuing_authority': False,
        'requires_document_number': False,
        'legacy_codes': ('passport_identification', 'passport'),
        'legacy_names': ('Passport / identification', 'Passport', 'Паспорт / идентификация'),
    },
    {
        'code': 'veterinary_certificate',
        'name': 'Ветеринарная справка / сертификат',
        'name_en': 'Veterinary certificate',
        'name_ru': 'Ветеринарная справка / сертификат',
        'name_me': 'Veterinarska potvrda / sertifikat',
        'name_de': 'Veterinaerbescheinigung / Zertifikat',
        'description': 'Official veterinary certificates and reference documents.',
        'requires_issue_date': True,
        'requires_expiry_date': False,
        'requires_issuing_authority': False,
        'requires_document_number': False,
        'legacy_codes': ('veterinary_certificate',),
        'legacy_names': ('Veterinary certificate', 'Ветеринарная справка / сертификат'),
    },
    {
        'code': 'lab_results',
        'name': 'Анализы',
        'name_en': 'Laboratory results',
        'name_ru': 'Анализы',
        'name_me': 'Analize',
        'name_de': 'Laborergebnisse',
        'description': 'Laboratory results such as blood, urine, PCR and histology tests.',
        'requires_issue_date': True,
        'requires_expiry_date': False,
        'requires_issuing_authority': False,
        'requires_document_number': False,
        'legacy_codes': ('lab_results',),
        'legacy_names': ('Laboratory results', 'Анализы'),
    },
    {
        'code': 'diagnostics',
        'name': 'Диагностика',
        'name_en': 'Diagnostics',
        'name_ru': 'Диагностика',
        'name_me': 'Dijagnostika',
        'name_de': 'Diagnostik',
        'description': 'Diagnostic studies such as X-ray, ultrasound, CT, MRI and related reports.',
        'requires_issue_date': True,
        'requires_expiry_date': False,
        'requires_issuing_authority': False,
        'requires_document_number': False,
        'legacy_codes': ('diagnostics',),
        'legacy_names': ('Diagnostics', 'Диагностика'),
    },
    {
        'code': 'discharge_doctor_orders',
        'name': 'Выписка / назначения врача',
        'name_en': 'Discharge / doctor orders',
        'name_ru': 'Выписка / назначения врача',
        'name_me': 'Otpusno pismo / preporuke veterinara',
        'name_de': 'Entlassung / Anordnungen des Tierarztes',
        'description': 'Discharge papers, recommendations, prescriptions and doctor instructions.',
        'requires_issue_date': True,
        'requires_expiry_date': False,
        'requires_issuing_authority': False,
        'requires_document_number': False,
        'legacy_codes': ('discharge_doctor_orders',),
        'legacy_names': ('Discharge / doctor orders', 'Выписка / назначения врача'),
    },
)


def seed_document_type_catalog(apps, schema_editor):
    """Синхронизирует таблицу типов документов с согласованным каталогом."""
    DocumentType = apps.get_model('pets', 'DocumentType')
    kept_ids = []

    for item in CATALOG_TYPES:
        candidate = DocumentType.objects.filter(code=item['code']).order_by('id').first()
        if candidate is None:
            candidate = DocumentType.objects.filter(code__in=item['legacy_codes']).order_by('id').first()
        if candidate is None:
            candidate = DocumentType.objects.filter(name__in=item['legacy_names']).order_by('id').first()

        defaults = {
            'name': item['name'],
            'name_en': item['name_en'],
            'name_ru': item['name_ru'],
            'name_me': item['name_me'],
            'name_de': item['name_de'],
            'code': item['code'],
            'description': item['description'],
            'requires_issue_date': item['requires_issue_date'],
            'requires_expiry_date': item['requires_expiry_date'],
            'requires_issuing_authority': item['requires_issuing_authority'],
            'requires_document_number': item['requires_document_number'],
            'is_active': True,
        }

        if candidate is None:
            candidate = DocumentType.objects.create(**defaults)
        else:
            for field_name, value in defaults.items():
                setattr(candidate, field_name, value)
            candidate.save(update_fields=list(defaults.keys()) + ['updated_at'])

        kept_ids.append(candidate.id)

    DocumentType.objects.exclude(id__in=kept_ids).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0021_remove_petrecordfile_medical_record_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documenttype',
            name='code',
            field=models.CharField(
                help_text='Canonical technical code synchronized from the approved document catalog.',
                max_length=50,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message='Code must contain only Latin letters, numbers and underscores.',
                        regex='^[a-zA-Z0-9_]+$',
                    )
                ],
                verbose_name='Code',
            ),
        ),
        migrations.AlterField(
            model_name='documenttype',
            name='description',
            field=models.TextField(
                blank=True,
                help_text='Canonical description synchronized from the approved document catalog.',
                verbose_name='Description',
            ),
        ),
        migrations.AlterField(
            model_name='documenttype',
            name='name',
            field=models.CharField(
                choices=[
                    ('Паспорт / идентификация', 'Паспорт / идентификация'),
                    ('Ветеринарная справка / сертификат', 'Ветеринарная справка / сертификат'),
                    ('Анализы', 'Анализы'),
                    ('Диагностика', 'Диагностика'),
                    ('Выписка / назначения врача', 'Выписка / назначения врача'),
                ],
                help_text='Select one of the approved document types.',
                max_length=100,
                verbose_name='Name',
            ),
        ),
        migrations.RunPython(seed_document_type_catalog, migrations.RunPython.noop),
    ]
