from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from booking.test_booking_flow_logic import BookingFlowBaseMixin
from pets.models import PetDocument, PetHealthNote, VisitRecord, VisitRecordAddendum


def _extract_results(payload):
    return payload if isinstance(payload, list) else payload.get('results', [])


class PetMedicalCardAPITests(BookingFlowBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.employee_a.user.add_role('employee')
        self.visit_record = VisitRecord.objects.create(
            pet=self.pet_one,
            provider=self.provider,
            provider_location=self.location_a,
            service=self.service,
            employee=self.employee_a,
            date=timezone.now() - timedelta(days=1),
            description='Visit summary',
            results='Stable',
            created_by=self.employee_a.user,
        )
        VisitRecordAddendum.objects.create(
            visit_record=self.visit_record,
            author=self.employee_a.user,
            content='Late clarification',
        )
        self.visit_document = PetDocument.objects.create(
            file=SimpleUploadedFile('visit.pdf', b'%PDF-1.4 visit', content_type='application/pdf'),
            name='Visit PDF',
            pet=self.pet_one,
            visit_record=self.visit_record,
            uploaded_by=self.employee_a.user,
        )
        self.owner_document = PetDocument.objects.create(
            file=SimpleUploadedFile('owner.pdf', b'%PDF-1.4 owner', content_type='application/pdf'),
            name='Owner lab result',
            pet=self.pet_one,
            uploaded_by=self.owner,
        )
        self.health_note = PetHealthNote.objects.create(
            pet=self.pet_one,
            date=timezone.localdate() - timedelta(days=2),
            title='External lab',
            description='Uploaded by owner',
        )

    def _url(self, pet_id):
        return f'/api/v1/pets/{pet_id}/medical-card/'

    def test_owner_sees_full_medical_card(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(self._url(self.pet_one.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['visit_records']), 1)
        self.assertEqual(len(response.data['health_notes']), 1)
        self.assertEqual(len(response.data['documents']), 2)
        self.assertEqual(response.data['visit_records'][0]['documents'][0]['name'], 'Visit PDF')
        self.assertEqual(response.data['visit_records'][0]['addenda'][0]['content'], 'Late clarification')

    def test_base_pet_detail_stays_lightweight(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(f'/api/v1/pets/{self.pet_one.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('visit_records', response.data)
        self.assertNotIn('health_notes', response.data)
        self.assertNotIn('documents', response.data)

    def test_base_pet_list_stays_lightweight(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get('/api/v1/pets/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _extract_results(response.data)
        pet_payload = next(item for item in results if item['id'] == self.pet_one.id)
        self.assertNotIn('visit_records', pet_payload)
        self.assertNotIn('health_notes', pet_payload)
        self.assertNotIn('documents', pet_payload)

    def test_employee_sees_only_visit_scoped_history_and_documents(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.get(self._url(self.pet_one.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['visit_records']), 1)
        self.assertEqual(response.data['health_notes'], [])
        self.assertEqual(len(response.data['documents']), 1)
        self.assertEqual(response.data['documents'][0]['name'], 'Visit PDF')

    def test_canonical_visit_records_endpoint_is_read_only(self):
        self.client.force_authenticate(self.owner)

        list_response = self.client.get(f'/api/v1/visit-records/?pet={self.pet_one.id}')
        patch_response = self.client.patch(
            f'/api/v1/visit-records/{self.visit_record.id}/',
            {'description': 'Mutated'},
            format='json',
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        results = _extract_results(list_response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.visit_record.id)
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class PetDocumentAPITests(BookingFlowBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.employee_a.user.add_role('employee')
        self.visit_record = VisitRecord.objects.create(
            pet=self.pet_one,
            provider=self.provider,
            provider_location=self.location_a,
            service=self.service,
            employee=self.employee_a,
            date=timezone.now() - timedelta(days=1),
            description='Visit summary',
            created_by=self.employee_a.user,
        )
        self.owner_document = PetDocument.objects.create(
            file=SimpleUploadedFile('owner-private.pdf', b'%PDF-1.4 owner', content_type='application/pdf'),
            name='Owner private document',
            pet=self.pet_one,
            uploaded_by=self.owner,
        )
        self.visit_document = PetDocument.objects.create(
            file=SimpleUploadedFile('visit-linked.pdf', b'%PDF-1.4 visit', content_type='application/pdf'),
            name='Visit linked document',
            pet=self.pet_one,
            visit_record=self.visit_record,
            uploaded_by=self.employee_a.user,
        )
        self.health_note = PetHealthNote.objects.create(
            pet=self.pet_one,
            date=timezone.localdate() - timedelta(days=3),
            title='Owner note',
            description='External recommendation',
        )

    def _documents_url(self, pet_id):
        return f'/api/v1/pets/{pet_id}/documents/'

    def _health_notes_url(self, pet_id):
        return f'/api/v1/pets/{pet_id}/health-notes/'

    def _download_url(self, document_id):
        return f'/api/v1/documents/{document_id}/download/'

    def test_owner_can_upload_standalone_document_via_canonical_endpoint(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            self._documents_url(self.pet_one.id),
            {
                'file': SimpleUploadedFile('standalone.pdf', b'%PDF-1.4 standalone', content_type='application/pdf'),
                'name': 'Standalone owner document',
                'description': 'Owner upload',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = PetDocument.objects.get(id=response.data['id'])
        self.assertEqual(created.pet_id, self.pet_one.id)
        self.assertIsNone(created.visit_record_id)

    def test_owner_can_upload_document_for_specific_visit_record(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            self._documents_url(self.pet_one.id),
            {
                'file': SimpleUploadedFile('legacy-upload.pdf', b'%PDF-1.4 legacy', content_type='application/pdf'),
                'name': 'Visit upload',
                'visit_record': self.visit_record.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        document = PetDocument.objects.get(id=response.data['id'])
        self.assertEqual(document.visit_record_id, self.visit_record.id)

    def test_owner_cannot_upload_word_document_via_canonical_endpoint(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            self._documents_url(self.pet_one.id),
            {
                'file': SimpleUploadedFile(
                    'notes.docx',
                    b'PK\x03\x04 fake-docx',
                    content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                ),
                'name': 'Unsupported office file',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('file', response.data)

    def test_owner_can_create_health_note_via_canonical_endpoint(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            self._health_notes_url(self.pet_one.id),
            {
                'date': str(timezone.localdate()),
                'title': 'Diet note',
                'description': 'Switch to hypoallergenic food',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(PetHealthNote.objects.filter(id=response.data['id'], pet=self.pet_one).exists())

    def test_employee_cannot_download_owner_private_document_without_visit_link(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.get(self._download_url(self.owner_document.id))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_can_download_visit_linked_document(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.get(self._download_url(self.visit_document.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_canonical_pet_documents_endpoint_lists_only_accessible_documents(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.get(f'/api/v1/pet-documents/?pet={self.pet_one.id}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _extract_results(response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.visit_document.id)

    def test_legacy_medical_records_endpoint_still_supports_attachment_uploads(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            '/api/v1/medical-records/',
            {
                'pet': self.pet_one.id,
                'date': str(timezone.localdate()),
                'title': 'Legacy external lab',
                'description': 'Legacy payload still works',
                'attachments': SimpleUploadedFile(
                    'legacy-lab.pdf',
                    b'%PDF-1.4 legacy-lab',
                    content_type='application/pdf',
                ),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response['Deprecation'], 'true')
        created_note = PetHealthNote.objects.get(id=response.data['id'])
        self.assertTrue(created_note.documents.exists())
        self.assertIsNotNone(response.data['attachments'])

    def test_legacy_pet_records_endpoint_still_lists_files(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(f'/api/v1/pet-records/?pet={self.pet_one.id}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Deprecation'], 'true')
        results = _extract_results(response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['files'], [self.visit_document.id])

    def test_legacy_records_upload_endpoint_still_creates_visit_document(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            f'/api/v1/records/{self.visit_record.id}/upload_file/',
            {
                'file': SimpleUploadedFile(
                    'legacy-record.pdf',
                    b'%PDF-1.4 legacy-record',
                    content_type='application/pdf',
                ),
                'name': 'Legacy record upload',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response['Deprecation'], 'true')
        document = PetDocument.objects.get(id=response.data['id'])
        self.assertEqual(document.visit_record_id, self.visit_record.id)
        self.assertEqual(response.data['pet_record'], self.visit_record.id)
