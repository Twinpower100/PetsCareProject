from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from billing.models import Currency, ProviderBlocking
from booking.test_booking_flow_logic import BookingFlowBaseMixin


class ProviderSearchBlockingTests(BookingFlowBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.owner)
        self.currency, _ = Currency.objects.get_or_create(
            code='EUR',
            defaults={
                'name': 'Euro',
                'symbol': 'EUR',
                'exchange_rate': Decimal('1.0000'),
            },
        )

    def test_search_keeps_provider_when_only_warning_is_active(self):
        ProviderBlocking.objects.create(
            provider=self.provider,
            status='active',
            blocking_level=1,
            debt_amount=Decimal('10.00'),
            overdue_days=5,
            currency=self.currency,
        )
        ProviderBlocking.objects.create(
            provider=self.provider,
            status='resolved',
            blocking_level=2,
            debt_amount=Decimal('20.00'),
            overdue_days=15,
            currency=self.currency,
        )

        response = self.client.get(
            '/api/v1/booking/search/',
            {
                'pet_id': self.pet_one.id,
                'service_query': 'Grooming',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.location_a.id)

    def test_search_returns_service_name_for_accept_language(self):
        self.service.name = 'Первичный осмотр и консультация'
        self.service.name_en = 'Initial examination and consultation'
        self.service.name_ru = 'Первичный осмотр и консультация'
        self.service.name_me = 'Prvi pregled i konsultacija'
        self.service.name_de = 'Erstuntersuchung und Beratung'
        self.service.save(update_fields=['name', 'name_en', 'name_ru', 'name_me', 'name_de'])

        response = self.client.get(
            '/api/v1/booking/search/',
            {
                'pet_id': self.pet_one.id,
                'service_query': 'Erstuntersuchung',
            },
            format='json',
            HTTP_ACCEPT_LANGUAGE='de',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['services'][0]['name'], 'Erstuntersuchung und Beratung')

    def test_search_hides_provider_when_search_blocking_is_active(self):
        ProviderBlocking.objects.create(
            provider=self.provider,
            status='active',
            blocking_level=2,
            debt_amount=Decimal('20.00'),
            overdue_days=15,
            currency=self.currency,
        )

        response = self.client.get(
            '/api/v1/booking/search/',
            {
                'pet_id': self.pet_one.id,
                'service_query': 'Grooming',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])
