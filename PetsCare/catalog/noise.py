"""
Utilities for identifying test/noise catalog services.
"""

from __future__ import annotations

from django.db.models import Q


NOISE_NAME_FRAGMENTS = [
    "Admin Ops",
    "Billing Demo",
    "Billing E2E",
    "E2E Bath",
    "Org Pricing",
]

NOISE_CODE_PREFIXES = [
    "admin_ops",
    "billing_demo",
    "billing_e2e",
    "e2e_",
    "org_pricing",
]


def build_noise_service_query(*, name_fragments: list[str] | None = None, code_prefixes: list[str] | None = None) -> Q:
    """Возвращает Q-условие для поиска тестовых/служебных шумовых услуг."""
    query = Q()
    for fragment in name_fragments or NOISE_NAME_FRAGMENTS:
        query |= Q(name__icontains=fragment)
        query |= Q(name_en__icontains=fragment)
    for prefix in code_prefixes or NOISE_CODE_PREFIXES:
        query |= Q(code__istartswith=prefix)
    return query
