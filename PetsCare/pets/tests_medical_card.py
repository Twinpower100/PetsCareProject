from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from booking.test_booking_flow_logic import BookingFlowBaseMixin
from pets.models import DocumentType, PetDocument, PetHealthNote, PetOwner, VisitRecord, VisitRecordAddendum


def _extract_results(payload):
    return payload if isinstance(payload, list) else payload.get('results', [])


def _data_dict(response):
    """Возвращает response.data как dict для assertIn/assertNotIn и доступа по ключу."""
    assert isinstance(response.data, dict)
    return response.data


class PetMedicalCardAPITests(BookingFlowBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.employee_a.user.add_role('employee')
        self.passport_type = DocumentType.objects.get(code='passport_identification')
        self.lab_results_type = DocumentType.objects.get(code='lab_results')
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
        self.addendum = VisitRecordAddendum.objects.create(
            visit_record=self.visit_record,
            author=self.employee_a.user,
            content='Late clarification',
        )
        self.visit_document = PetDocument.objects.create(
            file=SimpleUploadedFile('visit.pdf', b'%PDF-1.4 visit', content_type='application/pdf'),
            name='Visit PDF',
            pet=self.pet_one,
            document_type=self.lab_results_type,
            visit_record=self.visit_record,
            issue_date=timezone.localdate() - timedelta(days=1),
            uploaded_by=self.employee_a.user,
        )
        self.addendum_document = PetDocument.objects.create(
            file=SimpleUploadedFile('addendum.pdf', b'%PDF-1.4 addendum', content_type='application/pdf'),
            name='Addendum PDF',
            pet=self.pet_one,
            document_type=self.lab_results_type,
            visit_record_addendum=self.addendum,
            issue_date=timezone.localdate() - timedelta(days=1),
            uploaded_by=self.employee_a.user,
        )
        self.owner_document = PetDocument.objects.create(
            file=SimpleUploadedFile('owner.pdf', b'%PDF-1.4 owner', content_type='application/pdf'),
            name='Owner lab result',
            pet=self.pet_one,
            document_type=self.passport_type,
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
        data = _data_dict(response)
        self.assertEqual(len(data['visit_records']), 1)
        self.assertEqual(len(data['health_notes']), 1)
        self.assertEqual(len(data['documents']), 3)
        self.assertEqual(data['visit_records'][0]['documents'][0]['name'], 'Visit PDF')
        self.assertEqual(data['visit_records'][0]['addenda'][0]['content'], 'Late clarification')
        self.assertEqual(
            data['visit_records'][0]['addenda'][0]['documents'][0]['name'],
            'Addendum PDF',
        )

    def test_base_pet_detail_stays_lightweight(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(f'/api/v1/pets/{self.pet_one.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = _data_dict(response)
        self.assertNotIn('visit_records', data)
        self.assertNotIn('health_notes', data)
        self.assertNotIn('documents', data)

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
        data = _data_dict(response)
        self.assertEqual(len(data['visit_records']), 1)
        self.assertEqual(data['health_notes'], [])
        self.assertEqual(len(data['documents']), 2)
        self.assertEqual(
            {item['name'] for item in data['documents']},
            {'Visit PDF', 'Addendum PDF'},
        )

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

    def test_visit_record_detail_exposes_addendum_documents(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.get(f'/api/v1/visit-records/{self.visit_record.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data: dict = response.data  # type: ignore[assignment]
        self.assertEqual(data['addenda'][0]['documents'][0]['id'], self.addendum_document.id)


class PetDocumentAPITests(BookingFlowBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.employee_a.user.add_role('employee')
        self.coowner = self.owner.__class__.objects.create_user(
            email='coowner@example.com',
            password='password123',
            username='coowner_user',
            phone_number='+38267000003',
        )
        PetOwner.objects.create(pet=self.pet_one, user=self.coowner, role='coowner')
        self.today = timezone.localdate()
        self.passport_type = DocumentType.objects.get(code='passport_identification')
        self.lab_results_type = DocumentType.objects.get(code='lab_results')
        self.discharge_type = DocumentType.objects.get(code='discharge_doctor_orders')
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
        self.addendum = VisitRecordAddendum.objects.create(
            visit_record=self.visit_record,
            author=self.employee_a.user,
            content='Late clarification',
        )
        self.owner_document = PetDocument.objects.create(
            file=SimpleUploadedFile('owner-private.pdf', b'%PDF-1.4 owner', content_type='application/pdf'),
            name='Owner private document',
            pet=self.pet_one,
            document_type=self.passport_type,
            uploaded_by=self.owner,
        )
        self.visit_document = PetDocument.objects.create(
            file=SimpleUploadedFile('visit-linked.pdf', b'%PDF-1.4 visit', content_type='application/pdf'),
            name='Visit linked document',
            pet=self.pet_one,
            document_type=self.lab_results_type,
            visit_record=self.visit_record,
            issue_date=self.today - timedelta(days=1),
            uploaded_by=self.employee_a.user,
        )
        self.health_note = PetHealthNote.objects.create(
            pet=self.pet_one,
            date=self.today - timedelta(days=3),
            title='Owner note',
            description='External recommendation',
        )

    def _documents_url(self, pet_id):
        return f'/api/v1/pets/{pet_id}/documents/'

    def _detail_url(self, document_id):
        return f'/api/v1/pet-documents/{document_id}/'

    def _deactivate_url(self, document_id):
        return f'/api/v1/pet-documents/{document_id}/deactivate/'

    def _withdraw_url(self, document_id):
        return f'/api/v1/pet-documents/{document_id}/withdraw/'

    def _health_notes_url(self, pet_id):
        return f'/api/v1/pets/{pet_id}/health-notes/'

    def _download_url(self, document_id):
        return f'/api/v1/documents/{document_id}/download/'

    def _preview_url(self, document_id):
        return f'/api/v1/documents/{document_id}/preview/'

    def test_owner_can_create_pet_card_document_via_canonical_endpoint(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            self._documents_url(self.pet_one.id),
            {
                'file': SimpleUploadedFile('standalone.pdf', b'%PDF-1.4 standalone', content_type='application/pdf'),
                'document_type': self.passport_type.id,
                'description': 'Owner upload',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = _data_dict(response)
        created = PetDocument.objects.get(id=data['id'])
        self.assertEqual(created.pet_id, self.pet_one.id)
        self.assertIsNone(created.visit_record_id)
        self.assertEqual(created.document_type_id, self.passport_type.id)
        self.assertEqual(created.name, 'standalone.pdf')
        self.assertEqual(data['management_context'], 'owner_pet_card')
        self.assertEqual(data['lifecycle_status'], 'active')

    def test_owner_cannot_create_visit_linked_document_via_canonical_endpoint(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            self._documents_url(self.pet_one.id),
            {
                'file': SimpleUploadedFile('legacy-upload.pdf', b'%PDF-1.4 legacy', content_type='application/pdf'),
                'document_type': self.lab_results_type.id,
                'visit_record': self.visit_record.id,
                'issue_date': str(self.today),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = _data_dict(response)
        self.assertIn('visit_record', data)

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
                'document_type': self.passport_type.id,
                'name': 'Unsupported office file',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = _data_dict(response)
        self.assertIn('file', data)

    def test_owner_can_update_pet_card_document_metadata(self):
        self.client.force_authenticate(self.owner)

        response = self.client.patch(
            self._detail_url(self.owner_document.id),
            {
                'name': 'Updated owner document',
                'description': 'Updated metadata',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.owner_document.refresh_from_db()
        self.assertEqual(self.owner_document.name, 'Updated owner document')
        self.assertEqual(self.owner_document.description, 'Updated metadata')
        self.assertEqual(self.owner_document.version, 2)

    def test_coowner_can_deactivate_owner_space_document(self):
        self.client.force_authenticate(self.coowner)

        response = self.client.post(
            self._deactivate_url(self.owner_document.id),
            {
                'reason_code': 'owner_request',
                'reason_comment': 'Hidden from active owner flows',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.owner_document.refresh_from_db()
        self.assertEqual(self.owner_document.lifecycle_status, PetDocument.STATUS_DEACTIVATED)
        self.assertEqual(self.owner_document.deactivated_by_id, self.coowner.id)
        self.assertEqual(self.owner_document.lifecycle_reason_code, 'owner_request')

    def test_inactive_documents_are_hidden_by_default_and_available_via_flag(self):
        self.client.force_authenticate(self.owner)
        deactivate_response = self.client.post(
            self._deactivate_url(self.owner_document.id),
            {'reason_code': 'duplicate'},
            format='json',
        )
        self.assertEqual(deactivate_response.status_code, status.HTTP_200_OK)

        default_response = self.client.get(self._documents_url(self.pet_one.id))
        all_response = self.client.get(
            self._documents_url(self.pet_one.id),
            {'include_inactive': 'true'},
        )

        self.assertEqual(default_response.status_code, status.HTTP_200_OK)
        self.assertEqual(all_response.status_code, status.HTTP_200_OK)
        default_ids = {item['id'] for item in default_response.data}
        all_ids = {item['id'] for item in all_response.data}
        self.assertNotIn(self.owner_document.id, default_ids)
        self.assertIn(self.owner_document.id, all_ids)

    def test_provider_can_create_visit_linked_document_via_canonical_endpoint(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.post(
            self._documents_url(self.pet_one.id),
            {
                'file': SimpleUploadedFile('provider-lab.pdf', b'%PDF-1.4 lab', content_type='application/pdf'),
                'document_type': self.lab_results_type.id,
                'visit_record': self.visit_record.id,
                'issue_date': str(self.today),
                'description': 'Provider upload',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = _data_dict(response)
        created = PetDocument.objects.get(id=data['id'])
        self.assertEqual(created.visit_record_id, self.visit_record.id)
        self.assertEqual(created.uploaded_by_id, self.employee_a.user.id)
        self.assertEqual(data['management_context'], 'provider_visit')
        self.assertEqual(data['document_type_code'], 'lab_results')

    def test_provider_can_create_addendum_linked_document_via_canonical_endpoint(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.post(
            self._documents_url(self.pet_one.id),
            {
                'file': SimpleUploadedFile('provider-addendum.pdf', b'%PDF-1.4 addendum', content_type='application/pdf'),
                'document_type': self.lab_results_type.id,
                'visit_record_addendum': self.addendum.id,
                'issue_date': str(self.today),
                'description': 'Provider addendum upload',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = _data_dict(response)
        created = PetDocument.objects.get(id=data['id'])
        self.assertEqual(created.visit_record_addendum_id, self.addendum.id)
        self.assertIsNone(created.visit_record_id)
        self.assertEqual(data['management_context'], 'provider_visit')
        self.assertEqual(data['visit_record_addendum'], self.addendum.id)

    def test_provider_with_pet_owner_access_can_create_visit_linked_document_via_canonical_endpoint(self):
        PetOwner.objects.create(
            pet=self.pet_one,
            user=self.employee_a.user,
            role='coowner',
        )
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.post(
            self._documents_url(self.pet_one.id),
            {
                'file': SimpleUploadedFile('provider-mixed-role.pdf', b'%PDF-1.4 mixed-role', content_type='application/pdf'),
                'document_type': self.lab_results_type.id,
                'visit_record': self.visit_record.id,
                'issue_date': str(self.today),
                'description': 'Provider upload from mixed-role account',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = _data_dict(response)
        created = PetDocument.objects.get(id=data['id'])
        self.assertEqual(created.visit_record_id, self.visit_record.id)
        self.assertEqual(created.uploaded_by_id, self.employee_a.user.id)
        self.assertEqual(data['management_context'], 'provider_visit')
        self.assertEqual(data['document_type_code'], 'lab_results')

    def test_provider_can_update_visit_linked_document(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.patch(
            self._detail_url(self.visit_document.id),
            {
                'name': 'Updated visit document',
                'description': 'Adjusted after review',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.visit_document.refresh_from_db()
        self.assertEqual(self.visit_document.name, 'Updated visit document')
        self.assertEqual(self.visit_document.description, 'Adjusted after review')
        self.assertEqual(self.visit_document.version, 2)

    def test_provider_can_withdraw_visit_linked_document(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.post(
            self._withdraw_url(self.visit_document.id),
            {
                'reason_code': 'uploaded_in_error',
                'reason_comment': 'Superseded by corrected file',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.visit_document.refresh_from_db()
        self.assertEqual(self.visit_document.lifecycle_status, PetDocument.STATUS_WITHDRAWN)
        self.assertEqual(self.visit_document.withdrawn_by_id, self.employee_a.user.id)
        self.assertEqual(self.visit_document.lifecycle_reason_code, 'uploaded_in_error')

    def test_provider_is_forbidden_to_create_owner_space_document(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.post(
            self._documents_url(self.pet_one.id),
            {
                'file': SimpleUploadedFile('provider-passport.pdf', b'%PDF-1.4 passport', content_type='application/pdf'),
                'document_type': self.passport_type.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = _data_dict(response)
        self.assertIn('visit_record', data)

    def test_owner_cannot_create_addendum_linked_document_via_canonical_endpoint(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            self._documents_url(self.pet_one.id),
            {
                'file': SimpleUploadedFile('owner-addendum.pdf', b'%PDF-1.4 owner-addendum', content_type='application/pdf'),
                'document_type': self.lab_results_type.id,
                'visit_record_addendum': self.addendum.id,
                'issue_date': str(self.today),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = _data_dict(response)
        self.assertIn('visit_record', data)

    def test_provider_is_forbidden_to_use_owner_only_document_type_in_visit_context(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.post(
            self._documents_url(self.pet_one.id),
            {
                'file': SimpleUploadedFile('provider-passport.pdf', b'%PDF-1.4 passport', content_type='application/pdf'),
                'document_type': self.passport_type.id,
                'visit_record': self.visit_record.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = _data_dict(response)
        self.assertIn('document_type', data)

    def test_provider_is_forbidden_from_owner_space_document_detail_and_update(self):
        self.client.force_authenticate(self.employee_a.user)

        detail_response = self.client.get(self._detail_url(self.owner_document.id))
        patch_response = self.client.patch(
            self._detail_url(self.owner_document.id),
            {'name': 'Mutated by provider'},
            format='json',
        )

        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(patch_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_is_forbidden_from_provider_created_clinical_document_update_and_withdraw(self):
        self.client.force_authenticate(self.owner)

        patch_response = self.client.patch(
            self._detail_url(self.visit_document.id),
            {'name': 'Owner tries to edit provider doc'},
            format='json',
        )
        withdraw_response = self.client.post(
            self._withdraw_url(self.visit_document.id),
            {'reason_code': 'owner_request'},
            format='json',
        )

        self.assertEqual(patch_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(withdraw_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_canonical_detail_exposes_lifecycle_and_permission_fields(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(self._detail_url(self.owner_document.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = _data_dict(response)
        self.assertEqual(data['id'], self.owner_document.id)
        self.assertEqual(data['management_context'], 'owner_pet_card')
        self.assertEqual(data['lifecycle_status'], 'active')
        self.assertEqual(data['document_type_code'], 'passport_identification')
        self.assertTrue(data['can_update'])
        self.assertTrue(data['can_deactivate'])
        self.assertFalse(data['can_withdraw'])
        self.assertEqual(data['version'], 1)

    def test_file_replacement_on_patch_is_explicitly_rejected(self):
        self.client.force_authenticate(self.owner)

        response = self.client.patch(
            self._detail_url(self.owner_document.id),
            {
                'file': SimpleUploadedFile(
                    'replacement.pdf',
                    b'%PDF-1.4 replacement',
                    content_type='application/pdf',
                ),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = _data_dict(response)
        self.assertIn('file', data)

    def test_public_hard_delete_endpoint_is_not_exposed_for_pet_documents(self):
        self.client.force_authenticate(self.owner)

        response = self.client.delete(self._detail_url(self.owner_document.id))

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

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
        data = _data_dict(response)
        self.assertTrue(PetHealthNote.objects.filter(id=data['id'], pet=self.pet_one).exists())

    def test_employee_cannot_download_owner_private_document_without_visit_link(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.get(self._download_url(self.owner_document.id))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_can_download_visit_linked_document(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.get(self._download_url(self.visit_document.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_employee_can_preview_visit_linked_pdf_inline(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.get(self._preview_url(self.visit_document.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response['Content-Disposition'].startswith('inline;'))

    def test_canonical_pet_documents_endpoint_lists_only_accessible_documents(self):
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.get(f'/api/v1/pet-documents/?pet={self.pet_one.id}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _extract_results(response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.visit_document.id)
        self.assertEqual(results[0]['management_context'], 'provider_visit')

    def test_canonical_pet_documents_endpoint_supports_addendum_filter(self):
        addendum_document = PetDocument.objects.create(
            file=SimpleUploadedFile('visit-addendum.pdf', b'%PDF-1.4 visit-addendum', content_type='application/pdf'),
            name='Visit addendum document',
            pet=self.pet_one,
            document_type=self.lab_results_type,
            visit_record_addendum=self.addendum,
            issue_date=self.today,
            uploaded_by=self.employee_a.user,
        )
        self.client.force_authenticate(self.employee_a.user)

        response = self.client.get(
            '/api/v1/pet-documents/',
            {'visit_record_addendum': self.addendum.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _extract_results(response.data)
        self.assertEqual([item['id'] for item in results], [addendum_document.id])

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
        data = _data_dict(response)
        created_note = PetHealthNote.objects.get(id=data['id'])
        self.assertTrue(created_note.documents.exists())
        self.assertEqual(created_note.documents.first().document_type.code, 'discharge_doctor_orders')
        self.assertIsNotNone(data['attachments'])

    def test_legacy_pet_records_endpoint_still_lists_files(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(f'/api/v1/pet-records/?pet={self.pet_one.id}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Deprecation'], 'true')
        results = _extract_results(response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['files'], [self.visit_document.id])

    def test_legacy_records_upload_endpoint_still_creates_visit_document(self):
        self.client.force_authenticate(self.employee_a.user)

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
        data = _data_dict(response)
        document = PetDocument.objects.get(id=data['id'])
        self.assertEqual(document.visit_record_id, self.visit_record.id)
        self.assertEqual(document.document_type.code, 'discharge_doctor_orders')
        self.assertEqual(data['pet_record'], self.visit_record.id)

    def test_owner_is_forbidden_to_use_legacy_record_upload_endpoint(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            f'/api/v1/records/{self.visit_record.id}/upload_file/',
            {
                'file': SimpleUploadedFile(
                    'owner-legacy-record.pdf',
                    b'%PDF-1.4 owner-legacy-record',
                    content_type='application/pdf',
                ),
                'name': 'Owner legacy record upload',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
