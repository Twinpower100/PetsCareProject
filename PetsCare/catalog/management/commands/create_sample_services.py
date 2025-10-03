"""
Команда для создания примеров услуг в каталоге.
Использование: python manage.py create_sample_services
"""

from django.core.management.base import BaseCommand
from django.apps import apps

# Get the Service model dynamically to avoid import issues
Service = apps.get_model('catalog', 'Service')


class Command(BaseCommand):
    help = 'Создает примеры услуг в каталоге'

    def handle(self, *args, **options):
        self.stdout.write('Создание примеров услуг...')
        
        # Создаем корневые категории услуг
        veterinary = Service.objects.create(
            code='veterinary',
            name='Veterinary Services',
            name_en='Veterinary Services',
            name_ru='Ветеринарные услуги',
            name_me='Veterinarske usluge',
            name_de='Tierärztliche Dienstleistungen',
            description='Comprehensive veterinary care and consultations',
            description_en='Comprehensive veterinary care and consultations from certified veterinarians',
            description_ru='Комплексная ветеринарная помощь и консультации от сертифицированных ветеринаров',
            description_me='Sveobuhvatna veterinarska nega i konsultacije od sertifikovanih veterinara',
            description_de='Umfassende tierärztliche Versorgung und Beratung von zertifizierten Tierärzten',
            icon='🏥',
            is_active=True
        )
        
        grooming = Service.objects.create(
            code='grooming',
            name='Grooming Services',
            name_en='Grooming Services',
            name_ru='Услуги груминга',
            name_me='Usluge friziranja',
            name_de='Pflegedienstleistungen',
            description='Professional grooming services for your pets',
            description_en='Professional grooming services for your pets at specialized salons',
            description_ru='Профессиональные услуги груминга для ваших питомцев в специализированных салонах',
            description_me='Profesionalne usluge friziranja za vaše ljubimce u specijalizovanim salonima',
            description_de='Professionelle Pflegedienstleistungen für Ihre Haustiere in spezialisierten Salons',
            icon='✂️',
            is_active=True
        )
        
        sitting = Service.objects.create(
            code='pet_sitting',
            name='Pet Sitting Services',
            name_en='Pet Sitting Services',
            name_ru='Услуги передержки',
            name_me='Usluge čuvanja ljubimaca',
            name_de='Haustierbetreuung',
            description='Reliable pet sitting services',
            description_en='Reliable pet sitting services from verified pet sitters in your area',
            description_ru='Надежные услуги передержки от проверенных ситтеров в вашем районе',
            description_me='Pouzdane usluge čuvanja ljubimaca od provjerenih čuvara u vašoj oblasti',
            description_de='Zuverlässige Haustierbetreuung von verifizierten Sitttern in Ihrer Nähe',
            icon='🏠',
            is_active=True
        )
        
        training = Service.objects.create(
            code='training',
            name='Pet Training',
            name_en='Pet Training',
            name_ru='Дрессировка питомцев',
            name_me='Dresura ljubimaca',
            name_de='Haustiertraining',
            description='Professional pet training and behavior modification',
            description_en='Professional pet training and behavior modification services',
            description_ru='Профессиональная дрессировка и коррекция поведения питомцев',
            description_me='Profesionalna dresura i modifikacija ponašanja ljubimaca',
            description_de='Professionelles Haustiertraining und Verhaltensmodifikation',
            icon='🎓',
            is_active=True
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Успешно создано {Service.objects.count()} услуг в каталоге'
            )
        )
        
        # Показываем созданные услуги
        for service in Service.objects.all():
            self.stdout.write(f'- {service.name} ({service.code})')
