# Нормализация реквизитов провайдера для проверки уникальности (FunctionalDesign.md).
# Проверка выполняется по нормализованным значениям: лишние пробелы не должны влиять на результат.

import re


def normalize_tax_id(value: str) -> str:
    """Tax ID / ИНН: убираем все пробелы (проверка без пробелов)."""
    return re.sub(r'\s', '', (value or '').strip())


def normalize_registration_number(value: str) -> str:
    """Registration Number: trim + максимум один пробел между словами."""
    return ' '.join((value or '').strip().split())


def normalize_vat_number(value: str) -> str:
    """VAT Number: удаление пробелов + верхний регистр (FunctionalDesign)."""
    return re.sub(r'\s', '', (value or '').strip()).upper()


def normalize_iban(value: str) -> str:
    """IBAN: убираем все пробелы (часто вводят с пробелами каждые 4 символа)."""
    return re.sub(r'\s', '', (value or '').strip())
