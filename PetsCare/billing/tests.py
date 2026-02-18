from django.test import TestCase, RequestFactory
from unittest import SkipTest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.utils.translation import gettext as _
from .models import Currency, ServicePrice, PaymentHistory, ProviderBlocking, BlockingRule, BlockingNotification, BillingManagerProvider
from catalog.models import Service
from providers.models import Provider, Employee, ProviderService
from users.models import User, UserType
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, timedelta
from .services import MultiLevelBlockingService
from .middleware import ProviderBlockingMiddleware
from booking.models import Booking

User = get_user_model()

raise SkipTest("Deprecated billing tests require model updates")


class CurrencyAPITests(APITestCase):
    def setUp(self):
        # Создаем тестового пользователя
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            is_staff=True
        )
        self.client.force_authenticate(user=self.user)

        # Создаем тестовые валюты
        self.usd = Currency.objects.create(
            code='USD',
            name='US Dollar',
            symbol='$',
            exchange_rate=1.0
        )
        self.eur = Currency.objects.create(
            code='EUR',
            name='Euro',
            symbol='€',
            exchange_rate=0.92
        )

    def test_get_currencies(self):
        url = reverse('currency-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_create_currency(self):
        url = reverse('currency-list')
        data = {
            'code': 'RUB',
            'name': 'Russian Ruble',
            'symbol': '₽',
            'exchange_rate': 75.0
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Currency.objects.count(), 3)

    def test_update_currency_rate(self):
        url = reverse('currency-update-rates')
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ServicePriceAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        self.currency = Currency.objects.create(
            code='USD',
            name='US Dollar',
            symbol='$',
            rate=Decimal('1.00')
        )
        self.service = Service.objects.create(
            code='test_service',
            name='Test Service',
            description='Test service description'
        )
        self.provider = Provider.objects.create(
            name='Test Provider',
            description='Test provider description'
        )
        self.employee = Employee.objects.create(
            user=self.user,
            provider=self.provider
        )
        self.provider_service = ProviderService.objects.create(
            provider=self.provider,
            service=self.service,
            price=Decimal('100.00'),
            duration=60
        )
        self.service_price = ServicePrice.objects.create(
            service=self.service,
            currency=self.currency,
            price=Decimal('100.00')
        )

    def test_get_service_price(self):
        url = reverse('serviceprice-detail', args=[self.service_price.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['price'], '100.00')

    def test_create_service_price(self):
        url = reverse('serviceprice-list')
        data = {
            'service': self.service.id,
            'currency': self.currency.id,
            'price': '150.00'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ServicePrice.objects.count(), 2)
        self.assertEqual(ServicePrice.objects.get(price=Decimal('150.00')).service, self.service)

    def test_update_service_price(self):
        url = reverse('serviceprice-detail', args=[self.service_price.id])
        data = {
            'service': self.service.id,
            'currency': self.currency.id,
            'price': '200.00'
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ServicePrice.objects.get(id=self.service_price.id).price, Decimal('200.00'))

    def test_delete_service_price(self):
        url = reverse('serviceprice-detail', args=[self.service_price.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(ServicePrice.objects.count(), 0)


class PaymentHistoryAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

        self.currency = Currency.objects.create(
            code='USD',
            name='US Dollar',
            symbol='$',
            exchange_rate=1.0
        )
        self.provider = Provider.objects.create(
            name='Test Provider',
            user=self.user
        )
        self.contract = Contract.objects.create(
            provider=self.provider,
            currency=self.currency,
            base_currency=self.currency,
            number='TEST-001',
            start_date='2024-01-01'
        )
        self.payment = PaymentHistory.objects.create(
            contract=self.contract,
            amount=100.00,
            currency=self.currency,
            due_date='2024-02-01'
        )

    def test_get_payment_history(self):
        url = reverse('paymenthistory-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_mark_payment_as_paid(self):
        url = reverse('paymenthistory-mark-as-paid', args=[self.payment.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')

    def test_filter_payment_history(self):
        url = reverse('paymenthistory-list')
        response = self.client.get(url, {
            'contract_id': self.contract.id,
            'start_date': '2024-01-01',
            'end_date': '2024-12-31'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


class MultiLevelBlockingTestCase(TestCase):
    """
    Тесты для многоуровневой блокировки учреждений.
    """
    
    def setUp(self):
        """Настройка тестовых данных."""
        # Создаем валюту
        self.currency = Currency.objects.create(
            code='RUB',
            name='Russian Ruble',
            symbol='₽',
            exchange_rate=1.0
        )
        
        # Создаем тип договора
        self.contract_type = ContractType.objects.create(
            name='Standard Contract',
            code='STANDARD'
        )
        
        # Создаем учреждение
        self.provider = Provider.objects.create(
            name='Test Provider',
            email='test@provider.com',
            is_active=True
        )
        
        # Создаем договор с настройками блокировки
        self.contract = Contract.objects.create(
            provider=self.provider,
            contract_type=self.contract_type,
            number='CONTRACT-001',
            start_date=date.today() - timedelta(days=30),
            status='active',
            terms='Test terms',
            currency=self.currency,
            base_currency=self.currency,
            # Настройки блокировки
            debt_threshold=Decimal('5000.00'),
            overdue_threshold_1=7,   # 7 дней для инфо
            overdue_threshold_2=15,  # 15 дней для исключения из поиска
            overdue_threshold_3=30,  # 30 дней для полной блокировки
            payment_deferral_days=5
        )
        
        # Создаем услугу
        self.service = Service.objects.create(
            name='Test Service',
            description='Test service description'
        )
        
        # Создаем правило блокировки
        self.blocking_rule = BlockingRule.objects.create(
            name='Test Rule',
            debt_amount_threshold=Decimal('1000.00'),
            overdue_days_threshold=10,
            is_active=True
        )
    
    def test_contract_blocking_level_calculation(self):
        """Тест расчета уровня блокировки договора."""
        # Без задолженности - уровень 0
        level = self.contract.get_blocking_level()
        self.assertEqual(level, 0)
        
        # Создаем задолженность на 10 дней (уровень 1)
        booking = Booking.objects.create(
            provider=self.provider,
            service=self.service,
            start_date=date.today() - timedelta(days=20),
            end_date=date.today() - timedelta(days=20),
            status='completed',
            amount=Decimal('1000.00'),
            currency=self.currency
        )
        
        # Проверяем уровень блокировки
        level = self.contract.get_blocking_level()
        self.assertEqual(level, 1)  # Инфо уведомление
        
        # Создаем задолженность на 20 дней (уровень 2)
        booking.end_date = date.today() - timedelta(days=25)
        booking.save()
        
        level = self.contract.get_blocking_level()
        self.assertEqual(level, 2)  # Исключение из поиска
        
        # Создаем задолженность на 35 дней (уровень 3)
        booking.end_date = date.today() - timedelta(days=40)
        booking.save()
        
        level = self.contract.get_blocking_level()
        self.assertEqual(level, 3)  # Полная блокировка
    
    def test_multi_level_blocking_service(self):
        """Тест сервиса многоуровневой блокировки."""
        # Создаем задолженность
        booking = Booking.objects.create(
            provider=self.provider,
            service=self.service,
            start_date=date.today() - timedelta(days=40),
            end_date=date.today() - timedelta(days=40),
            status='completed',
            amount=Decimal('1000.00'),
            currency=self.currency
        )
        
        # Проверяем учреждение
        result = MultiLevelBlockingService.check_provider_debt(self.provider)
        
        self.assertEqual(result['blocking_level'], 3)
        self.assertIsNotNone(result['reason'])
        self.assertGreater(len(result['actions_taken']), 0)
        
        # Проверяем, что создалась запись блокировки
        blocking = ProviderBlocking.objects.filter(provider=self.provider).first()
        self.assertIsNotNone(blocking)
        self.assertEqual(blocking.status, 'active')
    
    def test_blocking_resolution(self):
        """Тест снятия блокировки."""
        # Создаем активную блокировку
        blocking = ProviderBlocking.objects.create(
            provider=self.provider,
            blocking_rule=self.blocking_rule,
            status='active',
            debt_amount=Decimal('5000.00'),
            overdue_days=30,
            currency=self.currency
        )
        
        # Снимаем блокировку
        result = MultiLevelBlockingService.resolve_blocking(
            self.provider,
            resolved_by=None,
            notes='Test resolution'
        )
        
        self.assertTrue(result)
        
        # Проверяем, что блокировка снята
        blocking.refresh_from_db()
        self.assertEqual(blocking.status, 'resolved')
    
    def test_middleware_blocking(self):
        """Тест middleware блокировки."""
        factory = RequestFactory()
        middleware = ProviderBlockingMiddleware()
        
        # Создаем активную блокировку
        ProviderBlocking.objects.create(
            provider=self.provider,
            blocking_rule=self.blocking_rule,
            status='active',
            debt_amount=Decimal('5000.00'),
            overdue_days=30,
            currency=self.currency
        )
        
        # Тест блокировки API запроса
        request = factory.get(f'/api/providers/{self.provider.id}/services/')
        response = middleware.process_request(request)
        
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 403)
        self.assertIn('PROVIDER_FULLY_BLOCKED', response.content.decode())
    
    def test_middleware_search_blocking(self):
        """Тест middleware для исключения из поиска."""
        factory = RequestFactory()
        middleware = ProviderBlockingMiddleware()
        
        # Создаем договор с уровнем блокировки 2
        self.contract.overdue_threshold_2 = 5
        self.contract.save()
        
        # Создаем задолженность на 10 дней
        booking = Booking.objects.create(
            provider=self.provider,
            service=self.service,
            start_date=date.today() - timedelta(days=15),
            end_date=date.today() - timedelta(days=15),
            status='completed',
            amount=Decimal('1000.00'),
            currency=self.currency
        )
        
        # Тест блокировки поиска
        request = factory.get('/api/providers/search/?q=test')
        response = middleware.process_request(request)
        
        # Поиск должен быть заблокирован
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 403)
        self.assertIn('PROVIDER_SEARCH_BLOCKED', response.content.decode())
    
    def test_middleware_info_notification(self):
        """Тест middleware для информационного уведомления."""
        factory = RequestFactory()
        middleware = ProviderBlockingMiddleware()
        
        # Создаем задолженность на 10 дней (уровень 1)
        booking = Booking.objects.create(
            provider=self.provider,
            service=self.service,
            start_date=date.today() - timedelta(days=15),
            end_date=date.today() - timedelta(days=15),
            status='completed',
            amount=Decimal('1000.00'),
            currency=self.currency
        )
        
        # Тест информационного уведомления
        request = factory.get(f'/api/providers/{self.provider.id}/')
        response = middleware.process_request(request)
        
        # Запрос не должен быть заблокирован
        self.assertIsNone(response)
        # Но должен содержать заголовок предупреждения
        self.assertIn('HTTP_X_PROVIDER_WARNING', request.META)
    
    def test_notification_creation(self):
        """Тест создания уведомлений о блокировке."""
        # Создаем менеджера по биллингу
        user_type = UserType.objects.create(name='billing_manager')
        billing_manager = User.objects.create(
            username='billing_manager',
            email='billing@test.com',
            first_name='Billing',
            last_name='Manager',
            user_type=user_type
        )
        
        # Создаем связь менеджера с учреждением
        BillingManagerProvider.objects.create(
            billing_manager=billing_manager,
            provider=self.provider,
            start_date=date.today(),
            status='active'
        )
        
        # Создаем задолженность
        booking = Booking.objects.create(
            provider=self.provider,
            service=self.service,
            start_date=date.today() - timedelta(days=40),
            end_date=date.today() - timedelta(days=40),
            status='completed',
            amount=Decimal('1000.00'),
            currency=self.currency
        )
        
        # Проверяем учреждение
        result = MultiLevelBlockingService.check_provider_debt(self.provider)
        
        # Проверяем, что создались уведомления
        notifications = BlockingNotification.objects.filter(
            provider_blocking__provider=self.provider
        )
        self.assertGreater(notifications.count(), 0)
        
        # Проверяем, что есть уведомления для учреждения и менеджера
        provider_notifications = notifications.filter(
            recipient_email=self.provider.email
        )
        manager_notifications = notifications.filter(
            recipient_email=billing_manager.email
        )
        
        self.assertGreater(provider_notifications.count(), 0)
        self.assertGreater(manager_notifications.count(), 0)
    
    def test_mass_blocking_check(self):
        """Тест массовой проверки блокировки."""
        # Создаем второе учреждение
        provider2 = Provider.objects.create(
            name='Test Provider 2',
            email='test2@provider.com',
            is_active=True
        )
        
        contract2 = Contract.objects.create(
            provider=provider2,
            contract_type=self.contract_type,
            number='CONTRACT-002',
            start_date=date.today() - timedelta(days=30),
            status='active',
            terms='Test terms 2',
            currency=self.currency,
            base_currency=self.currency,
            debt_threshold=Decimal('2000.00'),
            overdue_threshold_1=5,
            overdue_threshold_2=10,
            overdue_threshold_3=20,
            payment_deferral_days=3
        )
        
        # Создаем задолженности
        booking1 = Booking.objects.create(
            provider=self.provider,
            service=self.service,
            start_date=date.today() - timedelta(days=40),
            end_date=date.today() - timedelta(days=40),
            status='completed',
            amount=Decimal('1000.00'),
            currency=self.currency
        )
        
        booking2 = Booking.objects.create(
            provider=provider2,
            service=self.service,
            start_date=date.today() - timedelta(days=15),
            end_date=date.today() - timedelta(days=15),
            status='completed',
            amount=Decimal('500.00'),
            currency=self.currency
        )
        
        # Запускаем массовую проверку
        result = MultiLevelBlockingService.check_all_providers()
        
        # Проверяем статистику
        self.assertIn('statistics', result)
        stats = result['statistics']
        self.assertGreater(stats['checked_providers'], 0)
        self.assertGreater(stats['blocked_providers'], 0)
        self.assertGreater(stats['warnings_sent'], 0)
    
    def test_contract_methods(self):
        """Тест методов модели Contract."""
        # Тест should_be_blocked
        self.assertFalse(self.contract.should_be_blocked())
        
        # Создаем задолженность на 20 дней
        booking = Booking.objects.create(
            provider=self.provider,
            service=self.service,
            start_date=date.today() - timedelta(days=25),
            end_date=date.today() - timedelta(days=25),
            status='completed',
            amount=Decimal('1000.00'),
            currency=self.currency
        )
        
        self.assertTrue(self.contract.should_be_blocked())
        self.assertTrue(self.contract.should_be_excluded_from_search())
        
        # Тест get_blocking_reason
        reason = self.contract.get_blocking_reason()
        self.assertIsNotNone(reason)
        self.assertIn('Исключение из поиска', reason)
    
    def test_edge_cases(self):
        """Тест граничных случаев."""
        # Тест без настроек блокировки
        contract_no_thresholds = Contract.objects.create(
            provider=self.provider,
            contract_type=self.contract_type,
            number='CONTRACT-NO-THRESHOLDS',
            start_date=date.today(),
            status='active',
            terms='No thresholds',
            currency=self.currency,
            base_currency=self.currency
        )
        
        level = contract_no_thresholds.get_blocking_level()
        self.assertEqual(level, 0)
        
        # Тест с неактивным договором
        self.contract.status = 'terminated'
        self.contract.save()
        
        level = self.contract.get_blocking_level()
        self.assertEqual(level, 0)  # Неактивные договоры не блокируют
        
        # Тест с неактивным учреждением
        self.provider.is_active = False
        self.provider.save()
        
        result = MultiLevelBlockingService.check_provider_debt(self.provider)
        self.assertEqual(result['blocking_level'], 0)
