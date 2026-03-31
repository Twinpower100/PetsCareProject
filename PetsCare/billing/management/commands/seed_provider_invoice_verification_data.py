from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from billing.invoice_services import InvoiceGenerationService
from billing.models import Invoice
from booking.constants import (
    BOOKING_STATUS_COMPLETED,
    COMPLETED_BY_SYSTEM,
    COMPLETION_REASON_AUTO_TIMEOUT,
)
from booking.models import Booking, BookingPayment
from booking.services import BookingAvailabilityService, BookingTransactionService
from pets.models import Pet, PetOwner, SizeRule
from providers.models import Provider, ProviderLocationService
from users.models import User


@dataclass(frozen=True)
class SeedScenario:
    code: str
    label: str
    via_service: bool
    payment_method: str
    price: Decimal
    start_day: int
    start_hour: int
    start_minute: int


class Command(BaseCommand):
    help = (
        'Seed deterministic completed bookings and invoices for provider invoice verification '
        '(service-created and direct/manual bookings).'
    )

    target_provider_names = (
        'Roga und Copyta UG',
        'Roga und Kopyta GmbH',
    )
    notes_marker = '[billing-invoice-audit-seed]'
    seed_scenarios = (
        SeedScenario(
            code='service_online_a',
            label='Service / online / included A',
            via_service=True,
            payment_method='online',
            price=Decimal('80.00'),
            start_day=3,
            start_hour=9,
            start_minute=0,
        ),
        SeedScenario(
            code='service_online_b',
            label='Service / online / included B',
            via_service=True,
            payment_method='online',
            price=Decimal('120.00'),
            start_day=6,
            start_hour=11,
            start_minute=0,
        ),
        SeedScenario(
            code='service_cash_excluded',
            label='Service / cash / excluded',
            via_service=True,
            payment_method='cash',
            price=Decimal('95.00'),
            start_day=9,
            start_hour=15,
            start_minute=0,
        ),
        SeedScenario(
            code='direct_online_a',
            label='Direct / online / included A',
            via_service=False,
            payment_method='online',
            price=Decimal('150.00'),
            start_day=13,
            start_hour=10,
            start_minute=30,
        ),
        SeedScenario(
            code='direct_online_b',
            label='Direct / online / included B',
            via_service=False,
            payment_method='online',
            price=Decimal('210.00'),
            start_day=18,
            start_hour=14,
            start_minute=0,
        ),
        SeedScenario(
            code='direct_card_excluded',
            label='Direct / card / excluded',
            via_service=False,
            payment_method='card',
            price=Decimal('140.00'),
            start_day=23,
            start_hour=16,
            start_minute=0,
        ),
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--provider',
            action='append',
            dest='providers',
            help='Provider name to seed. Can be passed multiple times.',
        )
        parser.add_argument(
            '--period-start',
            dest='period_start',
            help='Start date in YYYY-MM-DD format. Defaults to previous full month.',
        )
        parser.add_argument(
            '--period-end',
            dest='period_end',
            help='End date in YYYY-MM-DD format. Defaults to previous full month.',
        )

    def handle(self, *args, **options):
        provider_names = tuple(options['providers'] or self.target_provider_names)
        start_date, end_date = self._resolve_period(
            start_raw=options.get('period_start'),
            end_raw=options.get('period_end'),
        )

        invoice_service = InvoiceGenerationService()
        summaries = []
        for provider_name in provider_names:
            provider = Provider.objects.filter(name=provider_name).first()
            if provider is None:
                raise CommandError(f'Provider "{provider_name}" was not found.')

            with transaction.atomic():
                summary = self._seed_provider_period(
                    provider=provider,
                    start_date=start_date,
                    end_date=end_date,
                    invoice_service=invoice_service,
                )
            summaries.append(summary)

        for summary in summaries:
            self.stdout.write(self.style.SUCCESS(summary))

    def _resolve_period(self, *, start_raw: str | None, end_raw: str | None):
        if bool(start_raw) != bool(end_raw):
            raise CommandError('Use both --period-start and --period-end together.')

        if start_raw and end_raw:
            start_date = datetime.strptime(start_raw, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_raw, '%Y-%m-%d').date()
            if end_date < start_date:
                raise CommandError('--period-end must be on or after --period-start.')
            return start_date, end_date

        today = timezone.localdate()
        current_month_start = today.replace(day=1)
        end_date = current_month_start - timedelta(days=1)
        start_date = end_date.replace(day=1)
        return start_date, end_date

    def _seed_provider_period(self, *, provider: Provider, start_date, end_date, invoice_service: InvoiceGenerationService) -> str:
        provider_marker = self._provider_marker(provider)
        self._cleanup_existing_seed_data(
            provider=provider,
            start_date=start_date,
            end_date=end_date,
            provider_marker=provider_marker,
        )

        owner = self._ensure_owner(provider)
        context = self._find_bookable_context(provider=provider, owner=owner)
        created_bookings: list[Booking] = []

        service_slot_index = 0
        for scenario in self.seed_scenarios:
            pet = self._ensure_pet(
                provider=provider,
                owner=owner,
                pet_type=context['pet_type'],
                weight=context['weight'],
                scenario=scenario,
            )
            booking_notes = self._build_notes(
                provider_marker=provider_marker,
                scenario=scenario,
                start_date=start_date,
                end_date=end_date,
            )
            historical_start = timezone.make_aware(
                datetime.combine(
                    start_date.replace(day=scenario.start_day),
                    time(scenario.start_hour, scenario.start_minute),
                )
            )

            if scenario.via_service:
                future_slot = context['future_slots'][service_slot_index % len(context['future_slots'])]
                service_slot_index += 1
                booking = BookingTransactionService.create_booking(
                    user=owner,
                    pet=pet,
                    provider=provider,
                    employee=future_slot['employee'],
                    service=context['service'],
                    start_time=future_slot['start_time'],
                    price=scenario.price,
                    notes=booking_notes,
                    provider_location=context['provider_location'],
                    escort_owner=owner,
                    source=Booking.BookingSource.BOOKING_SERVICE,
                )
            else:
                employee = context['future_slots'][0]['employee']
                end_time = historical_start + timedelta(minutes=context['duration_minutes'])
                booking = Booking.objects.create(
                    user=owner,
                    escort_owner=owner,
                    pet=pet,
                    provider=provider,
                    provider_location=context['provider_location'],
                    employee=employee,
                    service=context['service'],
                    status=Booking.get_status(BOOKING_STATUS_COMPLETED),
                    start_time=historical_start,
                    end_time=end_time,
                    occupied_duration_minutes=context['duration_minutes'],
                    source=Booking.BookingSource.MANUAL_ENTRY,
                    notes=booking_notes,
                    price=scenario.price,
                    completed_at=end_time,
                    completed_by_actor=COMPLETED_BY_SYSTEM,
                    completion_reason_code=COMPLETION_REASON_AUTO_TIMEOUT,
                )

            self._move_booking_to_historical_completion(
                booking=booking,
                start_time=historical_start,
                duration_minutes=context['duration_minutes'],
                notes=booking_notes,
            )
            self._attach_payment(booking=booking, payment_method=scenario.payment_method)
            created_bookings.append(booking)

        invoice = invoice_service.generate_for_provider(provider, start_date, end_date)
        if invoice is None:
            raise CommandError(f'Invoice was not generated for provider "{provider.name}".')

        invoice.refresh_from_db()
        line_bookings = list(
            invoice.lines.select_related('booking').order_by('booking__completed_at', 'booking__id')
        )
        included_bookings = [booking for booking in created_bookings if booking.payment.payment_method == 'online']
        excluded_bookings = [booking for booking in created_bookings if booking.payment.payment_method != 'online']

        included_ids = {booking.id for booking in included_bookings}
        invoice_booking_ids = {line.booking_id for line in line_bookings}
        if invoice_booking_ids != included_ids:
            raise CommandError(
                f'Invoice {invoice.number} for "{provider.name}" does not match expected online bookings.'
            )

        if any(line.vat_amount != Decimal('0.00') or line.vat_rate is not None for line in line_bookings):
            raise CommandError(f'Invoice {invoice.number} for "{provider.name}" unexpectedly contains VAT.')

        return (
            f'{provider.name}: seeded {len(created_bookings)} completed bookings '
            f'({len(included_bookings)} invoiced, {len(excluded_bookings)} excluded), '
            f'invoice={invoice.number}, amount={invoice.amount}'
        )

    def _cleanup_existing_seed_data(self, *, provider: Provider, start_date, end_date, provider_marker: str) -> None:
        invoices = (
            Invoice.objects.filter(provider=provider, start_date=start_date, end_date=end_date)
            .prefetch_related('lines__booking')
            .order_by('id')
        )
        for invoice in invoices:
            line_bookings = [line.booking for line in invoice.lines.all() if line.booking_id]
            if line_bookings and any(provider_marker not in (booking.notes or '') for booking in line_bookings):
                raise CommandError(
                    f'Invoice {invoice.number} already exists for {provider.name} and contains non-seeded bookings.'
                )
            invoice.delete()

        Booking.objects.filter(
            notes__contains=provider_marker,
        ).filter(
            completed_at__date__range=(start_date, end_date),
        ).delete()

    def _ensure_owner(self, provider: Provider) -> User:
        slug = slugify(provider.name)
        phone_suffix = f'{provider.id:07d}'
        owner, _ = User.objects.get_or_create(
            email=f'billing-audit-{slug}@example.com',
            defaults={
                'first_name': 'Billing',
                'last_name': f'Audit {provider.id}',
                'phone_number': f'+38269{phone_suffix}',
            },
        )
        if hasattr(owner, 'add_role'):
            owner.add_role('basic_user')
        return owner

    def _find_bookable_context(self, *, provider: Provider, owner: User) -> dict:
        date_start = timezone.localdate() + timedelta(days=1)
        date_end = date_start + timedelta(days=21)
        rows = (
            ProviderLocationService.objects.filter(
                location__provider=provider,
                location__is_active=True,
                is_active=True,
            )
            .select_related('location', 'service', 'pet_type')
            .order_by('id')
        )

        for row in rows:
            weight = self._resolve_weight_for_size(row.pet_type, row.size_code)
            probe_pet = Pet(name='Billing audit probe', pet_type=row.pet_type, weight=weight)
            grouped_slots = BookingAvailabilityService.get_available_slots(
                provider_location=row.location,
                service=row.service,
                pet=probe_pet,
                requester=owner,
                date_start=date_start,
                date_end=date_end,
            )
            flat_slots = []
            for day_slots in grouped_slots.values():
                for slot in day_slots:
                    employee = row.location.provider.employees.filter(id=slot['employee_id']).first()
                    if employee is None:
                        continue
                    flat_slots.append(
                        {
                            'start_time': datetime.fromisoformat(slot['start_time']),
                            'employee': employee,
                        }
                    )

            if flat_slots:
                return {
                    'provider_location': row.location,
                    'service': row.service,
                    'pet_type': row.pet_type,
                    'weight': weight,
                    'duration_minutes': int(row.duration_minutes),
                    'future_slots': flat_slots,
                }

        raise CommandError(f'No bookable location/service context found for provider "{provider.name}".')

    def _resolve_weight_for_size(self, pet_type, size_code: str) -> Decimal:
        rule = SizeRule.objects.filter(pet_type=pet_type, size_code=size_code).order_by('min_weight_kg').first()
        if rule is None:
            return Decimal('5.00')
        return (rule.min_weight_kg + rule.max_weight_kg) / Decimal('2')

    def _ensure_pet(self, *, provider: Provider, owner: User, pet_type, weight: Decimal, scenario: SeedScenario) -> Pet:
        slug = slugify(provider.name)
        pet, _ = Pet.objects.get_or_create(
            name=f'Billing Audit {provider.id} {scenario.code}',
            pet_type=pet_type,
            defaults={
                'weight': weight,
                'gender': 'U',
                'is_neutered': 'U',
                'description': f'{self.notes_marker} {slug} {scenario.label}',
            },
        )
        fields_to_update = []
        if pet.weight != weight:
            pet.weight = weight
            fields_to_update.append('weight')
        if pet.description != f'{self.notes_marker} {slug} {scenario.label}':
            pet.description = f'{self.notes_marker} {slug} {scenario.label}'
            fields_to_update.append('description')
        if fields_to_update:
            pet.save(update_fields=fields_to_update)

        pet_owner, created = PetOwner.objects.get_or_create(
            pet=pet,
            user=owner,
            defaults={'role': 'main'},
        )
        if not created and pet_owner.role != 'main':
            pet_owner.role = 'main'
            pet_owner.save(update_fields=['role'])
        return pet

    def _move_booking_to_historical_completion(self, *, booking: Booking, start_time, duration_minutes: int, notes: str) -> None:
        end_time = start_time + timedelta(minutes=duration_minutes)
        booking.start_time = start_time
        booking.end_time = end_time
        booking.status = Booking.get_status(BOOKING_STATUS_COMPLETED)
        booking.completed_at = end_time
        booking.completed_by_actor = COMPLETED_BY_SYSTEM
        booking.completed_by_user = None
        booking.completion_reason_code = COMPLETION_REASON_AUTO_TIMEOUT
        booking.notes = notes
        booking.save(
            update_fields=[
                'start_time',
                'end_time',
                'status',
                'completed_at',
                'completed_by_actor',
                'completed_by_user',
                'completion_reason_code',
                'notes',
                'updated_at',
            ]
        )

    def _attach_payment(self, *, booking: Booking, payment_method: str) -> None:
        BookingPayment.objects.update_or_create(
            booking=booking,
            defaults={
                'amount': booking.price,
                'payment_method': payment_method,
                'transaction_id': f'SEED-{booking.id}-{payment_method.upper()}',
            },
        )

    def _provider_marker(self, provider: Provider) -> str:
        return f'{self.notes_marker} provider={provider.id}'

    def _build_notes(self, *, provider_marker: str, scenario: SeedScenario, start_date, end_date) -> str:
        return (
            f'{provider_marker} scenario={scenario.code} '
            f'path={"service" if scenario.via_service else "direct"} '
            f'payment={scenario.payment_method} period={start_date}:{end_date}'
        )
