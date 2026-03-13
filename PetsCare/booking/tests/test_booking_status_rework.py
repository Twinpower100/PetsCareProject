from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIRequestFactory

from booking.constants import (
    BOOKING_STATUS_CANCELLED,
    BOOKING_STATUS_COMPLETED,
    CANCELLED_BY_PROVIDER,
    CANCELLATION_REASON_CLIENT_NO_SHOW,
    CLIENT_ATTENDANCE_ARRIVED,
    CLIENT_ATTENDANCE_NO_SHOW,
    COMPLETED_BY_SYSTEM,
    COMPLETED_BY_USER,
    COMPLETION_REASON_AUTO_TIMEOUT,
)
from booking.models import (
    BookingAutoCompleteSettings,
    BookingCancellationReason,
    BookingPayment,
    BookingReview,
)
from booking.serializers import BookingSerializer
from booking.services import BookingCompletionService
from booking.test_booking_flow_logic import BookingFlowBaseMixin
from pets.models import ChronicCondition, PetDocument, PetHealthNote, VisitRecord, VisitRecordAddendum


class BookingStatusReworkAPITests(BookingFlowBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.owner.add_role('pet_owner')
        self.employee_a.user.add_role('employee')
        self.provider_unavailable = BookingCancellationReason.objects.get(code='provider_unavailable')
        self.client_no_show = BookingCancellationReason.objects.get(code=CANCELLATION_REASON_CLIENT_NO_SHOW)
        self.client_changed_mind = BookingCancellationReason.objects.get(code='changed_mind')

    def _create_past_booking(self):
        start_time = timezone.now() - timedelta(hours=3)
        return self._create_booking(
            pet=self.pet_one,
            location=self.location_a,
            employee=self.employee_a,
            start_time=start_time,
        )

    def _action_url(self, booking_id, action):
        return f'/api/v1/bookings/{booking_id}/{action}/'

    def test_provider_can_cancel_after_end_time(self):
        booking = self._create_past_booking()
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.post(
            self._action_url(booking.id, 'cancel_by_provider'),
            {
                'reason_code': self.provider_unavailable.code,
                'reason_text': 'Service equipment failed',
                'client_attendance': CLIENT_ATTENDANCE_ARRIVED,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, BOOKING_STATUS_CANCELLED)
        self.assertEqual(booking.cancelled_by, CANCELLED_BY_PROVIDER)
        self.assertEqual(booking.cancellation_reason.code, self.provider_unavailable.code)
        self.assertEqual(booking.client_attendance, CLIENT_ATTENDANCE_ARRIVED)

    def test_client_cannot_cancel_after_end_time(self):
        booking = self._create_past_booking()
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            self._action_url(booking.id, 'cancel_by_client'),
            {'reason_code': self.client_changed_mind.code},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'active')

    def test_provider_no_show_is_cancelled_with_reason_and_attendance(self):
        booking = self._create_past_booking()
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.post(
            self._action_url(booking.id, 'mark_no_show_by_client'),
            {'reason_text': 'Client never arrived'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, BOOKING_STATUS_CANCELLED)
        self.assertEqual(booking.cancelled_by, CANCELLED_BY_PROVIDER)
        self.assertEqual(booking.cancellation_reason.code, self.client_no_show.code)
        self.assertEqual(booking.client_attendance, CLIENT_ATTENDANCE_NO_SHOW)

    def test_manual_completion_after_end_time_is_allowed(self):
        booking = self._create_past_booking()
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.post(
            self._action_url(booking.id, 'complete'),
            {'employee_comment': 'done'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, BOOKING_STATUS_COMPLETED)
        self.assertEqual(booking.completed_by_actor, COMPLETED_BY_USER)
        self.assertEqual(booking.completed_by_user, self.employee_a.user)

    def test_manual_completion_before_start_time_is_rejected(self):
        future_booking = self._create_booking(
            pet=self.pet_one,
            location=self.location_a,
            employee=self.employee_a,
            start_time=timezone.now() + timedelta(hours=2),
        )
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.post(
            self._action_url(future_booking.id, 'complete'),
            {'employee_comment': 'premature'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        future_booking.refresh_from_db()
        self.assertEqual(future_booking.status.name, 'active')
        self.assertIn('error', response.data)

    def test_completion_can_create_pet_record_entry(self):
        booking = self._create_past_booking()
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.post(
            self._action_url(booking.id, 'complete'),
            {
                'visit_record': {
                    'anamnesis': 'Owner reports low appetite',
                    'diagnosis': 'Stress reaction',
                    'results': 'Stabilized during visit',
                    'recommendations': 'Observe for 48 hours',
                    'notes': 'Follow-up if symptoms continue',
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        record = VisitRecord.objects.get(pet=booking.pet, service=booking.service, created_by=self.employee_a.user)
        self.assertEqual(booking.status.name, BOOKING_STATUS_COMPLETED)
        self.assertEqual(booking.visit_record_id, record.id)
        self.assertEqual(record.anamnesis, 'Owner reports low appetite')
        self.assertEqual(record.diagnosis, 'Stress reaction')
        self.assertEqual(record.results, 'Stabilized during visit')
        self.assertEqual(record.recommendations, 'Observe for 48 hours')
        self.assertEqual(record.notes, 'Follow-up if symptoms continue')

    def test_completion_accepts_legacy_pet_record_alias(self):
        booking = self._create_past_booking()
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.post(
            self._action_url(booking.id, 'complete'),
            {
                'pet_record': {
                    'description': 'Legacy alias payload',
                    'results': 'Completed successfully',
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertIsNotNone(booking.visit_record_id)
        self.assertEqual(booking.visit_record.description, 'Legacy alias payload')
        self.assertEqual(booking.visit_record.results, 'Completed successfully')

    def test_completed_booking_can_save_visit_record_postfactum(self):
        booking = self._create_past_booking()
        booking.complete_booking(self.employee_a.user)
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.patch(
            self._action_url(booking.id, 'visit_record'),
            {
                'description': 'Late follow-up summary',
                'results': 'Stable after discharge',
                'recommendations': 'Control visit in two weeks',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertIsNotNone(booking.visit_record_id)
        self.assertEqual(booking.visit_record.description, 'Late follow-up summary')
        self.assertEqual(booking.visit_record.results, 'Stable after discharge')

    def test_completed_booking_can_update_existing_linked_visit_record(self):
        booking = self._create_past_booking()
        booking.complete_booking(self.employee_a.user)
        linked_record = VisitRecord.objects.create(
            pet=booking.pet,
            provider=booking.provider,
            provider_location=booking.provider_location,
            service=booking.service,
            employee=booking.employee,
            date=booking.completed_at,
            description='Initial summary',
            recommendations='Initial recommendations',
            created_by=self.employee_a.user,
        )
        booking.visit_record = linked_record
        booking.save(update_fields=['visit_record', 'updated_at'])
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.patch(
            self._action_url(booking.id, 'visit_record'),
            {
                'description': 'Updated summary',
                'recommendations': 'Updated recommendations',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        linked_record.refresh_from_db()
        self.assertEqual(linked_record.description, 'Updated summary')
        self.assertEqual(linked_record.recommendations, 'Updated recommendations')

    def test_completed_booking_can_create_visit_record_addendum(self):
        booking = self._create_past_booking()
        booking.complete_booking(self.employee_a.user)
        linked_record = VisitRecord.objects.create(
            pet=booking.pet,
            provider=booking.provider,
            provider_location=booking.provider_location,
            service=booking.service,
            employee=booking.employee,
            date=booking.completed_at,
            description='Initial summary',
            created_by=self.employee_a.user,
        )
        booking.visit_record = linked_record
        booking.save(update_fields=['visit_record', 'updated_at'])
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.post(
            self._action_url(booking.id, 'visit-record-addenda'),
            {'content': 'Late clinical clarification'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        linked_record.refresh_from_db()
        self.assertEqual(linked_record.addenda.count(), 1)
        self.assertEqual(linked_record.addenda.first().content, 'Late clinical clarification')
        self.assertEqual(response.data['author'], self.employee_a.user.id)

    @patch('pets.models.VisitRecord.objects.create')
    def test_completion_visit_record_failure_returns_business_error(self, mocked_create):
        booking = self._create_past_booking()
        self.client.force_authenticate(self.employee_a.user)
        mocked_create.side_effect = IntegrityError('fk mismatch')

        response = self.client.post(
            self._action_url(booking.id, 'complete'),
            {
                'visit_record': {
                    'description': 'Completed service',
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data['code']), 'visit_record_save_failed')
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'active')

    def test_cancellation_requires_reason_code(self):
        booking = self._create_past_booking()
        future_booking = booking
        future_booking.start_time = timezone.now() + timedelta(hours=2)
        future_booking.end_time = future_booking.start_time + timedelta(hours=1)
        future_booking.save(update_fields=['start_time', 'end_time', 'updated_at'])
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            self._action_url(future_booking.id, 'cancel_by_client'),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('reason_code', response.data)

    def test_detail_endpoint_returns_compact_but_complete_payload(self):
        booking = self._create_past_booking()
        self.client.force_authenticate(self.employee_a.user)

        self.service.name_ru = 'Груминг'
        self.service.save(update_fields=['name_ru', 'updated_at'])
        self.pet_type.name_ru = 'Собака'
        self.pet_type.save(update_fields=['name_ru'])

        condition = ChronicCondition.objects.create(
            code='arthritis',
            name='Arthritis',
            name_ru='Артрит',
            category=ChronicCondition.CATEGORY_ORTHOPAEDIC,
        )
        booking.pet.chronic_conditions.add(condition)

        PetHealthNote.objects.create(
            pet=booking.pet,
            date=timezone.localdate() - timedelta(days=1),
            title='Checkup',
            description='General examination',
        )
        VisitRecord.objects.create(
            pet=booking.pet,
            provider=booking.provider,
            provider_location=booking.provider_location,
            service=booking.service,
            employee=booking.employee,
            date=timezone.now() - timedelta(days=2),
            description='Performed grooming',
            results='All good',
            recommendations='Repeat next month',
            created_by=self.employee_a.user,
        )
        BookingPayment.objects.create(
            booking=booking,
            amount=booking.price,
            payment_method='cash',
            transaction_id='pay-1',
        )
        BookingReview.objects.create(
            booking=booking,
            rating=5,
            comment='Excellent',
        )

        response = self.client.get(
            f'/api/v1/bookings/{booking.id}/',
            HTTP_ACCEPT_LANGUAGE='ru',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data
        self.assertEqual(payload['service']['name_display'], 'Груминг')
        self.assertEqual(payload['pet']['pet_type_name'], 'Собака')
        self.assertEqual(payload['pet']['chronic_conditions'][0]['name_display'], 'Артрит')
        self.assertEqual(payload['pet']['health_notes'][0]['title'], 'Checkup')
        self.assertEqual(payload['pet']['visit_records'][0]['service_name'], 'Груминг')
        self.assertIsNone(payload['visit_record'])
        self.assertEqual(payload['payment']['payment_method'], 'cash')
        self.assertEqual(payload['review']['rating'], 5)
        self.assertNotIn('services', payload['provider'])
        self.assertNotIn('employees', payload['provider'])
        self.assertNotIn('providers', payload['employee'])
        self.assertNotIn('access_list', payload['pet'])

    def test_detail_endpoint_returns_linked_visit_record(self):
        booking = self._create_past_booking()
        linked_record = VisitRecord.objects.create(
            pet=booking.pet,
            provider=booking.provider,
            provider_location=booking.provider_location,
            service=booking.service,
            employee=booking.employee,
            date=timezone.now() - timedelta(minutes=5),
            description='Linked summary',
            diagnosis='Linked diagnosis',
            created_by=self.employee_a.user,
        )
        PetDocument.objects.create(
            file=SimpleUploadedFile('visit-summary.pdf', b'%PDF-1.4 summary', content_type='application/pdf'),
            name='Visit summary',
            pet=booking.pet,
            visit_record=linked_record,
            uploaded_by=self.employee_a.user,
        )
        VisitRecordAddendum.objects.create(
            visit_record=linked_record,
            author=self.employee_a.user,
            content='Late note',
        )
        booking.complete_booking(self.employee_a.user)
        booking.visit_record = linked_record
        booking.save(update_fields=['visit_record', 'updated_at'])
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.get(f'/api/v1/bookings/{booking.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['visit_record']['id'], linked_record.id)
        self.assertEqual(response.data['pet_record']['id'], linked_record.id)
        self.assertEqual(response.data['visit_record']['documents'][0]['name'], 'Visit summary')
        self.assertEqual(response.data['visit_record']['addenda'][0]['content'], 'Late note')

    def test_detail_endpoint_exposes_legacy_pet_medical_card_aliases(self):
        booking = self._create_past_booking()
        self.client.force_authenticate(self.employee_a.user)

        health_note = PetHealthNote.objects.create(
            pet=booking.pet,
            date=timezone.localdate() - timedelta(days=1),
            title='External note',
            description='Legacy note alias',
        )
        visit_record = VisitRecord.objects.create(
            pet=booking.pet,
            provider=booking.provider,
            provider_location=booking.provider_location,
            service=booking.service,
            employee=booking.employee,
            date=timezone.now() - timedelta(days=2),
            description='Legacy record alias',
            created_by=self.employee_a.user,
        )

        response = self.client.get(f'/api/v1/bookings/{booking.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['pet']['medical_records'][0]['id'], health_note.id)
        self.assertEqual(response.data['pet']['records'][0]['id'], visit_record.id)


class BookingStatusReworkDomainTests(BookingFlowBaseMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.employee_a.user.add_role('employee')
        self.provider_unavailable = BookingCancellationReason.objects.get(code='provider_unavailable')

    def _past_booking(self, *, days_ago=1):
        start_time = timezone.now() - timedelta(days=days_ago, hours=2)
        return self._create_booking(
            pet=self.pet_one,
            location=self.location_a,
            employee=self.employee_a,
            start_time=start_time,
        )

    def test_auto_completion_records_system_actor(self):
        booking = self._past_booking(days_ago=10)
        settings = BookingAutoCompleteSettings.get_settings()
        settings.auto_complete_days = 3
        settings.save(update_fields=['auto_complete_days', 'updated_at'])

        completed_count = BookingCompletionService.auto_complete_bookings()

        self.assertEqual(completed_count, 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, BOOKING_STATUS_COMPLETED)
        self.assertEqual(booking.completed_by_actor, COMPLETED_BY_SYSTEM)
        self.assertIsNone(booking.completed_by_user)
        self.assertEqual(booking.completion_reason_code, COMPLETION_REASON_AUTO_TIMEOUT)

    def test_serializer_exposes_ui_and_cancellation_metadata(self):
        booking = self._past_booking()
        booking.cancel_booking(
            cancelled_by=CANCELLED_BY_PROVIDER,
            cancelled_by_user=self.employee_a.user,
            cancellation_reason=self.provider_unavailable,
            cancellation_reason_text='Operational issue',
            client_attendance=CLIENT_ATTENDANCE_ARRIVED,
        )

        payload = BookingSerializer(booking).data

        self.assertEqual(payload['status_code'], BOOKING_STATUS_CANCELLED)
        self.assertEqual(payload['ui_status']['code'], 'cancelled_by_provider')
        self.assertEqual(payload['cancellation_reason']['code'], self.provider_unavailable.code)
        self.assertEqual(payload['client_attendance'], CLIENT_ATTENDANCE_ARRIVED)
        self.assertFalse(payload['is_overdue'])

    def test_serializer_localizes_nested_service_and_pet_type_names(self):
        booking = self._past_booking()
        self.service.name_ru = 'Груминг'
        self.service.save(update_fields=['name_ru', 'updated_at'])
        self.pet_type.name_ru = 'Собака'
        self.pet_type.save(update_fields=['name_ru'])

        request = APIRequestFactory().get('/api/v1/bookings/', HTTP_ACCEPT_LANGUAGE='ru')
        payload = BookingSerializer(booking, context={'request': request}).data

        self.assertEqual(payload['service']['name_display'], 'Груминг')
        self.assertEqual(payload['pet']['pet_type_name'], 'Собака')

    def test_cancelled_booking_cannot_be_completed(self):
        booking = self._past_booking()
        booking.cancel_booking(
            cancelled_by=CANCELLED_BY_PROVIDER,
            cancelled_by_user=self.employee_a.user,
            cancellation_reason=self.provider_unavailable,
            client_attendance=CLIENT_ATTENDANCE_ARRIVED,
        )

        with self.assertRaisesMessage(ValueError, 'Cannot complete cancelled booking'):
            booking.complete_booking(self.employee_a.user)

    def test_future_booking_cannot_be_completed(self):
        future_booking = self._create_booking(
            pet=self.pet_one,
            location=self.location_a,
            employee=self.employee_a,
            start_time=timezone.now() + timedelta(hours=2),
        )

        with self.assertRaisesMessage(ValueError, 'before start time'):
            future_booking.complete_booking(self.employee_a.user)
