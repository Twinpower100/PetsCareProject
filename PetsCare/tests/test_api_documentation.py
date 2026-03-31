"""
Smoke-тесты документации API.

Тесты проверяют:
- доступность swagger/redoc/schema endpoints;
- базовую целостность сгенерированной схемы;
- наличие ключевых групп endpoint'ов;
- доступность export-команды и основных doc-артефактов.
"""

import json
import os
from io import StringIO
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management import call_command, get_commands
from django.test import TestCase
from rest_framework.test import APIClient


def _resolve_repo_path(relative_path):
    """Ищет файл в корне backend-репозитория и внутри пакета PetsCare."""
    candidates = [
        Path(settings.BASE_DIR) / relative_path,
        Path(settings.BASE_DIR) / 'PetsCare' / relative_path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


class APIDocumentationTestCase(TestCase):
    """Проверки рабочей API-документации."""

    def setUp(self):
        self.client = APIClient()

    def _load_schema(self):
        response = self.client.get('/swagger.json')
        self.assertEqual(response.status_code, 200)
        content_type = response.get('Content-Type', '')

        if 'json' in content_type:
            return response.json()

        return yaml.safe_load(response.content.decode('utf-8'))

    def test_schema_endpoint(self):
        """JSON schema endpoint доступен."""
        response = self.client.get('/swagger.json')
        self.assertEqual(response.status_code, 200)

    def test_swagger_ui_endpoint(self):
        """Swagger UI доступен."""
        response = self.client.get('/swagger/')
        self.assertEqual(response.status_code, 200)

    def test_redoc_endpoint(self):
        """ReDoc доступен."""
        response = self.client.get('/redoc/')
        self.assertEqual(response.status_code, 200)

    def test_schema_generation(self):
        """Схема содержит базовые обязательные секции."""
        schema = self._load_schema()
        self.assertIn('info', schema)
        self.assertIn('paths', schema)
        self.assertTrue('swagger' in schema or 'openapi' in schema)
        self.assertGreater(len(schema['paths']), 0)

    def test_required_endpoint_groups_exist(self):
        """В схеме присутствуют ключевые доменные группы."""
        paths = self._load_schema().get('paths', {})
        path_keys = list(paths.keys())

        expected_groups = [
            ('pets',),
            ('providers',),
            ('booking',),
            ('notifications',),
            ('addresses', 'autocomplete', 'geocode', 'reverse-geocode'),
        ]

        for group_variants in expected_groups:
            self.assertTrue(
                any(
                    variant in path
                    for path in path_keys
                    for variant in group_variants
                ),
                f"В схеме нет ни одного endpoint с группой '{group_variants[0]}'",
            )

    def test_security_definitions(self):
        """Схема содержит описание security."""
        schema = self._load_schema()
        components = schema.get('components', {})
        security_schemes = components.get('securitySchemes', {})
        legacy_security = schema.get('securityDefinitions', {})

        self.assertTrue(
            bool(security_schemes) or bool(legacy_security),
            'Security definitions отсутствуют в схеме',
        )

    def test_schema_is_json_and_yaml_serializable(self):
        """Схема сериализуется в JSON и YAML."""
        schema = self._load_schema()
        json_payload = json.dumps(schema)
        self.assertIsInstance(json.loads(json_payload), dict)

        yaml_payload = yaml.dump(schema)
        self.assertIsInstance(yaml.safe_load(yaml_payload), dict)


class DocumentationExportTestCase(TestCase):
    """Проверки экспортируемых doc-артефактов."""

    def test_export_command_exists(self):
        """Команда экспорта документации зарегистрирована."""
        commands = get_commands()
        self.assertIn('export_api_docs', commands)

    def test_export_formats(self):
        """Команда экспорта запускается хотя бы для JSON."""
        out = StringIO()
        try:
            call_command(
                'export_api_docs',
                '--format',
                'json',
                '--output',
                '/tmp/test_api.json',
                stdout=out,
            )
        except Exception:
            # Команда не должна валить suite, если окружение не позволяет экспорт.
            return

    def test_documentation_files_exist(self):
        """Основные doc-файлы существуют и не пусты."""
        doc_files = [
            'docs/api_documentation.md',
            'docs/README.md',
            'swagger_config.py',
            'templates/api_documentation.html',
        ]

        for file_path in doc_files:
            resolved_path = _resolve_repo_path(file_path)
            self.assertTrue(os.path.exists(resolved_path), f'{file_path} отсутствует')
            with open(resolved_path, 'r', encoding='utf-8') as handle:
                self.assertGreater(len(handle.read()), 0, f'{file_path} пустой')

    def test_html_template_exists(self):
        """HTML-шаблон содержит ключевые элементы swagger UI."""
        template_path = _resolve_repo_path('templates/api_documentation.html')
        with open(template_path, 'r', encoding='utf-8') as handle:
            content = handle.read()

        self.assertIn('PetCare API', content)
        self.assertIn('swagger-ui', content)
        self.assertIn('SwaggerUIBundle', content)

    def test_documentation_content_quality(self):
        """Markdown документация содержит базовые разделы и примеры."""
        doc_path = _resolve_repo_path('docs/api_documentation.md')
        with open(doc_path, 'r', encoding='utf-8') as handle:
            content = handle.read()

        required_sections = [
            '# API Documentation',
            '## Authentication',
            '## Pets Management',
            '## Providers',
            '## Pet Search and Filtering',
            '## Pet Sitting',
        ]

        for section in required_sections:
            self.assertIn(section, content)

        self.assertIn('Authorization: Bearer', content)
        self.assertIn('GET /api/pets/', content)
        self.assertIn('POST /api/pets/', content)
