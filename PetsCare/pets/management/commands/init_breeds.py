# -*- coding: utf-8 -*-
"""Заполнение пород (Breed). Типы питомцев по code: dog, cat, bird, snake, turtle (в БД — нижний регистр)."""
from django.core.management.base import BaseCommand

from pets.models import Breed, PetType 

class Command(BaseCommand):
    help = 'Populates the database with initial breeds'

    def handle(self, *args, **kwargs):
        # 1. Сначала определяем Типы животных (они должны уже быть, но на всякий случай)
        # Ключ словаря = код PetType
        
        breeds_data = [
            # --- СОБАКИ (DOG) ---
            {
                'type_code': 'DOG',
                'code': 'dog_mixed',
                'name': 'Mixed Breed / Mongrel',
                'name_ru': 'Метис / Дворняжка',
                'name_me': 'Mješanac',
                'name_de': 'Mischling',
                'description': 'Собака без подтвержденной породы'
            },
            {
                'type_code': 'DOG',
                'code': 'dog_yorkie',
                'name': 'Yorkshire Terrier',
                'name_ru': 'Йоркширский терьер',
                'name_me': 'Jorkširski terijer',
                'name_de': 'Yorkshire Terrier',
                'description': 'Size: S'
            },
            {
                'type_code': 'DOG',
                'code': 'dog_jack_russell',
                'name': 'Jack Russell Terrier',
                'name_ru': 'Джек-рассел-терьер',
                'name_me': 'Džek Rasel terijer',
                'name_de': 'Jack Russell Terrier',
                'description': 'Size: M'
            },
            {
                'type_code': 'DOG',
                'code': 'dog_corgi',
                'name': 'Welsh Corgi',
                'name_ru': 'Вельш-корги',
                'name_me': 'Velški korgi',
                'name_de': 'Welsh Corgi',
                'description': 'Size: M'
            },
            {
                'type_code': 'DOG',
                'code': 'dog_french_bulldog',
                'name': 'French Bulldog',
                'name_ru': 'Французский бульдог',
                'name_me': 'Francuski buldog',
                'name_de': 'Französische Bulldogge',
                'description': 'Size: M'
            },
            {
                'type_code': 'DOG',
                'code': 'dog_labrador',
                'name': 'Labrador Retriever',
                'name_ru': 'Лабрадор ретривер',
                'name_me': 'Labrador retriver',
                'name_de': 'Labrador Retriever',
                'description': 'Size: L'
            },
            {
                'type_code': 'DOG',
                'code': 'dog_gsd',
                'name': 'German Shepherd',
                'name_ru': 'Немецкая овчарка',
                'name_me': 'Njemački ovčar',
                'name_de': 'Deutscher Schäferhund',
                'description': 'Size: L'
            },
            {
                'type_code': 'DOG',
                'code': 'dog_husky',
                'name': 'Siberian Husky',
                'name_ru': 'Сибирский хаски',
                'name_me': 'Sibirski haski',
                'name_de': 'Siberian Husky',
                'description': 'Size: L'
            },
            {
                'type_code': 'DOG',
                'code': 'dog_newfoundland',
                'name': 'Newfoundland',
                'name_ru': 'Ньюфаундленд',
                'name_me': 'Njufaundlend',
                'name_de': 'Neufundländer',
                'description': 'Size: XL'
            },
            {
                'type_code': 'DOG',
                'code': 'dog_poodle_toy',
                'name': 'Poodle (Toy)',
                'name_ru': 'Пудель (Той)',
                'name_me': 'Pudla (Toy)',
                'name_de': 'Pudel (Toy)',
                'description': 'Size: S'
            },
            {
                'type_code': 'DOG',
                'code': 'dog_doberman',
                'name': 'Doberman',
                'name_ru': 'Доберман',
                'name_me': 'Doberman',
                'name_de': 'Dobermann',
                'description': 'Size: L'
            },

            # --- КОШКИ (CAT) ---
            {
                'type_code': 'CAT',
                'code': 'cat_mixed',
                'name': 'Domestic Short Hair',
                'name_ru': 'Беспородная / Метис',
                'name_me': 'Domaća mačka',
                'name_de': 'Hauskatze',
                'description': 'Size: S'
            },
            {
                'type_code': 'CAT',
                'code': 'cat_british',
                'name': 'British Shorthair',
                'name_ru': 'Британская короткошерстная',
                'name_me': 'Britanska kratkodlaka',
                'name_de': 'Britisch Kurzhaar',
                'description': 'Size: S'
            },
            {
                'type_code': 'CAT',
                'code': 'cat_mainecoon',
                'name': 'Maine Coon',
                'name_ru': 'Мейн-кун',
                'name_me': 'Mejn kun',
                'name_de': 'Maine Coon',
                'description': 'Size: L (Крупная)'
            },
            {
                'type_code': 'CAT',
                'code': 'cat_sphynx',
                'name': 'Sphynx',
                'name_ru': 'Сфинкс',
                'name_me': 'Sfinks',
                'name_de': 'Sphynx-Katze',
                'description': 'Size: S (Hairless)'
            },
            {
                'type_code': 'CAT',
                'code': 'cat_persian',
                'name': 'Persian',
                'name_ru': 'Персидская',
                'name_me': 'Persijska mačka',
                'name_de': 'Perserkatze',
                'description': 'Size: S (Long Hair)'
            },
            {
                'type_code': 'CAT',
                'code': 'cat_siamese',
                'name': 'Siamese',
                'name_ru': 'Сиамская',
                'name_me': 'Sijamska mačka',
                'name_de': 'Siamkatze',
                'description': 'Size: S'
            },

            # --- ПТИЦЫ (BIRD) ---
            {
                'type_code': 'BIRD',
                'code': 'bird_budgie',
                'name': 'Budgerigar',
                'name_ru': 'Волнистый попугай',
                'name_me': 'Tigrica',
                'name_de': 'Wellensittich',
                'description': 'Size: S'
            },
            {
                'type_code': 'BIRD',
                'code': 'bird_cockatiel',
                'name': 'Cockatiel',
                'name_ru': 'Корелла',
                'name_me': 'Nimfa',
                'name_de': 'Nymphensittich',
                'description': 'Size: M'
            },
            {
                'type_code': 'BIRD',
                'code': 'bird_africangrey',
                'name': 'African Grey Parrot',
                'name_ru': 'Жако',
                'name_me': 'Žako',
                'name_de': 'Graupapagei',
                'description': 'Size: L'
            },
            {
                'type_code': 'BIRD',
                'code': 'bird_canary',
                'name': 'Canary',
                'name_ru': 'Канарейка',
                'name_me': 'Kanarinac',
                'name_de': 'Kanarienvogel',
                'description': 'Size: S'
            },

            # --- ЗМЕИ (SNAKE) ---
            {
                'type_code': 'SNAKE',
                'code': 'snake_corn',
                'name': 'Corn Snake',
                'name_ru': 'Маисовый полоз',
                'name_me': 'Kukuruzna zmija',
                'name_de': 'Kornnatter',
                'description': 'Size: S/M'
            },
            {
                'type_code': 'SNAKE',
                'code': 'snake_ballpython',
                'name': 'Ball Python',
                'name_ru': 'Королевский питон',
                'name_me': 'Kraljevski piton',
                'name_de': 'Königspython',
                'description': 'Size: M'
            },
            {
                'type_code': 'SNAKE',
                'code': 'snake_boa',
                'name': 'Boa Constrictor',
                'name_ru': 'Обыкновенный удав',
                'name_me': 'Carski udav',
                'name_de': 'Abgottschlange',
                'description': 'Size: L'
            },

            # --- ЧЕРЕПАХИ (TURTLE) ---
            {
                'type_code': 'TURTLE',
                'code': 'turtle_red_eared',
                'name': 'Red-eared Slider',
                'name_ru': 'Красноухая черепаха',
                'name_me': 'Crvenouha kornjača',
                'name_de': 'Rotwangen-Schmuckschildkröte',
                'description': 'Aquatic'
            },
            {
                'type_code': 'TURTLE',
                'code': 'turtle_land',
                'name': 'Central Asian Tortoise',
                'name_ru': 'Среднеазиатская черепаха',
                'name_me': 'Stepska kornjača',
                'name_de': 'Vierzehenschildkröte',
                'description': 'Land'
            }
        ]

        created_count = 0
        updated_count = 0
        for data in breeds_data:
            type_code = data.pop('type_code').lower()  # в БД: dog, cat, bird, snake, turtle
            try:
                pet_type = PetType.objects.get(code=type_code)
            except PetType.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'PetType code={type_code!r} not found, skip breed {data.get("code")}.'))
                continue

            _, created = Breed.objects.update_or_create(
                code=data['code'],
                defaults={
                    'pet_type': pet_type,
                    'name': data['name'],
                    'name_en': data.get('name_en', data['name']),
                    'name_ru': data.get('name_ru', ''),
                    'name_me': data.get('name_me', ''),
                    'name_de': data.get('name_de', ''),
                    'description': data.get('description', ''),
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Breeds: {created_count} created, {updated_count} updated.'
        ))