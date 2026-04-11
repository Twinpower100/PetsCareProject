from datetime import timedelta
from decimal import Decimal
from hashlib import md5

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from billing.models import BillingConfig, Currency, Invoice, InvoiceLine, PaymentHistory
from booking.constants import COMPLETED_BY_SYSTEM
from booking.models import Booking, BookingPayment, BookingStatus
from catalog.models import Service
from geolocation.models import Address
from legal.models import DocumentAcceptance, LegalDocument, LegalDocumentType
from pets.models import Pet, PetOwner, PetType
from providers.models import Employee, EmployeeProvider, Provider, ProviderLocation, ProviderLocationService, ProviderService
from users.models import User


class Command(BaseCommand):
    help = 'Generate deterministic billing demo data for blocking scenarios'
    demo_password = 'Secret123!'

    scenarios = (
        {
            'name': 'Provider_FullyPaid',
            'invoice_amount': Decimal('120.00'),
            'overdue_days': 0,
            'paid_amount': Decimal('120.00'),
            'expected_status': 'paid',
        },
        {
            'name': 'Provider_Level1',
            'invoice_amount': Decimal('80.00'),
            'overdue_days': 35,
            'paid_amount': Decimal('4.00'),
            'expected_status': 'partially_paid',
        },
        {
            'name': 'Provider_Level2',
            'invoice_amount': Decimal('150.00'),
            'overdue_days': 70,
            'paid_amount': Decimal('0.00'),
            'expected_status': 'overdue',
        },
        {
            'name': 'Provider_Level3',
            'invoice_amount': Decimal('220.00'),
            'overdue_days': 100,
            'paid_amount': Decimal('0.00'),
            'expected_status': 'overdue',
        },
    )

    @transaction.atomic
    def handle(self, *args, **kwargs):
        today = timezone.now().date()

        currency, owner, pet = self._ensure_shared_entities()
        self._ensure_billing_admin()
        offer = self._ensure_offer()
        service = self._ensure_leaf_service()

        for scenario in self.scenarios:
            provider = self._upsert_provider(scenario['name'], currency)
            self._ensure_offer_acceptance(provider, offer, owner)
            provider_service = self._ensure_provider_service(provider, service)
            self._reset_provider_billing(provider)

            invoice = self._create_invoice(
                provider=provider,
                provider_service=provider_service,
                pet=pet,
                currency=currency,
                invoice_amount=scenario['invoice_amount'],
                today=today,
            )
            payment_history = invoice.payment_record

            if payment_history is None:
                raise RuntimeError(f'Invoice {invoice.number} has no payment history')

            if scenario['overdue_days'] > 0:
                payment_history.due_date = today - timedelta(days=scenario['overdue_days'])
                payment_history.save()

            if scenario['paid_amount'] > Decimal('0.00'):
                payment_history.apply_payment(
                    scenario['paid_amount'],
                    payment_date=today - timedelta(days=max(scenario['overdue_days'], 1)),
                )

            invoice.refresh_from_db()
            payment_history.refresh_from_db()

            if invoice.status != scenario['expected_status'] or payment_history.status != scenario['expected_status']:
                raise RuntimeError(
                    f"Scenario {provider.name} expected {scenario['expected_status']} "
                    f"but got invoice={invoice.status}, payment={payment_history.status}"
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"{provider.name}: invoice={invoice.amount} status={invoice.status} "
                    f"paid={payment_history.paid_amount} outstanding={payment_history.outstanding_amount}"
                )
            )

    def _ensure_shared_entities(self):
        currency, _ = Currency.objects.get_or_create(
            code='EUR',
            defaults={
                'name': 'Euro',
                'symbol': 'EUR',
                'exchange_rate': Decimal('1.00'),
                'is_active': True,
            },
        )

        owner, _ = self._ensure_demo_user(
            email='billing-demo-owner@example.com',
            username='billing-demo-owner',
            phone_number='+38267000001',
            first_name='Billing',
            last_name='Owner',
        )
        owner.add_role('basic_user')

        pet_type, _ = PetType.objects.get_or_create(
            code='dog',
            defaults={'name': 'Dog'},
        )
        pet, created = Pet.objects.get_or_create(
            name='Billing Demo Pet',
            pet_type=pet_type,
            defaults={'weight': Decimal('12.50')},
        )
        PetOwner.objects.filter(pet=pet, role='main').exclude(user=owner).update(role='coowner')
        PetOwner.objects.update_or_create(
            pet=pet,
            user=owner,
            defaults={'role': 'main'},
        )

        return currency, owner, pet

    def _ensure_billing_admin(self):
        admin_user, _ = self._ensure_demo_user(
            email='billing-admin@example.com',
            username='billing-admin',
            phone_number='+38267000090',
            first_name='Billing',
            last_name='Manager',
            is_staff=True,
            is_superuser=True,
        )
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.save(update_fields=['is_staff', 'is_superuser'])

    def _ensure_offer(self):
        offer_type, _ = LegalDocumentType.objects.get_or_create(
            code='global_offer',
            defaults={
                'name': 'Global Offer',
                'requires_billing_config': True,
            },
        )
        if not offer_type.requires_billing_config:
            offer_type.requires_billing_config = True
            offer_type.save(update_fields=['requires_billing_config'])

        billing_config, _ = BillingConfig.objects.update_or_create(
            name='Billing Demo Global Offer Config',
            defaults={
                'description': 'Demo billing config for deterministic billing scenarios.',
                'commission_percent': Decimal('10.00'),
                'payment_deferral_days': 5,
                'invoice_period_days': 3,
                'is_active': True,
            },
        )
        offer, _ = LegalDocument.objects.update_or_create(
            document_type=offer_type,
            version='billing-demo-1.0',
            defaults={
                'title': 'Billing Demo Global Offer',
                'billing_config': billing_config,
                'effective_date': timezone.now().date() - timedelta(days=365),
                'is_active': True,
                'commission_type': 'percent',
                'commission_percent': billing_config.commission_percent,
                'debt_threshold': Decimal('500.00'),
                'overdue_threshold_1': 30,
                'overdue_threshold_2': 60,
                'overdue_threshold_3': 90,
            },
        )
        return offer

    def _ensure_leaf_service(self):
        service, _ = Service.objects.get_or_create(
            code='billing_demo_service',
            defaults={
                'name': 'Billing Demo Service',
                'is_client_facing': True,
            },
        )
        return service

    def _upsert_provider(self, name, currency):
        phone_suffix = f"{(sum(ord(char) for char in name) % 1000000):06d}"
        provider, _ = Provider.objects.update_or_create(
            name=name,
            defaults={
                'email': f'{name.lower()}@example.com',
                'phone_number': f'+38267{phone_suffix}',
                'country': 'ME',
                'invoice_currency': currency,
                'is_active': True,
            },
        )
        return provider

    def _ensure_offer_acceptance(self, provider, offer, owner):
        DocumentAcceptance.objects.update_or_create(
            provider=provider,
            document=offer,
            defaults={
                'accepted_by': owner,
                'is_active': True,
                'accepted_at': timezone.now(),
            },
        )

    def _ensure_provider_service(self, provider, service):
        provider_service, _ = ProviderService.objects.update_or_create(
            provider=provider,
            service=service,
            defaults={
                'price': Decimal('100.00'),
                'base_price': Decimal('100.00'),
                'duration_minutes': 60,
            },
        )
        return provider_service

    def _reset_provider_billing(self, provider):
        PaymentHistory.objects.filter(provider=provider).delete()
        Invoice.objects.filter(provider=provider).delete()
        provider.blockings.all().delete()

    def _create_invoice(self, *, provider, provider_service, pet, currency, invoice_amount, today):
        booking = self._create_booking(provider=provider, provider_service=provider_service, pet=pet, today=today)
        start_date = today - timedelta(days=30)
        end_date = today - timedelta(days=1)

        invoice = Invoice.objects.create(
            provider=provider,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
            status='sent',
            issued_at=timezone.now() - timedelta(days=3),
            amount=Decimal('0.00'),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            booking=booking,
            amount=invoice_amount,
            commission=Decimal('0.00'),
            rate=Decimal('10.00'),
            currency=currency,
            vat_rate=Decimal('20.00'),
        )
        invoice.refresh_from_db()
        return invoice

    def _create_booking(self, *, provider, provider_service, pet, today):
        booking_status, _ = BookingStatus.objects.get_or_create(name='completed')
        address, _ = Address.objects.get_or_create(
            formatted_address=f'Billing Street 1, {provider.name}',
            defaults={
                'country': 'ME',
                'city': 'Podgorica',
                'street': 'Billing Street',
                'house_number': '1',
            },
        )
        location, _ = ProviderLocation.objects.get_or_create(
            provider=provider,
            name='Main Clinic',
            defaults={
                'is_active': True,
                'structured_address': address,
                'email': f'location-{provider.id}@example.com',
                'phone_number': '+38267000124',
            },
        )
        if location.structured_address_id != address.id:
            location.structured_address = address
            location.save(update_fields=['structured_address'])
        location.served_pet_types.add(pet.pet_type)
        ProviderLocationService.objects.update_or_create(
            location=location,
            service=provider_service.service,
            pet_type=pet.pet_type,
            size_code=pet.get_current_size_category() or 'M',
            defaults={
                'price': provider_service.base_price,
                'duration_minutes': provider_service.duration_minutes,
                'tech_break_minutes': 0,
                'is_active': True,
            },
        )

        provider_slug = slugify(provider.name) or f'provider-{provider.id}'
        employee_user, _ = self._ensure_demo_user(
            email=f'billing-owner-{provider_slug}@example.com',
            username=f'billing-owner-{provider_slug}',
            phone_number=self._build_demo_phone('68', provider_slug),
            first_name='Billing',
            last_name=provider.name.replace('Provider_', '').replace('_', ' '),
            fallback_user=self._get_existing_provider_owner(provider),
        )
        employee_user.add_role('owner')
        employee, _ = Employee.objects.get_or_create(user=employee_user)
        EmployeeProvider.objects.update_or_create(
            employee=employee,
            provider=provider,
            start_date=today - timedelta(days=120),
            defaults={
                'role': EmployeeProvider.ROLE_OWNER,
                'end_date': None,
                'is_manager': True,
                'is_owner': True,
                'is_provider_manager': True,
                'is_provider_admin': True,
            },
        )

        start_time = timezone.now() - timedelta(days=7)
        booking = Booking.objects.create(
            user=pet.main_owner,
            employee=employee,
            provider_location=location,
            service=provider_service.service,
            pet=pet,
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            status=booking_status,
            price=provider_service.base_price,
            completed_at=start_time + timedelta(hours=1),
            completed_by_actor=COMPLETED_BY_SYSTEM,
        )
        BookingPayment.objects.update_or_create(
            booking=booking,
            defaults={
                'amount': provider_service.base_price,
                'payment_method': 'online',
                'transaction_id': f'BILLING-DEMO-{provider.id}-{booking.id}',
            },
        )
        return booking

    def _ensure_demo_user(
        self,
        *,
        email,
        username,
        phone_number,
        first_name,
        last_name,
        fallback_user=None,
        **extra_fields,
    ):
        user = (
            User.objects.filter(email=email).first()
            or User.objects.filter(username=username).first()
            or fallback_user
            or User.objects.filter(phone_number=phone_number).first()
        )
        created = user is None

        if user is None:
            user = User(
                email=email,
                username=username,
                phone_number=phone_number,
                first_name=first_name,
                last_name=last_name,
                **extra_fields,
            )
        else:
            user.email = email
            user.username = username
            user.phone_number = phone_number
            user.first_name = first_name
            user.last_name = last_name
            for field_name, field_value in extra_fields.items():
                setattr(user, field_name, field_value)

        user.set_password(self.demo_password)
        user.save()
        return user, created

    def _get_existing_provider_owner(self, provider):
        employee_provider = (
            EmployeeProvider.objects.select_related('employee__user')
            .filter(provider=provider, is_owner=True)
            .order_by('id')
            .first()
        )
        if employee_provider is not None:
            return employee_provider.employee.user

        employee_provider = (
            EmployeeProvider.objects.select_related('employee__user')
            .filter(provider=provider, is_provider_admin=True)
            .order_by('id')
            .first()
        )
        if employee_provider is not None:
            return employee_provider.employee.user

        return None

    def _build_demo_phone(self, prefix, key):
        digest = md5(key.encode('utf-8')).hexdigest()
        numeric_suffix = int(digest[:8], 16) % 1000000
        return f'+382{prefix}{numeric_suffix:06d}'
