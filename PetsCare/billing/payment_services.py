"""
Сервисы для проводки входящих платежей по счетам.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from billing.models import Invoice, Payment, PaymentHistory, quantize_money


class PaymentAllocationService:
    """
    Сервис для проводки бухгалтерского платежа по счетам провайдера.

    Поддерживает:
    - явное погашение конкретного счета;
    - FIFO-проводку по всем открытым счетам провайдера;
    - безопасную работу через транзакцию и блокировки строк.
    """

    @transaction.atomic
    def apply_payment(self, payment):
        """
        Проводит платеж и обновляет связанные счета.
        """
        locked_payment = (
            Payment.objects.select_for_update()
            .get(pk=payment.pk)
        )

        if locked_payment.applied_at is not None:
            return locked_payment
        if locked_payment.provider_id is None:
            raise ValidationError(_('Payment provider is required'))

        remaining_amount = quantize_money(locked_payment.amount)
        payment_date = timezone.now().date()

        if locked_payment.invoice_id is not None:
            invoice = (
                Invoice.objects.select_for_update()
                .get(pk=locked_payment.invoice_id)
            )
            if invoice.provider_id != locked_payment.provider_id:
                raise ValidationError(_('Selected invoice does not belong to the payment provider'))
            remaining_amount -= self._apply_to_invoice(invoice, remaining_amount, payment_date)
        else:
            open_invoices = (
                Invoice.objects.select_for_update()
                .filter(
                    provider=locked_payment.provider,
                    status__in=['sent', 'partially_paid', 'overdue'],
                )
                .order_by('issued_at', 'created_at', 'id')
            )
            for invoice in open_invoices:
                if remaining_amount <= Decimal('0.00'):
                    break
                remaining_amount -= self._apply_to_invoice(invoice, remaining_amount, payment_date)

        notes = locked_payment.notes or ''
        if remaining_amount > Decimal('0.00'):
            unapplied_note = _(
                'Unapplied remainder after invoice allocation: %(amount)s'
            ) % {'amount': remaining_amount}
            notes = '\n'.join(filter(None, [notes, unapplied_note]))

        applied_at = timezone.now()
        Payment.objects.filter(pk=locked_payment.pk).update(
            applied_at=applied_at,
            notes=notes,
            updated_at=applied_at,
        )
        locked_payment.applied_at = applied_at
        locked_payment.notes = notes
        return locked_payment

    def _apply_to_invoice(self, invoice, amount, payment_date):
        """
        Проводит часть суммы в конкретный счет и возвращает использованную сумму.
        """
        payment_record = self._get_payment_record(invoice)
        amount_to_apply = min(payment_record.outstanding_amount, quantize_money(amount))
        if amount_to_apply <= Decimal('0.00'):
            return Decimal('0.00')

        payment_record.apply_payment(amount_to_apply, payment_date=payment_date)
        return amount_to_apply

    def _get_payment_record(self, invoice):
        """
        Возвращает заблокированную запись PaymentHistory для счета.
        """
        payment_record = (
            PaymentHistory.objects.select_for_update()
            .filter(invoice=invoice)
            .order_by('-created_at')
            .first()
        )
        if payment_record is not None:
            return payment_record

        invoice.sync_payment_history()
        payment_record = (
            PaymentHistory.objects.select_for_update()
            .filter(invoice=invoice)
            .order_by('-created_at')
            .first()
        )
        if payment_record is None:
            raise ValidationError(_('Invoice payment record is not available'))
        return payment_record
