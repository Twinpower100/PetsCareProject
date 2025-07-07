"""
Тесты для модуля питомцев.

Этот модуль содержит тесты для:
1. Моделей питомцев
2. API представлений
3. Сериализаторов
4. URL-маршрутов
5. Валидации данных

Основные тестовые классы:
- PetModelTest: Тесты модели Pet
- MedicalRecordModelTest: Тесты модели MedicalRecord
- PetRecordModelTest: Тесты модели PetRecord
- PetAccessModelTest: Тесты модели PetAccess
- PetAPITest: Тесты API представлений
"""

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from .models import Breed, Pet, MedicalRecord, PetRecord, PetAccess, PetRecordFile, PetType
from users.models import User
from providers.models import EmployeeProvider, Provider, Employee
from catalog.models import Service, ServiceCategory
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile


class PetModelTest(TestCase):
    """
    Тесты для модели Pet.
    
    Тестирует:
    - Создание питомца
    - Валидацию полей
    - Методы модели
    - Связи с другими моделями
    """
    def setUp(self):
        """Подготовка тестовых данных."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.pet_data = {
            'name': 'Test Pet',
            'pet_type': 'dog',
            'breed': 'Labrador',
            'birth_date': '2020-01-01',
            'weight': 25.5,
            'description': 'Test description'
        }

    def test_create_pet(self):
        """Тест создания питомца."""
        pet = Pet.objects.create(**self.pet_data)
        pet.owners.add(self.user)
        self.assertEqual(pet.name, self.pet_data['name'])
        self.assertEqual(pet.pet_type, self.pet_data['pet_type'])
        self.assertEqual(pet.breed, self.pet_data['breed'])

    def test_pet_str(self):
        """Тест строкового представления питомца."""
        pet = Pet.objects.create(**self.pet_data)
        pet.owners.add(self.user)
        self.assertEqual(str(pet), f"{pet.name} ({pet.get_pet_type_display()})")

    def test_pet_age(self):
        """Тест расчета возраста питомца."""
        pet = Pet.objects.create(**self.pet_data)
        pet.owners.add(self.user)
        self.assertIsNotNone(pet.get_age())


class MedicalRecordModelTest(TestCase):
    """
    Тесты для модели MedicalRecord.
    
    Тестирует:
    - Создание медицинской записи
    - Валидацию полей
    - Связи с питомцем
    """
    def setUp(self):
        """Подготовка тестовых данных."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.pet = Pet.objects.create(
            name='Test Pet',
            pet_type='dog',
            breed='Labrador'
        )
        self.pet.owners.add(self.user)
        self.record_data = {
            'pet': self.pet,
            'date': '2023-01-01',
            'title': 'Test Record',
            'description': 'Test description'
        }

    def test_create_medical_record(self):
        """Тест создания медицинской записи."""
        record = MedicalRecord.objects.create(**self.record_data)
        self.assertEqual(record.title, self.record_data['title'])
        self.assertEqual(record.pet, self.pet)

    def test_medical_record_str(self):
        """Тест строкового представления медицинской записи."""
        record = MedicalRecord.objects.create(**self.record_data)
        self.assertEqual(str(record), f"{record.title} - {record.pet.name}")


class PetRecordModelTest(TestCase):
    """
    Тесты для модели PetRecord.
    
    Тестирует:
    - Создание записи в карте питомца
    - Валидацию полей
    - Связи с услугами и сотрудниками
    """
    def setUp(self):
        """Подготовка тестовых данных."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.pet = Pet.objects.create(
            name='Test Pet',
            pet_type='dog',
            breed='Labrador'
        )
        self.pet.owners.add(self.user)
        self.provider = Provider.objects.create(
            name='Test Provider',
            user=self.user
        )
        self.employee = Employee.objects.create(
            user=self.user,
            provider=self.provider
        )
        self.service_category = ServiceCategory.objects.create(
            name='Test Category'
        )
        self.service = Service.objects.create(
            name='Test Service',
            category=self.service_category
        )
        self.record_data = {
            'pet': self.pet,
            'service_category': self.service_category,
            'provider': self.provider,
            'service': self.service,
            'employee': self.employee,
            'date': '2023-01-01',
            'description': 'Test description'
        }

    def test_create_pet_record(self):
        """Тест создания записи в карте питомца."""
        record = PetRecord.objects.create(**self.record_data)
        self.assertEqual(record.description, self.record_data['description'])
        self.assertEqual(record.pet, self.pet)

    def test_pet_record_str(self):
        """Тест строкового представления записи в карте питомца."""
        record = PetRecord.objects.create(**self.record_data)
        self.assertEqual(str(record), f"{record.service.name} - {record.pet.name}")


class PetAccessModelTest(TestCase):
    """
    Тесты для модели PetAccess.
    
    Тестирует:
    - Создание доступа к карте питомца
    - Валидацию полей
    - Управление разрешениями
    """
    def setUp(self):
        """Подготовка тестовых данных."""
        self.owner = User.objects.create_user(
            email='owner@example.com',
            password='testpass123'
        )
        self.granted_to = User.objects.create_user(
            email='granted@example.com',
            password='testpass123'
        )
        self.pet = Pet.objects.create(
            name='Test Pet',
            pet_type='dog',
            breed='Labrador'
        )
        self.pet.owners.add(self.owner)
        self.access_data = {
            'pet': self.pet,
            'granted_to': self.granted_to,
            'granted_by': self.owner,
            'permissions': {'read': True, 'write': False, 'book': True}
        }

    def test_create_pet_access(self):
        """Тест создания доступа к карте питомца."""
        access = PetAccess.objects.create(**self.access_data)
        self.assertEqual(access.pet, self.pet)
        self.assertEqual(access.granted_to, self.granted_to)

    def test_pet_access_str(self):
        """Тест строкового представления доступа к карте питомца."""
        access = PetAccess.objects.create(**self.access_data)
        self.assertEqual(str(access), f"{self.granted_to.email} - {self.pet.name}")


class PetAPITest(APITestCase):
    """
    Тесты для API представлений питомцев.
    
    Тестирует:
    - Создание питомца
    - Получение списка питомцев
    - Обновление питомца
    - Удаление питомца
    - Поиск питомцев
    """
    def setUp(self):
        """Подготовка тестовых данных."""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        self.pet_data = {
            'name': 'Test Pet',
            'pet_type': 'dog',
            'breed': 'Labrador',
            'birth_date': '2020-01-01',
            'weight': 25.5,
            'description': 'Test description'
        }

    def test_create_pet(self):
        """Тест создания питомца через API."""
        response = self.client.post('/api/pets/', self.pet_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Pet.objects.count(), 1)
        self.assertEqual(Pet.objects.get().name, self.pet_data['name'])

    def test_get_pets(self):
        """Тест получения списка питомцев через API."""
        pet = Pet.objects.create(**self.pet_data)
        pet.owners.add(self.user)
        response = self.client.get('/api/pets/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], self.pet_data['name'])

    def test_update_pet(self):
        """Тест обновления питомца через API."""
        pet = Pet.objects.create(**self.pet_data)
        pet.owners.add(self.user)
        updated_data = self.pet_data.copy()
        updated_data['name'] = 'Updated Pet'
        response = self.client.put(f'/api/pets/{pet.id}/', updated_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Pet.objects.get(id=pet.id).name, 'Updated Pet')

    def test_delete_pet(self):
        """Тест удаления питомца через API."""
        pet = Pet.objects.create(**self.pet_data)
        pet.owners.add(self.user)
        response = self.client.delete(f'/api/pets/{pet.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Pet.objects.count(), 0)


class PetRecordFileUploadAPIViewTest(TestCase):
    """
    Тесты для API загрузки файлов в записи питомца.
    """
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.pet_owner = User.objects.create_user(
            username='petowner',
            email='owner@example.com',
            password='testpass123'
        )
        self.employee = User.objects.create_user(
            username='employee',
            email='employee@example.com',
            password='testpass123'
        )
        self.employee.add_role('employee')
        
        # Создаем питомца
        self.pet = Pet.objects.create(
            main_owner=self.pet_owner,
            name='Test Pet',
            pet_type=PetType.objects.create(name='Dog', code='dog'),
            breed=Breed.objects.create(
                pet_type=PetType.objects.get(name='Dog'),
                name='Labrador',
                code='labrador'
            )
        )
        self.pet.owners.add(self.pet_owner)
        
        # Создаем учреждение
        self.provider = Provider.objects.create(
            name='Test Clinic',
            address='Test Address',
            phone_number='1234567890',
            email='clinic@example.com'
        )
        
        # Создаем сотрудника
        self.employee_profile = Employee.objects.create(
            user=self.employee,
            position='Veterinarian'
        )
        
        # Связываем сотрудника с учреждением
        EmployeeProvider.objects.create(
            employee=self.employee_profile,
            provider=self.provider,
            start_date=timezone.now().date(),
            is_confirmed=True
        )
        
        # Создаем услугу
        self.service = Service.objects.create(
            name='Vaccination',
            description='Pet vaccination'
        )
        
        # Создаем запись
        self.record = PetRecord.objects.create(
            pet=self.pet,
            provider=self.provider,
            service=self.service,
            employee=self.employee_profile,
            date=timezone.now(),
            description='Test record',
            created_by=self.employee
        )
    
    def test_employee_can_upload_file_to_own_record(self):
        """Тест: сотрудник может загружать файл в свою запись"""
        self.client.force_authenticate(user=self.employee)
        
        # Создаем тестовый файл
        test_file = SimpleUploadedFile(
            "test.pdf",
            b"file_content",
            content_type="application/pdf"
        )
        
        response = self.client.post(
            f'/pets/records/{self.record.id}/upload_file/',
            {
                'file': test_file,
                'name': 'Test Document',
                'description': 'Test description'
            },
            format='multipart'
        )
        
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PetRecordFile.objects.count(), 1)
        
        file_obj = PetRecordFile.objects.first()
        self.assertEqual(file_obj.name, 'Test Document')
        self.assertEqual(file_obj.description, 'Test description')
        self.assertIn(file_obj, self.record.files.all())
    
    def test_pet_owner_can_upload_file(self):
        """Тест: владелец питомца может загружать файл"""
        self.client.force_authenticate(user=self.pet_owner)
        
        test_file = SimpleUploadedFile(
            "test.jpg",
            b"image_content",
            content_type="image/jpeg"
        )
        
        response = self.client.post(
            f'/pets/records/{self.record.id}/upload_file/',
            {
                'file': test_file,
                'name': 'Pet Photo',
                'description': 'Photo of the pet'
            },
            format='multipart'
        )
        
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PetRecordFile.objects.count(), 1)
    
    def test_unauthorized_user_cannot_upload_file(self):
        """Тест: неавторизованный пользователь не может загружать файл"""
        test_file = SimpleUploadedFile(
            "test.pdf",
            b"file_content",
            content_type="application/pdf"
        )
        
        response = self.client.post(
            f'/pets/records/{self.record.id}/upload_file/',
            {
                'file': test_file,
                'name': 'Test Document'
            },
            format='multipart'
        )
        
        self.assertEqual(response.status_code, 401)
        self.assertEqual(PetRecordFile.objects.count(), 0)
    
    def test_file_validation_size_limit(self):
        """Тест: валидация размера файла"""
        self.client.force_authenticate(user=self.employee)
        
        # Создаем файл больше 10MB
        large_file = SimpleUploadedFile(
            "large.pdf",
            b"x" * (11 * 1024 * 1024),  # 11MB
            content_type="application/pdf"
        )
        
        response = self.client.post(
            f'/pets/records/{self.record.id}/upload_file/',
            {
                'file': large_file,
                'name': 'Large Document'
            },
            format='multipart'
        )
        
        self.assertEqual(response.status_code, 400)
        self.assertIn('Файл слишком большой', response.data['error'])
        self.assertEqual(PetRecordFile.objects.count(), 0)
    
    def test_file_validation_type_limit(self):
        """Тест: валидация типа файла"""
        self.client.force_authenticate(user=self.employee)
        
        invalid_file = SimpleUploadedFile(
            "test.exe",
            b"executable_content",
            content_type="application/x-msdownload"
        )
        
        response = self.client.post(
            f'/pets/records/{self.record.id}/upload_file/',
            {
                'file': invalid_file,
                'name': 'Test Executable'
            },
            format='multipart'
        )
        
        self.assertEqual(response.status_code, 400)
        self.assertIn('Неподдерживаемый тип файла', response.data['error'])
        self.assertEqual(PetRecordFile.objects.count(), 0)
