"""Утилиты для хранения служебной metadata ручных бронирований в notes."""

from __future__ import annotations

import json
from typing import Any


MANUAL_BOOKING_META_PREFIX = '[manual-booking-meta]'


def build_manual_booking_notes(*, metadata: dict[str, Any], notes: str = '') -> str:
    """Собирает notes с префиксом metadata для ручного бронирования."""
    payload = json.dumps(metadata, ensure_ascii=True, separators=(',', ':'))
    clean_notes = notes.strip()
    if clean_notes:
        return f'{MANUAL_BOOKING_META_PREFIX}{payload}\n{clean_notes}'
    return f'{MANUAL_BOOKING_META_PREFIX}{payload}'


def extract_manual_booking_metadata(notes: str | None) -> dict[str, Any] | None:
    """Извлекает metadata ручного бронирования из notes."""
    if not notes:
        return None
    if not notes.startswith(MANUAL_BOOKING_META_PREFIX):
        return None

    first_line, _, _ = notes.partition('\n')
    raw_payload = first_line[len(MANUAL_BOOKING_META_PREFIX):].strip()
    if not raw_payload:
        return None

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def strip_manual_booking_metadata(notes: str | None) -> str:
    """Возвращает пользовательскую часть notes без служебной metadata."""
    if not notes:
        return ''
    if not notes.startswith(MANUAL_BOOKING_META_PREFIX):
        return notes
    _, _, remainder = notes.partition('\n')
    return remainder


def replace_manual_booking_notes(notes: str | None, new_display_notes: str) -> str:
    """Обновляет пользовательскую часть notes, сохраняя служебную metadata."""
    metadata = extract_manual_booking_metadata(notes)
    if metadata is None:
        return new_display_notes
    return build_manual_booking_notes(metadata=metadata, notes=new_display_notes)
