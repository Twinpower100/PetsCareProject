"""
Команда для настройки иерархии услуг.

Эта команда создает правильную иерархию услуг:
- Груминговые услуги (корневая категория)
  - Hair Cutting (услуга)
  - Nail trimming (услуга)
- Ветеринарные услуги (корневая категория)
  - Прививки (подкатегория)
    - Прививка от бешенства (услуга)
    - Прививка от чумки (услуга)
"""

from django.core.management.base import BaseCommand
from catalog.models import Service
from pets.models import PetType


class Command(BaseCommand):
    help = 'Настройка иерархии услуг'

    def handle(self, *args, **options):
        self.stdout.write('Настройка иерархии услуг...')
        
        # Получаем типы животных
        try:
            dog_type = PetType.objects.get(code='dog')
            cat_type = PetType.objects.get(code='cat')
        except PetType.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('Типы животных "dog" и "cat" не найдены. Создайте их сначала.')
            )
            return
        
        # Создаем корневые категории
        grooming, created = Service.objects.get_or_create(
            code='grooming',
            defaults={
                'name': 'Груминговые услуги',
                'description': 'Услуги по уходу за внешним видом питомцев',
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(f'Создана категория: {grooming.name}')
        
        veterinary, created = Service.objects.get_or_create(
            code='veterinary',
            defaults={
                'name': 'Ветеринарные услуги',
                'description': 'Медицинские услуги для питомцев',
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(f'Создана категория: {veterinary.name}')
        
        # Создаем услуги груминга
        hair_cutting, created = Service.objects.get_or_create(
            code='hair_cutting',
            defaults={
                'name': 'Hair Cutting',
                'description': 'Стрижка шерсти',
                'parent': grooming,
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(f'Создана услуга: {hair_cutting.name}')
        
        # Назначаем типы животных для Hair Cutting
        hair_cutting.allowed_pet_types.set([dog_type, cat_type])
        
        nail_trimming, created = Service.objects.get_or_create(
            code='nail_trimming',
            defaults={
                'name': 'Nail trimming',
                'description': 'Стрижка когтей',
                'parent': grooming,
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(f'Создана услуга: {nail_trimming.name}')
        
        # Назначаем типы животных для Nail trimming
        nail_trimming.allowed_pet_types.set([dog_type, cat_type])
        
        # Создаем подкатегорию "Прививки"
        vaccinations, created = Service.objects.get_or_create(
            code='vaccinations',
            defaults={
                'name': 'Прививки',
                'description': 'Вакцинация питомцев',
                'parent': veterinary,
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(f'Создана подкатегория: {vaccinations.name}')
        
        # Создаем услуги прививок
        rabies_vaccination, created = Service.objects.get_or_create(
            code='rabies_vaccination',
            defaults={
                'name': 'Прививка от бешенства',
                'description': 'Вакцинация от бешенства',
                'parent': vaccinations,
                'is_periodic': True,
                'period_days': 365,
                'send_reminders': True,
                'reminder_days_before': 30,
                'is_mandatory': True,
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(f'Создана услуга: {rabies_vaccination.name}')
        
        # Назначаем типы животных для прививки от бешенства
        rabies_vaccination.allowed_pet_types.set([dog_type, cat_type])
        
        distemper_vaccination, created = Service.objects.get_or_create(
            code='distemper_vaccination',
            defaults={
                'name': 'Прививка от чумки',
                'description': 'Вакцинация от чумки',
                'parent': vaccinations,
                'is_periodic': True,
                'period_days': 365,
                'send_reminders': True,
                'reminder_days_before': 30,
                'is_mandatory': True,
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(f'Создана услуга: {distemper_vaccination.name}')
        
        # Назначаем типы животных для прививки от чумки
        distemper_vaccination.allowed_pet_types.set([dog_type])
        
        # Создаем услугу "Диагностика" напрямую под ветеринарными услугами
        diagnostics, created = Service.objects.get_or_create(
            code='diagnostics',
            defaults={
                'name': 'Диагностика',
                'description': 'Диагностические услуги',
                'parent': veterinary,
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(f'Создана услуга: {diagnostics.name}')
        
        self.stdout.write(
            self.style.SUCCESS('Иерархия услуг успешно настроена!')
        )
        
        # Показываем итоговую структуру
        self.stdout.write('\nИтоговая структура:')
        self._print_tree()
    
    def _print_tree(self):
        """Выводит дерево услуг в консоль."""
        root_services = Service.objects.filter(parent=None).order_by('name')
        
        for root in root_services:
            self.stdout.write(f'📁 {root.name}')
            self._print_children(root, 1)
    
    def _print_children(self, parent, level):
        """Рекурсивно выводит дочерние элементы."""
        children = Service.objects.filter(parent=parent).order_by('name')
        indent = '    ' * level
        
        for child in children:
            if child.children.exists():
                icon = '📂'
            else:
                icon = '📄'
            
            self.stdout.write(f'{indent}{icon} {child.name}')
            self._print_children(child, level + 1)
