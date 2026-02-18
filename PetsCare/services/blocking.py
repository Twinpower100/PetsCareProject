from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from billing.models import BlockingRule, ProviderBlocking, BlockingNotification
from providers.models import Provider
from billing.models import Currency
from billing.models import PaymentHistory
from billing.logging import (
    log_blocking_created, log_blocking_resolved, log_automatic_check_started,
    log_automatic_check_completed
)


def check_and_block_providers():
    """
    Проверяет задолженности учреждений и применяет правила блокировки.
    """
    # Логируем начало проверки
    log_automatic_check_started()
    
    now = timezone.now().date()
    active_rules = BlockingRule.objects.filter(is_active=True).order_by('priority')
    providers = Provider.objects.filter(is_active=True)
    
    blocked_count = 0
    resolved_count = 0

    for provider in providers:
        # Получаем задолженность и просрочку
        debt_info = get_provider_debt_info(provider)
        if not debt_info:
            continue
        debt_amount, overdue_days, currency = debt_info

        # Применяем подходящее правило
        for rule in active_rules:
            if not is_rule_applicable(rule, provider):
                continue
            if debt_amount >= rule.debt_amount_threshold and overdue_days >= rule.overdue_days_threshold:
                # Проверяем, нет ли уже активной блокировки
                if not ProviderBlocking.objects.filter(provider=provider, status='active').exists():
                    blocking = ProviderBlocking.objects.create(
                        provider=provider,
                        blocking_rule=rule,
                        debt_amount=debt_amount,
                        overdue_days=overdue_days,
                        currency=currency
                    )
                    
                    # Логируем создание блокировки
                    log_blocking_created(blocking)
                    blocked_count += 1
                    
                    # Создаём уведомление
                    notification = BlockingNotification.objects.create(
                        provider_blocking=blocking,
                        notification_type='blocking_activated',
                        subject=_('Provider blocked'),
                        message=_('Provider {provider} was blocked due to outstanding debt.').format(
                            provider=provider.name
                        )
                    )
                break  # Применяем только одно правило

        # Снимаем блокировку, если долг погашен
        if debt_amount == Decimal('0.00'):
            active_blockings = ProviderBlocking.objects.filter(provider=provider, status='active')
            for blocking in active_blockings:
                blocking.resolve()
                resolved_count += 1
                
                # Логируем снятие блокировки
                log_blocking_resolved(blocking, resolved_by=None, notes='Автоматическое снятие при погашении долга')
                
                notification = BlockingNotification.objects.create(
                    provider_blocking=blocking,
                    notification_type='blocking_resolved',
                    subject=_('Blocking resolved'),
                    message=_('Blocking for provider {provider} was resolved after debt repayment.').format(
                        provider=provider.name
                    )
                )
    
    # Логируем завершение проверки
    log_automatic_check_completed(blocked_count, resolved_count)


def get_provider_debt_info(provider):
    """
    Возвращает (debt_amount, overdue_days, currency) для учреждения.
    """
    # Пример: ищем максимальную просрочку и сумму по истории платежей
    overdue_payments = PaymentHistory.objects.filter(
        provider=provider,
        status='overdue'
    )
    if not overdue_payments.exists():
        return None
    max_overdue = 0
    total_debt = Decimal('0.00')
    currency = None
    today = timezone.now().date()
    for payment in overdue_payments:
        overdue_days = (today - payment.due_date).days
        if overdue_days > max_overdue:
            max_overdue = overdue_days
        total_debt += payment.amount
        currency = payment.currency
    return total_debt, max_overdue, currency


def is_rule_applicable(rule, provider):
    """
    Проверяет, применимо ли правило к учреждению (по регионам, типам услуг и т.д.)
    """
    if not rule.is_mass_rule:
        return True
    if rule.regions:
        if not provider.structured_address or provider.structured_address.region not in rule.regions:
            return False
    if rule.service_types:
        if not provider.locations.filter(available_services__id__in=rule.service_types).exists():
            return False
    return True 