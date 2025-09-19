"""
Команда для проверки иерархии услуг.
"""

from django.core.management.base import BaseCommand
from catalog.models import Service


class Command(BaseCommand):
    help = 'Проверка иерархии услуг'

    def handle(self, *args, **options):
        self.stdout.write('Проверка иерархии услуг...')
        
        # Проверяем, что Hair Cutting и Nail trimming относятся к Grooming
        try:
            grooming = Service.objects.get(code='grooming')
            hair_cutting = Service.objects.get(code='hair_cutting')
            nail_trimming = Service.objects.get(code='nail_trimming')
            
            self.stdout.write(f'Grooming: {grooming.name}')
            self.stdout.write(f'Hair Cutting parent: {hair_cutting.parent.name if hair_cutting.parent else "None"}')
            self.stdout.write(f'Nail trimming parent: {nail_trimming.parent.name if nail_trimming.parent else "None"}')
            
            if hair_cutting.parent == grooming and nail_trimming.parent == grooming:
                self.stdout.write(
                    self.style.SUCCESS('✓ Hair Cutting и Nail trimming правильно относятся к Grooming')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('✗ Hair Cutting и Nail trimming НЕ относятся к Grooming')
                )
                
        except Service.DoesNotExist as e:
            self.stdout.write(
                self.style.ERROR(f'Услуга не найдена: {e}')
            )
        
        # Показываем полную структуру
        self.stdout.write('\nПолная структура услуг:')
        self._print_tree()
    
    def _print_tree(self):
        """Выводит дерево услуг в консоль."""
        root_services = Service.objects.filter(parent=None).order_by('name')
        
        for root in root_services:
            self.stdout.write(f'📁 {root.name} (level: {root.level})')
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
            
            # Показываем типы животных для услуг
            pet_types = ', '.join([pt.name for pt in child.allowed_pet_types.all()])
            if not pet_types:
                pet_types = 'All types'
            
            self.stdout.write(f'{indent}{icon} {child.name} (level: {child.level}, pets: {pet_types})')
            self._print_children(child, level + 1)
