"""
Единый согласованный каталог типов документов питомца.

Модуль используется как единый source of truth для:
- выбора типа документа в модели DocumentType
- синхронизации технического кода и локализованных названий
- сидирования базы данных миграциями
- порядка отображения в API и админке
"""

from dataclasses import dataclass

from django.db.models import Case, IntegerField, Value, When


@dataclass(frozen=True)
class DocumentTypeDefinition:
    """Описание согласованного типа документа питомца."""

    code: str
    name: str
    name_en: str
    name_ru: str
    name_me: str
    name_de: str
    description: str
    requires_issue_date: bool = False
    requires_expiry_date: bool = False
    requires_issuing_authority: bool = False
    requires_document_number: bool = False


DOCUMENT_TYPE_DEFINITIONS = (
    DocumentTypeDefinition(
        code='passport_identification',
        name='Passport / identification',
        name_en='Passport / identification',
        name_ru='Паспорт / идентификация',
        name_me='Pasos / identifikacija',
        name_de='Pass / Identifikation',
        description='Passport, microchip and other pet identification documents.',
    ),
    DocumentTypeDefinition(
        code='veterinary_certificate',
        name='Veterinary certificate',
        name_en='Veterinary certificate',
        name_ru='Ветеринарная справка / сертификат',
        name_me='Veterinarska potvrda / sertifikat',
        name_de='Veterinaerbescheinigung / Zertifikat',
        description='Official veterinary certificates and reference documents.',
        requires_issue_date=True,
    ),
    DocumentTypeDefinition(
        code='lab_results',
        name='Laboratory results',
        name_en='Laboratory results',
        name_ru='Анализы',
        name_me='Analize',
        name_de='Laborergebnisse',
        description='Laboratory results such as blood, urine, PCR and histology tests.',
        requires_issue_date=True,
    ),
    DocumentTypeDefinition(
        code='diagnostics',
        name='Diagnostics',
        name_en='Diagnostics',
        name_ru='Диагностика',
        name_me='Dijagnostika',
        name_de='Diagnostik',
        description='Diagnostic studies such as X-ray, ultrasound, CT, MRI and related reports.',
        requires_issue_date=True,
    ),
    DocumentTypeDefinition(
        code='discharge_doctor_orders',
        name='Discharge / doctor orders',
        name_en='Discharge / doctor orders',
        name_ru='Выписка / назначения врача',
        name_me='Otpusno pismo / preporuke veterinara',
        name_de='Entlassung / Anordnungen des Tierarztes',
        description='Discharge papers, recommendations, prescriptions and doctor instructions.',
        requires_issue_date=True,
    ),
)

DOCUMENT_TYPE_NAME_CHOICES = tuple(
    (definition.name, definition.name)
    for definition in DOCUMENT_TYPE_DEFINITIONS
)

DOCUMENT_TYPE_ALLOWED_EXTENSIONS = (
    '.pdf',
    '.jpg',
    '.jpeg',
    '.png',
)

DOCUMENT_TYPE_ALLOWED_MIME_TYPES = (
    'application/pdf',
    'image/jpeg',
    'image/png',
)

OWNER_PET_CARD_DOCUMENT_CONTEXT = 'owner_pet_card'
PROVIDER_VISIT_DOCUMENT_CONTEXT = 'provider_visit'
LEGACY_DEFAULT_DOCUMENT_TYPE_CODE = 'discharge_doctor_orders'

PROVIDER_VISIT_DOCUMENT_TYPE_CODES = (
    'lab_results',
    'diagnostics',
    'discharge_doctor_orders',
)

DOCUMENT_TYPE_CODES_BY_CONTEXT = {
    OWNER_PET_CARD_DOCUMENT_CONTEXT: tuple(
        definition.code for definition in DOCUMENT_TYPE_DEFINITIONS
    ),
    PROVIDER_VISIT_DOCUMENT_CONTEXT: PROVIDER_VISIT_DOCUMENT_TYPE_CODES,
}

_DOCUMENT_TYPES_BY_NAME = {
    definition.name: definition
    for definition in DOCUMENT_TYPE_DEFINITIONS
}
_DOCUMENT_TYPES_BY_CODE = {
    definition.code: definition
    for definition in DOCUMENT_TYPE_DEFINITIONS
}


def get_document_type_definition_by_name(name):
    """Возвращает описание типа документа по согласованному имени."""

    return _DOCUMENT_TYPES_BY_NAME.get(name)


def get_document_type_definition_by_code(code):
    """Возвращает описание типа документа по техническому коду."""

    return _DOCUMENT_TYPES_BY_CODE.get(code)


def get_document_type_codes_for_context(context):
    """Возвращает допустимые коды типов документов для заданного контекста."""

    return DOCUMENT_TYPE_CODES_BY_CONTEXT.get(context)


def get_legacy_default_document_type_code():
    """Возвращает согласованный fallback-код для deprecated write-путей."""

    return LEGACY_DEFAULT_DOCUMENT_TYPE_CODE


def get_document_type_order_expression(field_name='code'):
    """Возвращает выражение для стабильной сортировки типов документов."""

    return Case(
        *[
            When(**{field_name: definition.code}, then=Value(index))
            for index, definition in enumerate(DOCUMENT_TYPE_DEFINITIONS)
        ],
        default=Value(len(DOCUMENT_TYPE_DEFINITIONS)),
        output_field=IntegerField(),
    )
