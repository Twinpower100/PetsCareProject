"""
Сервисы для расчета задолженности и уровней блокировки провайдеров.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from providers.models import EmployeeProvider, Provider

from .models import (
    BlockingNotification,
    BlockingSystemSettings,
    ProviderBlocking,
)

logger = logging.getLogger(__name__)

# Короткий TTL-кэш результата проверки блокировки на провайдера.
# Снимает нагрузку с middleware, который дёргает 4–5 запросов к БД на каждый
# API-запрос (calculate_debt, get_max_overdue_days, get_blocking_thresholds,
# has_active_offer_acceptance, ProviderBlocking lookup). 10 секунд достаточно
# мало, чтобы пользователь не видел залежавшийся баннер после оплаты долга.
BLOCKING_CHECK_CACHE_TTL = 10
BLOCKING_CHECK_CACHE_KEY = "billing:blocking_check:provider:{provider_id}"


def invalidate_provider_blocking_cache(provider_id: int) -> None:
    """Сбрасывает кэш проверки блокировки. Вызывать при оплате/изменении статуса."""
    cache.delete(BLOCKING_CHECK_CACHE_KEY.format(provider_id=provider_id))


class MultiLevelBlockingService:
    """
    Единый источник истины для расчета и применения блокировок.

    Сервис:
    - рассчитывает уровень блокировки из фактической задолженности,
    - создает или обновляет активную запись ProviderBlocking,
    - снимает блокировку, когда оснований больше нет,
    - формирует уведомления для администраторов провайдера.
    """

    def __init__(self):
        self.settings = BlockingSystemSettings.get_settings()

    def check_provider_blocking(self, provider: Provider, *, use_cache: bool = True) -> Dict[str, Any]:
        """
        Возвращает нормализованный результат проверки блокировки провайдера.

        Параметр ``use_cache`` включает локальный TTL-кэш (10 секунд) для горячего
        пути middleware. Hot-path (apply_blocking, ручные пересчёты) проходят с
        ``use_cache=False``.
        """
        cache_key = BLOCKING_CHECK_CACHE_KEY.format(provider_id=provider.id)
        cached_payload = cache.get(cache_key) if use_cache else None
        if cached_payload is not None:
            # Кэшируем только сериализуемую часть; provider/active_blocking подцепляем заново.
            active_blocking = ProviderBlocking.objects.filter(
                provider=provider,
                status='active',
            ).only('id', 'blocking_level', 'status', 'blocked_at').order_by('-blocked_at').first()
            return {**cached_payload, 'provider': provider, 'active_blocking': active_blocking}

        if provider.exclude_from_blocking_checks:
            return {
                'provider': provider,
                'should_block': False,
                'blocking_level': 0,
                'reasons': [],
                'reason': 'Provider excluded from automatic blocking checks',
            }

        if not provider.has_active_offer_acceptance():
            return {
                'provider': provider,
                'should_block': False,
                'blocking_level': 0,
                'reasons': [],
                'reason': 'Provider has no active offer acceptance',
            }

        debt_info = provider.calculate_debt()
        overdue_days = provider.get_max_overdue_days()
        thresholds = provider.get_blocking_thresholds()

        blocking_level = self._resolve_blocking_level(
            overdue_debt=debt_info['overdue_debt'],
            overdue_days=overdue_days,
            thresholds=thresholds,
        )
        reasons = self._build_reasons(
            overdue_debt=debt_info['overdue_debt'],
            overdue_days=overdue_days,
            thresholds=thresholds,
            blocking_level=blocking_level,
        )

        active_blocking = ProviderBlocking.objects.filter(
            provider=provider,
            status='active',
        ).order_by('-blocked_at').first()

        result = {
            'provider': provider,
            'should_block': blocking_level > 0,
            'blocking_level': blocking_level,
            'reasons': reasons,
            'reason': reasons[0] if reasons else None,
            'debt_info': debt_info,
            'overdue_days': overdue_days,
            'thresholds': thresholds,
            'active_blocking': active_blocking,
        }

        if use_cache:
            cacheable = {k: v for k, v in result.items() if k not in ('provider', 'active_blocking')}
            try:
                cache.set(cache_key, cacheable, timeout=BLOCKING_CHECK_CACHE_TTL)
            except Exception as exc:
                logger.debug("Failed to cache blocking check for provider=%s: %s", provider.id, exc)

        return result

    def _resolve_blocking_level(
        self,
        *,
        overdue_debt: Decimal,
        overdue_days: int,
        thresholds: Dict[str, Any],
    ) -> int:
        """
        Рассчитывает уровень по региональной политике: просроченный долг vs допуск, дни vs L2/L3.
        """
        tolerance = Decimal(str(thresholds.get('tolerance_amount') or '0'))
        l2 = int(thresholds.get('overdue_days_l2_from') or 0)
        l3 = int(thresholds.get('overdue_days_l3_from') or 0)
        od = Decimal(overdue_debt)

        if od <= tolerance:
            return 0
        if l2 <= 0:
            return 0
        if overdue_days < l2:
            return 1
        if l3 <= 0 or overdue_days < l3:
            return 2
        return 3

    def _build_reasons(
        self,
        *,
        overdue_debt: Decimal,
        overdue_days: int,
        thresholds: Dict[str, Any],
        blocking_level: int,
    ) -> List[str]:
        """
        Формирует список причин для UI, логов и уведомлений.
        """
        if blocking_level == 0:
            return []

        reasons: List[str] = []
        tolerance = thresholds.get('tolerance_amount')
        l2 = thresholds.get('overdue_days_l2_from')
        l3 = thresholds.get('overdue_days_l3_from')
        region = thresholds.get('blocking_region_code') or ''

        reasons.append(
            _("Overdue debt %(debt)s exceeds tolerance %(tol)s (region %(region)s)") % {
                'debt': overdue_debt,
                'tol': tolerance,
                'region': region,
            }
        )

        if blocking_level == 3 and l3 is not None:
            reasons.append(
                _("Level 3: overdue days %(days)s >= %(threshold)s") % {
                    'days': overdue_days,
                    'threshold': l3,
                }
            )
        elif blocking_level == 2 and l2 is not None:
            reasons.append(
                _("Level 2: overdue days %(days)s >= %(l2)s and < %(l3)s") % {
                    'days': overdue_days,
                    'l2': l2,
                    'l3': l3,
                }
            )
        elif blocking_level == 1:
            reasons.append(
                _("Level 1: overdue days %(days)s < %(l2)s") % {
                    'days': overdue_days,
                    'l2': l2,
                }
            )

        return reasons

    @transaction.atomic
    def apply_blocking(
        self,
        provider: Provider,
        blocking_level: int,
        reasons: List[str],
        *,
        debt_info: Optional[Dict[str, Any]] = None,
        overdue_days: Optional[int] = None,
        thresholds: Optional[Dict[str, Any]] = None,
    ) -> ProviderBlocking:
        """
        Создает или обновляет активную блокировку нужного уровня.
        """
        debt_info = debt_info or provider.calculate_debt()
        overdue_days = overdue_days if overdue_days is not None else provider.get_max_overdue_days()
        thresholds = thresholds or provider.get_blocking_thresholds()

        active_blockings = list(
            ProviderBlocking.objects.select_for_update().filter(
                provider=provider,
                status='active',
            )
        )

        current_blocking = next(
            (blocking for blocking in active_blockings if blocking.blocking_level == blocking_level),
            None,
        )

        for blocking in active_blockings:
            if current_blocking is None or blocking.id != current_blocking.id:
                blocking.resolve(notes='Superseded by a new billing blocking evaluation')

        notes = '; '.join(reasons)

        if current_blocking:
            current_blocking.debt_amount = debt_info['total_debt']
            current_blocking.overdue_days = overdue_days
            current_blocking.currency = debt_info['currency']
            current_blocking.notes = notes
            current_blocking.save(
                update_fields=[
                    'debt_amount',
                    'overdue_days',
                    'currency',
                    'notes',
                ]
            )
            blocking = current_blocking
            blocking_changed = False
        else:
            blocking = ProviderBlocking.objects.create(
                provider=provider,
                blocking_level=blocking_level,
                status='active',
                debt_amount=debt_info['total_debt'],
                overdue_days=overdue_days,
                currency=debt_info['currency'],
                notes=notes,
            )
            blocking_changed = True

        if blocking_level == 1:
            self._ensure_warning_notification(blocking)
        elif blocking_changed:
            self._create_notifications(blocking)

        if self.settings.log_all_checks:
            logger.info(
                "Provider %s evaluated to blocking level %s (debt=%s, overdue_days=%s)",
                provider.id,
                blocking_level,
                debt_info['total_debt'],
                overdue_days,
            )

        invalidate_provider_blocking_cache(provider.id)
        return blocking

    @transaction.atomic
    def resolve_provider_blocking(self, provider: Provider, notes: str = '') -> int:
        """
        Снимает все активные блокировки провайдера.
        """
        active_blockings = ProviderBlocking.objects.select_for_update().filter(
            provider=provider,
            status='active',
        )
        resolved_count = 0
        for blocking in active_blockings:
            blocking.resolve(notes=notes or 'Billing debt resolved')
            self._create_resolution_notification(blocking)
            resolved_count += 1
        if resolved_count:
            invalidate_provider_blocking_cache(provider.id)
        return resolved_count

    def check_all_providers(self) -> Dict[str, Any]:
        """
        Выполняет полную проверку всех активных провайдеров.
        """
        providers = Provider.objects.filter(is_active=True)
        stats = {
            'total_providers': providers.count(),
            'checked_providers': 0,
            'blocked_providers': 0,
            'resolved_blockings': 0,
            'warnings': 0,
            'errors': [],
        }

        for provider in providers.iterator():
            try:
                result = self.check_provider_blocking(provider)
                stats['checked_providers'] += 1

                if result['should_block']:
                    self.apply_blocking(
                        provider,
                        result['blocking_level'],
                        result['reasons'],
                        debt_info=result['debt_info'],
                        overdue_days=result['overdue_days'],
                        thresholds=result['thresholds'],
                    )
                    stats['blocked_providers'] += 1
                    if result['blocking_level'] == 1:
                        stats['warnings'] += 1
                else:
                    stats['resolved_blockings'] += self.resolve_provider_blocking(
                        provider,
                        notes='Billing blocking automatically removed after reevaluation',
                    )
            except Exception as exc:
                logger.exception("Error while checking provider %s for billing blocking", provider.id)
                stats['errors'].append(f"Provider {provider.id}: {exc}")

        return stats

    def _create_notifications(self, blocking: ProviderBlocking) -> None:
        """
        Создает уведомления о включении блокировки.
        """
        recipients = self._get_notification_recipients(blocking.provider)
        for recipient in recipients:
            BlockingNotification.objects.create(
                provider_blocking=blocking,
                notification_type='blocking_activated',
                status='pending',
                recipient_email=recipient.get('email', ''),
                recipient_phone=recipient.get('phone', ''),
                subject=_("Provider billing blocking level %(level)s") % {
                    'level': blocking.blocking_level,
                },
                message=self._build_notification_message(blocking),
            )

    def _ensure_warning_notification(self, blocking: ProviderBlocking) -> None:
        """
        Создает warning-уведомление для уровня 1 только один раз на активную блокировку.
        """
        if blocking.notifications.filter(notification_type='blocking_warning').exists():
            return

        recipients = self._get_notification_recipients(blocking.provider)
        for recipient in recipients:
            BlockingNotification.objects.create(
                provider_blocking=blocking,
                notification_type='blocking_warning',
                status='pending',
                recipient_email=recipient.get('email', ''),
                recipient_phone=recipient.get('phone', ''),
                subject=_("Provider payment warning"),
                message=self._build_notification_message(blocking),
            )

    def _create_resolution_notification(self, blocking: ProviderBlocking) -> None:
        """
        Создает уведомление о снятии блокировки.
        """
        recipients = self._get_notification_recipients(blocking.provider)
        for recipient in recipients:
            BlockingNotification.objects.create(
                provider_blocking=blocking,
                notification_type='blocking_resolved',
                status='pending',
                recipient_email=recipient.get('email', ''),
                recipient_phone=recipient.get('phone', ''),
                subject=_("Provider billing blocking resolved"),
                message=_("Provider %(provider)s is no longer blocked for billing reasons.") % {
                    'provider': blocking.provider.name,
                },
            )

    def _get_notification_recipients(self, provider: Provider) -> List[Dict[str, str]]:
        """
        Возвращает получателей уведомлений для организации.
        """
        recipients: List[Dict[str, str]] = []
        admin_links = EmployeeProvider.get_active_admin_links(provider)
        for admin_link in admin_links:
            user = admin_link.employee.user
            if user.email:
                recipients.append({
                    'email': user.email,
                    'phone': getattr(user, 'phone_number', '') or '',
                })

        if not recipients and provider.email:
            recipients.append({
                'email': provider.email,
                'phone': provider.phone_number or '',
            })

        return recipients

    def _build_notification_message(self, blocking: ProviderBlocking) -> str:
        """
        Формирует стандартное тело уведомления по блокировке.
        """
        return _(
            "Provider %(provider)s has billing blocking level %(level)s. "
            "Debt: %(debt)s %(currency)s. Overdue days: %(days)s."
        ) % {
            'provider': blocking.provider.name,
            'level': blocking.blocking_level,
            'debt': blocking.debt_amount,
            'currency': blocking.currency.code,
            'days': blocking.overdue_days,
        }
