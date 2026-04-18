from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from billing.models import Invoice, Payment, quantize_money
from billing.services import invalidate_provider_blocking_cache


class PaymentRefundService:
    """
    Применяет и откатывает бухгалтерские возвраты по completed/refunded payment.

    Логика:
    - refund сначала списывается из неразнесенного остатка переплаты;
    - затем, если суммы не хватает, уменьшает net-paid по invoice ledger
      через PaymentHistory.refunded_amount;
    - при откате используется обратное правило.
    """

    @transaction.atomic
    def apply_refund(self, refund):
        locked_payment = Payment.objects.select_for_update().get(pk=refund.payment_id)
        self._validate_payment_for_refund(locked_payment)

        other_refunds_total = locked_payment.effective_refund_total(exclude_refund_id=refund.pk)
        max_refundable_amount = quantize_money(locked_payment.amount - other_refunds_total)
        refund_amount = quantize_money(refund.amount)
        if refund_amount > max_refundable_amount:
            raise ValidationError(_('Refund amount cannot exceed remaining refundable payment amount'))

        remaining_amount = refund_amount
        available_unapplied = max(
            quantize_money(locked_payment.unapplied_remainder_amount - other_refunds_total),
            Decimal('0.00'),
        )
        if available_unapplied > Decimal('0.00'):
            remaining_amount = quantize_money(
                remaining_amount - min(remaining_amount, available_unapplied)
            )

        if remaining_amount > Decimal('0.00'):
            remaining_amount = self._apply_to_invoices(locked_payment, remaining_amount)

        if remaining_amount > Decimal('0.00'):
            raise ValidationError(_('Refund amount exceeds refundable invoice allocations'))

        locked_payment.sync_status_from_refunds()
        if locked_payment.provider_id:
            invalidate_provider_blocking_cache(locked_payment.provider_id)
        return refund

    @transaction.atomic
    def revert_refund(self, refund):
        locked_payment = Payment.objects.select_for_update().get(pk=refund.payment_id)
        self._validate_payment_for_refund(locked_payment, allow_refunded=True)

        refund_amount = quantize_money(refund.amount)
        other_refunds_total = locked_payment.effective_refund_total(exclude_refund_id=refund.pk)

        remaining_amount = refund_amount
        refundable_from_unapplied = max(
            quantize_money(locked_payment.unapplied_remainder_amount - other_refunds_total),
            Decimal('0.00'),
        )
        if refundable_from_unapplied > Decimal('0.00'):
            remaining_amount = quantize_money(
                remaining_amount - min(remaining_amount, refundable_from_unapplied)
            )

        if remaining_amount > Decimal('0.00'):
            remaining_amount = self._revert_from_invoices(locked_payment, remaining_amount)

        if remaining_amount > Decimal('0.00'):
            raise ValidationError(_('Refund revert amount exceeds refunded invoice allocations'))

        locked_payment.sync_status_from_refunds(exclude_refund_id=refund.pk)
        if locked_payment.provider_id:
            invalidate_provider_blocking_cache(locked_payment.provider_id)
        return refund

    def _validate_payment_for_refund(self, payment, *, allow_refunded=False):
        valid_statuses = {'completed'}
        if allow_refunded:
            valid_statuses.add('refunded')
        if payment.status not in valid_statuses:
            raise ValidationError(_('Refund can be applied only to completed payments'))

    def _apply_to_invoices(self, payment, amount):
        remaining_amount = quantize_money(amount)
        for invoice in self._get_refundable_invoices(payment):
            if remaining_amount <= Decimal('0.00'):
                break

            payment_record = invoice.payment_record
            if payment_record is None:
                continue

            refundable_amount = quantize_money(
                payment_record.paid_amount - payment_record.refunded_amount
            )
            amount_to_apply = min(refundable_amount, remaining_amount)
            if amount_to_apply <= Decimal('0.00'):
                continue

            payment_record.apply_refund(amount_to_apply)
            remaining_amount = quantize_money(remaining_amount - amount_to_apply)

        return remaining_amount

    def _revert_from_invoices(self, payment, amount):
        remaining_amount = quantize_money(amount)
        for invoice in self._get_refundable_invoices(payment):
            if remaining_amount <= Decimal('0.00'):
                break

            payment_record = invoice.payment_record
            if payment_record is None or payment_record.refunded_amount <= Decimal('0.00'):
                continue

            amount_to_revert = min(payment_record.refunded_amount, remaining_amount)
            payment_record.revert_refund(amount_to_revert)
            remaining_amount = quantize_money(remaining_amount - amount_to_revert)

        return remaining_amount

    def _get_refundable_invoices(self, payment):
        if payment.invoice_id is not None:
            invoice = (
                Invoice.objects.select_for_update()
                .get(pk=payment.invoice_id)
            )
            return [invoice]

        return list(
            Invoice.objects.select_for_update()
            .filter(provider=payment.provider)
            .exclude(status__in=['draft', 'cancelled'])
            .order_by('-issued_at', '-created_at', '-id')
        )
