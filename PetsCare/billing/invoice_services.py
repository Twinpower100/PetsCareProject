"""
Сервисы для генерации инвойсов и PDF-файлов.
"""

from decimal import Decimal
from html.parser import HTMLParser
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from billing.models import (
    Currency,
    Invoice,
    InvoiceLine,
    PlatformCompany,
    VATRate,
    quantize_money,
)
from booking.constants import BOOKING_STATUS_COMPLETED
from booking.models import Booking


def format_invoice_period(start_date, end_date, empty_value=''):
    """
    Возвращает человекочитаемый период счета.
    """
    if start_date and end_date:
        return f'{start_date:%Y-%m-%d} - {end_date:%Y-%m-%d}'
    if start_date:
        return f'{start_date:%Y-%m-%d}'
    if end_date:
        return f'{end_date:%Y-%m-%d}'
    return empty_value


def build_invoice_breakdown_rows(invoice):
    """
    Возвращает детализацию бронирований, входящих в счет.
    """
    rows = []
    line_queryset = invoice.lines.select_related(
        'booking__user',
        'booking__pet',
        'booking__service',
        'booking__provider_location',
    ).order_by('booking__completed_at', 'booking__end_time', 'booking_id')

    for line in line_queryset:
        booking = line.booking
        completed_at = booking.completed_at or booking.end_time
        rows.append({
            'booking_id': booking.pk,
            'booking_code': booking.code or '',
            'booking_label': booking.code or f'#{booking.pk}',
            'completed_at': completed_at,
            'completed_at_label': completed_at.strftime('%Y-%m-%d %H:%M') if completed_at else '',
            'service': str(booking.service) if booking.service else '',
            'client': booking.user.email if booking.user else '',
            'pet': str(booking.pet) if booking.pet else '',
            'location': str(booking.provider_location) if booking.provider_location else '',
            'amount': line.amount,
            'commission': line.commission,
            'vat_amount': line.vat_amount,
            'total_with_vat': line.total_with_vat,
        })
    return rows


def summarize_invoice_breakdown(invoice, rows=None):
    """
    Возвращает агрегированную сводку по бронированиям счета.
    """
    if rows is None:
        rows = build_invoice_breakdown_rows(invoice)

    return {
        'period_label': format_invoice_period(invoice.start_date, invoice.end_date, empty_value='—'),
        'booking_count': len(rows),
        'booking_amount_total': quantize_money(
            sum((row['amount'] for row in rows), Decimal('0.00'))
        ),
        'commission_total': quantize_money(
            sum((row['commission'] for row in rows), Decimal('0.00'))
        ),
        'vat_total': quantize_money(
            sum((row['vat_amount'] for row in rows), Decimal('0.00'))
        ),
        'total_amount': quantize_money(
            sum((row['total_with_vat'] for row in rows), Decimal('0.00'))
        ),
        'currency_code': invoice.currency.code if invoice.currency else '',
    }


class InvoiceGenerationService:
    """
    Сервис ручной генерации счетов по завершенным онлайн-бронированиям.
    """

    @transaction.atomic
    def generate_for_provider(self, provider, start_date, end_date):
        """
        Создает один счет по провайдеру за выбранный период.
        """
        invoice_currency = provider.invoice_currency or self._get_default_currency()
        financial_document = self.get_financial_document(provider)
        platform_company = PlatformCompany.resolve_for_provider(provider)

        if platform_company is None:
            raise ValidationError(_('No platform company is configured for invoice generation'))
        if financial_document is None:
            raise ValidationError(_('Provider has no active accepted billing document'))

        bookings = list(self._get_eligible_bookings(provider, start_date, end_date))
        if not bookings:
            return None

        invoice = Invoice.objects.create(
            provider=provider,
            platform_company=platform_company,
            start_date=start_date,
            end_date=end_date,
            amount=Decimal('0.00'),
            currency=invoice_currency,
            status='sent',
            issued_at=timezone.now(),
        )

        for booking in bookings:
            line_data = self._build_line_data(
                provider=provider,
                booking=booking,
                invoice_currency=invoice_currency,
                financial_document=financial_document,
            )
            InvoiceLine.objects.create(
                invoice=invoice,
                booking=booking,
                amount=line_data['amount'],
                commission=line_data['commission'],
                rate=line_data['rate'],
                currency=invoice_currency,
                vat_rate=line_data['vat_rate'],
                vat_amount=line_data['vat_amount'],
                total_with_vat=line_data['total_with_vat'],
            )

        invoice.save(
            update_fields=['amount', 'updated_at'],
            refresh_amount=True,
            synchronize_payment_history=True,
        )
        invoice.ensure_pdf_file(force=True)
        return invoice

    def get_financial_document(self, provider):
        """
        Возвращает документ с финансовыми условиями для провайдера.
        """
        side_letter = (
            provider.legal_documents.filter(
                document_type__code='side_letter',
                is_active=True,
            )
            .order_by('-signed_at', '-effective_date', '-id')
            .first()
        )
        if side_letter is not None:
            return side_letter

        active_acceptance = (
            provider.document_acceptances.select_related('document')
            .filter(
                document__document_type__code='global_offer',
                is_active=True,
            )
            .order_by('-accepted_at', '-id')
            .first()
        )
        if active_acceptance is None:
            return None
        return active_acceptance.document

    def _get_eligible_bookings(self, provider, start_date, end_date):
        """
        Возвращает завершенные онлайн-бронирования без инвойса за период.
        """
        return (
            Booking.objects.select_related('payment', 'provider_location__provider')
            .filter(
                Q(provider=provider) | Q(provider_location__provider=provider),
                status__name=BOOKING_STATUS_COMPLETED,
                payment__payment_method='online',
                invoiceline__isnull=True,
            )
            .filter(
                Q(completed_at__date__range=(start_date, end_date)) |
                Q(completed_at__isnull=True, end_time__date__range=(start_date, end_date))
            )
            .order_by('completed_at', 'end_time', 'id')
            .distinct()
        )

    def _build_line_data(self, provider, booking, invoice_currency, financial_document):
        """
        Рассчитывает финансовые параметры строки инвойса.
        """
        booking_currency = invoice_currency
        booking_amount = quantize_money(booking.price)
        commission = quantize_money(
            financial_document.calculate_commission(
                booking_amount,
                booking_currency,
                invoice_currency,
            )
        )
        if commission <= Decimal('0.00') and booking_amount > Decimal('0.00'):
            commission = quantize_money(
                provider.calculate_commission(
                    booking_amount,
                    booking_currency,
                    invoice_currency,
                )
            )

        vat_rate = None
        vat_amount = Decimal('0.00')
        if not provider.is_vat_payer and provider.country:
            vat_rate = VATRate.get_rate_for_country(provider.country)
            if vat_rate:
                vat_amount = quantize_money(commission * (Decimal(vat_rate) / Decimal('100')))

        rate = Decimal('0.00')
        if booking_amount > Decimal('0.00'):
            rate = quantize_money((commission / booking_amount) * Decimal('100'))

        return {
            'amount': booking_amount,
            'commission': commission,
            'rate': rate,
            'vat_rate': vat_rate,
            'vat_amount': vat_amount,
            'total_with_vat': quantize_money(commission + vat_amount),
        }

    def _get_default_currency(self):
        """
        Возвращает базовую валюту для инвойсов.
        """
        return (
            Currency.objects.filter(code='EUR', is_active=True).first()
            or Currency.objects.filter(is_active=True).order_by('code').first()
        )


class InvoicePdfService:
    """
    Сервис генерации PDF-файлов для счетов.

    При наличии WeasyPrint использует HTML-шаблон как основной рендер.
    Если библиотека не установлена, использует встроенный минимальный
    PDF-генератор, чтобы процесс выставления счета не падал.
    """

    template_name = 'admin/billing/invoice_pdf.html'

    @transaction.atomic
    def generate_pdf(self, invoice, force=False):
        """
        Генерирует PDF-файл счета и сохраняет его в модель Invoice.
        """
        locked_invoice = (
            Invoice.objects.select_for_update()
            .prefetch_related('lines__booking')
            .get(pk=invoice.pk)
        )

        if locked_invoice.pdf_file and not force:
            return locked_invoice.pdf_file

        platform_company = locked_invoice.platform_company or PlatformCompany.resolve_for_provider(locked_invoice.provider)
        if platform_company is None:
            raise ValidationError(_('No platform company is configured for invoice PDF generation'))

        if locked_invoice.platform_company_id is None:
            locked_invoice.platform_company = platform_company

        context = self._build_context(locked_invoice, platform_company)
        html_content = render_to_string(self.template_name, context)
        pdf_bytes = self._render_pdf_bytes(html_content, context)

        file_name = f"invoice-{slugify(locked_invoice.number) or locked_invoice.pk}.pdf"
        locked_invoice.pdf_file.save(file_name, ContentFile(pdf_bytes), save=False)
        locked_invoice.save(update_fields=['platform_company', 'pdf_file', 'updated_at'])
        return locked_invoice.pdf_file

    def _build_context(self, invoice, platform_company):
        """
        Подготавливает контекст для HTML/PDF-шаблона счета.
        """
        lines = build_invoice_breakdown_rows(invoice)
        summary = summarize_invoice_breakdown(invoice, rows=lines)
        payment_record = invoice.payment_record
        return {
            'invoice': invoice,
            'platform_company': platform_company,
            'provider': invoice.provider,
            'lines': lines,
            'currency_code': summary['currency_code'],
            'due_date': payment_record.due_date if payment_record else None,
            'paid_amount': payment_record.paid_amount if payment_record else Decimal('0.00'),
            'outstanding_amount': invoice.outstanding_amount,
            'service_period_label': summary['period_label'],
            'booking_count': summary['booking_count'],
            'booking_amount_total': summary['booking_amount_total'],
            'commission_total': summary['commission_total'],
            'vat_total': summary['vat_total'],
        }

    def _render_pdf_bytes(self, html_content, context):
        """
        Рендерит PDF через WeasyPrint или через встроенный fallback.
        """
        try:
            from weasyprint import HTML

            return HTML(string=html_content).write_pdf()
        except Exception:
            text_lines = self._build_fallback_lines(context)
            return self._build_minimal_pdf(text_lines)

    def _build_fallback_lines(self, context):
        """
        Формирует текстовое представление счета для fallback PDF.
        """
        invoice = context['invoice']
        company = context['platform_company']
        provider = context['provider']
        lines = [
            f"Invoice: {invoice.number}",
            f"Issued at: {invoice.issued_at:%Y-%m-%d}",
            f"Period: {invoice.start_date} - {invoice.end_date}",
            '',
            f"Platform company: {company.name}",
            f"Address: {company.address}",
            f"Tax ID: {company.tax_id}",
            f"Bank: {company.bank_name}",
            f"IBAN: {company.iban}",
            f"BIC: {company.bic}",
            f"SWIFT: {company.swift}",
            '',
            f"Provider: {provider.name if provider else ''}",
            f"Currency: {context['currency_code']}",
            f"Due date: {context['due_date'] or ''}",
            '',
            'Summary:',
            f"- Service period: {context['service_period_label']}",
            f"- Booking count: {context['booking_count']}",
            f"- Booking amount total: {context['booking_amount_total']}",
            f"- Commission total: {context['commission_total']}",
            f"- VAT total: {context['vat_total']}",
            '',
            f"Total amount: {invoice.amount}",
            f"Paid amount: {context['paid_amount']}",
            f"Outstanding amount: {context['outstanding_amount']}",
        ]
        return lines

    def _build_minimal_pdf(self, lines):
        """
        Собирает простой одностраничный/многостраничный PDF без внешних зависимостей.
        """
        pages = []
        chunk_size = 42
        for index in range(0, len(lines), chunk_size):
            pages.append(lines[index:index + chunk_size])

        objects = []
        font_object_id = 3
        page_object_ids = []
        content_object_ids = []

        objects.append(b'<< /Type /Catalog /Pages 2 0 R >>')
        objects.append(None)
        objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')

        next_object_id = 4
        for page_lines in pages:
            page_object_ids.append(next_object_id)
            content_object_ids.append(next_object_id + 1)
            next_object_id += 2

        kids_reference = ' '.join(f'{object_id} 0 R' for object_id in page_object_ids)
        objects[1] = f'<< /Type /Pages /Count {len(page_object_ids)} /Kids [{kids_reference}] >>'.encode('utf-8')

        for page_object_id, content_object_id, page_lines in zip(page_object_ids, content_object_ids, pages):
            stream_commands = [
                'BT',
                '/F1 11 Tf',
                '50 790 Td',
                '14 TL',
            ]
            for line in page_lines:
                stream_commands.append(f'({self._escape_pdf_text(line)}) Tj')
                stream_commands.append('T*')
            stream_commands.append('ET')
            stream_bytes = '\n'.join(stream_commands).encode('latin-1', errors='replace')

            page_bytes = (
                f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] '
                f'/Resources << /Font << /F1 {font_object_id} 0 R >> >> '
                f'/Contents {content_object_id} 0 R >>'
            ).encode('utf-8')
            content_bytes = (
                f'<< /Length {len(stream_bytes)} >>\nstream\n'.encode('utf-8') +
                stream_bytes +
                b'\nendstream'
            )
            objects.append(page_bytes)
            objects.append(content_bytes)

        buffer = BytesIO()
        buffer.write(b'%PDF-1.4\n')
        offsets = [0]

        for index, pdf_object in enumerate(objects, start=1):
            offsets.append(buffer.tell())
            buffer.write(f'{index} 0 obj\n'.encode('utf-8'))
            buffer.write(pdf_object)
            buffer.write(b'\nendobj\n')

        xref_offset = buffer.tell()
        buffer.write(f'xref\n0 {len(objects) + 1}\n'.encode('utf-8'))
        buffer.write(b'0000000000 65535 f \n')
        for offset in offsets[1:]:
            buffer.write(f'{offset:010d} 00000 n \n'.encode('utf-8'))
        buffer.write(
            (
                f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n'
                f'startxref\n{xref_offset}\n%%EOF'
            ).encode('utf-8')
        )
        return buffer.getvalue()

    def _escape_pdf_text(self, value):
        """
        Экранирует строку для безопасной вставки в PDF content stream.
        """
        return (
            str(value)
            .replace('\\', '\\\\')
            .replace('(', '\\(')
            .replace(')', '\\)')
        )


class InvoiceTextExtractor(HTMLParser):
    """
    Простой извлекатель текста из HTML.

    Оставлен как самостоятельный класс на случай, если потребуется
    расширить fallback-генерацию PDF без внешних библиотек.
    """

    def __init__(self):
        """Инициализирует накопитель текста."""
        super().__init__()
        self.lines = []

    def handle_data(self, data):
        """Сохраняет значимый текст из HTML."""
        stripped_data = data.strip()
        if stripped_data:
            self.lines.append(stripped_data)
