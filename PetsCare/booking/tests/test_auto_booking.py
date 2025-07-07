"""
Тесты для автоматического бронирования работника.

Тестирует функционал автоматического выбора и бронирования работника
для услуг в системе PetCare.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime, timedelta, date
from decimal import Decimal

from booking.services import EmployeeAutoBookingService, BookingAvailabilityService
from booking.models import Booking, BookingStatus
from pets.models import Pet, PetType
from providers.models import Provider, Service, Employee, EmployeeProvider, ProviderService
from users.models import User

User = get_user_model()


class EmployeeAutoBookingServiceTestCase(TestCase):
    """Тесты для сервиса автоматического бронирования работника."""
    
    def setUp(self):
        """Настройка тестовых данных."""
        # Создаем пользователей
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        
        self.employee_user1 = User.objects.create_user(
            username='employee1',
            email='employee1@example.com',
            password='testpass123',
            first_name='Employee',
            last_name='One'
        )
        
        self.employee_user2 = User.objects.create_user(
            username='employee2',
            email='employee2@example.com',
            password='testpass123',
            first_name='Employee',
            last_name='Two'
        )
        
        # Создаем учреждение
        self.provider = Provider.objects.create(
            name='Test Clinic',
            description='Test veterinary clinic',
            is_active=True
        )
        
        # Создаем услугу
        self.service = Service.objects.create(
            name='Vaccination',
            description='Pet vaccination service',
            category='veterinary',
            is_active=True
        )
        
        # Создаем работников
        self.employee1 = Employee.objects.create(
            user=self.employee_user1,
            specialization='veterinarian',
            experience_years=5
        )
        
        self.employee2 = Employee.objects.create(
            user=self.employee_user2,
            specialization='veterinarian',
            experience_years=3
        )
        
        # Связываем работников с учреждением
        self.employee_provider1 = EmployeeProvider.objects.create(
            employee=self.employee1,
            provider=self.provider,
            start_date=date.today(),
            is_active=True
        )
        
        self.employee_provider2 = EmployeeProvider.objects.create(
            employee=self.employee2,
            provider=self.provider,
            start_date=date.today(),
            is_active=True
        )
        
        # Создаем услугу учреждения
        self.provider_service = ProviderService.objects.create(
            provider=self.provider,
            service=self.service,
            price=1500.00,
            base_price=1500.00,
            duration_minutes=45,
            tech_break_minutes=15,
            is_active=True
        )
        
        # Создаем питомца
        self.pet_type = PetType.objects.create(
            name='Dog',
            description='Canine'
        )
        
        self.pet = Pet.objects.create(
            name='Buddy',
            type=self.pet_type,
            breed='Golden Retriever',
            birth_date=date(2020, 1, 1),
            owner=self.user
        )
        
        # Создаем статусы бронирования
        self.active_status = BookingStatus.objects.create(
            name='active',
            description='Active booking'
        )
        
        self.pending_status = BookingStatus.objects.create(
            name='pending_confirmation',
            description='Pending confirmation'
        )
    
    def test_find_available_employee_success(self):
        """Тест успешного поиска доступного работника."""
        # Устанавливаем время в будущем
        start_time = timezone.now() + timedelta(hours=2)
        end_time = start_time + timedelta(hours=1)
        
        # Ищем доступного работника
        employee = EmployeeAutoBookingService._find_available_employee(
            provider=self.provider,
            service=self.service,
            start_time=start_time,
            end_time=end_time
        )
        
        # Должен найти одного из работников
        self.assertIsNotNone(employee)
        self.assertIn(employee, [self.employee1, self.employee2])
    
    def test_find_available_employee_no_employees(self):
        """Тест поиска работника когда нет доступных работников."""
        # Деактивируем всех работников
        self.employee_provider1.is_active = False
        self.employee_provider1.save()
        self.employee_provider2.is_active = False
        self.employee_provider2.save()
        
        start_time = timezone.now() + timedelta(hours=2)
        end_time = start_time + timedelta(hours=1)
        
        employee = EmployeeAutoBookingService._find_available_employee(
            provider=self.provider,
            service=self.service,
            start_time=start_time,
            end_time=end_time
        )
        
        self.assertIsNone(employee)
    
    def test_find_available_employee_all_busy(self):
        """Тест поиска работника когда все работники заняты."""
        # Создаем бронирование для первого работника
        start_time = timezone.now() + timedelta(hours=2)
        end_time = start_time + timedelta(hours=1)
        
        Booking.objects.create(
            user=self.user,
            pet=self.pet,
            provider=self.provider,
            employee=self.employee1,
            service=self.service,
            start_time=start_time,
            end_time=end_time,
            price=Decimal('1000.00'),
            status=self.active_status
        )
        
        # Создаем бронирование для второго работника в то же время
        Booking.objects.create(
            user=self.user,
            pet=self.pet,
            provider=self.provider,
            employee=self.employee2,
            service=self.service,
            start_time=start_time,
            end_time=end_time,
            price=Decimal('1000.00'),
            status=self.active_status
        )
        
        # Ищем доступного работника
        employee = EmployeeAutoBookingService._find_available_employee(
            provider=self.provider,
            service=self.service,
            start_time=start_time,
            end_time=end_time
        )
        
        # Не должен найти работника
        self.assertIsNone(employee)
    
    def test_auto_book_employee_success(self):
        """Тест успешного автоматического бронирования работника."""
        start_time = timezone.now() + timedelta(hours=2)
        end_time = start_time + timedelta(hours=1)
        
        # Автоматически бронируем работника
        booking = EmployeeAutoBookingService.auto_book_employee(
            user=self.user,
            pet=self.pet,
            provider=self.provider,
            service=self.service,
            start_time=start_time,
            end_time=end_time,
            price=1000.00,
            notes='Test booking'
        )
        
        # Проверяем, что бронирование создано
        self.assertIsNotNone(booking)
        self.assertEqual(booking.user, self.user)
        self.assertEqual(booking.pet, self.pet)
        self.assertEqual(booking.provider, self.provider)
        self.assertEqual(booking.service, self.service)
        self.assertEqual(booking.start_time, start_time)
        self.assertEqual(booking.end_time, end_time)
        self.assertEqual(booking.price, Decimal('1000.00'))
        self.assertEqual(booking.notes, 'Test booking')
        
        # Проверяем, что работник назначен
        self.assertIn(booking.employee, [self.employee1, self.employee2])
    
    def test_auto_book_employee_no_available_employee(self):
        """Тест автоматического бронирования когда нет доступных работников."""
        # Деактивируем всех работников
        self.employee_provider1.is_active = False
        self.employee_provider1.save()
        self.employee_provider2.is_active = False
        self.employee_provider2.save()
        
        start_time = timezone.now() + timedelta(hours=2)
        end_time = start_time + timedelta(hours=1)
        
        # Пытаемся автоматически забронировать работника
        booking = EmployeeAutoBookingService.auto_book_employee(
            user=self.user,
            pet=self.pet,
            provider=self.provider,
            service=self.service,
            start_time=start_time,
            end_time=end_time,
            price=1000.00,
            notes='Test booking'
        )
        
        # Бронирование не должно быть создано
        self.assertIsNone(booking)
    
    def test_get_available_employees_with_slots(self):
        """Тест получения списка доступных работников со слотами."""
        # Устанавливаем дату в будущем
        future_date = date.today() + timedelta(days=1)
        
        # Получаем доступных работников со слотами
        available_employees = EmployeeAutoBookingService.get_available_employees_with_slots(
            provider=self.provider,
            service=self.service,
            date=future_date
        )
        
        # Должны получить список работников
        self.assertGreater(len(available_employees), 0)
        
        for item in available_employees:
            self.assertIn('employee', item)
            self.assertIn('available_slots', item)
            self.assertIn('workload', item)
            self.assertIn('rating', item)
            
            # Проверяем, что работник из нашего учреждения
            self.assertIn(item['employee'], [self.employee1, self.employee2])
    
    def test_calculate_employee_workload(self):
        """Тест расчета загруженности работника."""
        # Создаем бронирование для работника
        start_time = timezone.now() + timedelta(hours=2)
        end_time = start_time + timedelta(hours=2)  # 2 часа
        
        Booking.objects.create(
            user=self.user,
            pet=self.pet,
            provider=self.provider,
            employee=self.employee1,
            service=self.service,
            start_time=start_time,
            end_time=end_time,
            price=Decimal('1000.00'),
            status=self.active_status
        )
        
        # Рассчитываем загруженность
        workload = EmployeeAutoBookingService._calculate_employee_workload(
            self.employee1, start_time.date()
        )
        
        # Загруженность должна быть 2 часа
        self.assertEqual(workload, 2.0)
    
    def test_get_employee_rating(self):
        """Тест получения рейтинга работника."""
        # Устанавливаем рейтинг работнику
        self.employee1.rating = 4.5
        self.employee1.save()
        
        # Получаем рейтинг
        rating = EmployeeAutoBookingService._get_employee_rating(self.employee1)
        
        # Рейтинг должен быть 4.5
        self.assertEqual(rating, 4.5)
    
    def test_get_employee_rating_default(self):
        """Тест получения рейтинга работника по умолчанию."""
        # Получаем рейтинг работника без установленного рейтинга
        rating = EmployeeAutoBookingService._get_employee_rating(self.employee2)
        
        # Рейтинг должен быть по умолчанию 4.0
        self.assertEqual(rating, 4.0)
    
    def test_employee_selection_priority(self):
        """Тест приоритета выбора работника (наименьшая загруженность, затем лучший рейтинг)."""
        # Устанавливаем разные рейтинги
        self.employee1.rating = 4.0
        self.employee1.save()
        self.employee2.rating = 4.5
        self.employee2.save()
        
        # Создаем бронирование для первого работника (увеличиваем загруженность)
        start_time = timezone.now() + timedelta(hours=2)
        end_time = start_time + timedelta(hours=1)
        
        Booking.objects.create(
            user=self.user,
            pet=self.pet,
            provider=self.provider,
            employee=self.employee1,
            service=self.service,
            start_time=start_time,
            end_time=end_time,
            price=Decimal('1000.00'),
            status=self.active_status
        )
        
        # Ищем работника для другого времени
        other_start_time = timezone.now() + timedelta(hours=4)
        other_end_time = other_start_time + timedelta(hours=1)
        
        employee = EmployeeAutoBookingService._find_available_employee(
            provider=self.provider,
            service=self.service,
            start_time=other_start_time,
            end_time=other_end_time
        )
        
        # Должен выбрать второго работника (меньше загруженность, выше рейтинг)
        self.assertEqual(employee, self.employee2) 