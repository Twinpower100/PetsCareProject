"""
Команда repair для восстановления provider/team state после сломанной reactivate-логики.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from providers.pricing_services import ProviderPricingService


class Command(BaseCommand):
    """
    Восстанавливает филиалы, org links и branch roles для указанных организаций.
    """

    help = 'Repair provider lifecycle reactivation fallout for specific organizations.'

    def add_arguments(self, parser):
        """
        Регистрирует аргументы CLI.
        """
        parser.add_argument(
            '--provider',
            action='append',
            dest='providers',
            required=True,
            help='Exact provider name to repair. Can be passed multiple times.',
        )
        parser.add_argument(
            '--reason',
            dest='reason',
            default='Lifecycle repair after broken reactivation flow',
            help='Audit reason stored on repaired branches.',
        )

    def handle(self, *args, **options):
        """
        Выполняет восстановление и печатает краткий результат.
        """
        provider_names = options['providers'] or []
        if not provider_names:
            raise CommandError('At least one --provider value is required.')

        repaired = ProviderPricingService.repair_provider_lifecycle_state(
            provider_names=provider_names,
            effective_date=timezone.localdate(),
            reason=options['reason'],
        )
        if not repaired:
            raise CommandError('No providers were repaired. Check provider names.')

        for item in repaired:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{item['provider_name']}: "
                    f"links={len(item['restored_provider_link_ids'])}, "
                    f"roles={len(item['restored_location_role_ids'])}, "
                    f"locations={len(item['reactivated_location_ids'])}"
                )
            )
