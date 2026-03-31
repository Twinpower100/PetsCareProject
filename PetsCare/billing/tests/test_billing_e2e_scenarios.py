import json
from types import SimpleNamespace

from django.core.management import call_command
from django.http import JsonResponse
from django.test import RequestFactory, TestCase

from billing.middleware import ProviderBlockingMiddleware
from billing.models import BlockingNotification, BlockingSystemSettings, Invoice, ProviderBlocking
from billing.services import MultiLevelBlockingService
from providers.models import Provider


class BillingE2EScenariosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('generate_billing_data')
        BlockingSystemSettings.get_settings()

    def setUp(self):
        self.factory = RequestFactory()
        self.service = MultiLevelBlockingService()
        self.middleware = ProviderBlockingMiddleware(lambda request: JsonResponse({'ok': True}))

    def _build_request(self, path, provider_id):
        request = self.factory.get(path, HTTP_ACCEPT='application/json')
        request.user = SimpleNamespace(is_authenticated=False)
        request.resolver_match = SimpleNamespace(kwargs={'provider_id': provider_id, 'pk': provider_id})
        return request

    def test_invoice_totals_and_payment_history_are_synced(self):
        provider = Provider.objects.get(name='Provider_Level1')
        invoice = Invoice.objects.get(provider=provider)
        payment_history = invoice.payment_record

        self.assertIsNotNone(payment_history)
        self.assertEqual(invoice.amount, sum(line.total_with_vat for line in invoice.lines.all()))
        self.assertEqual(invoice.status, 'partially_paid')
        self.assertEqual(payment_history.status, 'partially_paid')
        self.assertGreater(payment_history.outstanding_amount, 0)
        self.assertLess(payment_history.paid_amount, invoice.amount)

    def test_blocking_service_assigns_expected_levels(self):
        stats = self.service.check_all_providers()

        self.assertEqual(stats['errors'], [])
        self.assertIsNone(
            Provider.objects.get(name='Provider_FullyPaid').blockings.filter(status='active').first()
        )
        self.assertEqual(
            Provider.objects.get(name='Provider_Level1').blockings.get(status='active').blocking_level,
            1,
        )
        self.assertEqual(
            Provider.objects.get(name='Provider_Level2').blockings.get(status='active').blocking_level,
            2,
        )
        self.assertEqual(
            Provider.objects.get(name='Provider_Level3').blockings.get(status='active').blocking_level,
            3,
        )

    def test_middleware_adds_warning_header_for_level_1(self):
        self.service.check_all_providers()
        provider = Provider.objects.get(name='Provider_Level1')
        request = self._build_request('/api/v1/providers/1/', provider.id)

        response = self.middleware.process_request(request)
        self.assertIsNone(response)

        final_response = self.middleware.process_response(request, JsonResponse({'ok': True}))
        payload = json.loads(final_response.content.decode('utf-8'))

        self.assertIn('X-Provider-Blocking-Warning', final_response.headers)
        self.assertEqual(payload['blocking_warning']['level'], 1)
        self.assertEqual(payload['blocking_warning']['provider_name'], provider.name)

    def test_middleware_returns_451_for_level_2_search_requests(self):
        self.service.check_all_providers()
        provider = Provider.objects.get(name='Provider_Level2')
        request = self._build_request('/api/v1/providers/search/', provider.id)

        response = self.middleware.process_request(request)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 451)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['blocking_level'], 2)
        self.assertEqual(payload['error'], 'provider_blocked')

    def test_middleware_returns_403_for_level_3_private_requests(self):
        self.service.check_all_providers()
        provider = Provider.objects.get(name='Provider_Level3')
        request = self._build_request(f'/api/v1/providers/{provider.id}/', provider.id)

        response = self.middleware.process_request(request)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 403)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['blocking_level'], 3)
        self.assertIn('critical billing debt', payload['message'].lower())

    def test_blocking_records_store_level_on_model(self):
        self.service.check_all_providers()
        blocking = ProviderBlocking.objects.get(provider__name='Provider_Level2', status='active')

        self.assertEqual(blocking.blocking_level, 2)
        self.assertGreaterEqual(blocking.overdue_days, 60)

    def test_blocking_notifications_created_for_warning_and_activation(self):
        self.service.check_all_providers()

        self.assertTrue(
            BlockingNotification.objects.filter(
                provider_blocking__provider__name='Provider_Level1',
                notification_type='blocking_warning',
            ).exists()
        )
        self.assertTrue(
            BlockingNotification.objects.filter(
                provider_blocking__provider__name='Provider_Level2',
                notification_type='blocking_activated',
            ).exists()
        )
