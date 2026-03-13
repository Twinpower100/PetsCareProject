from django.test import TestCase

from catalog.models import Service


class PublicServiceSearchTest(TestCase):
    def test_public_search_autocomplete_matches_partial_synonym(self):
        category = Service.objects.create(
            code='vaccinations_partial',
            name='Vaccinations',
            level=0,
            is_active=True,
            is_client_facing=True,
        )
        service = Service.objects.create(
            parent=category,
            code='vaccination_rabies_partial',
            name='Rabies vaccination',
            level=1,
            is_active=True,
            is_client_facing=True,
            search_keywords=['прививка', 'прививка от бешенства'],
        )

        response = self.client.get('/api/v1/public/services/search/', {'q': 'прив'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(len(payload['results']), 1)
        self.assertEqual(payload['results'][0]['id'], service.id)

    def test_public_search_matches_service_synonym_keyword(self):
        category = Service.objects.create(
            code='vaccinations',
            name='Vaccinations',
            level=0,
            is_active=True,
            is_client_facing=True,
        )
        service = Service.objects.create(
            parent=category,
            code='vaccination_rabies',
            name='Rabies vaccination',
            name_ru='Вакцинация от бешенства',
            level=1,
            is_active=True,
            is_client_facing=True,
            search_keywords=['прививка', 'прививка от'],
        )

        response = self.client.get('/api/v1/public/services/search/', {'q': 'прививка'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(len(payload['results']), 1)
        self.assertEqual(payload['results'][0]['id'], service.id)

    def test_public_search_matches_synonym_case_insensitively(self):
        category = Service.objects.create(
            code='vaccinations_case',
            name='Vaccinations',
            level=0,
            is_active=True,
            is_client_facing=True,
        )
        service = Service.objects.create(
            parent=category,
            code='vaccination_rabies_case',
            name='Rabies vaccination',
            level=1,
            is_active=True,
            is_client_facing=True,
            search_keywords=['прививка'],
        )

        response = self.client.get('/api/v1/public/services/search/', {'q': 'ПрИвИвКа'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(len(payload['results']), 1)
        self.assertEqual(payload['results'][0]['id'], service.id)
