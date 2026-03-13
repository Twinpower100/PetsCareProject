from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from pets.document_type_catalog import DOCUMENT_TYPE_DEFINITIONS
from pets.models import DocumentType


def _extract_results(payload):
    return payload if isinstance(payload, list) else payload.get('results', [])


class DocumentTypeCatalogTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='document-viewer@example.com',
            password='testpass123',
            phone_number='+38267000011',
        )
        self.admin = user_model.objects.create_superuser(
            email='document-admin@example.com',
            password='testpass123',
            phone_number='+38267000012',
        )

    def test_catalog_is_seeded_and_returned_in_agreed_order(self):
        self.client.force_authenticate(self.user)

        response = self.client.get('/api/v1/document-types/', HTTP_ACCEPT_LANGUAGE='de')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _extract_results(response.data)
        self.assertEqual(
            [item['code'] for item in results],
            [definition.code for definition in DOCUMENT_TYPE_DEFINITIONS],
        )
        self.assertEqual(
            [item['name'] for item in results],
            [definition.name for definition in DOCUMENT_TYPE_DEFINITIONS],
        )
        self.assertEqual(
            [item['name_display'] for item in results],
            [definition.name_de for definition in DOCUMENT_TYPE_DEFINITIONS],
        )

    def test_admin_cannot_create_custom_document_type_outside_catalog(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            '/api/v1/document-types/',
            {'name': 'Несогласованный тип'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response.data)

    def test_model_resyncs_derived_fields_from_selected_name(self):
        document_type = DocumentType.objects.get(code=DOCUMENT_TYPE_DEFINITIONS[2].code)

        document_type.code = 'broken_code'
        document_type.description = 'Broken description'
        document_type.name_en = 'Broken name'
        document_type.save()
        document_type.refresh_from_db()

        self.assertEqual(document_type.code, DOCUMENT_TYPE_DEFINITIONS[2].code)
        self.assertEqual(document_type.description, DOCUMENT_TYPE_DEFINITIONS[2].description)
        self.assertEqual(document_type.name_en, DOCUMENT_TYPE_DEFINITIONS[2].name_en)
