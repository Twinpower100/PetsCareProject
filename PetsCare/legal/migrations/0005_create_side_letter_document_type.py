# Generated manually for creating side_letter document type

from django.db import migrations


def create_side_letter_type(apps, schema_editor):
    """
    Создает тип документа side_letter в LegalDocumentType.
    """
    LegalDocumentType = apps.get_model('legal', 'LegalDocumentType')
    
    # Проверяем, не существует ли уже этот тип
    if not LegalDocumentType.objects.filter(code='side_letter').exists():
        LegalDocumentType.objects.create(
            code='side_letter',
            name='Side Letter',
            description='Additional agreement (Side Letter) for large clients. Paper document that modifies individual clauses of the public offer.',
            requires_billing_config=False,
            requires_region_code=False,
            requires_addendum_type=False,
            allows_variables=True,
            is_required_for_all_countries=False,
            is_multiple_allowed=True,  # Один провайдер может иметь несколько Side Letter
            is_active=True,
            display_order=5,
            requires_provider=True,  # Требует провайдера
            allows_financial_terms=True,  # Разрешает финансовые условия
        )


def reverse_side_letter_type(apps, schema_editor):
    """
    Удаляет тип документа side_letter.
    """
    LegalDocumentType = apps.get_model('legal', 'LegalDocumentType')
    LegalDocumentType.objects.filter(code='side_letter').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('legal', '0004_add_side_letter_fields'),
    ]

    operations = [
        migrations.RunPython(create_side_letter_type, reverse_side_letter_type),
    ]
