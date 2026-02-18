# -*- coding: utf-8 -*-
"""
Management command: clear existing catalog and load veterinary + grooming hierarchy.

Usage:
  python manage.py load_catalog_veterinary_grooming
  python manage.py load_catalog_veterinary_grooming --no-input  # skip confirmation

Before running: PetType with codes bird, cat, dog, snake, turtle must exist (pets app).
Deletes: ProviderLocationService, Provider.available_category_levels, ProviderLocation.available_services,
  PetRecord, then all Service. Other FK to Service (booking, billing, etc.) are CASCADE or must be empty.
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from catalog.models import Service
from pets.models import PetType
from providers.models import Provider, ProviderLocation, ProviderLocationService


# Все узлы каталога: код, родительский код, названия EN/RU/DE/ME, для листьев — периодичность и типы животных.
# name = name_en (основной), переводы в name_ru, name_de, name_me. Описания заполняются из названий при загрузке.
CATALOG_DATA = [
    # 1. Ветеринария
    {
        "code": "veterinary",
        "parent_code": None,
        "name_en": "Veterinary",
        "name_ru": "Ветеринария",
        "name_de": "Veterinärwesen",
        "name_me": "Veterina",
    },
    {
        "code": "therapeutic_visit",
        "parent_code": "veterinary",
        "name_en": "Therapeutic visit",
        "name_ru": "Терапевтический прием",
        "name_de": "Therapeutischer Besuch",
        "name_me": "Terapijski pregled",
    },
    {
        "code": "initial_exam_consultation",
        "parent_code": "therapeutic_visit",
        "name_en": "Initial examination and consultation",
        "name_ru": "Первичный осмотр и консультация",
        "name_de": "Erstuntersuchung und Beratung",
        "name_me": "Početni pregled i savjetovanje",
        "is_periodic": False,
        "pet_codes": ["bird", "cat", "dog", "snake", "turtle"],
    },
    {
        "code": "preventive_medicine",
        "parent_code": "veterinary",
        "name_en": "Preventive medicine",
        "name_ru": "Профилактическая медицина",
        "name_de": "Präventivmedizin",
        "name_me": "Preventivna medicina",
    },
    {
        "code": "vaccination_rabies",
        "parent_code": "preventive_medicine",
        "name_en": "Vaccination: Rabies",
        "name_ru": "Вакцинация: Бешенство",
        "name_de": "Impfung: Tollwut",
        "name_me": "Vakcinacija: bjesnilo",
        "is_periodic": True,
        "period_days": 365,
        "send_reminders": True,
        "reminder_days_before": 30,
        "pet_codes": ["dog", "cat"],
    },
    {
        "code": "vaccination_complex",
        "parent_code": "preventive_medicine",
        "name_en": "Vaccination: Complex",
        "name_ru": "Вакцинация: Комплексная",
        "name_de": "Impfung: Kombination",
        "name_me": "Vakcinacija: kombinovana",
        "is_periodic": True,
        "period_days": 365,
        "send_reminders": True,
        "reminder_days_before": 14,
        "pet_codes": ["dog", "cat"],
    },
    {
        "code": "deworming",
        "parent_code": "preventive_medicine",
        "name_en": "Deworming",
        "name_ru": "Дегельминтизация (от глистов)",
        "name_de": "Entwurmung",
        "name_me": "Dehelmintizacija",
        "is_periodic": True,
        "period_days": 90,
        "send_reminders": True,
        "reminder_days_before": 5,
        "pet_codes": ["dog", "cat", "snake", "turtle"],
    },
    {
        "code": "ectoparasite_treatment",
        "parent_code": "preventive_medicine",
        "name_en": "Ectoparasite treatment (fleas/ticks)",
        "name_ru": "Обработка от эктопаразитов (блохи/клещи)",
        "name_de": "Behandlung gegen Ektoparasiten (Flöhe/Zecken)",
        "name_me": "Tretman protiv ektoparazita (buhe/krpelji)",
        "is_periodic": True,
        "period_days": 30,
        "send_reminders": True,
        "reminder_days_before": 3,
        "pet_codes": ["dog", "cat"],
    },
    {
        "code": "specialized_care",
        "parent_code": "veterinary",
        "name_en": "Specialized care",
        "name_ru": "Специализированная помощь",
        "name_de": "Spezialisierte Versorgung",
        "name_me": "Specijalizovana nega",
    },
    {
        "code": "dentistry",
        "parent_code": "specialized_care",
        "name_en": "Dentistry",
        "name_ru": "Стоматология",
        "name_de": "Zahnheilkunde",
        "name_me": "Stomatologija",
    },
    {
        "code": "dental_ultrasonic_cleaning",
        "parent_code": "dentistry",
        "name_en": "Ultrasonic dental cleaning",
        "name_ru": "Ультразвуковая чистка зубов",
        "name_de": "Ultraschall-Zahnreinigung",
        "name_me": "Ultrazvučno čišćenje zuba",
        "is_periodic": True,
        "period_days": 365,
        "send_reminders": True,
        "reminder_days_before": 30,
        "pet_codes": ["dog", "cat"],
    },
    {
        "code": "tooth_extraction",
        "parent_code": "dentistry",
        "name_en": "Tooth extraction",
        "name_ru": "Удаление зубов",
        "name_de": "Zahnentfernung",
        "name_me": "Ekstrakcija zuba",
        "is_periodic": False,
        "pet_codes": ["dog", "cat", "snake"],
    },
    {
        "code": "horn_beak_care",
        "parent_code": "specialized_care",
        "name_en": "Horn and beak care",
        "name_ru": "Роговые покровы и клюв",
        "name_de": "Horn und Schnabelpflege",
        "name_me": "Nega rogova i kljuna",
    },
    {
        "code": "beak_trimming",
        "parent_code": "horn_beak_care",
        "name_en": "Beak trimming",
        "name_ru": "Коррекция клюва",
        "name_de": "Schnabelkorrektur",
        "name_me": "Korekcija kljuna",
        "is_periodic": True,
        "period_days": 60,
        "send_reminders": True,
        "reminder_days_before": 7,
        "pet_codes": ["bird", "turtle"],
    },
    {
        "code": "nail_trimming",
        "parent_code": "horn_beak_care",
        "name_en": "Nail trimming",
        "name_ru": "Стрижка когтей",
        "name_de": "Krallen schneiden",
        "name_me": "Šišanje noktiju",
        "is_periodic": True,
        "period_days": 30,
        "send_reminders": True,
        "reminder_days_before": 3,
        "pet_codes": ["dog", "cat", "bird", "turtle"],
    },
    {
        "code": "shell_injury_treatment",
        "parent_code": "horn_beak_care",
        "name_en": "Shell injury treatment",
        "name_ru": "Лечение травм панциря",
        "name_de": "Behandlung von Panzerverletzungen",
        "name_me": "Liječenje povreda oklopa",
        "is_periodic": False,
        "pet_codes": ["turtle"],
    },
    {
        "code": "surgery_identification",
        "parent_code": "veterinary",
        "name_en": "Surgery and identification",
        "name_ru": "Хирургия и идентификация",
        "name_de": "Chirurgie und Identifikation",
        "name_me": "Hirurgija i identifikacija",
    },
    {
        "code": "sterilization_castration",
        "parent_code": "surgery_identification",
        "name_en": "Sterilization / Castration",
        "name_ru": "Стерилизация / Кастрация",
        "name_de": "Sterilisation / Kastration",
        "name_me": "Sterilizacija / kastracija",
        "is_periodic": False,
        "pet_codes": ["dog", "cat"],
    },
    {
        "code": "microchipping",
        "parent_code": "surgery_identification",
        "name_en": "Microchipping",
        "name_ru": "Электронное чипирование",
        "name_de": "Mikrochip-Implantation",
        "name_me": "Elektronsko čipiranje",
        "is_periodic": False,
        "pet_codes": ["dog", "cat", "snake", "turtle"],
    },
    {
        "code": "sex_determination",
        "parent_code": "surgery_identification",
        "name_en": "Sex determination",
        "name_ru": "Определение пола",
        "name_de": "Geschlechtsbestimmung",
        "name_me": "Određivanje pola",
        "is_periodic": False,
        "pet_codes": ["bird", "snake", "turtle"],
    },
    # 2. Груминг
    {
        "code": "grooming",
        "parent_code": None,
        "name_en": "Grooming",
        "name_ru": "Груминг",
        "name_de": "Fellpflege",
        "name_me": "Grooming",
    },
    {
        "code": "aesthetic_grooming",
        "parent_code": "grooming",
        "name_en": "Aesthetic grooming",
        "name_ru": "Эстетический груминг",
        "name_de": "Ästhetische Fellpflege",
        "name_me": "Estetski grooming",
    },
    {
        "code": "clipping_styling",
        "parent_code": "aesthetic_grooming",
        "name_en": "Clipping and styling",
        "name_ru": "Стрижки и стайлинг",
        "name_de": "Scheren und Styling",
        "name_me": "Šišanje i stajling",
    },
    {
        "code": "breed_trim",
        "parent_code": "clipping_styling",
        "name_en": "Breed trim (full)",
        "name_ru": "Модельная стрижка (комплекс)",
        "name_de": "Rasse-Schnitt (Komplex)",
        "name_me": "Modelsko šišanje (kompleks)",
        "is_periodic": True,
        "period_days": 45,
        "send_reminders": True,
        "reminder_days_before": 7,
        "pet_codes": ["dog", "cat"],
    },
    {
        "code": "hand_stripping",
        "parent_code": "clipping_styling",
        "name_en": "Hand stripping (wire coat)",
        "name_ru": "Тримминг жесткой шерсти",
        "name_de": "Trimming (drahtiges Fell)",
        "name_me": "Trimming (žica dlaka)",
        "is_periodic": True,
        "period_days": 90,
        "send_reminders": True,
        "reminder_days_before": 10,
        "pet_codes": ["dog"],
    },
    {
        "code": "shedding_care",
        "parent_code": "aesthetic_grooming",
        "name_en": "Shedding care",
        "name_ru": "Уход за линяющими",
        "name_de": "Pflege bei Haarwechsel",
        "name_me": "Nega linjavih",
    },
    {
        "code": "express_shedding",
        "parent_code": "shedding_care",
        "name_en": "Express shedding",
        "name_ru": "Экспресс-линька",
        "name_de": "Express-Haarwechsel",
        "name_me": "Ekspres linjanje",
        "is_periodic": True,
        "period_days": 180,
        "send_reminders": True,
        "reminder_days_before": 14,
        "pet_codes": ["dog", "cat", "snake"],
    },
    {
        "code": "hygienic_grooming",
        "parent_code": "grooming",
        "name_en": "Hygienic grooming",
        "name_ru": "Гигиенический уход",
        "name_de": "Hygienische Pflege",
        "name_me": "Hijienski grooming",
    },
    {
        "code": "bath_and_dry",
        "parent_code": "hygienic_grooming",
        "name_en": "Bath and blow-dry",
        "name_ru": "Комплексное мытье и сушка",
        "name_de": "Komplexes Waschen und Trocknen",
        "name_me": "Kompleksno pranje i sušenje",
        "is_periodic": True,
        "period_days": 30,
        "send_reminders": True,
        "reminder_days_before": 3,
        "pet_codes": ["dog", "cat"],
    },
    {
        "code": "hygienic_trim",
        "parent_code": "hygienic_grooming",
        "name_en": "Hygienic trim (paws, ears, groin)",
        "name_ru": "Гигиеническая стрижка (лапы, уши, пах)",
        "name_de": "Hygieneschnitt (Pfoten, Ohren, Leiste)",
        "name_me": "Hijiensko šišanje (šape, uši, prepone)",
        "is_periodic": True,
        "period_days": 21,
        "send_reminders": True,
        "reminder_days_before": 3,
        "pet_codes": ["dog", "cat"],
    },
    {
        "code": "spa_exotic",
        "parent_code": "grooming",
        "name_en": "SPA and exotic",
        "name_ru": "SPA и экзотика",
        "name_de": "SPA und Exoten",
        "name_me": "SPA i egzotika",
    },
    {
        "code": "ozone_bath",
        "parent_code": "spa_exotic",
        "name_en": "Ozone bath",
        "name_ru": "Озоновая ванна",
        "name_de": "Ozonbad",
        "name_me": "Ozonska kupka",
        "is_periodic": False,
        "pet_codes": ["dog", "cat"],
    },
    {
        "code": "shell_clean_polish",
        "parent_code": "spa_exotic",
        "name_en": "Shell cleaning and polishing",
        "name_ru": "Чистка и полировка панциря",
        "name_de": "Panzerreinigung und -politur",
        "name_me": "Čišćenje i poliranje oklopa",
        "is_periodic": True,
        "period_days": 180,
        "send_reminders": True,
        "reminder_days_before": 14,
        "pet_codes": ["turtle"],
    },
]


class Command(BaseCommand):
    help = _(
        "Clear existing catalog and load veterinary + grooming hierarchy. "
        "Requires PetType with codes: bird, cat, dog, snake, turtle."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-input",
            action="store_true",
            help=_("Do not ask for confirmation"),
        )

    def handle(self, *args, **options):
        if not options["no_input"]:
            if input(_("Delete all catalog services and load new hierarchy? [y/N]: ")).strip().lower() != "y":
                self.stdout.write(self.style.WARNING(_("Aborted.")))
                return

        pet_types_by_code = {}
        for code in ("bird", "cat", "dog", "snake", "turtle"):
            try:
                pet_types_by_code[code] = PetType.objects.get(code=code)
            except PetType.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(
                        _("PetType with code '%(code)s' not found. Create pet types first.") % {"code": code}
                    )
                )
                return

        with transaction.atomic():
            self._clear_catalog()
            created = self._load_catalog(pet_types_by_code)

        call_command("update_hierarchy_order")
        self.stdout.write(self.style.SUCCESS(_("Created %(count)s catalog services.") % {"count": created}))

    def _clear_catalog(self):
        """Удаляем все зависимости от Service, затем все Service."""
        # M2M: очищаем связи, чтобы удаление Service не трогало провайдеров
        for p in Provider.objects.all():
            p.available_category_levels.clear()
        for loc in ProviderLocation.objects.all():
            loc.available_services.clear()
        # Записи, ссылающиеся на Service с PROTECT
        from pets.models import PetRecord

        deleted_pr = PetRecord.objects.all().delete()
        self.stdout.write(_("Deleted PetRecord count: %(n)s") % {"n": deleted_pr[0]})
        # ProviderLocationService и прочие CASCADE удалятся при удалении Service
        Service.objects.all().delete()
        self.stdout.write(_("Catalog (Service) cleared."))

    def _load_catalog(self, pet_types_by_code):
        by_code = {}
        for item in CATALOG_DATA:
            parent = by_code.get(item["parent_code"]) if item["parent_code"] else None
            name_en = item["name_en"]
            name_ru = item.get("name_ru", "")
            name_de = item.get("name_de", "")
            name_me = item.get("name_me", "")
            defaults = {
                "name": name_en,
                "name_en": name_en,
                "name_ru": name_ru,
                "name_de": name_de,
                "name_me": name_me,
                "description": name_en,
                "description_en": name_en,
                "description_ru": name_ru or name_en,
                "description_de": name_de or name_en,
                "description_me": name_me or name_en,
                "parent": parent,
                "is_active": True,
                "is_mandatory": False,
                "is_periodic": item.get("is_periodic", False),
                "period_days": item.get("period_days"),
                "send_reminders": item.get("send_reminders", False),
                "reminder_days_before": item.get("reminder_days_before"),
            }
            obj = Service.objects.create(code=item["code"], **defaults)
            by_code[item["code"]] = obj
            if item.get("pet_codes"):
                obj.allowed_pet_types.set(
                    [pet_types_by_code[c] for c in item["pet_codes"] if c in pet_types_by_code]
                )
        return len(by_code)
