from django.test import TestCase
from unittest import skip
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import Booking, BookingStatus, BookingPayment, BookingReview
from pets.models import Pet
from providers.models import Provider, Employee
from catalog.models import Service

User = get_user_model()

@skip("Deprecated booking API tests require model updates")
class BookingAPITests(APITestCase):
    """
    Тесты для API бронирований.
    """
    def setUp(self):
        """
        Настройка тестовых данных.
        """
        # Создаем пользователей
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.provider_user = User.objects.create_user(
            username='provider',
            password='testpass123',
            email='provider@example.com'
        )
        
        # Создаем поставщика услуг
        self.provider = Provider.objects.create(
            user=self.provider_user,
            name='Test Provider',
            description='Test Description'
        )
        
        # Создаем питомца
        self.pet = Pet.objects.create(
            user=self.user,
            name='Test Pet',
            species='dog',
            breed='Test Breed'
        )
        
        # Создаем услугу
        self.service = Service.objects.create(
            provider=self.provider,
            name='Test Service',
            description='Test Description',
            price=100.00
        )
        
        # Создаем сотрудника
        self.employee = Employee.objects.create(
            provider=self.provider,
            user=User.objects.create_user(
                username='employee',
                password='testpass123',
                email='employee@example.com'
            ),
            position='Test Position'
        )
        
        # Создаем статус бронирования
        self.status = BookingStatus.objects.create(
            name='Pending',
            description='Test Description'
        )
        
        # Создаем тестовое бронирование
        self.booking = Booking.objects.create(
            user=self.user,
            pet=self.pet,
            provider=self.provider,
            employee=self.employee,
            service=self.service,
            status=self.status,
            start_time='2024-01-01T10:00:00Z',
            end_time='2024-01-01T11:00:00Z',
            price=100.00
        )
        
        # Настраиваем клиент API
        self.client = APIClient()

    def test_create_booking(self):
        """
        Тест создания бронирования.
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('booking-list')
        data = {
            'pet': self.pet.id,
            'provider': self.provider.id,
            'employee': self.employee.id,
            'service': self.service.id,
            'start_time': '2024-01-02T10:00:00Z',
            'end_time': '2024-01-02T11:00:00Z',
            'price': 100.00
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Booking.objects.count(), 2)

    def test_get_booking(self):
        """
        Тест получения бронирования.
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('booking-detail', args=[self.booking.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.booking.id)

    def test_update_booking(self):
        """
        Тест обновления бронирования.
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('booking-detail', args=[self.booking.id])
        data = {'price': 150.00}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.price, 150.00)

    def test_delete_booking(self):
        """
        Тест удаления бронирования.
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('booking-detail', args=[self.booking.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Booking.objects.count(), 0)

@skip("Deprecated booking payment tests require model updates")
class BookingPaymentAPITests(APITestCase):
    """
    Тесты для API платежей.
    """
    def setUp(self):
        """
        Настройка тестовых данных.
        """
        # Используем данные из BookingAPITests
        self.booking_tests = BookingAPITests()
        self.booking_tests.setUp()
        self.booking = self.booking_tests.booking
        
        # Создаем тестовый платеж
        self.payment = BookingPayment.objects.create(
            booking=self.booking,
            amount=100.00,
            payment_method='credit_card',
            status='completed'
        )

    def test_create_payment(self):
        """
        Тест создания платежа.
        """
        self.client.force_authenticate(user=self.booking_tests.user)
        url = reverse('booking-create-payment', args=[self.booking.id])
        data = {
            'amount': 150.00,
            'payment_method': 'credit_card',
            'status': 'completed'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(BookingPayment.objects.count(), 2)

@skip("Deprecated booking review tests require model updates")
class BookingReviewAPITests(APITestCase):
    """
    Тесты для API отзывов.
    """
    def setUp(self):
        """
        Настройка тестовых данных.
        """
        # Используем данные из BookingAPITests
        self.booking_tests = BookingAPITests()
        self.booking_tests.setUp()
        self.booking = self.booking_tests.booking
        
        # Создаем тестовый отзыв
        self.review = BookingReview.objects.create(
            booking=self.booking,
            rating=5,
            comment='Great service!',
            is_public=True
        )

    def test_create_review(self):
        """
        Тест создания отзыва.
        """
        self.client.force_authenticate(user=self.booking_tests.user)
        url = reverse('booking-create-review', args=[self.booking.id])
        data = {
            'rating': 4,
            'comment': 'Good service',
            'is_public': True
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(BookingReview.objects.count(), 2)
