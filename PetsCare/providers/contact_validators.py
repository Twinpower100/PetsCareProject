"""
Валидаторы контактных данных (телефон, email) для провайдера и локаций.

Используются в Provider и ProviderLocation для проверки формата
телефона (E.164-подобный, 10–15 цифр) и email.
Сообщения об ошибках — на английском, обёрнуты в _() для мультиязычности.
"""

import re
from typing import Tuple, Optional

from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


# Допустимые символы в телефоне: цифры, + в начале, пробелы, дефисы, скобки
PHONE_ALLOWED_PATTERN = re.compile(r'^\+?[\d\s\-\(\)]+$')
# Минимум/максимум цифр в номере (E.164-подобный)
PHONE_DIGITS_MIN = 10
PHONE_DIGITS_MAX = 15


def validate_phone_contact(value: str) -> Tuple[bool, Optional[str]]:
    """
    Валидация формата контактного телефона (локация или организация).

    Допускаются: цифры, + в начале, пробелы, дефисы, скобки.
    Количество цифр: от 10 до 15 (E.164-подобный формат).

    Args:
        value: Строка телефона для проверки.

    Returns:
        (True, None) если валидно, иначе (False, сообщение об ошибке).
    """
    if not value or not isinstance(value, str):
        return False, _('Phone number is required.')
    stripped = value.strip()
    if not stripped:
        return False, _('Phone number is required.')
    if not PHONE_ALLOWED_PATTERN.match(stripped):
        return False, _('Phone number may only contain digits, plus sign, spaces, hyphens, and parentheses.')
    digits_only = re.sub(r'\D', '', stripped)
    if len(digits_only) < PHONE_DIGITS_MIN:
        return False, _('Phone number must contain at least %(min)s digits.') % {'min': PHONE_DIGITS_MIN}
    if len(digits_only) > PHONE_DIGITS_MAX:
        return False, _('Phone number must contain at most %(max)s digits.') % {'max': PHONE_DIGITS_MAX}
    return True, None


def validate_email_contact(value: str) -> Tuple[bool, Optional[str]]:
    """
    Валидация формата email (базовый формат: локальная часть @ домен).

    Django EmailField уже проверяет формат; эта функция даёт единообразное
    сообщение и дополнительную проверку длины/символов при необходимости.

    Args:
        value: Строка email для проверки.

    Returns:
        (True, None) если формат допустим, иначе (False, сообщение об ошибке).
    """
    if not value or not isinstance(value, str):
        return False, _('Email is required.')
    stripped = value.strip()
    if not stripped:
        return False, _('Email is required.')
    # Базовый формат: есть ровно один @ и непустые части
    if stripped.count('@') != 1:
        return False, _('Enter a valid email address.')
    local, domain = stripped.split('@', 1)
    if not local or not domain or '.' not in domain:
        return False, _('Enter a valid email address.')
    if len(stripped) > 254:
        return False, _('Email address is too long.')
    return True, None
