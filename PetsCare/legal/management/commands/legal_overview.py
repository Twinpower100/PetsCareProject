"""
Management команда для обзора юридических документов и ставок НДС.

Использование:
    python manage.py legal_overview
"""

from django.core.management.base import BaseCommand
from django.db.models import Count

from legal.models import LegalDocumentType, LegalDocument, CountryLegalConfig
from billing.models import VATRate


class Command(BaseCommand):
    """Команда для вывода сводной информации по legal и VAT."""

    help = 'Shows legal documents and VAT rates overview'

    def handle(self, *args, **options):
        """Выводит типы документов, документы, конфиги стран и VAT ставки."""
        self._print_document_types()
        self._print_documents()
        self._print_country_configs()
        self._print_vat_rates()

    def _print_document_types(self):
        """Выводит список типов документов и их флаги."""
        self.stdout.write('=== Legal document types ===')
        types = LegalDocumentType.objects.all().order_by('code')
        if not types.exists():
            self.stdout.write('No document types found.')
            return
        
        for dt in types:
            flags = (
                f"billing={dt.requires_billing_config}, "
                f"region={dt.requires_region_code}, "
                f"addendum={dt.requires_addendum_type}, "
                f"variables={dt.allows_variables}, "
                f"provider={dt.requires_provider}, "
                f"financial={dt.allows_financial_terms}, "
                f"required_all={dt.is_required_for_all_countries}, "
                f"multiple={dt.is_multiple_allowed}"
            )
            self.stdout.write(f"- {dt.code} | active={dt.is_active} | {flags}")

    def _print_documents(self):
        """Выводит список документов с краткими параметрами."""
        self.stdout.write('\n=== Legal documents ===')
        documents = (
            LegalDocument.objects
            .select_related('document_type', 'billing_config')
            .annotate(translations_count=Count('translations'))
            .order_by('document_type__code', 'id')
        )
        if not documents.exists():
            self.stdout.write('No legal documents found.')
            return
        
        for doc in documents:
            self.stdout.write(
                f"- id={doc.id} | type={doc.document_type.code} | "
                f"version={doc.version} | active={doc.is_active} | "
                f"region={doc.region_code or '-'} | addendum={doc.addendum_type or '-'} | "
                f"translations={doc.translations_count} | "
                f"billing_config_id={doc.billing_config_id or '-'}"
            )

    def _print_country_configs(self):
        """Выводит конфигурации стран и привязанные документы."""
        self.stdout.write('\n=== Country legal configs ===')
        configs = CountryLegalConfig.objects.all().order_by('country')
        if not configs.exists():
            self.stdout.write('No country configs found.')
            return
        
        for cfg in configs:
            self.stdout.write(
                f"- country={cfg.country} | "
                f"global_offer_id={cfg.global_offer_id or '-'} | "
                f"privacy_policy_id={cfg.privacy_policy_id or '-'} | "
                f"terms_of_service_id={cfg.terms_of_service_id or '-'} | "
                f"cookie_policy_id={cfg.cookie_policy_id or '-'} | "
                f"regional_addendums={cfg.regional_addendums.count()}"
            )

    def _print_vat_rates(self):
        """Выводит список ставок НДС по странам."""
        self.stdout.write('\n=== VAT rates ===')
        rates = VATRate.objects.all().order_by('country', '-effective_date')
        if not rates.exists():
            self.stdout.write('No VAT rates found.')
            return
        
        for rate in rates:
            self.stdout.write(
                f"- country={rate.country} | rate={rate.rate} | "
                f"effective_date={rate.effective_date} | active={rate.is_active}"
            )
