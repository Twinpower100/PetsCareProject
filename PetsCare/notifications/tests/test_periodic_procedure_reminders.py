from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from booking.test_booking_flow_logic import BookingFlowBaseMixin
from catalog.models import Service
from celery_config import app as celery_app
from notifications.models import Notification, NotificationType
from notifications.tasks import process_reminders_task
from pets.serializers import PetSerializer
from pets.models import PetType, PetOwner, VisitRecord
from users.models import User
from rest_framework.test import APIRequestFactory


class PeriodicProcedureReminderTaskTests(BookingFlowBaseMixin, TestCase):
    """
    Тесты MVP-потока periodic procedure reminder.
    """

    def setUp(self):
        super().setUp()
        self.reference_time = timezone.make_aware(
            datetime.combine(timezone.localdate(), time(hour=9, minute=0)),
            timezone.get_current_timezone(),
        )
        service_code = f'periodic_{abs(hash(self._testMethodName))}'
        self.periodic_service = Service.objects.create(
            code=service_code[:50],
            name='Periodic Procedure',
            is_periodic=True,
            period_days=30,
            send_reminders=True,
            reminder_days_before=5,
            is_client_facing=True,
        )
        self.periodic_service.allowed_pet_types.add(self.pet_type)
        self.rabies_service = Service.objects.create(
            code='vaccination_rabies',
            name='Vaccination: Rabies',
            is_periodic=True,
            period_days=365,
            send_reminders=True,
            reminder_days_before=30,
            is_client_facing=True,
        )
        self.rabies_service.allowed_pet_types.add(self.pet_type)

    def _create_due_visit_record(self, *, next_date=None, service=None):
        """
        Создает visit record, reminder для которого due на reference_time.
        """
        service = service or self.periodic_service
        next_date = next_date or (timezone.localdate(self.reference_time) + timedelta(days=5))
        visit_record = VisitRecord.objects.create(
            pet=self.pet_one,
            provider=self.provider,
            provider_location=self.location_a,
            service=service,
            employee=self.employee_a,
            date=self.reference_time - timedelta(days=service.period_days),
            description='Periodic demo record',
            recommendations='Periodic demo recommendation',
            created_by=self.employee_a.user,
        )
        visit_record.next_date = next_date
        visit_record.save()
        return visit_record

    @patch('notifications.services.send_mail', return_value=1)
    def test_task_uses_main_owner_without_legacy_pet_owner_field(self, mocked_send_mail):
        """
        Task выбирает main_owner и не зависит от отсутствующего legacy pet.owner.
        """
        visit_record = self._create_due_visit_record()
        coowner = User.objects.create_user(
            email='periodic-coowner@example.com',
            password='password123',
            first_name='Co',
            last_name='Owner',
            phone_number='+38267000019',
        )
        PetOwner.objects.create(
            pet=self.pet_one,
            user=coowner,
            role='coowner',
        )

        result = process_reminders_task(reference_time=self.reference_time)

        notification = Notification.objects.get(
            notification_type='reminder',
            data__visit_record_id=visit_record.id,
            data__reminder_type='periodic_procedure',
        )
        self.assertEqual(result['processed_count'], 1)
        self.assertEqual(result['sent_count'], 1)
        self.assertEqual(notification.user, self.owner)
        self.assertEqual(notification.channel, 'email')
        self.assertIsNotNone(notification.sent_at)
        mocked_send_mail.assert_called_once()

    @patch('notifications.services.send_mail', return_value=1)
    def test_repeat_run_does_not_duplicate_periodic_reminder(self, mocked_send_mail):
        """
        Повторный запуск task не создает duplicate reminder для той же next_date.
        """
        visit_record = self._create_due_visit_record()

        process_reminders_task(reference_time=self.reference_time)
        second_result = process_reminders_task(reference_time=self.reference_time)

        self.assertEqual(second_result['sent_count'], 0)
        self.assertEqual(
            Notification.objects.filter(
                notification_type='reminder',
                data__visit_record_id=visit_record.id,
                data__reminder_type='periodic_procedure',
            ).count(),
            1,
        )
        mocked_send_mail.assert_called_once()

    @patch('notifications.services.send_mail', return_value=1)
    def test_shifted_next_date_creates_new_reminder_without_conflict(self, mocked_send_mail):
        """
        После сдвига next_date reminder создается заново уже для новой даты.
        """
        visit_record = self._create_due_visit_record()

        process_reminders_task(reference_time=self.reference_time)

        visit_record.next_date = timezone.localdate(self.reference_time) + timedelta(days=35)
        visit_record.save()

        second_reference_time = self.reference_time + timedelta(days=30)
        second_result = process_reminders_task(reference_time=second_reference_time)

        self.assertEqual(second_result['sent_count'], 1)
        self.assertEqual(
            Notification.objects.filter(
                notification_type='reminder',
                data__visit_record_id=visit_record.id,
                data__reminder_type='periodic_procedure',
            ).count(),
            2,
        )
        self.assertTrue(
            Notification.objects.filter(
                notification_type='reminder',
                data__visit_record_id=visit_record.id,
                data__next_date=visit_record.next_date.isoformat(),
            ).exists()
        )
        self.assertEqual(mocked_send_mail.call_count, 2)

    @patch('notifications.services.send_mail', return_value=1)
    def test_pet_vaccination_expiry_receives_reminder_without_visit_record(self, mocked_send_mail):
        """
        Reminder работает и от expiry-поля питомца, если VisitRecord еще отсутствует.
        """
        self.pet_one.rabies_vaccination_expiry = timezone.localdate(self.reference_time) + timedelta(days=30)
        self.pet_one.save(update_fields=['rabies_vaccination_expiry'])

        result = process_reminders_task(reference_time=self.reference_time)

        notification = Notification.objects.get(
            notification_type='reminder',
            pet=self.pet_one,
            data__reminder_source='pet_vaccination_expiry',
            data__pet_expiry_field='rabies_vaccination_expiry',
        )
        self.assertEqual(result['processed_count'], 1)
        self.assertEqual(result['sent_count'], 1)
        self.assertEqual(notification.user, self.owner)
        mocked_send_mail.assert_called_once()

    @patch('notifications.services.send_mail', return_value=1)
    def test_vaccination_visit_record_syncs_pet_card_and_reminder_uses_pet_source(self, mocked_send_mail):
        """
        Для вакцинаций VisitRecord обновляет карточку питомца, а reminder строится из нее.
        """
        target_next_date = timezone.localdate(self.reference_time) + timedelta(days=30)
        visit_record = self._create_due_visit_record(
            next_date=target_next_date,
            service=self.rabies_service,
        )
        self.pet_one.refresh_from_db()

        self.assertEqual(self.pet_one.rabies_vaccination_expiry, target_next_date)
        result = process_reminders_task(reference_time=self.reference_time)

        self.assertEqual(result['sent_count'], 1)
        notification = Notification.objects.get(
            notification_type='reminder',
            pet=self.pet_one,
            data__reminder_source='pet_vaccination_expiry',
            data__pet_expiry_field='rabies_vaccination_expiry',
            data__next_date=target_next_date.isoformat(),
        )
        self.assertEqual(notification.user, self.owner)
        self.assertFalse(
            Notification.objects.filter(
                notification_type='reminder',
                data__visit_record_id=visit_record.id,
                data__reminder_type='periodic_procedure',
            ).exists()
        )
        mocked_send_mail.assert_called_once()

    def test_older_vaccination_visit_record_update_does_not_override_latest_pet_expiry(self):
        """
        При редактировании старой записи срок действия в карточке не откатывается назад.
        """
        older_record = VisitRecord.objects.create(
            pet=self.pet_one,
            provider=self.provider,
            provider_location=self.location_a,
            service=self.rabies_service,
            employee=self.employee_a,
            date=self.reference_time - timedelta(days=730),
            description='Older rabies record',
            recommendations='Older rabies recommendation',
            created_by=self.employee_a.user,
            next_date=timezone.localdate(self.reference_time) + timedelta(days=30),
        )
        latest_record = VisitRecord.objects.create(
            pet=self.pet_one,
            provider=self.provider,
            provider_location=self.location_a,
            service=self.rabies_service,
            employee=self.employee_a,
            date=self.reference_time - timedelta(days=365),
            description='Latest rabies record',
            recommendations='Latest rabies recommendation',
            created_by=self.employee_a.user,
            next_date=timezone.localdate(self.reference_time) + timedelta(days=365),
        )

        self.pet_one.refresh_from_db()
        self.assertEqual(self.pet_one.rabies_vaccination_expiry, latest_record.next_date)

        older_record.next_date = timezone.localdate(self.reference_time) + timedelta(days=14)
        older_record.save()

        self.pet_one.refresh_from_db()
        self.assertEqual(self.pet_one.rabies_vaccination_expiry, latest_record.next_date)

    def test_celery_beat_includes_periodic_procedure_task(self):
        """
        Рабочий celery beat содержит ежедневную задачу periodic reminders.
        """
        beat_entry = celery_app.conf.beat_schedule['process-periodic-procedure-reminders']
        self.assertEqual(beat_entry['task'], 'notifications.tasks.process_reminders_task')


class PetCreationVaccinationExpiryReminderTests(BookingFlowBaseMixin, TestCase):
    """
    Тесты покрытия reminder при создании питомца с expiry-полями.
    """

    def setUp(self):
        super().setUp()
        self.factory = APIRequestFactory()
        self.reference_time = timezone.make_aware(
            datetime.combine(timezone.localdate(), time(hour=9, minute=0)),
            timezone.get_current_timezone(),
        )
        self.rabies_service = Service.objects.create(
            code='vaccination_rabies',
            name='Vaccination: Rabies',
            is_periodic=True,
            period_days=365,
            send_reminders=True,
            reminder_days_before=30,
            is_client_facing=True,
        )
        self.rabies_service.allowed_pet_types.add(self.pet_type)

    @patch('notifications.services.send_mail', return_value=1)
    def test_pet_created_with_vaccination_expiry_is_covered_by_reminder_flow(self, mocked_send_mail):
        """
        Если при создании питомца передан срок действия прививки, reminder flow его подхватывает.
        """
        request = self.factory.post('/api/v1/pets/')
        request.user = self.owner
        serializer = PetSerializer(
            data={
                'name': 'Expiry Flow Pet',
                'pet_type': self.pet_type.id,
                'breed': self.breed.id,
                'weight': '7.5',
                'rabies_vaccination_expiry': (
                    timezone.localdate(self.reference_time) + timedelta(days=30)
                ).isoformat(),
            },
            context={'request': request},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        pet = serializer.save()

        result = process_reminders_task(reference_time=self.reference_time)

        self.assertEqual(result['sent_count'], 1)
        self.assertTrue(
            Notification.objects.filter(
                pet=pet,
                data__reminder_source='pet_vaccination_expiry',
                data__pet_expiry_field='rabies_vaccination_expiry',
            ).exists()
        )
        mocked_send_mail.assert_called_once()


class PeriodicProcedureReminderSetupCommandTests(TestCase):
    """
    Тесты idempotent-команды подготовки demo-данных.
    """

    def setUp(self):
        self.dog_type = PetType.objects.create(
            name='Dog',
            code='dog',
        )
        self.cat_type = PetType.objects.create(
            name='Cat',
            code='cat',
        )

        self.rabies_service = Service.objects.create(
            code='vaccination_rabies',
            name='Vaccination: Rabies',
            is_periodic=True,
            period_days=365,
            send_reminders=True,
            reminder_days_before=30,
            is_client_facing=True,
        )
        self.rabies_service.allowed_pet_types.add(self.dog_type, self.cat_type)

        self.complex_service = Service.objects.create(
            code='vaccination_complex',
            name='Vaccination: Complex',
            is_periodic=True,
            period_days=365,
            send_reminders=True,
            reminder_days_before=14,
            is_client_facing=True,
        )
        self.complex_service.allowed_pet_types.add(self.dog_type)

        self.deworming_service = Service.objects.create(
            code='deworming',
            name='Deworming',
            is_periodic=True,
            period_days=90,
            send_reminders=True,
            reminder_days_before=5,
            is_client_facing=True,
        )
        self.deworming_service.allowed_pet_types.add(self.cat_type)

    def test_setup_command_is_idempotent(self):
        """
        Команда создает demo owner/pet/visit record без дублей при повторном запуске.
        """
        call_command('setup_periodic_procedure_reminders')
        call_command('setup_periodic_procedure_reminders')

        self.assertEqual(NotificationType.objects.filter(code='reminder').count(), 1)
        self.assertEqual(
            User.objects.filter(email__startswith='periodic-reminder-owner-').count(),
            3,
        )
        self.assertEqual(
            VisitRecord.objects.filter(
                description='Periodic reminder MVP demo record',
                next_date__isnull=False,
            ).count(),
            3,
        )
