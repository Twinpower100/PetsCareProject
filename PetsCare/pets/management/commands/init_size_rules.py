# -*- coding: utf-8 -*-
"""Заполнение SizeRule. Типы питомцев по code: dog, cat, bird, snake, turtle."""
from django.core.management.base import BaseCommand
from decimal import Decimal

from pets.models import PetType, SizeRule 

class Command(BaseCommand):
    help = 'Populates the Global Size Rules for Pets'

    def handle(self, *args, **kwargs):
        # Удаляем старые правила, чтобы не было дублей при перезапуске
        # SizeRule.objects.all().delete()  <-- Раскомментируй, если хочешь чистую перезаливку
        
        rules_data = [
            # --- DOGS ---
            {
                'pet_type': 'DOG',
                'size_code': 'S',
                'name': 'Small (< 6kg)',
                'min_weight_kg': Decimal('0.00'),
                'max_weight_kg': Decimal('6.00')
            },
            {
                'pet_type': 'DOG',
                'size_code': 'M',
                'name': 'Medium (6-15kg)',
                'min_weight_kg': Decimal('6.01'),
                'max_weight_kg': Decimal('15.00')
            },
            {
                'pet_type': 'DOG',
                'size_code': 'L',
                'name': 'Large (15-40kg)',
                'min_weight_kg': Decimal('15.01'),
                'max_weight_kg': Decimal('40.00')
            },
            {
                'pet_type': 'DOG',
                'size_code': 'XL',
                'name': 'Giant (> 40kg)',
                'min_weight_kg': Decimal('40.01'),
                'max_weight_kg': Decimal('999.99')
            },

            # --- CATS ---
            {
                'pet_type': 'CAT',
                'size_code': 'S',
                'name': 'Standard (< 7kg)',
                'min_weight_kg': Decimal('0.00'),
                'max_weight_kg': Decimal('7.00')
            },
            {
                'pet_type': 'CAT',
                'size_code': 'L', # M пропускаем, для кошек обычно 2 категории
                'name': 'Large / Maine Coon (> 7kg)',
                'min_weight_kg': Decimal('7.01'),
                'max_weight_kg': Decimal('30.00')
            },

            # --- BIRDS ---
            {
                'pet_type': 'BIRD',
                'size_code': 'S',
                'name': 'Small (Budgie, Finch)',
                'min_weight_kg': Decimal('0.00'),
                'max_weight_kg': Decimal('0.10') # 100 грамм
            },
            {
                'pet_type': 'BIRD',
                'size_code': 'M',
                'name': 'Medium (Cockatiel)',
                'min_weight_kg': Decimal('0.11'),
                'max_weight_kg': Decimal('0.60') # 600 грамм
            },
            {
                'pet_type': 'BIRD',
                'size_code': 'L',
                'name': 'Large (Parrot, Macaw)',
                'min_weight_kg': Decimal('0.61'),
                'max_weight_kg': Decimal('10.00')
            },

            # --- SNAKES ---
            # Змей считают по длине, но вес коррелирует.
            # До 0.5 кг - это "шнурки". Свыше 3 кг - это уже серьезный зверь.
            {
                'pet_type': 'SNAKE',
                'size_code': 'S',
                'name': 'Small / Young',
                'min_weight_kg': Decimal('0.00'),
                'max_weight_kg': Decimal('0.50')
            },
            {
                'pet_type': 'SNAKE',
                'size_code': 'M',
                'name': 'Standard (Ball Python)',
                'min_weight_kg': Decimal('0.51'),
                'max_weight_kg': Decimal('3.00')
            },
            {
                'pet_type': 'SNAKE',
                'size_code': 'L',
                'name': 'Large / Giant',
                'min_weight_kg': Decimal('3.01'),
                'max_weight_kg': Decimal('200.00')
            },

            # --- TURTLES ---
            {
                'pet_type': 'TURTLE',
                'size_code': 'S',
                'name': 'Small (Hatchling)',
                'min_weight_kg': Decimal('0.00'),
                'max_weight_kg': Decimal('0.50')
            },
            {
                'pet_type': 'TURTLE',
                'size_code': 'M',
                'name': 'Standard (Adult Slider)',
                'min_weight_kg': Decimal('0.51'),
                'max_weight_kg': Decimal('2.00')
            },
            {
                'pet_type': 'TURTLE',
                'size_code': 'L',
                'name': 'Large / Giant',
                'min_weight_kg': Decimal('2.01'),
                'max_weight_kg': Decimal('100.00')
            },
        ]

        created_count = 0
        updated_count = 0
        for rule in rules_data:
            pet_type_str = rule.pop('pet_type')  # 'DOG', 'CAT', ...
            pet_type_code = pet_type_str.lower()  # в БД code: dog, cat, bird, snake, turtle
            try:
                pet_type = PetType.objects.get(code=pet_type_code)
            except PetType.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'PetType code={pet_type_code!r} not found, skip.'))
                continue
            # В SizeRule нет поля name — не передаём в defaults
            defaults = {'min_weight_kg': rule['min_weight_kg'], 'max_weight_kg': rule['max_weight_kg']}
            obj, created = SizeRule.objects.update_or_create(
                pet_type=pet_type,
                size_code=rule['size_code'],
                defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Size rules: {created_count} created, {updated_count} updated.'
        ))