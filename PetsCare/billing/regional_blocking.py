"""
Региональные политики блокировок: сопоставление провайдера с политикой и пороги в валюте счёта.
"""

from decimal import Decimal
from typing import Any, Dict, Optional

from django.conf import settings

from .models import RegionalBlockingPolicy


def resolve_blocking_region_code(provider) -> str:
    """
    Возвращает код региона политики блокировок для провайдера.

    Приоритет: явное поле blocking_region_code → страна EU → код страны → DEFAULT.
    """
    explicit = getattr(provider, 'blocking_region_code', None) or ''
    if explicit.strip():
        return explicit.strip().upper()

    country = getattr(provider, 'country', None)
    country_code = ''
    if country is not None:
        country_code = getattr(country, 'code', None) or str(country) or ''
    country_code = (country_code or '').upper()
    if not country_code:
        return 'DEFAULT'

    from utils.countries import is_eu_country

    if is_eu_country(country_code):
        return 'EU'
    return country_code


def get_active_policy_for_region(region_code: str) -> Optional[RegionalBlockingPolicy]:
    """Активная строка политики для кода региона или DEFAULT."""
    code = (region_code or 'DEFAULT').upper()
    policy = (
        RegionalBlockingPolicy.objects.filter(region_code=code, is_active=True)
        .select_related('currency')
        .first()
    )
    if policy is None and code != 'DEFAULT':
        policy = (
            RegionalBlockingPolicy.objects.filter(region_code='DEFAULT', is_active=True)
            .select_related('currency')
            .first()
        )
    return policy


def tolerance_in_provider_currency(
    policy: RegionalBlockingPolicy,
    provider,
) -> Decimal:
    """Переводит допуск из валюты политики в валюту счёта провайдера."""
    if policy is None:
        return Decimal('0.00')
    amount = policy.tolerance_amount
    if amount is None:
        return Decimal('0.00')
    pc = getattr(provider, 'invoice_currency', None)
    if pc is None:
        return amount
    cur = policy.currency
    if cur.id == pc.id:
        return amount
    return cur.convert_amount(amount, pc)


def resolve_blocking_thresholds_for_provider(provider) -> Dict[str, Any]:
    """
    Собирает словарь порогов для MultiLevelBlockingService и UI.

    Использует просроченную задолженность против tolerance_amount в валюте счёта;
    дни сравниваются с overdue_days_l2_from и overdue_days_l3_from.
    """
    region_code = resolve_blocking_region_code(provider)
    policy = get_active_policy_for_region(region_code)
    if policy is None:
        return _fallback_thresholds(region_code)

    tolerance = tolerance_in_provider_currency(policy, provider)
    pc_code = policy.currency.code if policy.currency_id else 'EUR'
    return {
        'blocking_region_code': region_code,
        'policy_currency_code': pc_code,
        'tolerance_amount': tolerance,
        'overdue_days_l2_from': policy.overdue_days_l2_from,
        'overdue_days_l3_from': policy.overdue_days_l3_from,
        'debt_threshold': None,
        'overdue_threshold_1': policy.overdue_days_l2_from,
        'overdue_threshold_2': policy.overdue_days_l2_from,
        'overdue_threshold_3': policy.overdue_days_l3_from,
    }


def _fallback_thresholds(region_code: str) -> Dict[str, Any]:
    """Дефолты из settings, если в БД нет политики."""
    bs = getattr(settings, 'BLOCKING_SETTINGS', {})
    l2 = int(bs.get('DEFAULT_OVERDUE_DAYS_L2_FROM', 60))
    l3 = int(bs.get('DEFAULT_OVERDUE_DAYS_L3_FROM', 90))
    tol = Decimal(str(bs.get('DEFAULT_TOLERANCE_AMOUNT', '5.00')))
    return {
        'blocking_region_code': region_code,
        'policy_currency_code': 'EUR',
        'tolerance_amount': tol,
        'overdue_days_l2_from': l2,
        'overdue_days_l3_from': l3,
        'debt_threshold': None,
        'overdue_threshold_1': l2,
        'overdue_threshold_2': l2,
        'overdue_threshold_3': l3,
    }
