"""
MVP-сервис напоминаний о периодических процедурах.

Этот модуль сознательно не использует notifications.Reminder как отдельный
источник правды. Для MVP достаточно:
1. для обычных периодических процедур брать назначенную следующую дату из VisitRecord;
2. для вакцинаций использовать owner-facing expiry-поля карточки питомца;
3. учитывать periodic-настройки самой услуги;
4. создавать idempotent Notification только в момент, когда reminder уже due.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from notifications.models import Notification, NotificationPreference
from notifications.services import NotificationService
from catalog.models import Service
from pets.models import Pet, VisitRecord, PET_VACCINATION_EXPIRY_SERVICE_FIELD_MAP

logger = logging.getLogger(__name__)

class PeriodicProcedureReminderService:
    """
    MVP-сервис генерации email reminder по периодическим процедурам питомцев.
    """

    def send_due_reminders(self, reference_time=None) -> dict[str, int]:
        """
        Обходит due-источники и отправляет reminder без дублей.
        """
        reference_time = reference_time or timezone.now()
        reference_date = timezone.localdate(reference_time)
        visit_record_ids = self._get_due_visit_record_ids(reference_date=reference_date)
        pet_expiry_sources = self._get_due_pet_expiry_sources(reference_date=reference_date)

        processed_count = 0
        sent_count = 0

        for visit_record_id in visit_record_ids:
            processed_count += 1
            sent_count += self.send_due_reminder_for_visit_record(
                visit_record_id=visit_record_id,
                reference_time=reference_time,
            )

        for pet_id, service_code in pet_expiry_sources:
            processed_count += 1
            sent_count += self.send_due_reminder_for_pet_expiry(
                pet_id=pet_id,
                service_code=service_code,
                reference_time=reference_time,
            )

        return {
            'processed_count': processed_count,
            'sent_count': sent_count,
        }

    def send_due_reminder_for_visit_record(self, visit_record_id: int, reference_time=None) -> int:
        """
        Отправляет reminder для одной записи визита, если он действительно due.
        """
        reference_time = reference_time or timezone.now()
        reference_date = timezone.localdate(reference_time)
        notification_id: int | None = None

        with transaction.atomic():
            visit_record = (
                VisitRecord.objects.select_for_update()
                .select_related('pet', 'service')
                .filter(id=visit_record_id)
                .first()
            )
            if visit_record is None:
                logger.info(
                    "Visit record %s was not found for periodic reminder",
                    visit_record_id,
                )
                return 0

            if not self._is_latest_active_record(visit_record):
                logger.info(
                    "Visit record %s is not the latest active periodic source, skipping",
                    visit_record_id,
                )
                return 0

            if not self._is_due(visit_record=visit_record, reference_date=reference_date):
                return 0

            owner = self._get_pet_owner(visit_record.pet)
            if owner is None:
                logger.info(
                    "Pet %s has no owner eligible for periodic reminder",
                    visit_record.pet_id,
                )
                return 0

            if not self._is_email_channel_enabled(owner):
                logger.info(
                    "Periodic reminder email channel is disabled for user %s",
                    owner.id,
                )
                return 0

            notification = self._get_existing_notification(visit_record=visit_record, owner=owner)
            if notification is None:
                reminder_due_date = self._get_reminder_due_date(visit_record)
                notification = Notification.objects.create(
                    user=owner,
                    pet=visit_record.pet,
                    notification_type='reminder',
                    title=_('Periodic Procedure Reminder'),
                    message=self._build_message(
                        visit_record=visit_record,
                        reference_date=reference_date,
                    ),
                    priority='medium',
                    channel='email',
                    scheduled_for=self._build_scheduled_for(reminder_due_date),
                    data={
                        'visit_record_id': visit_record.id,
                        'service_id': visit_record.service_id,
                        'service_name': visit_record.service.name,
                        'next_date': visit_record.next_date.isoformat(),
                        'reminder_type': 'periodic_procedure',
                        'reminder_days_before': visit_record.service.reminder_days_before,
                        'reminder_due_date': reminder_due_date.isoformat(),
                    },
                )

            if notification.sent_at is None:
                notification_id = notification.id

        if notification_id is None:
            return 0

        self._deliver_notification(notification_id=notification_id)
        return 1

    def send_due_reminder_for_pet_expiry(
        self,
        *,
        pet_id: int,
        service_code: str,
        reference_time=None,
    ) -> int:
        """
        Отправляет reminder по owner-facing expiry-полю питомца.
        """
        reference_time = reference_time or timezone.now()
        reference_date = timezone.localdate(reference_time)
        notification_id: int | None = None

        with transaction.atomic():
            pet = (
                Pet.objects.select_for_update()
                .prefetch_related('petowner_set', 'petowner_set__user')
                .filter(id=pet_id)
                .first()
            )
            if pet is None:
                logger.info(
                    "Pet %s was not found for vaccination expiry reminder",
                    pet_id,
                )
                return 0

            service = self._get_expiry_mapped_service(service_code=service_code)
            if service is None:
                return 0

            expiry_field_name = PET_VACCINATION_EXPIRY_SERVICE_FIELD_MAP[service_code]
            next_date = getattr(pet, expiry_field_name, None)
            if next_date is None:
                return 0

            if not self._is_due_date(
                next_date=next_date,
                reminder_days_before=service.reminder_days_before,
                reference_date=reference_date,
            ):
                return 0

            owner = self._get_pet_owner(pet)
            if owner is None:
                logger.info(
                    "Pet %s has no owner eligible for vaccination expiry reminder",
                    pet.id,
                )
                return 0

            if not self._is_email_channel_enabled(owner):
                logger.info(
                    "Periodic reminder email channel is disabled for user %s",
                    owner.id,
                )
                return 0

            notification = self._get_existing_pet_expiry_notification(
                pet=pet,
                owner=owner,
                service=service,
                next_date=next_date,
                expiry_field_name=expiry_field_name,
            )
            if notification is None:
                reminder_due_date = next_date - timedelta(days=service.reminder_days_before or 0)
                notification = Notification.objects.create(
                    user=owner,
                    pet=pet,
                    notification_type='reminder',
                    title=_('Periodic Procedure Reminder'),
                    message=self._build_message_for_due_date(
                        pet=pet,
                        service=service,
                        next_date=next_date,
                        reference_date=reference_date,
                    ),
                    priority='medium',
                    channel='email',
                    scheduled_for=self._build_scheduled_for(reminder_due_date),
                    data={
                        'service_id': service.id,
                        'service_name': service.name,
                        'next_date': next_date.isoformat(),
                        'reminder_type': 'periodic_procedure',
                        'reminder_source': 'pet_vaccination_expiry',
                        'pet_expiry_field': expiry_field_name,
                        'reminder_days_before': service.reminder_days_before,
                        'reminder_due_date': reminder_due_date.isoformat(),
                    },
                )

            if notification.sent_at is None:
                notification_id = notification.id

        if notification_id is None:
            return 0

        self._deliver_notification(notification_id=notification_id)
        return 1

    def _get_due_visit_record_ids(self, *, reference_date) -> list[int]:
        """
        Возвращает только те visit records, которые уже попали в окно reminder.
        """
        max_days_before = (
            VisitRecord.objects.filter(
                service__is_periodic=True,
                service__send_reminders=True,
                service__reminder_days_before__isnull=False,
                next_date__isnull=False,
            )
            .exclude(
                service__code__in=PET_VACCINATION_EXPIRY_SERVICE_FIELD_MAP.keys(),
            ).aggregate(max_days=Max('service__reminder_days_before'))['max_days']
            or 0
        )
        if max_days_before <= 0:
            return []

        candidate_records = (
            VisitRecord.objects.select_related('service')
            .filter(
                service__is_periodic=True,
                service__send_reminders=True,
                service__reminder_days_before__isnull=False,
                next_date__isnull=False,
                next_date__gte=reference_date,
                next_date__lte=reference_date + timedelta(days=max_days_before),
            )
            .exclude(service__code__in=PET_VACCINATION_EXPIRY_SERVICE_FIELD_MAP.keys())
            .order_by('pet_id', 'service_id', '-date', '-id')
        )

        latest_by_pair: dict[tuple[int, int], VisitRecord] = {}
        for visit_record in candidate_records:
            key = (visit_record.pet_id, visit_record.service_id)
            latest_by_pair.setdefault(key, visit_record)

        due_ids: list[int] = []
        for visit_record in latest_by_pair.values():
            if self._is_due(visit_record=visit_record, reference_date=reference_date):
                due_ids.append(visit_record.id)

        return sorted(due_ids)

    def _get_due_pet_expiry_sources(self, *, reference_date) -> list[tuple[int, str]]:
        """
        Возвращает due-источники из owner-facing expiry-полей питомца.
        """
        due_sources: list[tuple[int, str]] = []

        for service_code, field_name in PET_VACCINATION_EXPIRY_SERVICE_FIELD_MAP.items():
            service = self._get_expiry_mapped_service(service_code=service_code)
            if service is None:
                continue

            filter_kwargs = {
                'is_active': True,
                f'{field_name}__isnull': False,
                f'{field_name}__gte': reference_date,
                f'{field_name}__lte': reference_date + timedelta(days=service.reminder_days_before or 0),
            }
            for pet_id in Pet.objects.filter(**filter_kwargs).values_list('id', flat=True):
                due_sources.append((pet_id, service_code))

        return due_sources

    def _is_due(self, *, visit_record: VisitRecord, reference_date) -> bool:
        """
        Проверяет, что reminder по записи уже должен быть отправлен.
        """
        if visit_record.next_date is None:
            return False

        service = visit_record.service
        if not service.is_periodic or not service.send_reminders or service.reminder_days_before is None:
            return False

        reminder_due_date = self._get_reminder_due_date(visit_record)
        return reminder_due_date <= reference_date <= visit_record.next_date

    def _is_due_date(self, *, next_date, reminder_days_before: int | None, reference_date) -> bool:
        """
        Проверяет due-окно по произвольной следующей дате.
        """
        if next_date is None or reminder_days_before is None:
            return False

        reminder_due_date = next_date - timedelta(days=reminder_days_before)
        return reminder_due_date <= reference_date <= next_date

    def _get_reminder_due_date(self, visit_record: VisitRecord):
        """
        Возвращает дату, с которой reminder считается due.
        """
        return visit_record.next_date - timedelta(days=visit_record.service.reminder_days_before or 0)

    def _is_latest_active_record(self, visit_record: VisitRecord) -> bool:
        """
        Защищает от дублей, если по той же услуге уже появился более свежий визит.
        """
        latest_id = (
            VisitRecord.objects.filter(
                pet_id=visit_record.pet_id,
                service_id=visit_record.service_id,
                next_date__isnull=False,
            )
            .order_by('-date', '-id')
            .values_list('id', flat=True)
            .first()
        )
        return latest_id == visit_record.id

    def _get_expiry_mapped_service(self, *, service_code: str):
        """
        Возвращает periodic service для owner-facing vaccination expiry.
        """
        return (
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

    def _get_pet_owner(self, pet):
        """
        Возвращает основного владельца текущей модели Pet с fallback для legacy-кода.
        """
        owner = getattr(pet, 'main_owner', None)
        if owner is not None:
            return owner

        owner = getattr(pet, 'owner', None)
        if owner is not None:
            return owner

        return pet.owners.order_by('id').first()

    def _is_email_channel_enabled(self, user) -> bool:
        """
        Для MVP reminder отправляется по email, если пользователь явно его не выключил.
        """
        preference = (
            NotificationPreference.objects.filter(
                user=user,
                notification_type__code='reminder',
            )
            .order_by('-updated_at', '-id')
            .first()
        )
        if preference is None:
            return True
        return preference.email_enabled

    def _get_existing_notification(self, *, visit_record: VisitRecord, owner):
        """
        Ищет уже созданный reminder для конкретной следующей даты процедуры.
        """
        return (
            Notification.objects.filter(
                user=owner,
                notification_type='reminder',
                data__visit_record_id=visit_record.id,
                data__reminder_type='periodic_procedure',
                data__next_date=visit_record.next_date.isoformat(),
            )
            .order_by('-created_at')
            .first()
        )

    def _get_existing_pet_expiry_notification(self, *, pet, owner, service: Service, next_date, expiry_field_name: str):
        """
        Ищет уже созданный reminder для expiry-поля питомца.
        """
        return (
            Notification.objects.filter(
                user=owner,
                pet=pet,
                notification_type='reminder',
                data__service_id=service.id,
                data__reminder_type='periodic_procedure',
                data__reminder_source='pet_vaccination_expiry',
                data__pet_expiry_field=expiry_field_name,
                data__next_date=next_date.isoformat(),
            )
            .order_by('-created_at')
            .first()
        )

    def _deliver_notification(self, *, notification_id: int) -> None:
        """
        Отправляет уже созданное email-уведомление, если оно еще не отправлено.
        """
        notification = Notification.objects.select_related('user').filter(id=notification_id).first()
        if notification is None or notification.sent_at is not None:
            return

        NotificationService()._send_notification(notification, ['email'])

    def _build_scheduled_for(self, reminder_due_date):
        """
        Нормализует scheduled_for к началу дня reminder для аудита и отладки.
        """
        scheduled_at = datetime.combine(reminder_due_date, time(hour=9, minute=0))
        return timezone.make_aware(scheduled_at, timezone.get_current_timezone())

    def _build_message(self, *, visit_record: VisitRecord, reference_date) -> str:
        """
        Формирует понятный MVP-текст для владельца питомца.
        """
        return self._build_message_for_due_date(
            pet=visit_record.pet,
            service=visit_record.service,
            next_date=visit_record.next_date,
            reference_date=reference_date,
        )

    def _build_message_for_due_date(self, *, pet, service: Service, next_date, reference_date) -> str:
        """
        Формирует понятный MVP-текст для владельца по следующей дате.
        """
        time_until_due = self._format_time_until_due(
            next_date=next_date,
            reference_date=reference_date,
        )
        if next_date > reference_date:
            return _(
                '%(service)s for %(pet)s is due in %(time_until_due)s on %(next_date)s.'
            ) % {
                'service': service.name,
                'pet': pet.name,
                'time_until_due': time_until_due,
                'next_date': next_date.isoformat(),
            }

        return _(
            '%(service)s for %(pet)s is due today (%(next_date)s).'
        ) % {
            'service': service.name,
            'pet': pet.name,
            'next_date': next_date.isoformat(),
        }

    def _format_time_until_due(self, *, next_date, reference_date) -> str:
        """
        Возвращает человекочитаемый интервал до следующей процедуры.
        """
        days_until_due = max((next_date - reference_date).days, 0)
        if days_until_due == 0:
            return _('today')

        return ngettext(
            '%(count)d day',
            '%(count)d days',
            days_until_due,
        ) % {'count': days_until_due}
