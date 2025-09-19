"""
Команда для очистки дублирующихся услуг.
"""

from django.core.management.base import BaseCommand
from catalog.models import Service


class Command(BaseCommand):
    help = 'Очистка дублирующихся услуг'

    def handle(self, *args, **options):
        self.stdout.write('Очистка дублирующихся услуг...')
        
        # Удаляем дублирующуюся услугу "Прививки" (она должна быть подкатегорией "Vaccination")
        try:
            duplicate_vaccinations = Service.objects.filter(
                name='Прививки',
                parent__name='Ветеринарные услуги'
            ).exclude(code='vaccinations')
            
            for service in duplicate_vaccinations:
                self.stdout.write(f'Удаляем дублирующуюся услугу: {service.name}')
                service.delete()
                
        except Exception as e:
            self.stdout.write(f'Ошибка при удалении дублирующихся услуг: {e}')
        
        # Проверяем и исправляем иерархию
        self._fix_hierarchy()
        
        self.stdout.write(
            self.style.SUCCESS('Очистка завершена!')
        )
        
        # Показываем итоговую структуру
        self.stdout.write('\nИтоговая структура:')
        self._print_tree()
    
    def _fix_hierarchy(self):
        """Исправляет иерархию услуг."""
        # Убеждаемся, что Hair Cutting и Nail trimming относятся к Grooming
        try:
            grooming = Service.objects.get(code='grooming')
            hair_cutting = Service.objects.get(code='hair_cutting')
            nail_trimming = Service.objects.get(code='nail_trimming')
            
            if hair_cutting.parent != grooming:
                hair_cutting.parent = grooming
                hair_cutting.save()
                self.stdout.write('Исправлен parent для Hair Cutting')
            
            if nail_trimming.parent != grooming:
                nail_trimming.parent = grooming
                nail_trimming.save()
                self.stdout.write('Исправлен parent для Nail trimming')
                
        except Service.DoesNotExist as e:
            self.stdout.write(f'Услуга не найдена: {e}')
    
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
