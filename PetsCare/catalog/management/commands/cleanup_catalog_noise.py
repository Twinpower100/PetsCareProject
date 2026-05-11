"""
Safely remove or archive test/noise services from the catalog.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError

from catalog.models import Service
from catalog.noise import NOISE_CODE_PREFIXES, NOISE_NAME_FRAGMENTS, build_noise_service_query
from providers.models import EmployeeLocationService, Provider, ProviderLocationService


class Command(BaseCommand):
    help = "Safely remove or archive test/noise services from the catalog."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply changes. Without this flag the command only prints a dry-run report.",
        )
        parser.add_argument(
            "--name-fragment",
            action="append",
            default=[],
            help="Additional service name fragment to treat as noise. Can be passed multiple times.",
        )
        parser.add_argument(
            "--code-prefix",
            action="append",
            default=[],
            help="Additional service code prefix to treat as noise. Can be passed multiple times.",
        )
        parser.add_argument(
            "--include-archived",
            action="store_true",
            help="Also target already archived inactive noise services.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        targets = self._get_targets(
            name_fragments=NOISE_NAME_FRAGMENTS + options["name_fragment"],
            code_prefixes=NOISE_CODE_PREFIXES + options["code_prefix"],
            include_archived=options["include_archived"],
        )

        self.stdout.write(f"Matched noise services: {targets.count()}")
        if not apply_changes:
            self.stdout.write("Dry run only. Re-run with --apply to change data.")
            for service in targets:
                self.stdout.write(self._format_service(service))
            return

        deleted = 0
        archived = 0
        target_ids = list(targets.values_list("id", flat=True))
        with transaction.atomic():
            locked_targets = Service.objects.filter(id__in=target_ids).select_for_update().order_by("hierarchy_order", "name")
            for service in locked_targets:
                self._detach_from_active_configuration(service)
                try:
                    with transaction.atomic():
                        service.delete()
                    deleted += 1
                except (ProtectedError, IntegrityError):
                    service.is_active = False
                    service.is_client_facing = False
                    service.save(update_fields=["is_active", "is_client_facing", "level", "hierarchy_order", "version"])
                    archived += 1
                    self.stdout.write(f"Archived referenced service: {self._format_service(service)}")

        self.stdout.write(self.style.SUCCESS(f"Cleanup complete. Deleted: {deleted}. Archived: {archived}."))

    def _get_targets(self, *, name_fragments: list[str], code_prefixes: list[str], include_archived: bool):
        query = build_noise_service_query(name_fragments=name_fragments, code_prefixes=code_prefixes)
        if include_archived:
            return Service.objects.filter(query).order_by("hierarchy_order", "name").distinct()

        active_configuration_query = (
            Q(is_active=True)
            | Q(is_client_facing=True)
            | Q(available_providers__isnull=False)
            | Q(location_services__is_active=True)
        )
        return Service.objects.filter(query & active_configuration_query).order_by("hierarchy_order", "name").distinct()

    def _detach_from_active_configuration(self, service: Service) -> None:
        """Убирает мусорную услугу из активных настроек, не трогая исторические документы."""
        for provider in Provider.objects.filter(available_category_levels=service):
            provider.available_category_levels.remove(service)

        ProviderLocationService.objects.filter(service=service).update(is_active=False)
        EmployeeLocationService.objects.filter(service=service).delete()

    def _format_service(self, service: Service) -> str:
        return (
            f"id={service.id}, code={service.code}, name={service.name}, "
            f"active={service.is_active}, client_facing={service.is_client_facing}, path={service.get_full_path()}"
        )
