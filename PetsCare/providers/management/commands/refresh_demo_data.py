from __future__ import annotations

from contextlib import contextmanager
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_delete, post_save
from django.utils import timezone

from billing.models import Invoice, PaymentHistory
from billing.services import MultiLevelBlockingService
from booking.manual_notes import build_manual_booking_notes
from booking.manual_v2_models import ManualBooking, ManualVisitProtocol, ProviderClientLead
from booking.models import Booking, BookingCancellationReason, BookingPayment, BookingStatus
from catalog.models import Service
from geolocation.models import Address, UserLocation
from pets.models import Breed, Pet, PetOwner, PetType, SizeRule
from providers.models import (
    Employee,
    EmployeeLocationRole,
    EmployeeLocationService,
    EmployeeProvider,
    LocationSchedule,
    Provider,
    ProviderLocation,
    ProviderLocationService,
    ProviderServicePricing,
    Schedule,
)
from providers.pricing_services import ProviderPricingService
from sitters.models import Conversation, PetSitting, PetSittingAd, PetSittingResponse, SitterProfile
from users.models import EmailVerificationToken

User = get_user_model()


class Command(BaseCommand):
    help = 'Полный идемпотентный refresh demo-данных для MVP, e2e и демо-прогонов.'

    demo_password = 'Secret123!'
    team_start_date = date(2026, 4, 1)
    provider_ops_manual_lead_phone = '+38267027705'

    public_booking_provider_name = 'Provider_PublicBookingE2E'
    public_booking_service_code = 'e2e_public_booking_service'
    public_booking_service_name = 'E2E Bath and Brush'

    org_pricing_provider_name = 'Provider_OrgPricing'
    org_pricing_service_code = 'org_pricing_grooming'
    org_pricing_service_name = 'Org Pricing Grooming'

    org_pricing_toggle_provider_name = 'Provider_OrgPricingToggle'
    org_pricing_toggle_service_code = 'org_pricing_toggle_grooming'
    org_pricing_toggle_service_name = 'Org Pricing Toggle Grooming'

    provider_ops_provider_name = 'Provider_AdminOps'
    provider_ops_primary_service_code = 'admin_ops_grooming'
    provider_ops_primary_service_name = 'Admin Ops Grooming'
    provider_ops_secondary_service_code = 'admin_ops_nail_trim'
    provider_ops_secondary_service_name = 'Admin Ops Nail Trim'

    exact_demo_emails = {
        'billing-demo-owner@example.com',
        'billing-admin@example.com',
        'billing-owner-provider_fullypaid@example.com',
        'billing-owner-provider_level1@example.com',
        'billing-owner-provider_level2@example.com',
        'billing-owner-provider_level3@example.com',
        'public-booking-provider@example.com',
        'public-booking-specialist@example.com',
        'pet-invite-owner@example.com',
        'pet-invite-recipient@example.com',
        'shared-pet-owner@example.com',
        'shared-pet-coowner1@example.com',
        'shared-pet-coowner2@example.com',
        'boarding-browser-owner@example.com',
        'boarding-browser-sitter@example.com',
        'boarding-accepted-owner@example.com',
        'boarding-accepted-sitter@example.com',
        'org-pricing-owner@example.com',
        'org-pricing-toggle-owner@example.com',
        'provider-ops-owner@example.com',
        'provider-ops-client@example.com',
        'provider-ops-worker1@example.com',
        'provider-ops-worker2@example.com',
        'manual-browser-owner@example.com',
    }
    demo_email_prefixes = (
        'browser-owner-',
        'provider-ops-owner-',
        'provider-ops-client-',
        'provider-ops-worker1-',
        'provider-ops-worker2-',
    )
    exact_demo_provider_names = {
        'Provider_FullyPaid',
        'Provider_Level1',
        'Provider_Level2',
        'Provider_Level3',
        public_booking_provider_name,
        org_pricing_provider_name,
        org_pricing_toggle_provider_name,
        provider_ops_provider_name,
    }
    demo_provider_name_prefixes = ('Provider Admin Ops Demo',)
    exact_demo_pet_names = {
        'Billing Demo Pet',
        'Invite Browser Pet',
        'Shared Demo Pet',
        'Boarding Browser Pet',
        'Boarding Accepted Pet',
        'AdminOps Demo Pet',
    }
    demo_pet_name_prefixes = ('Browser Pet ', 'Manual Browser Pet ', 'AdminOps Pet ')
    exact_demo_service_codes = {
        'billing_demo_service',
        public_booking_service_code,
        org_pricing_service_code,
        org_pricing_toggle_service_code,
        provider_ops_primary_service_code,
        provider_ops_secondary_service_code,
    }
    demo_service_code_prefixes = ('admin_ops_grooming_', 'admin_ops_nail_trim_')
    exact_demo_breed_codes = {
        'e2e_public_booking_dog',
        'e2e_invite_dog',
        'shared_demo_dog',
        'e2e_boarding_dog',
        'e2e_boarding_accepted_dog',
        'admin_ops_demo_breed',
    }
    demo_breed_code_prefixes = ('admin_ops_breed_',)
    exact_demo_addresses = {
        'Booking Demo Street 1, Podgorica',
        'Org Pricing Street 1',
        'Org Pricing Toggle Street 1',
        'Подгорица, Черногория',
        'Billing Street 1, Provider_FullyPaid',
        'Billing Street 1, Provider_Level1',
        'Billing Street 1, Provider_Level2',
        'Billing Street 1, Provider_Level3',
        'Admin Ops Street 1, Podgorica',
    }
    demo_address_prefixes = ('Admin Ops Street ', 'Billing Street 1, Provider_')

    @transaction.atomic
    def handle(self, *args, **options):
        self._ensure_reference_data()
        with self._muted_booking_notifications():
            self._cleanup_demo_data()
            catalog = self._ensure_shared_catalog()
            self._seed_billing_scenarios()
            self._seed_public_booking_scenario(catalog)
            self._seed_pet_invite_scenario(catalog)
            self._seed_shared_pet_scenario(catalog)
            self._seed_boarding_scenarios(catalog)
            self._seed_org_pricing_scenarios(catalog)
            self._seed_provider_operations_scenario(catalog)

        MultiLevelBlockingService().check_all_providers()
        self._validate_demo_visibility_rules()
        self.stdout.write(self.style.SUCCESS('Demo data refresh completed successfully.'))

    def _ensure_reference_data(self):
        """Подготавливает минимальные справочники, без которых сиды нестабильны."""
        call_command('ensure_user_types')
        BookingStatus.ensure_canonical_statuses()
        BookingCancellationReason.ensure_default_reasons()

    @contextmanager
    def _muted_booking_notifications(self):
        """Временно отключает email/notification side effects для demo refresh."""
        from booking.signals import send_booking_confirmation, send_payment_confirmation
        from notifications.signals import (
            handle_booking_cancellation_notification,
            handle_booking_notifications,
            handle_pet_reminder_notifications,
            handle_provider_blocking_notifications,
        )

        disconnected = []
        for signal, receiver in (
            (post_save, send_booking_confirmation),
            (post_save, send_payment_confirmation),
            (post_save, handle_booking_notifications),
            (post_delete, handle_booking_cancellation_notification),
            (post_save, handle_provider_blocking_notifications),
            (post_save, handle_pet_reminder_notifications),
        ):
            try:
                sender = Booking
                if receiver is send_payment_confirmation:
                    sender = BookingPayment
                elif receiver is handle_provider_blocking_notifications:
                    sender = Provider
                elif receiver is handle_pet_reminder_notifications:
                    sender = PetOwner

                if signal.disconnect(receiver, sender=sender):
                    disconnected.append((signal, receiver))
            except Exception:
                continue

        try:
            yield
        finally:
            for signal, receiver in disconnected:
                sender = Booking
                if receiver is send_payment_confirmation:
                    sender = BookingPayment
                elif receiver is handle_provider_blocking_notifications:
                    sender = Provider
                elif receiver is handle_pet_reminder_notifications:
                    sender = PetOwner

                signal.connect(receiver, sender=sender)

    def _cleanup_demo_data(self):
        """Удаляет только demo/test namespaces, чтобы refresh был повторяемым и безопасным."""
        demo_provider_ids = list(self._demo_provider_queryset().values_list('id', flat=True))
        demo_user_ids = list(self._demo_user_queryset().values_list('id', flat=True))
        demo_pet_ids = list(self._demo_pet_queryset().values_list('id', flat=True))
        demo_location_ids = list(
            ProviderLocation.objects.filter(provider_id__in=demo_provider_ids).values_list('id', flat=True)
        )

        if demo_user_ids:
            EmailVerificationToken.objects.filter(user_id__in=demo_user_ids).delete()

        if demo_provider_ids or demo_location_ids or demo_user_ids:
            ManualVisitProtocol.objects.filter(
                Q(manual_booking__provider_id__in=demo_provider_ids)
                | Q(provider_location_id__in=demo_location_ids)
                | Q(created_by_id__in=demo_user_ids)
                | Q(updated_by_id__in=demo_user_ids)
            ).delete()
            ManualBooking.objects.filter(
                Q(provider_id__in=demo_provider_ids)
                | Q(provider_location_id__in=demo_location_ids)
                | Q(created_by_id__in=demo_user_ids)
                | Q(updated_by_id__in=demo_user_ids)
            ).delete()
            ProviderClientLead.objects.filter(
                Q(provider_id__in=demo_provider_ids) | Q(provider_location_id__in=demo_location_ids)
            ).delete()

        if demo_user_ids:
            UserLocation.objects.filter(user_id__in=demo_user_ids).delete()

        if demo_pet_ids or demo_user_ids:
            Conversation.objects.filter(
                Q(participants__id__in=demo_user_ids)
                | Q(pet_sitting_ad__pet_id__in=demo_pet_ids)
                | Q(pet_sitting__pet_id__in=demo_pet_ids)
            ).distinct().delete()
            PetSitting.objects.filter(
                Q(pet_id__in=demo_pet_ids)
                | Q(ad__owner_id__in=demo_user_ids)
                | Q(sitter__user_id__in=demo_user_ids)
            ).delete()
            PetSittingResponse.objects.filter(
                Q(ad__pet_id__in=demo_pet_ids) | Q(sitter__user_id__in=demo_user_ids)
            ).delete()
            PetSittingAd.objects.filter(Q(pet_id__in=demo_pet_ids) | Q(owner_id__in=demo_user_ids)).delete()
            SitterProfile.objects.filter(user_id__in=demo_user_ids).update(is_active=False)
            SitterProfile.objects.filter(user_id__in=demo_user_ids).delete()

        if demo_provider_ids:
            PaymentHistory.objects.filter(provider_id__in=demo_provider_ids).delete()
            Invoice.objects.filter(provider_id__in=demo_provider_ids).delete()

        if demo_provider_ids or demo_pet_ids or demo_user_ids:
            Booking.objects.filter(
                Q(provider_id__in=demo_provider_ids)
                | Q(provider_location__provider_id__in=demo_provider_ids)
                | Q(user_id__in=demo_user_ids)
                | Q(escort_owner_id__in=demo_user_ids)
                | Q(pet_id__in=demo_pet_ids)
            ).delete()

        if demo_pet_ids or demo_user_ids:
            PetOwner.objects.filter(Q(pet_id__in=demo_pet_ids) | Q(user_id__in=demo_user_ids)).delete()
            Pet.objects.filter(id__in=demo_pet_ids).delete()

        if demo_provider_ids:
            Provider.objects.filter(id__in=demo_provider_ids).delete()

        if demo_user_ids:
            User.objects.filter(id__in=demo_user_ids).exclude(username='pet_admin').delete()

        Service.objects.filter(self._service_query()).delete()
        Breed.objects.filter(self._breed_query()).delete()
        Address.objects.filter(self._address_query()).delete()

    def _demo_user_queryset(self):
        return User.objects.filter(self._email_query('email'))

    def _demo_provider_queryset(self):
        return Provider.objects.filter(self._provider_name_query())

    def _demo_pet_queryset(self):
        return Pet.objects.filter(self._pet_name_query())

    def _email_query(self, field_name: str):
        query = Q(**{f'{field_name}__in': sorted(self.exact_demo_emails)})
        for prefix in self.demo_email_prefixes:
            query |= Q(**{f'{field_name}__startswith': prefix})
        return query

    def _provider_name_query(self):
        query = Q(name__in=sorted(self.exact_demo_provider_names))
        for prefix in self.demo_provider_name_prefixes:
            query |= Q(name__startswith=prefix)
        return query

    def _pet_name_query(self):
        query = Q(name__in=sorted(self.exact_demo_pet_names))
        for prefix in self.demo_pet_name_prefixes:
            query |= Q(name__startswith=prefix)
        return query

    def _service_query(self):
        query = Q(code__in=sorted(self.exact_demo_service_codes))
        for prefix in self.demo_service_code_prefixes:
            query |= Q(code__startswith=prefix)
        return query

    def _breed_query(self):
        query = Q(code__in=sorted(self.exact_demo_breed_codes))
        for prefix in self.demo_breed_code_prefixes:
            query |= Q(code__startswith=prefix)
        return query

    def _address_query(self):
        query = Q(formatted_address__in=sorted(self.exact_demo_addresses))
        for prefix in self.demo_address_prefixes:
            query |= Q(formatted_address__startswith=prefix)
        return query

    def _ensure_shared_catalog(self):
        """Готовит общие pet/service сущности, которые переиспользуются разными demo-сценариями."""
        dog = self._ensure_pet_type(
            code='dog',
            name='Dog',
            name_ru='Собака',
            name_me='Pas',
            name_de='Hund',
        )
        cat = self._ensure_pet_type(
            code='cat',
            name='Cat',
            name_ru='Кошка',
            name_me='Mačka',
            name_de='Katze',
        )
        self._ensure_size_rules(dog)
        self._ensure_size_rules(cat)

        return {
            'dog': dog,
            'cat': cat,
            'public_booking_breed': self._ensure_breed('e2e_public_booking_dog', dog, 'E2E Demo Dog'),
            'invite_breed': self._ensure_breed('e2e_invite_dog', dog, 'Invite Demo Dog'),
            'shared_breed': self._ensure_breed('shared_demo_dog', dog, 'Shared Demo Dog'),
            'boarding_breed': self._ensure_breed('e2e_boarding_dog', dog, 'Boarding Demo Dog'),
            'boarding_accepted_breed': self._ensure_breed(
                'e2e_boarding_accepted_dog',
                dog,
                'Boarding Accepted Demo Dog',
            ),
            'admin_ops_breed': self._ensure_breed('admin_ops_demo_breed', dog, 'Admin Ops Demo Breed'),
        }

    def _seed_billing_scenarios(self):
        """Переиспользует существующий deterministic billing seed и обновляет blocking state."""
        call_command('generate_billing_data')

    def _seed_public_booking_scenario(self, catalog):
        """Создаёт клиентский публичный booking flow без скрытых услуг."""
        owner_user = self._ensure_user(
            email='public-booking-provider@example.com',
            username='public-booking-provider@example.com',
            phone_number='+38267002001',
            first_name='Public',
            last_name='Provider',
            roles=('provider_admin',),
        )
        specialist_user = self._ensure_user(
            email='public-booking-specialist@example.com',
            username='public-booking-specialist@example.com',
            phone_number='+38267002002',
            first_name='Booking',
            last_name='Specialist',
            roles=('employee',),
        )
        owner_employee = self._ensure_employee(owner_user)
        specialist_employee = self._ensure_employee(specialist_user)

        provider = self._ensure_provider(
            name=self.public_booking_provider_name,
            email='public-booking-provider-org@example.com',
            phone_number='+38267012001',
            use_unified_service_pricing=False,
        )
        provider.available_category_levels.clear()

        service = self._ensure_service(
            code=self.public_booking_service_code,
            name=self.public_booking_service_name,
            hierarchy_order='910',
        )
        provider.available_category_levels.add(service)
        provider.served_pet_types.set([catalog['dog']])

        self._ensure_employee_provider(owner_employee, provider, role=EmployeeProvider.ROLE_OWNER, is_owner=True)
        self._ensure_employee_provider(
            specialist_employee,
            provider,
            role=EmployeeProvider.ROLE_SERVICE_WORKER,
        )

        location = self._ensure_location(
            provider=provider,
            name='Public Booking Branch',
            formatted_address='Booking Demo Street 1, Podgorica',
            country='Montenegro',
            city='Podgorica',
            street='Booking Demo Street',
            house_number='1',
            latitude=42.4411,
            longitude=19.2624,
            phone_number='+38267012002',
            email='public-booking-branch@example.com',
        )
        location.served_pet_types.set([catalog['dog']])
        owner_employee.locations.add(location)
        specialist_employee.locations.add(location)
        self._ensure_location_role(
            owner_employee,
            location,
            EmployeeLocationRole.ROLE_BRANCH_MANAGER,
        )
        self._ensure_location_role(
            specialist_employee,
            location,
            EmployeeLocationRole.ROLE_SERVICE_WORKER,
        )
        self._ensure_location_service(
            location=location,
            service=service,
            pet_type=catalog['dog'],
            size_code='S',
            price='35.00',
            duration_minutes=60,
        )
        self._ensure_employee_location_service(specialist_employee, location, service)
        self._ensure_weekly_schedules(
            location,
            [
                {'employee': specialist_employee, 'start': time(8, 0), 'end': time(18, 0)},
            ],
        )
        self._remove_hidden_demo_prices(provider)

    def _seed_pet_invite_scenario(self, catalog):
        """Создаёт базовый pet invite demo без заранее принятого invite."""
        owner = self._ensure_user(
            email='pet-invite-owner@example.com',
            username='pet-invite-owner@example.com',
            phone_number='+38267002101',
            first_name='Invite',
            last_name='Owner',
            roles=('basic_user',),
        )
        recipient = self._ensure_user(
            email='pet-invite-recipient@example.com',
            username='pet-invite-recipient@example.com',
            phone_number='+38267002102',
            first_name='Invite',
            last_name='Recipient',
            roles=('basic_user',),
        )
        self._ensure_pet(
            name='Invite Browser Pet',
            owner=owner,
            pet_type=catalog['dog'],
            breed=catalog['invite_breed'],
            weight='7.50',
            description='Pet invite browser demo pet.',
        )
        recipient.refresh_from_db()

    def _seed_shared_pet_scenario(self, catalog):
        """Создаёт отдельный demo-pet с несколькими совладельцами для клиентских показов."""
        owner = self._ensure_user(
            email='shared-pet-owner@example.com',
            username='shared-pet-owner@example.com',
            phone_number='+38267002201',
            first_name='Shared',
            last_name='Owner',
            roles=('basic_user',),
        )
        coowner_one = self._ensure_user(
            email='shared-pet-coowner1@example.com',
            username='shared-pet-coowner1@example.com',
            phone_number='+38267002202',
            first_name='Shared',
            last_name='Coowner One',
            roles=('basic_user',),
        )
        coowner_two = self._ensure_user(
            email='shared-pet-coowner2@example.com',
            username='shared-pet-coowner2@example.com',
            phone_number='+38267002203',
            first_name='Shared',
            last_name='Coowner Two',
            roles=('basic_user',),
        )
        self._ensure_pet(
            name='Shared Demo Pet',
            owner=owner,
            pet_type=catalog['dog'],
            breed=catalog['shared_breed'],
            weight='9.00',
            description='Shared ownership demo pet.',
            coowners=(coowner_one, coowner_two),
        )

    def _seed_boarding_scenarios(self, catalog):
        """Создаёт два boarding-сценария: пустой старт и уже accepted waiting_start."""
        self._seed_boarding_search_scenario(catalog)
        self._seed_boarding_accepted_scenario(catalog)

    def _seed_boarding_search_scenario(self, catalog):
        owner = self._ensure_user(
            email='boarding-browser-owner@example.com',
            username='boarding-browser-owner@example.com',
            phone_number='+38267002301',
            first_name='Boarding',
            last_name='Owner',
            roles=('basic_user',),
        )
        sitter = self._ensure_user(
            email='boarding-browser-sitter@example.com',
            username='boarding-browser-sitter@example.com',
            phone_number='+38267002302',
            first_name='Boarding',
            last_name='Sitter',
            roles=('basic_user', 'pet_sitter'),
        )
        today = timezone.localdate()
        self._ensure_pet(
            name='Boarding Browser Pet',
            owner=owner,
            pet_type=catalog['dog'],
            breed=catalog['boarding_breed'],
            weight='7.00',
            description='Browser-based boarding test pet.',
        )
        self._ensure_sitter_profile(
            sitter,
            description='Calm home boarding with daily updates.',
            experience_years=4,
            available_from=today + timedelta(days=1),
            available_to=today + timedelta(days=21),
            max_distance_km=20,
            hourly_rate='8.00',
        )
        UserLocation.objects.update_or_create(
            user=sitter,
            defaults={
                'point': Point(19.2624, 42.4411, srid=4326),
                'source': 'map',
            },
        )

    def _seed_boarding_accepted_scenario(self, catalog):
        owner = self._ensure_user(
            email='boarding-accepted-owner@example.com',
            username='boarding-accepted-owner@example.com',
            phone_number='+38267002401',
            first_name='Accepted',
            last_name='Owner',
            roles=('basic_user',),
        )
        sitter = self._ensure_user(
            email='boarding-accepted-sitter@example.com',
            username='boarding-accepted-sitter@example.com',
            phone_number='+38267002402',
            first_name='Accepted',
            last_name='Sitter',
            roles=('basic_user', 'pet_sitter'),
        )
        today = timezone.localdate()
        pet = self._ensure_pet(
            name='Boarding Accepted Pet',
            owner=owner,
            pet_type=catalog['dog'],
            breed=catalog['boarding_accepted_breed'],
            weight='8.00',
            description='Accepted boarding demo pet.',
        )
        profile = self._ensure_sitter_profile(
            sitter,
            description='Home boarding with photo updates.',
            experience_years=5,
            available_from=today + timedelta(days=1),
            available_to=today + timedelta(days=30),
            max_distance_km=15,
            hourly_rate='9.50',
        )
        UserLocation.objects.update_or_create(
            user=sitter,
            defaults={
                'point': Point(19.2593642, 42.4304196, srid=4326),
                'source': 'map',
            },
        )
        address = self._ensure_address(
            formatted_address='Подгорица, Черногория',
            country='Черногория',
            city='Подгорица',
            street='Подгорица',
            house_number='1',
            latitude=42.4304196,
            longitude=19.2593642,
        )
        ad = PetSittingAd.objects.create(
            pet=pet,
            owner=owner,
            start_date=today + timedelta(days=2),
            end_date=today + timedelta(days=4),
            description='',
            status='closed',
            location='Подгорица, Черногория',
            structured_address=address,
            max_distance_km=10,
            compensation_type='paid',
        )
        response = PetSittingResponse.objects.create(
            ad=ad,
            sitter=profile,
            message='Могу взять питомца домой, буду присылать фото и короткие отчеты каждый день.',
            status='accepted',
        )
        sitting = PetSitting.objects.create(
            ad=ad,
            response=response,
            sitter=profile,
            pet=pet,
            start_date=ad.start_date,
            end_date=ad.end_date,
            status='waiting_start',
        )
        conversation = Conversation.objects.create(
            pet_sitting_ad=ad,
            pet_sitting=sitting,
            is_active=True,
        )
        conversation.participants.add(owner, sitter)

    def _seed_org_pricing_scenarios(self, catalog):
        """Подготавливает unified pricing и branch-owned pricing варианты."""
        self._seed_unified_org_pricing_scenario(catalog)
        self._seed_branch_owned_pricing_scenario(catalog)

    def _seed_unified_org_pricing_scenario(self, catalog):
        owner = self._ensure_user(
            email='org-pricing-owner@example.com',
            username='org-pricing-owner@example.com',
            phone_number='+38267002501',
            first_name='Org',
            last_name='Pricing',
            roles=('provider_admin',),
        )
        employee = self._ensure_employee(owner)
        provider = self._ensure_provider(
            name=self.org_pricing_provider_name,
            email='provider-org-pricing@example.com',
            phone_number='+38267012501',
            use_unified_service_pricing=False,
        )
        provider.available_category_levels.clear()
        service = self._ensure_service(
            code=self.org_pricing_service_code,
            name=self.org_pricing_service_name,
            hierarchy_order='920',
        )
        provider.available_category_levels.add(service)
        provider.served_pet_types.set([catalog['dog'], catalog['cat']])
        self._ensure_employee_provider(employee, provider, role=EmployeeProvider.ROLE_OWNER, is_owner=True)

        location = self._ensure_location(
            provider=provider,
            name='Org Pricing Branch',
            formatted_address='Org Pricing Street 1',
            country='Montenegro',
            city='Podgorica',
            street='Org Pricing Street',
            house_number='1',
            latitude=42.44,
            longitude=19.26,
            phone_number='+38267012502',
            email='org-pricing-branch@example.com',
        )
        location.served_pet_types.set([catalog['dog']])
        employee.locations.add(location)
        self._ensure_location_role(employee, location, EmployeeLocationRole.ROLE_BRANCH_MANAGER)
        self._ensure_location_service(
            location=location,
            service=service,
            pet_type=catalog['dog'],
            size_code='S',
            price='25.00',
            duration_minutes=30,
        )

        prices = [
            {
                'pet_type_id': catalog['dog'].id,
                'base_price': '45.00',
                'base_duration_minutes': 60,
                'variants': [{'size_code': 'S', 'price': '45.00', 'duration_minutes': 60}],
            },
            {
                'pet_type_id': catalog['cat'].id,
                'base_price': '49.00',
                'base_duration_minutes': 65,
                'variants': [{'size_code': 'S', 'price': '49.00', 'duration_minutes': 65}],
            },
        ]
        ProviderPricingService.replace_provider_service_prices(
            provider_id=provider.id,
            service_id=service.id,
            prices=prices,
        )
        provider.use_unified_service_pricing = True
        provider.save(update_fields=['use_unified_service_pricing', 'updated_at'])
        ProviderPricingService.replace_provider_service_prices(
            provider_id=provider.id,
            service_id=service.id,
            prices=prices,
        )
        self._remove_hidden_demo_prices(provider)

    def _seed_branch_owned_pricing_scenario(self, catalog):
        owner = self._ensure_user(
            email='org-pricing-toggle-owner@example.com',
            username='org-pricing-toggle-owner@example.com',
            phone_number='+38267002601',
            first_name='Org',
            last_name='Toggle',
            roles=('provider_admin',),
        )
        employee = self._ensure_employee(owner)
        provider = self._ensure_provider(
            name=self.org_pricing_toggle_provider_name,
            email='provider-org-pricing-toggle@example.com',
            phone_number='+38267012601',
            use_unified_service_pricing=False,
        )
        provider.available_category_levels.clear()
        service = self._ensure_service(
            code=self.org_pricing_toggle_service_code,
            name=self.org_pricing_toggle_service_name,
            hierarchy_order='921',
        )
        provider.available_category_levels.add(service)
        provider.served_pet_types.set([catalog['dog']])
        self._ensure_employee_provider(employee, provider, role=EmployeeProvider.ROLE_OWNER, is_owner=True)

        location = self._ensure_location(
            provider=provider,
            name='Org Pricing Toggle Branch',
            formatted_address='Org Pricing Toggle Street 1',
            country='Montenegro',
            city='Podgorica',
            street='Org Pricing Toggle Street',
            house_number='1',
            latitude=42.46,
            longitude=19.28,
            phone_number='+38267012602',
            email='org-pricing-toggle-branch@example.com',
        )
        location.served_pet_types.set([catalog['dog']])
        employee.locations.add(location)
        self._ensure_location_role(employee, location, EmployeeLocationRole.ROLE_BRANCH_MANAGER)
        self._ensure_location_service(
            location=location,
            service=service,
            pet_type=catalog['dog'],
            size_code='S',
            price='27.00',
            duration_minutes=35,
        )
        ProviderServicePricing.objects.filter(provider=provider).delete()
        self._remove_hidden_demo_prices(provider)

    def _seed_provider_operations_scenario(self, catalog):
        """Готовит provider-admin demo для dashboard, визитов, персонала, графиков и manual flow."""
        owner_user = self._ensure_user(
            email='provider-ops-owner@example.com',
            username='provider-ops-owner@example.com',
            phone_number='+38267002701',
            first_name='Provider',
            last_name='Owner',
            roles=('provider_admin',),
        )
        client_user = self._ensure_user(
            email='provider-ops-client@example.com',
            username='provider-ops-client@example.com',
            phone_number='+38267002702',
            first_name='Client',
            last_name='Owner',
            roles=('basic_user',),
        )
        staff_primary_user = self._ensure_user(
            email='provider-ops-worker1@example.com',
            username='provider-ops-worker1@example.com',
            phone_number='+38267002703',
            first_name='Mila',
            last_name='Worker',
            roles=('employee',),
        )
        staff_secondary_user = self._ensure_user(
            email='provider-ops-worker2@example.com',
            username='provider-ops-worker2@example.com',
            phone_number='+38267002704',
            first_name='Luka',
            last_name='Helper',
            roles=('employee',),
        )

        owner_employee = self._ensure_employee(owner_user)
        staff_primary = self._ensure_employee(staff_primary_user)
        staff_secondary = self._ensure_employee(staff_secondary_user)

        provider = self._ensure_provider(
            name=self.provider_ops_provider_name,
            email='provider-ops-org@example.com',
            phone_number='+38267012701',
            use_unified_service_pricing=False,
        )
        provider.available_category_levels.clear()

        primary_service = self._ensure_service(
            code=self.provider_ops_primary_service_code,
            name=self.provider_ops_primary_service_name,
            hierarchy_order='930',
        )
        secondary_service = self._ensure_service(
            code=self.provider_ops_secondary_service_code,
            name=self.provider_ops_secondary_service_name,
            hierarchy_order='931',
        )
        provider.available_category_levels.add(primary_service, secondary_service)
        provider.served_pet_types.set([catalog['dog']])

        self._ensure_employee_provider(owner_employee, provider, role=EmployeeProvider.ROLE_OWNER, is_owner=True)
        self._ensure_employee_provider(staff_primary, provider, role=EmployeeProvider.ROLE_SERVICE_WORKER)
        self._ensure_employee_provider(staff_secondary, provider, role=EmployeeProvider.ROLE_SERVICE_WORKER)

        location = self._ensure_location(
            provider=provider,
            name='Admin Ops Branch',
            formatted_address='Admin Ops Street 1, Podgorica',
            country='Montenegro',
            city='Podgorica',
            street='Admin Ops Street',
            house_number='1',
            latitude=42.4411,
            longitude=19.2624,
            phone_number='+38267012702',
            email='provider-ops-branch@example.com',
        )
        location.served_pet_types.set([catalog['dog']])
        owner_employee.locations.add(location)
        staff_primary.locations.add(location)
        staff_secondary.locations.add(location)

        self._ensure_location_role(owner_employee, location, EmployeeLocationRole.ROLE_BRANCH_MANAGER)
        self._ensure_location_role(staff_primary, location, EmployeeLocationRole.ROLE_SERVICE_WORKER)
        self._ensure_location_role(staff_secondary, location, EmployeeLocationRole.ROLE_SERVICE_WORKER)

        self._ensure_location_service(
            location=location,
            service=primary_service,
            pet_type=catalog['dog'],
            size_code='S',
            price='42.00',
            duration_minutes=60,
        )
        self._ensure_location_service(
            location=location,
            service=secondary_service,
            pet_type=catalog['dog'],
            size_code='S',
            price='18.00',
            duration_minutes=30,
        )
        self._ensure_employee_location_service(staff_primary, location, primary_service)
        EmployeeLocationService.objects.filter(
            employee=staff_primary,
            provider_location=location,
            service=secondary_service,
        ).delete()
        EmployeeLocationService.objects.filter(
            employee=staff_secondary,
            provider_location=location,
        ).delete()
        self._ensure_weekly_schedules(
            location,
            [
                {'employee': staff_primary, 'start': time(8, 0), 'end': time(18, 0)},
                {'employee': staff_secondary, 'start': time(9, 0), 'end': time(17, 0)},
            ],
        )

        pet = self._ensure_pet(
            name='AdminOps Demo Pet',
            owner=client_user,
            pet_type=catalog['dog'],
            breed=catalog['admin_ops_breed'],
            weight='8.50',
            description='Provider operations demo pet.',
        )
        active_status = Booking.get_status('active')
        now = timezone.now()

        future_start = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        self._create_booking(
            user=client_user,
            pet=pet,
            provider=provider,
            location=location,
            employee=staff_primary,
            service=primary_service,
            status=active_status,
            start_time=future_start,
            end_time=future_start + timedelta(minutes=60),
            source=Booking.BookingSource.BOOKING_SERVICE,
            price='42.00',
            notes='Admin ops future online booking',
        )

        past_start = (now - timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)
        self._create_booking(
            user=client_user,
            pet=pet,
            provider=provider,
            location=location,
            employee=staff_primary,
            service=primary_service,
            status=active_status,
            start_time=past_start,
            end_time=past_start + timedelta(minutes=60),
            source=Booking.BookingSource.BOOKING_SERVICE,
            price='42.00',
            notes='Admin ops past online booking',
        )

        manual_start = (now - timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
        self._create_booking(
            user=client_user,
            pet=pet,
            provider=provider,
            location=location,
            employee=staff_primary,
            service=primary_service,
            status=active_status,
            start_time=manual_start,
            end_time=manual_start + timedelta(minutes=60),
            source=Booking.BookingSource.MANUAL_ENTRY,
            price='42.00',
            notes=build_manual_booking_notes(
                metadata={
                    'is_guest': False,
                    'is_emergency': False,
                    'size_code': 'S',
                    'protocol_family': 'grooming',
                },
                notes='Admin ops past manual booking',
            ),
        )

        lead = ProviderClientLead.objects.create(
            provider=provider,
            provider_location=location,
            first_name='Manual',
            last_name='Lead',
            phone_number=self.provider_ops_manual_lead_phone,
            normalized_phone_number=self.provider_ops_manual_lead_phone,
            email='provider-ops-manual-lead@example.com',
        )
        manual_v2_start = (now + timedelta(days=2)).replace(hour=14, minute=0, second=0, microsecond=0)
        ManualBooking.objects.create(
            provider=provider,
            provider_location=location,
            lead=lead,
            employee=staff_primary,
            service=primary_service,
            pet_type=catalog['dog'],
            breed=catalog['admin_ops_breed'],
            size_code='S',
            owner_first_name='Manual',
            owner_last_name='Lead',
            owner_phone_number=self.provider_ops_manual_lead_phone,
            owner_email='provider-ops-manual-lead@example.com',
            pet_name='Admin Ops Manual Booking Pet',
            notes='Admin ops manual v2 booking',
            is_emergency=False,
            start_time=manual_v2_start,
            end_time=manual_v2_start + timedelta(minutes=60),
            occupied_duration_minutes=60,
            price='42.00',
            created_by=owner_user,
            updated_by=owner_user,
        )
        self._remove_hidden_demo_prices(provider)

    def _ensure_pet_type(self, *, code, name, name_ru, name_me, name_de):
        pet_type, _ = PetType.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'name_en': name,
                'name_ru': name_ru,
                'name_me': name_me,
                'name_de': name_de,
            },
        )
        return pet_type

    def _ensure_size_rules(self, pet_type):
        for size_code, min_weight, max_weight in (
            ('S', Decimal('0.00'), Decimal('15.00')),
            ('M', Decimal('15.01'), Decimal('30.00')),
            ('L', Decimal('30.01'), Decimal('45.00')),
            ('XL', Decimal('45.01'), Decimal('99.00')),
        ):
            SizeRule.objects.update_or_create(
                pet_type=pet_type,
                size_code=size_code,
                defaults={
                    'min_weight_kg': min_weight,
                    'max_weight_kg': max_weight,
                },
            )

    def _ensure_breed(self, code, pet_type, name):
        breed, _ = Breed.objects.update_or_create(
            code=code,
            defaults={
                'pet_type': pet_type,
                'name': name,
                'name_en': name,
                'name_ru': name,
                'name_me': name,
                'name_de': name,
            },
        )
        return breed

    def _ensure_user(
        self,
        *,
        email,
        username,
        phone_number,
        first_name,
        last_name,
        roles=(),
        is_staff=False,
        is_superuser=False,
    ):
        user = (
            User.objects.select_for_update().filter(email=email).first()
            or User.objects.select_for_update().filter(username=username).first()
            or User.objects.select_for_update().filter(phone_number=phone_number).first()
        )
        if user is None:
            user = User(email=email)

        user.email = email
        user.username = username
        user.phone_number = phone_number
        user.first_name = first_name
        user.last_name = last_name
        user.is_active = True
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.email_verified = True
        user.email_verified_at = timezone.now()
        user.set_password(self.demo_password)
        user.save()
        for role in roles:
            user.add_role(role)
        return user

    def _ensure_employee(self, user):
        employee, _ = Employee.objects.get_or_create(user=user)
        if not employee.is_active:
            employee.is_active = True
            employee.save(update_fields=['is_active'])
        return employee

    def _ensure_provider(self, *, name, email, phone_number, use_unified_service_pricing):
        provider, _ = Provider.objects.update_or_create(
            name=name,
            defaults={
                'email': email,
                'phone_number': phone_number,
                'country': 'ME',
                'activation_status': 'active',
                'partnership_status': Provider.PARTNERSHIP_STATUS_ACTIVE,
                'is_active': True,
                'show_services': True,
                'use_unified_service_pricing': use_unified_service_pricing,
            },
        )
        return provider

    def _ensure_service(self, *, code, name, hierarchy_order):
        service, _ = Service.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'level': 0,
                'is_client_facing': True,
                'hierarchy_order': hierarchy_order,
                'parent': None,
            },
        )
        if service.parent_id is not None:
            service.parent = None
            service.save(update_fields=['parent'])
        return service

    def _ensure_address(
        self,
        *,
        formatted_address,
        country,
        city,
        street,
        house_number,
        latitude,
        longitude,
    ):
        address, _ = Address.objects.update_or_create(
            formatted_address=formatted_address,
            defaults={
                'country': country,
                'city': city,
                'street': street,
                'house_number': house_number,
                'latitude': latitude,
                'longitude': longitude,
                'validation_status': 'valid',
            },
        )
        return address

    def _ensure_location(
        self,
        *,
        provider,
        name,
        formatted_address,
        country,
        city,
        street,
        house_number,
        latitude,
        longitude,
        phone_number,
        email,
    ):
        address = self._ensure_address(
            formatted_address=formatted_address,
            country=country,
            city=city,
            street=street,
            house_number=house_number,
            latitude=latitude,
            longitude=longitude,
        )
        location, _ = ProviderLocation.objects.update_or_create(
            provider=provider,
            name=name,
            defaults={
                'structured_address': address,
                'phone_number': phone_number,
                'email': email,
                'is_active': True,
            },
        )
        if location.structured_address_id != address.id:
            location.structured_address = address
            location.save(update_fields=['structured_address'])
        return location

    def _ensure_employee_provider(self, employee, provider, *, role, is_owner=False):
        EmployeeProvider.objects.update_or_create(
            employee=employee,
            provider=provider,
            start_date=self.team_start_date,
            defaults={
                'role': role,
                'end_date': None,
                'is_owner': is_owner,
                'is_manager': is_owner,
                'is_provider_manager': is_owner,
                'is_provider_admin': is_owner,
            },
        )

    def _ensure_location_role(self, employee, location, role):
        EmployeeLocationRole.objects.update_or_create(
            employee=employee,
            provider_location=location,
            defaults={
                'role': role,
                'is_active': True,
                'end_date': None,
            },
        )

    def _ensure_location_service(self, *, location, service, pet_type, size_code, price, duration_minutes):
        ProviderLocationService.objects.update_or_create(
            location=location,
            service=service,
            pet_type=pet_type,
            size_code=size_code,
            defaults={
                'price': price,
                'duration_minutes': duration_minutes,
                'tech_break_minutes': 0,
                'is_active': True,
            },
        )

    def _ensure_employee_location_service(self, employee, location, service):
        EmployeeLocationService.objects.update_or_create(
            employee=employee,
            provider_location=location,
            service=service,
        )

    def _ensure_weekly_schedules(self, location, employee_hours):
        for weekday in range(7):
            LocationSchedule.objects.update_or_create(
                provider_location=location,
                weekday=weekday,
                defaults={
                    'open_time': time(8, 0),
                    'close_time': time(18, 0),
                    'is_closed': False,
                },
            )
            for item in employee_hours:
                Schedule.objects.update_or_create(
                    employee=item['employee'],
                    provider_location=location,
                    day_of_week=weekday,
                    defaults={
                        'start_time': item['start'],
                        'end_time': item['end'],
                        'break_start': None,
                        'break_end': None,
                        'is_working': True,
                    },
                )

    def _ensure_pet(self, *, name, owner, pet_type, breed, weight, description, coowners=()):
        pet, _ = Pet.objects.get_or_create(
            name=name,
            defaults={
                'pet_type': pet_type,
                'breed': breed,
                'weight': Decimal(weight),
                'description': description,
            },
        )
        pet.pet_type = pet_type
        pet.breed = breed
        pet.weight = Decimal(weight)
        pet.description = description
        pet.save()

        allowed_user_ids = [owner.id, *[user.id for user in coowners]]
        PetOwner.objects.filter(pet=pet).exclude(user_id__in=allowed_user_ids).delete()
        PetOwner.objects.update_or_create(pet=pet, user=owner, defaults={'role': 'main'})
        PetOwner.objects.filter(pet=pet, role='main').exclude(user=owner).update(role='coowner')
        for user in coowners:
            PetOwner.objects.update_or_create(pet=pet, user=user, defaults={'role': 'coowner'})
        return pet

    def _ensure_sitter_profile(
        self,
        user,
        *,
        description,
        experience_years,
        available_from,
        available_to,
        max_distance_km,
        hourly_rate,
    ):
        profile, _ = SitterProfile.objects.update_or_create(
            user=user,
            defaults={
                'description': description,
                'experience_years': experience_years,
                'pet_types': ['dog'],
                'max_pets': 2,
                'available_from': available_from,
                'available_to': available_to,
                'max_distance_km': max_distance_km,
                'is_active': True,
                'compensation_type': 'paid',
                'hourly_rate': hourly_rate,
            },
        )
        return profile

    def _create_booking(
        self,
        *,
        user,
        pet,
        provider,
        location,
        employee,
        service,
        status,
        start_time,
        end_time,
        source,
        price,
        notes,
    ):
        return Booking.objects.create(
            user=user,
            escort_owner=user,
            pet=pet,
            provider=provider,
            provider_location=location,
            employee=employee,
            service=service,
            status=status,
            start_time=start_time,
            end_time=end_time,
            occupied_duration_minutes=int((end_time - start_time).total_seconds() // 60),
            source=source,
            price=price,
            notes=notes,
        )

    def _remove_hidden_demo_prices(self, provider):
        """Страховка от утечки скрытых услуг в demo search/pricing."""
        ProviderLocationService.objects.filter(location__provider=provider, service__is_client_facing=False).delete()
        ProviderServicePricing.objects.filter(provider=provider, service__is_client_facing=False).delete()
        hidden_services = list(provider.available_category_levels.filter(is_client_facing=False))
        if hidden_services:
            provider.available_category_levels.remove(*hidden_services)

    def _validate_demo_visibility_rules(self):
        """Проверяет инвариант prompt'а: в demo-поиске нет скрытых услуг и скрытых ценовых строк."""
        demo_provider_names = sorted(self.exact_demo_provider_names)
        hidden_branch_prices = ProviderLocationService.objects.filter(
            location__provider__name__in=demo_provider_names,
            service__is_client_facing=False,
        ).exists()
        hidden_org_prices = ProviderServicePricing.objects.filter(
            provider__name__in=demo_provider_names,
            service__is_client_facing=False,
        ).exists()
        if hidden_branch_prices or hidden_org_prices:
            raise CommandError('Demo refresh created hidden services in public/demo pricing scope.')
