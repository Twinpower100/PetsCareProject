"""
Сервисы для org-level матрицы цен и режима единых цен организации.
"""

from __future__ import annotations

from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from catalog.models import Service
from pets.models import PetType

from .models import (
    Provider,
    ProviderLocation,
    ProviderLocationService,
    ProviderServicePricing,
)
from .permission_service import ProviderPermissionService


class ProviderPricingService:
    """
    Оркестрирует org-level прайс-матрицу и синхронизацию цен в филиалы.
    """

    @classmethod
    def get_provider_served_pet_types(cls, provider: Provider):
        """
        Возвращает org-level scope типов животных организации.
        """
        return provider.served_pet_types.all().order_by('code')

    @classmethod
    def build_provider_price_matrix(cls, provider: Provider) -> list[dict]:
        """
        Строит org-level матрицу цен в формате, совместимом с frontend builder.
        """
        rows = (
            ProviderServicePricing.objects.filter(provider=provider, is_active=True)
            .select_related('service', 'pet_type')
            .order_by('service__name', 'pet_type__code', 'size_code')
        )
        by_service: dict[int, dict] = {}
        for row in rows:
            service_entry = by_service.setdefault(
                row.service_id,
                {
                    'service_id': row.service_id,
                    'service_name': getattr(row.service, 'name', '') or '',
                    'prices': {},
                },
            )
            pet_entry = service_entry['prices'].setdefault(
                row.pet_type_id,
                {
                    'pet_type_id': row.pet_type_id,
                    'pet_type_code': row.pet_type.code,
                    'pet_type_name': getattr(row.pet_type, 'name', None) or row.pet_type.code,
                    'base_price': str(row.price),
                    'base_duration_minutes': row.duration_minutes,
                    'variants': [],
                },
            )
            pet_entry['variants'].append(
                {
                    'size_code': row.size_code,
                    'price': str(row.price),
                    'duration_minutes': row.duration_minutes,
                }
            )

        result: list[dict] = []
        for service_entry in by_service.values():
            result.append(
                {
                    'service_id': service_entry['service_id'],
                    'service_name': service_entry['service_name'],
                    'pricing_scope': 'organization',
                    'prices': list(service_entry['prices'].values()),
                }
            )
        return result

    @classmethod
    @transaction.atomic
    def replace_provider_service_prices(
        cls,
        *,
        provider_id: int,
        service_id: int,
        prices: list[dict],
    ) -> dict:
        """
        Полностью заменяет org-level матрицу цен по одной услуге.
        """
        provider = Provider.objects.select_for_update().get(pk=provider_id)
        service = Service.objects.get(pk=service_id)

        cls._validate_provider_service(provider=provider, service=service)
        cls._validate_pet_types_belong_to_provider(provider=provider, prices=prices)
        ProviderServicePricing.objects.select_for_update().filter(
            provider=provider,
            service=service,
        ).delete()

        created_rows: list[ProviderServicePricing] = []
        for item in prices:
            pet_type_id = item['pet_type_id']
            base_price = item['base_price']
            base_duration = item['base_duration_minutes']
            for variant in item.get('variants', []):
                created_rows.append(
                    ProviderServicePricing(
                        provider=provider,
                        service=service,
                        pet_type_id=pet_type_id,
                        size_code=variant['size_code'],
                        price=variant.get('price', base_price),
                        duration_minutes=variant.get('duration_minutes', base_duration),
                    )
                )
        ProviderServicePricing.objects.bulk_create(created_rows)

        synced_location_ids: list[int] = []
        if provider.use_unified_service_pricing:
            synced_location_ids = cls._sync_service_to_locations(provider=provider, service_ids=[service_id])

        return {
            'service_id': service_id,
            'synced_location_ids': synced_location_ids,
        }

    @classmethod
    @transaction.atomic
    def set_unified_pricing_mode(cls, *, provider_id: int, enabled: bool) -> dict:
        """
        Включает или выключает режим единых цен организации.
        """
        provider = Provider.objects.select_for_update().get(pk=provider_id)
        if provider.use_unified_service_pricing == enabled:
            return {
                'use_unified_service_pricing': enabled,
                'synced_location_ids': [],
            }

        service_ids = cls._get_provider_priced_service_ids(provider)
        if enabled:
            cls._bootstrap_provider_prices_from_locations(provider=provider)
            service_ids = cls._get_provider_priced_service_ids(provider)
        elif service_ids:
            # Перед возвратом полномочий филиалам фиксируем в branch rows
            # последнюю организационную матрицу как их стартовое состояние.
            cls._sync_service_to_locations(provider=provider, service_ids=service_ids)

        provider.use_unified_service_pricing = enabled
        provider.save(update_fields=['use_unified_service_pricing', 'updated_at'])

        synced_location_ids: list[int] = []
        if enabled and service_ids:
            synced_location_ids = cls._sync_service_to_locations(provider=provider, service_ids=service_ids)

        return {
            'use_unified_service_pricing': provider.use_unified_service_pricing,
            'synced_location_ids': synced_location_ids,
        }

    @classmethod
    def _get_provider_priced_service_ids(cls, provider: Provider) -> list[int]:
        """
        Возвращает список услуг, для которых у организации уже есть org-level цены.
        """
        return list(
            ProviderServicePricing.objects.filter(provider=provider, is_active=True)
            .values_list('service_id', flat=True)
            .distinct()
        )

    @classmethod
    @transaction.atomic
    def repair_provider_lifecycle_state(
        cls,
        *,
        provider_names: list[str],
        effective_date,
        reason: str = '',
    ) -> list[dict]:
        """
        Восстанавливает provider/team links и реактивирует филиалы после сломанной reactivate-логики.
        """
        from .lifecycle_services import ProviderLifecycleService

        repaired: list[dict] = []
        providers = (
            Provider.objects.select_for_update()
            .filter(name__in=provider_names)
            .order_by('name')
        )
        for provider in providers:
            restored_link_ids, restored_user_ids = ProviderLifecycleService._restore_provider_team_after_reactivation(
                provider=provider,
                terminated_effective_date=provider.partnership_effective_date,
            )

            restored_role_ids: list[int] = []
            restored_location_ids: list[int] = []
            locations = list(
                ProviderLocation.objects.select_for_update()
                .filter(provider=provider)
                .order_by('id')
            )
            for location in locations:
                if location.lifecycle_status != ProviderLocation.LIFECYCLE_STATUS_ACTIVE:
                    location.lifecycle_status = ProviderLocation.LIFECYCLE_STATUS_ACTIVE
                    location.lifecycle_effective_date = effective_date
                    location.lifecycle_resume_date = None
                    location.lifecycle_reason = reason
                    location.is_active = True
                    location.save(
                        update_fields=[
                            'lifecycle_status',
                            'lifecycle_effective_date',
                            'lifecycle_resume_date',
                            'lifecycle_reason',
                            'is_active',
                            'updated_at',
                        ]
                    )
                    restored_location_ids.append(location.id)

                location_role_ids, role_user_ids = ProviderLifecycleService._restore_location_team_after_reactivation(
                    location=location,
                    inactive_since_date=location.lifecycle_effective_date,
                )
                restored_role_ids.extend(location_role_ids)
                restored_user_ids.update(role_user_ids)

            ProviderLifecycleService._sync_access_roles_for_users(restored_user_ids)
            repaired.append(
                {
                    'provider_id': provider.id,
                    'provider_name': provider.name,
                    'restored_provider_link_ids': restored_link_ids,
                    'restored_location_role_ids': restored_role_ids,
                    'reactivated_location_ids': restored_location_ids,
                }
            )
        return repaired

    @classmethod
    def _validate_provider_service(cls, *, provider: Provider, service: Service) -> None:
        """
        Проверяет, что услуга разрешена для организации и клиентская.
        """
        if not service.is_client_facing:
            raise ValidationError(_('Technical services cannot be added to organization pricing.'))

        root_ids = list(
            provider.available_category_levels.filter(level=0, parent__isnull=True)
            .values_list('id', flat=True)
        )
        allowed_ids = set(root_ids)
        frontier_ids = set(root_ids)
        while frontier_ids:
            child_ids = set(
                Service.objects.filter(parent_id__in=frontier_ids, is_active=True)
                .values_list('id', flat=True)
            ) - allowed_ids
            if not child_ids:
                break
            allowed_ids.update(child_ids)
            frontier_ids = child_ids

        if service.id not in allowed_ids:
            raise ValidationError(_('Service must be from provider\'s available category levels (level 0).'))

    @classmethod
    def _validate_pet_types_belong_to_provider(cls, *, provider: Provider, prices: list[dict]) -> None:
        """
        Проверяет, что org-level матрица использует только pet types организации.
        """
        served_ids = set(cls.get_provider_served_pet_types(provider).values_list('id', flat=True))
        for item in prices:
            if item['pet_type_id'] not in served_ids:
                raise ValidationError(_('Each pet type must be served by at least one branch of the organization.'))

    @classmethod
    def _validate_unified_mode_coverage(cls, *, provider: Provider, service_id: int, prices: list[dict]) -> None:
        """
        При включённом unified mode запрещает терять покрытие существующих branch rows.
        """
        if not provider.use_unified_service_pricing:
            return

        provided_keys = {
            (item['pet_type_id'], variant['size_code'])
            for item in prices
            for variant in item.get('variants', [])
        }
        missing_keys = []
        existing_rows = (
            ProviderLocationService.objects.filter(
                location__provider=provider,
                service_id=service_id,
                is_active=True,
            )
            .values_list('pet_type_id', 'size_code')
            .distinct()
        )
        for pet_type_id, size_code in existing_rows:
            if (pet_type_id, size_code) not in provided_keys:
                missing_keys.append(f'{pet_type_id}:{size_code}')

        if missing_keys:
            raise ValidationError(
                _('Organization pricing must cover every existing branch price combination before unified mode can stay enabled.')
            )

    @classmethod
    def _validate_full_unified_pricing_coverage(cls, provider: Provider) -> None:
        """
        Проверяет, что org-level матрица покрывает все текущие branch rows организации.
        """
        provider_keys = set(
            ProviderServicePricing.objects.filter(provider=provider, is_active=True)
            .values_list('service_id', 'pet_type_id', 'size_code')
        )
        missing = []
        existing_rows = (
            ProviderLocationService.objects.filter(location__provider=provider, is_active=True)
            .values_list('service_id', 'pet_type_id', 'size_code')
            .distinct()
        )
        for service_id, pet_type_id, size_code in existing_rows:
            if (service_id, pet_type_id, size_code) not in provider_keys:
                missing.append(f'{service_id}:{pet_type_id}:{size_code}')

        if missing:
            raise ValidationError(
                _('Cannot enable unified organization pricing until organization-level prices cover all existing branch price rows.')
            )

    @classmethod
    def _bootstrap_provider_prices_from_locations(cls, *, provider: Provider) -> list[int]:
        """
        Заполняет недостающие org-level price rows текущими branch prices.

        Существующие org-level строки остаются источником истины. Для комбинаций,
        которых ещё нет на уровне организации, берётся первое активное branch row
        по порядку location_id / row id.
        """
        provider_served_pet_type_ids = set(
            cls.get_provider_served_pet_types(provider).values_list('id', flat=True)
        )
        if not provider_served_pet_type_ids:
            return []

        existing_keys = set(
            ProviderServicePricing.objects.select_for_update()
            .filter(provider=provider)
            .values_list('service_id', 'pet_type_id', 'size_code')
        )
        branch_rows = (
            ProviderLocationService.objects.select_related('service')
            .filter(
                location__provider=provider,
                service__is_client_facing=True,
                pet_type_id__in=provider_served_pet_type_ids,
                is_active=True,
            )
            .order_by('service_id', 'pet_type_id', 'size_code', 'location_id', 'id')
        )

        created_rows: list[ProviderServicePricing] = []
        created_service_ids: set[int] = set()
        for branch_row in branch_rows:
            key = (branch_row.service_id, branch_row.pet_type_id, branch_row.size_code)
            if key in existing_keys:
                continue
            created_rows.append(
                ProviderServicePricing(
                    provider=provider,
                    service_id=branch_row.service_id,
                    pet_type_id=branch_row.pet_type_id,
                    size_code=branch_row.size_code,
                    price=branch_row.price,
                    duration_minutes=branch_row.duration_minutes,
                    tech_break_minutes=branch_row.tech_break_minutes,
                    is_active=True,
                )
            )
            existing_keys.add(key)
            created_service_ids.add(branch_row.service_id)

        if created_rows:
            ProviderServicePricing.objects.bulk_create(created_rows)

        return sorted(created_service_ids)

    @classmethod
    @transaction.atomic
    def update_provider_served_pet_types(cls, *, provider_id: int, pet_type_ids: list[int]) -> dict:
        """
        Обновляет org-level scope типов животных для организации.
        """
        provider = Provider.objects.select_for_update().prefetch_related('served_pet_types').get(pk=provider_id)
        allowed_ids = set(PetType.objects.filter(id__in=pet_type_ids).values_list('id', flat=True))
        requested_ids = set(pet_type_ids)
        if allowed_ids != requested_ids:
            raise ValidationError(_('Unknown pet type was provided.'))

        if provider.use_unified_service_pricing:
            invalid_locations = []
            for location in ProviderLocation.objects.filter(provider=provider).prefetch_related('served_pet_types'):
                location_ids = set(location.served_pet_types.values_list('id', flat=True))
                if not location_ids.issubset(requested_ids):
                    invalid_locations.append(location.name)
            if invalid_locations:
                raise ValidationError(
                    _('Every branch served pet type must stay within the organization served pet types while unified pricing is enabled.')
                )

        provider.served_pet_types.set(sorted(requested_ids))
        ProviderServicePricing.objects.filter(provider=provider).exclude(pet_type_id__in=requested_ids).delete()

        return {
            'served_pet_type_ids': sorted(requested_ids),
        }

    @classmethod
    def _sync_service_to_locations(cls, *, provider: Provider, service_ids: list[int]) -> list[int]:
        """
        Синхронизирует org-level цены в branch rows для заданных услуг.
        """
        if not service_ids:
            return []

        pricing_rows = (
            ProviderServicePricing.objects.select_for_update()
            .filter(provider=provider, service_id__in=service_ids, is_active=True)
            .order_by('service_id', 'pet_type_id', 'size_code')
        )
        pricing_map: dict[int, dict[int, list[ProviderServicePricing]]] = defaultdict(lambda: defaultdict(list))
        for row in pricing_rows:
            pricing_map[row.service_id][row.pet_type_id].append(row)

        synced_location_ids: list[int] = []
        locations = list(
            ProviderLocation.objects.select_for_update()
            .filter(provider=provider)
            .prefetch_related('served_pet_types')
        )
        for location in locations:
            served_pet_type_ids = set(location.served_pet_types.values_list('id', flat=True))
            if not served_pet_type_ids:
                continue

            existing_rows = list(
                ProviderLocationService.objects.select_for_update().filter(
                    location=location,
                    service_id__in=service_ids,
                )
            )
            if not existing_rows:
                continue

            rows_by_service: dict[int, list[ProviderLocationService]] = defaultdict(list)
            for row in existing_rows:
                rows_by_service[row.service_id].append(row)

            location_changed = False
            for service_id in service_ids:
                service_rows = rows_by_service.get(service_id, [])
                if not service_rows:
                    continue

                relevant_rows = [
                    row
                    for row in service_rows
                    if row.pet_type_id in served_pet_type_ids
                ]
                existing_pet_type_ids = {row.pet_type_id for row in relevant_rows}
                if not existing_pet_type_ids:
                    continue

                existing_by_key = {
                    (row.pet_type_id, row.size_code): row
                    for row in relevant_rows
                }
                expected_keys = set()
                rows_to_create = []
                rows_to_update = []
                for pet_type_id in sorted(existing_pet_type_ids):
                    for pricing_row in pricing_map.get(service_id, {}).get(pet_type_id, []):
                        key = (pet_type_id, pricing_row.size_code)
                        expected_keys.add(key)
                        existing_row = existing_by_key.get(key)
                        if existing_row is not None:
                            changed = False
                            if existing_row.price != pricing_row.price:
                                existing_row.price = pricing_row.price
                                changed = True
                            if existing_row.duration_minutes != pricing_row.duration_minutes:
                                existing_row.duration_minutes = pricing_row.duration_minutes
                                changed = True
                            if existing_row.tech_break_minutes != pricing_row.tech_break_minutes:
                                existing_row.tech_break_minutes = pricing_row.tech_break_minutes
                                changed = True
                            if not existing_row.is_active:
                                existing_row.is_active = True
                                changed = True
                            if changed:
                                rows_to_update.append(existing_row)
                            continue

                        rows_to_create.append(
                            ProviderLocationService(
                                location=location,
                                service_id=service_id,
                                pet_type_id=pet_type_id,
                                size_code=pricing_row.size_code,
                                price=pricing_row.price,
                                duration_minutes=pricing_row.duration_minutes,
                                tech_break_minutes=pricing_row.tech_break_minutes,
                                is_active=True,
                            )
                        )

                stale_ids = [
                    row.id
                    for key, row in existing_by_key.items()
                    if key not in expected_keys
                ]
                if stale_ids:
                    ProviderLocationService.objects.filter(id__in=stale_ids).delete()
                    location_changed = True

                if rows_to_update:
                    ProviderLocationService.objects.bulk_update(
                        rows_to_update,
                        ['price', 'duration_minutes', 'tech_break_minutes', 'is_active', 'updated_at'],
                    )
                    location_changed = True

                if rows_to_create:
                    ProviderLocationService.objects.bulk_create(rows_to_create)
                    location_changed = True

                if not expected_keys:
                    continue

            if location_changed:
                synced_location_ids.append(location.id)

        return synced_location_ids

    @classmethod
    def validate_branch_price_mutation_allowed(cls, *, provider: Provider) -> None:
        """
        Блокирует branch-level изменение матрицы цен, когда включён unified mode.
        """
        if provider.use_unified_service_pricing:
            raise ValidationError(
                _('Branch price matrix is read-only while unified organization pricing is enabled.')
            )
