from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase

from billing.middleware import ProviderBlockingMiddleware


class ProviderBlockingMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        with patch('billing.middleware.MultiLevelBlockingService', return_value=Mock()), patch(
            'billing.middleware.BlockingSystemSettings.get_settings',
            return_value=SimpleNamespace(is_system_enabled=True, log_all_checks=False),
        ):
            self.middleware = ProviderBlockingMiddleware(lambda request: None)
        self.middleware.settings = SimpleNamespace(is_system_enabled=True, log_all_checks=False)

    def test_login_path_skips_provider_blocking_lookup(self):
        request = self.factory.post('/api/v1/login/', data={'email': 'user@example.com'})

        with patch.object(
            self.middleware,
            '_get_provider_from_request',
            side_effect=AssertionError('provider lookup must not run for login'),
        ):
            response = self.middleware.process_request(request)

        self.assertIsNone(response)
        self.assertFalse(hasattr(request, 'provider_blocking_check_performed'))

    def test_sets_timing_attributes_only_when_provider_check_is_performed(self):
        provider = Mock(exclude_from_blocking_checks=False)
        request = self.factory.get('/api/v1/providers/73/')

        with patch.object(self.middleware, '_get_provider_from_request', return_value=provider), patch.object(
            self.middleware,
            '_check_provider_blocking',
            return_value={'is_blocked': False},
        ):
            response = self.middleware.process_request(request)

        self.assertIsNone(response)
        self.assertTrue(request.provider_blocking_check_performed)
        self.assertTrue(hasattr(request, 'blocking_start_time'))
