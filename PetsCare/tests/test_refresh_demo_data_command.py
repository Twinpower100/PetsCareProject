from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from booking.manual_v2_models import ManualBooking
from booking.models import Booking
from pets.models import Pet, PetOwner
from providers.models import Provider, ProviderLocationService, ProviderServicePricing


User = get_user_model()


class RefreshDemoDataCommandTestCase(TestCase):
    provider_names = [
        'Provider_FullyPaid',
        'Provider_Level1',
        'Provider_Level2',
        'Provider_Level3',
        'Provider_PublicBookingE2E',
        'Provider_OrgPricing',
        'Provider_OrgPricingToggle',
        'Provider_AdminOps',
    ]

    demo_emails = [
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
    ]

    def test_refresh_demo_data_is_idempotent_and_keeps_public_catalog_clean(self):
        first_snapshot = self._run_refresh_and_collect_snapshot()
        second_snapshot = self._run_refresh_and_collect_snapshot()

        self.assertEqual(first_snapshot, second_snapshot)
        self.assertEqual(
            Provider.objects.filter(name__in=self.provider_names).count(),
            len(self.provider_names),
        )
        self.assertEqual(
            User.objects.filter(email__in=self.demo_emails).count(),
            len(self.demo_emails),
        )

        shared_pet = Pet.objects.get(name='Shared Demo Pet')
        ownership = list(
            PetOwner.objects.filter(pet=shared_pet)
            .select_related('user')
            .order_by('role', 'user__email')
            .values_list('user__email', 'role')
        )
        self.assertEqual(
            ownership,
            [
                ('shared-pet-coowner1@example.com', 'coowner'),
                ('shared-pet-coowner2@example.com', 'coowner'),
                ('shared-pet-owner@example.com', 'main'),
            ],
        )

        provider = Provider.objects.get(name='Provider_AdminOps')
        self.assertTrue(
            Booking.objects.filter(provider=provider, notes='Admin ops future online booking').exists()
        )
        self.assertTrue(
            Booking.objects.filter(provider=provider, notes='Admin ops past online booking').exists()
        )
        self.assertTrue(
            Booking.objects.filter(
                provider=provider,
                notes__icontains='Admin ops past manual booking',
            ).exists()
        )
        self.assertTrue(
            ManualBooking.objects.filter(
                provider=provider,
                notes='Admin ops manual v2 booking',
            ).exists()
        )

        demo_provider_ids = Provider.objects.filter(name__in=self.provider_names).values_list('id', flat=True)
        self.assertFalse(
            ProviderLocationService.objects.filter(
                location__provider_id__in=demo_provider_ids,
                service__is_client_facing=False,
            ).exists()
        )
        self.assertFalse(
            ProviderServicePricing.objects.filter(
                provider_id__in=demo_provider_ids,
                service__is_client_facing=False,
            ).exists()
        )

    def _run_refresh_and_collect_snapshot(self):
        call_command('refresh_demo_data', stdout=StringIO())

        return {
            'provider_count': Provider.objects.filter(name__in=self.provider_names).count(),
            'user_count': User.objects.filter(email__in=self.demo_emails).count(),
            'shared_pet_owner_count': PetOwner.objects.filter(pet__name='Shared Demo Pet').count(),
            'accepted_boarding_count': Booking.objects.filter(
                provider__name='Provider_AdminOps',
                notes='Admin ops future online booking',
            ).count(),
            'manual_v2_count': ManualBooking.objects.filter(
                provider__name='Provider_AdminOps',
                notes='Admin ops manual v2 booking',
            ).count(),
            'hidden_location_price_count': ProviderLocationService.objects.filter(
                location__provider__name__in=self.provider_names,
                service__is_client_facing=False,
            ).count(),
            'hidden_provider_price_count': ProviderServicePricing.objects.filter(
                provider__name__in=self.provider_names,
                service__is_client_facing=False,
            ).count(),
        }
