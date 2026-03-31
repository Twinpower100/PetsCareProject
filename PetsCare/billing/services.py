"""
Сервисы для расчета задолженности и уровней блокировки провайдеров.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from providers.models import EmployeeProvider, Provider

from .models import (
    BlockingNotification,
    BlockingRule,
    BlockingSystemSettings,
    ProviderBlocking,
)

logger = logging.getLogger(__name__)


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

    def check_provider_blocking(self, provider: Provider) -> Dict[str, Any]:
        """
        Возвращает нормализованный результат проверки блокировки провайдера.
        """
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
            total_debt=debt_info['total_debt'],
            overdue_days=overdue_days,
            thresholds=thresholds,
        )
        reasons = self._build_reasons(
            total_debt=debt_info['total_debt'],
            overdue_debt=debt_info['overdue_debt'],
            overdue_days=overdue_days,
            thresholds=thresholds,
            blocking_level=blocking_level,
        )

        active_blocking = ProviderBlocking.objects.filter(
            provider=provider,
            status='active',
        ).order_by('-blocked_at').first()

        return {
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

    def _resolve_blocking_level(
        self,
        *,
        total_debt: Decimal,
        overdue_days: int,
        thresholds: Dict[str, Any],
    ) -> int:
        """
        Рассчитывает уровень блокировки по общей задолженности и просрочке.
        """
        debt_threshold = thresholds.get('debt_threshold')
        threshold_1 = int(thresholds.get('overdue_threshold_1') or 0)
        threshold_2 = int(thresholds.get('overdue_threshold_2') or 0)
        threshold_3 = int(thresholds.get('overdue_threshold_3') or 0)

        if debt_threshold is not None and Decimal(total_debt) > Decimal(str(debt_threshold)):
            return 3
        if threshold_3 and overdue_days >= threshold_3:
            return 3
        if threshold_2 and overdue_days >= threshold_2:
            return 2
        if threshold_1 and overdue_days >= threshold_1:
            return 1
        return 0

    def _build_reasons(
        self,
        *,
        total_debt: Decimal,
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
        debt_threshold = thresholds.get('debt_threshold')
        threshold_1 = thresholds.get('overdue_threshold_1')
        threshold_2 = thresholds.get('overdue_threshold_2')
        threshold_3 = thresholds.get('overdue_threshold_3')

        if debt_threshold is not None and Decimal(total_debt) > Decimal(str(debt_threshold)):
            reasons.append(
                _("Debt threshold exceeded: %(debt)s > %(threshold)s") % {
                    'debt': total_debt,
                    'threshold': debt_threshold,
                }
            )

        if blocking_level == 3 and threshold_3:
            reasons.append(
                _("Critical overdue: %(days)s days >= %(threshold)s") % {
                    'days': overdue_days,
                    'threshold': threshold_3,
                }
            )
        elif blocking_level == 2 and threshold_2:
            reasons.append(
                _("Search visibility disabled: %(days)s days >= %(threshold)s") % {
                    'days': overdue_days,
                    'threshold': threshold_2,
                }
            )
        elif blocking_level == 1 and threshold_1:
            reasons.append(
                _("Payment warning: %(days)s days >= %(threshold)s") % {
                    'days': overdue_days,
                    'threshold': threshold_1,
                }
            )

        if overdue_debt > Decimal('0.00'):
            reasons.append(
                _("Overdue amount: %(amount)s") % {
                    'amount': overdue_debt,
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

        blocking_rule = self._get_or_create_rule(blocking_level, thresholds)
        notes = '; '.join(reasons)

        if current_blocking:
            current_blocking.blocking_rule = blocking_rule
            current_blocking.debt_amount = debt_info['total_debt']
            current_blocking.overdue_days = overdue_days
            current_blocking.currency = debt_info['currency']
            current_blocking.notes = notes
            current_blocking.save(
                update_fields=[
                    'blocking_rule',
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
                blocking_rule=blocking_rule,
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

    def _get_or_create_rule(self, blocking_level: int, thresholds: Dict[str, Any]) -> BlockingRule:
        """
        Возвращает служебное правило блокировки для указанного уровня.
        """
        overdue_threshold_map = {
            1: int(thresholds.get('overdue_threshold_1') or 0),
            2: int(thresholds.get('overdue_threshold_2') or 0),
            3: int(thresholds.get('overdue_threshold_3') or 0),
        }
        debt_threshold = Decimal(str(thresholds.get('debt_threshold') or '0.00'))

        rule, _ = BlockingRule.objects.get_or_create(
            name=f'Automatic billing blocking L{blocking_level}',
            defaults={
                'description': 'Automatically maintained by MultiLevelBlockingService',
                'debt_amount_threshold': debt_threshold,
                'overdue_days_threshold': overdue_threshold_map[blocking_level],
                'priority': blocking_level,
                'is_active': True,
            },
        )

        fields_to_update: List[str] = []
        if rule.debt_amount_threshold != debt_threshold:
            rule.debt_amount_threshold = debt_threshold
            fields_to_update.append('debt_amount_threshold')
        if rule.overdue_days_threshold != overdue_threshold_map[blocking_level]:
            rule.overdue_days_threshold = overdue_threshold_map[blocking_level]
            fields_to_update.append('overdue_days_threshold')
        if not rule.is_active:
            rule.is_active = True
            fields_to_update.append('is_active')
        if fields_to_update:
            rule.save(update_fields=fields_to_update)

        return rule

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
