"""
Команда подготовки MVP-демо-данных для periodic procedure reminders.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalog.models import Service
from notifications.models import NotificationType
from pets.models import Pet, PetOwner, PetType, VisitRecord

User = get_user_model()

DEFAULT_DEMO_PASSWORD = 'TestPassword123!'
DEMO_SERVICE_CODES = [
    'vaccination_rabies',
    'vaccination_complex',
    'deworming',
]
DEMO_OWNER_EMAILS = [
    'periodic-reminder-owner-1@example.com',
    'periodic-reminder-owner-2@example.com',
    'periodic-reminder-owner-3@example.com',
]
DEMO_PET_NAMES = [
    'Reminder Demo Atlas',
    'Reminder Demo Luna',
    'Reminder Demo Max',
]


class Command(BaseCommand):
    """
    Идемпотентно создает минимальные demo-данные для periodic reminder MVP.
    """

    help = 'Create demo pets and visit records for periodic procedure reminders MVP'

    @transaction.atomic
    def handle(self, *args, **options):
        """
        Выполняет подготовку demo-данных по следующей дате процедуры.
        """
        notification_type, _ = NotificationType.objects.update_or_create(
            code='reminder',
            defaults={
                'name': 'Reminder',
                'name_en': 'Reminder',
                'description': 'Generic reminder notifications',
                'description_en': 'Generic reminder notifications',
                'is_active': True,
                'default_enabled': True,
                'is_required': False,
            },
        )

        services = self._get_demo_services()
        if len(services) < len(DEMO_OWNER_EMAILS):
            raise CommandError(
                'Not enough periodic services with reminders enabled to prepare demo data.'
            )

        created_users = 0
        created_pets = 0
        created_records = 0
        updated_records = 0
        reference_date = timezone.localdate()

        for index, service in enumerate(services, start=1):
            owner, owner_created = self._get_or_create_demo_owner(index=index)
            if owner_created:
                created_users += 1

            pet, pet_created = self._get_or_create_demo_pet(index=index, owner=owner, service=service)
            if pet_created:
                created_pets += 1

            record_created = self._upsert_visit_record(
                pet=pet,
                owner=owner,
                service=service,
                reference_date=reference_date,
            )
            if record_created:
                created_records += 1
            else:
                updated_records += 1

        self.stdout.write(
            self.style.SUCCESS(
                'Periodic procedure reminder MVP data is ready: '
                f'notification_type_id={notification_type.id}, '
                f'users_created={created_users}, '
                f'pets_created={created_pets}, '
                f'visit_records_created={created_records}, '
                f'visit_records_updated={updated_records}'
            )
        )

    def _get_demo_services(self) -> list[Service]:
        """
        Возвращает подходящие periodic-услуги в стабильном порядке.
        """
        preferred_services: list[Service] = []
        used_ids: set[int] = set()

        for service_code in DEMO_SERVICE_CODES:
            service = (
                Service.objects.filter(
                    code=service_code,
                    is_active=True,
                    is_periodic=True,
                    send_reminders=True,
                    reminder_days_before__isnull=False,
                )
                .order_by('id')
                .first()
            )
            if service is not None and service.id not in used_ids:
                preferred_services.append(service)
                used_ids.add(service.id)

        fallback_services = (
            Service.objects.filter(
                is_active=True,
                is_periodic=True,
                send_reminders=True,
                reminder_days_before__isnull=False,
            )
            .exclude(id__in=used_ids)
            .order_by('id')
        )
        for service in fallback_services:
            preferred_services.append(service)
            if len(preferred_services) >= len(DEMO_OWNER_EMAILS):
                break

        return preferred_services

    def _get_or_create_demo_owner(self, *, index: int):
        """
        Создает или переиспользует владельца с безопасным demo-email.
        """
        email = DEMO_OWNER_EMAILS[index - 1]
        defaults = {
            'first_name': 'Periodic',
            'last_name': f'Demo {index}',
            'phone_number': f'+3826701000{index}',
            'is_active': True,
        }

        owner = User.objects.filter(email=email).first()
        if owner is not None:
            changed_fields: list[str] = []
            for field_name, field_value in defaults.items():
                if not getattr(owner, field_name):
                    setattr(owner, field_name, field_value)
                    changed_fields.append(field_name)
            if changed_fields:
                owner.save(update_fields=changed_fields)
            if not owner.has_role('pet_owner'):
                owner.add_role('pet_owner')
            return owner, False

        owner = User.objects.create_user(
            email=email,
            password=DEFAULT_DEMO_PASSWORD,
            **defaults,
        )
        owner.add_role('pet_owner')
        return owner, True

    def _get_or_create_demo_pet(self, *, index: int, owner, service: Service):
        """
        Создает или переиспользует demo-питомца под конкретный periodic service.
        """
        pet_type = self._resolve_pet_type_for_service(service)
        if pet_type is None:
            raise CommandError(
                f'No pet type is available for service "{service.code}".'
            )

        pet_name = DEMO_PET_NAMES[index - 1]
        pet = Pet.objects.filter(name=pet_name).order_by('id').first()
        if pet is None:
            pet = Pet.objects.create(
                name=pet_name,
                pet_type=pet_type,
                weight=10 + index,
            )
            created = True
        else:
            created = False
            changed_fields: list[str] = []
            if pet.pet_type_id != pet_type.id:
                pet.pet_type = pet_type
                changed_fields.append('pet_type')
            expected_weight = 10 + index
            if pet.weight != expected_weight:
                pet.weight = expected_weight
                changed_fields.append('weight')
            if changed_fields:
                pet.save(update_fields=changed_fields)

        pet_owner = PetOwner.objects.filter(pet=pet, user=owner).first()
        if pet_owner is None:
            existing_main_owner = PetOwner.objects.filter(pet=pet, role='main').exclude(user=owner).first()
            if existing_main_owner is not None:
                existing_main_owner.role = 'coowner'
                existing_main_owner.save(update_fields=['role'])

            PetOwner.objects.create(
                pet=pet,
                user=owner,
                role='main',
            )
        elif pet_owner.role != 'main':
            PetOwner.objects.filter(pet=pet, role='main').exclude(user=owner).update(role='coowner')
            pet_owner.role = 'main'
            pet_owner.save(update_fields=['role'])

        return pet, created

    def _upsert_visit_record(self, *, pet: Pet, owner, service: Service, reference_date) -> bool:
        """
        Создает или обновляет VisitRecord так, чтобы reminder был due уже сегодня.
        """
        target_next_date = reference_date + timedelta(days=service.reminder_days_before or 0)
        performed_at = timezone.make_aware(
            datetime.combine(
                target_next_date - timedelta(days=service.period_days or 0),
                time(hour=9, minute=0),
            ),
            timezone.get_current_timezone(),
        )

        visit_record = VisitRecord.objects.filter(pet=pet, service=service).order_by('id').first()
        if visit_record is None:
            visit_record = VisitRecord.objects.create(
                pet=pet,
                service=service,
                date=performed_at,
                description='Periodic reminder MVP demo record',
                recommendations='The next procedure date is set for periodic reminder demo.',
                created_by=owner,
            )
            created = True
        else:
            created = False

        visit_record.date = performed_at
        visit_record.next_date = target_next_date
        visit_record.description = 'Periodic reminder MVP demo record'
        visit_record.recommendations = 'The next procedure date is set for periodic reminder demo.'
        visit_record.created_by = owner
        visit_record.save()
        return created

    def _resolve_pet_type_for_service(self, service: Service):
        """
        Подбирает подходящий тип питомца для demo-записи.
        """
        pet_type = service.allowed_pet_types.order_by('id').first()
        if pet_type is not None:
            return pet_type

        for preferred_code in ['dog', 'cat', 'bird', 'turtle']:
            pet_type = PetType.objects.filter(code__iexact=preferred_code).order_by('id').first()
            if pet_type is not None:
                return pet_type

        return PetType.objects.order_by('id').first()
