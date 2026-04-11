"""
Коды региона для политики блокировок: DEFAULT, EU, ISO-страны (django-countries).

Используется в админке (выпадающий список) и валидации RegionalBlockingPolicy.
"""

from __future__ import annotations

from typing import List, Tuple

from django.utils.translation import gettext_lazy as _


def get_region_code_choice_tuples() -> List[Tuple[str, str]]:
    """Список (код, подпись) для Select: сначала DEFAULT и EU, затем страны ISO."""
    from django_countries import countries

    rows: List[Tuple[str, str]] = [
        (
            'DEFAULT',
            str(
                _(
                    'DEFAULT — fallback if there is no row for the provider’s resolved code '
                    '(country / EU / override)'
                )
            ),
        ),
        (
            'EU',
            str(_('EU — European Union aggregate (all EU member states)')),
        ),
    ]
    seen = {code for code, _ in rows}
    for code, name in countries:
        if code in seen:
            continue
        rows.append((code, f'{name} ({code})'))
        seen.add(code)
    return rows


def is_allowed_region_code(code: str) -> bool:
    code = (code or '').strip().upper()
    if not code:
        return False
    allowed = {c for c, _ in get_region_code_choice_tuples()}
    return code in allowed
