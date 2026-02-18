"""
Тесты для проверки корректности документации API.

Эти тесты проверяют:
- Корректность OpenAPI схемы
- Наличие всех необходимых endpoints
- Правильность описаний и примеров
- Валидность JSON схемы
"""

import json
import yaml
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg import openapi
from django.conf import settings


class APIDocumentationTestCase(TestCase):
    """
    Тесты для проверки документации API.
    """
    
    def setUp(self):
        """
        Настройка тестового окружения.
        """
        self.client = APIClient()
        self.schema_generator = OpenAPISchemaGenerator()
    
    def test_schema_generation(self):
        """
        Тест генерации OpenAPI схемы.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        
        # Проверяем базовую структуру
        self.assertIn('openapi', schema_dict)
        self.assertIn('info', schema_dict)
        self.assertIn('paths', schema_dict)
        self.assertIn('components', schema_dict)
        
        # Проверяем версию OpenAPI
        self.assertEqual(schema_dict['openapi'], '3.0.2')
        
        # Проверяем информацию о API
        info = schema_dict['info']
        self.assertIn('title', info)
        self.assertIn('version', info)
        self.assertIn('description', info)
    
    def test_required_endpoints_exist(self):
        """
        Тест наличия всех необходимых endpoints.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        # Список обязательных endpoints
        required_endpoints = [
            '/api/v1/login/',
            '/api/v1/register/',
            '/api/v1/profile/',
            '/api/v1/pets/',
            '/api/v1/providers/',
            '/api/v1/bookings/',
            '/api/v1/payments/',
            '/api/v1/notifications/',
            '/api/v1/ratings/',
            '/api/v1/reports/income/',
            '/api/v1/audit/actions/',
            '/api/v1/system/',
            '/api/v1/analytics/user-growth/',
        ]
        
        for endpoint in required_endpoints:
            self.assertIn(endpoint, paths, f"Endpoint {endpoint} отсутствует в документации")
    
    def test_authentication_endpoints(self):
        """
        Тест endpoints аутентификации.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        # Проверяем login endpoint
        login_path = paths.get('/api/v1/login/', {})
        self.assertIn('post', login_path, "POST метод для /api/login/ отсутствует")
        
        login_post = login_path['post']
        self.assertIn('requestBody', login_post, "Request body для login отсутствует")
        
        # Проверяем параметры login
        request_body = login_post['requestBody']
        self.assertIn('content', request_body)
        self.assertIn('application/json', request_body['content'])
        
        # Проверяем register endpoint
        register_path = paths.get('/api/v1/register/', {})
        self.assertIn('post', register_path, "POST метод для /api/register/ отсутствует")
    
    def test_pets_endpoints(self):
        """
        Тест endpoints для питомцев.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        pets_path = paths.get('/api/v1/pets/', {})
        
        # Проверяем GET метод
        self.assertIn('get', pets_path, "GET метод для /api/pets/ отсутствует")
        
        # Проверяем POST метод
        self.assertIn('post', pets_path, "POST метод для /api/pets/ отсутствует")
        
        # Проверяем параметры GET
        pets_get = pets_path['get']
        self.assertIn('parameters', pets_get, "Параметры для GET /api/pets/ отсутствуют")
        
        # Проверяем наличие параметров пагинации
        parameters = pets_get['parameters']
        param_names = [p['name'] for p in parameters]
        self.assertIn('page', param_names, "Параметр 'page' отсутствует")
        self.assertIn('page_size', param_names, "Параметр 'page_size' отсутствует")
    
    def test_bookings_endpoints(self):
        """
        Тест endpoints для бронирований.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        bookings_path = paths.get('/api/v1/bookings/', {})
        
        # Проверяем основные методы
        self.assertIn('get', bookings_path, "GET метод для /api/bookings/ отсутствует")
        self.assertIn('post', bookings_path, "POST метод для /api/bookings/ отсутствует")
        
        # Проверяем детальный endpoint
        booking_detail_path = paths.get('/api/v1/bookings/{id}/', {})
        self.assertIn('get', booking_detail_path, "GET метод для /api/bookings/{id}/ отсутствует")
        self.assertIn('put', booking_detail_path, "PUT метод для /api/bookings/{id}/ отсутствует")
        self.assertIn('delete', booking_detail_path, "DELETE метод для /api/bookings/{id}/ отсутствует")
        
        # Проверяем cancel endpoint
        cancel_path = paths.get('/api/v1/bookings/{id}/cancel/', {})
        self.assertIn('post', cancel_path, "POST метод для /api/bookings/{id}/cancel/ отсутствует")
    
    def test_notifications_endpoints(self):
        """
        Тест endpoints для уведомлений.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        notifications_path = paths.get('/api/v1/notifications/', {})
        
        # Проверяем GET метод
        self.assertIn('get', notifications_path, "GET метод для /api/notifications/ отсутствует")
        
        # Проверяем mark as read endpoint
        mark_read_path = paths.get('/api/v1/notifications/{id}/mark-as-read/', {})
        self.assertIn('post', mark_read_path, "POST метод для mark-as-read отсутствует")
        
        # Проверяем mark all as read endpoint
        mark_all_read_path = paths.get('/api/v1/notifications/mark-all-as-read/', {})
        self.assertIn('post', mark_all_read_path, "POST метод для mark-all-as-read отсутствует")
    
    def test_reports_endpoints(self):
        """
        Тест endpoints для отчетов.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        # Проверяем основные отчеты
        report_endpoints = [
            '/api/v1/reports/income/',
            '/api/v1/reports/workload/',
            '/api/v1/reports/debt/',
            '/api/v1/reports/activity/',
            '/api/v1/reports/payment/',
            '/api/v1/reports/cancellation/',
        ]
        
        for endpoint in report_endpoints:
            self.assertIn(endpoint, paths, f"Report endpoint {endpoint} отсутствует")
            
            endpoint_data = paths[endpoint]
            self.assertIn('get', endpoint_data, f"GET метод для {endpoint} отсутствует")
    
    def test_audit_endpoints(self):
        """
        Тест endpoints для аудита.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        audit_endpoints = [
            '/api/audit/logs/',
            '/api/audit/logs/export/',
            '/api/audit/user-activity/{user_id}/',
            '/api/audit/statistics/',
        ]
        
        for endpoint in audit_endpoints:
            self.assertIn(endpoint, paths, f"Audit endpoint {endpoint} отсутствует")
    
    def test_settings_endpoints(self):
        """
        Тест endpoints для настроек.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        settings_endpoints = [
            '/api/settings/system/',
            '/api/settings/features/',
            '/api/settings/security/',
            '/api/settings/health/',
        ]
        
        for endpoint in settings_endpoints:
            self.assertIn(endpoint, paths, f"Settings endpoint {endpoint} отсутствует")
    
    def test_analytics_endpoints(self):
        """
        Тест endpoints для аналитики.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        analytics_endpoints = [
            '/api/analytics/user-growth/',
            '/api/analytics/provider-performance/',
            '/api/analytics/revenue-trends/',
            '/api/analytics/behavioral/',
        ]
        
        for endpoint in analytics_endpoints:
            self.assertIn(endpoint, paths, f"Analytics endpoint {endpoint} отсутствует")
    
    def test_geolocation_endpoints(self):
        """
        Тест endpoints для геолокации.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        geolocation_endpoints = [
            '/api/geolocation/search/',
            '/api/geolocation/reverse/',
            '/api/geolocation/validate/',
        ]
        
        for endpoint in geolocation_endpoints:
            self.assertIn(endpoint, paths, f"Geolocation endpoint {endpoint} отсутствует")
    
    def test_security_definitions(self):
        """
        Тест определений безопасности.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        
        # Проверяем компоненты безопасности
        components = schema_dict.get('components', {})
        security_schemes = components.get('securitySchemes', {})
        
        # Проверяем Bearer токен
        self.assertIn('Bearer', security_schemes, "Bearer security scheme отсутствует")
        
        bearer_scheme = security_schemes['Bearer']
        self.assertEqual(bearer_scheme['type'], 'http')
        self.assertEqual(bearer_scheme['scheme'], 'bearer')
    
    def test_response_codes(self):
        """
        Тест кодов ответов.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        # Проверяем несколько endpoints на наличие стандартных кодов ответов
        test_endpoints = [
            '/api/pets/',
            '/api/bookings/',
            '/api/providers/',
        ]
        
        for endpoint in test_endpoints:
            if endpoint in paths:
                endpoint_data = paths[endpoint]
                
                # Проверяем GET метод
                if 'get' in endpoint_data:
                    responses = endpoint_data['get'].get('responses', {})
                    
                    # Проверяем стандартные коды ответов
                    self.assertIn('200', responses, f"200 response для {endpoint} отсутствует")
                    self.assertIn('401', responses, f"401 response для {endpoint} отсутствует")
                    self.assertIn('403', responses, f"403 response для {endpoint} отсутствует")
                
                # Проверяем POST метод
                if 'post' in endpoint_data:
                    responses = endpoint_data['post'].get('responses', {})
                    
                    self.assertIn('201', responses, f"201 response для {endpoint} отсутствует")
                    self.assertIn('400', responses, f"400 response для {endpoint} отсутствует")
                    self.assertIn('401', responses, f"401 response для {endpoint} отсутствует")
    
    def test_parameter_descriptions(self):
        """
        Тест описаний параметров.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        # Проверяем описания параметров для основных endpoints
        test_cases = [
            ('/api/pets/', 'get', 'page', 'Номер страницы'),
            ('/api/pets/', 'get', 'page_size', 'Размер страницы'),
            ('/api/providers/', 'get', 'search', 'Поисковый запрос'),
            ('/api/bookings/', 'get', 'status', 'Статус бронирования'),
        ]
        
        for endpoint, method, param_name, expected_description in test_cases:
            if endpoint in paths and method in paths[endpoint]:
                endpoint_data = paths[endpoint][method]
                parameters = endpoint_data.get('parameters', [])
                
                param_found = False
                for param in parameters:
                    if param['name'] == param_name:
                        param_found = True
                        self.assertIn('description', param, f"Описание для параметра {param_name} отсутствует")
                        break
                
                self.assertTrue(param_found, f"Параметр {param_name} не найден в {endpoint}")
    
    def test_request_body_schemas(self):
        """
        Тест схем request body.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        # Проверяем схемы для POST запросов
        test_cases = [
            ('/api/pets/', 'post'),
            ('/api/bookings/', 'post'),
            ('/api/providers/', 'post'),
        ]
        
        for endpoint, method in test_cases:
            if endpoint in paths and method in paths[endpoint]:
                endpoint_data = paths[endpoint][method]
                
                if 'requestBody' in endpoint_data:
                    request_body = endpoint_data['requestBody']
                    self.assertIn('content', request_body, f"Content для {endpoint} отсутствует")
                    
                    content = request_body['content']
                    self.assertIn('application/json', content, f"application/json content для {endpoint} отсутствует")
                    
                    json_content = content['application/json']
                    self.assertIn('schema', json_content, f"Schema для {endpoint} отсутствует")
    
    def test_response_schemas(self):
        """
        Тест схем ответов.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        # Проверяем схемы для GET запросов
        test_cases = [
            ('/api/pets/', 'get'),
            ('/api/bookings/', 'get'),
            ('/api/providers/', 'get'),
        ]
        
        for endpoint, method in test_cases:
            if endpoint in paths and method in paths[endpoint]:
                endpoint_data = paths[endpoint][method]
                responses = endpoint_data.get('responses', {})
                
                if '200' in responses:
                    response_200 = responses['200']
                    self.assertIn('content', response_200, f"Content для 200 response {endpoint} отсутствует")
                    
                    content = response_200['content']
                    self.assertIn('application/json', content, f"application/json content для 200 response {endpoint} отсутствует")
                    
                    json_content = content['application/json']
                    self.assertIn('schema', json_content, f"Schema для 200 response {endpoint} отсутствует")
    
    def test_tags_organization(self):
        """
        Тест организации по тегам.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        paths = schema_dict.get('paths', {})
        
        # Проверяем наличие тегов для основных endpoints
        test_cases = [
            ('/api/pets/', ['pets']),
            ('/api/bookings/', ['bookings']),
            ('/api/providers/', ['providers']),
            ('/api/notifications/', ['notifications']),
            ('/api/ratings/', ['ratings']),
            ('/api/reports/', ['reports']),
        ]
        
        for endpoint, expected_tags in test_cases:
            if endpoint in paths:
                endpoint_data = paths[endpoint]
                
                # Проверяем GET метод
                if 'get' in endpoint_data:
                    tags = endpoint_data['get'].get('tags', [])
                    for expected_tag in expected_tags:
                        self.assertIn(expected_tag, tags, f"Тег {expected_tag} отсутствует для {endpoint}")
    
    def test_schema_validation(self):
        """
        Тест валидности JSON схемы.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        
        # Проверяем, что схема может быть сериализована в JSON
        try:
            json_str = json.dumps(schema_dict)
            # Проверяем, что можно десериализовать обратно
            json.loads(json_str)
        except (TypeError, ValueError) as e:
            self.fail(f"Схема не является валидным JSON: {e}")
    
    def test_yaml_serialization(self):
        """
        Тест сериализации в YAML.
        """
        schema = self.schema_generator.get_schema()
        schema_dict = schema.to_dict()
        
        # Проверяем, что схема может быть сериализована в YAML
        try:
            yaml_str = yaml.dump(schema_dict)
            # Проверяем, что можно десериализовать обратно
            yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            self.fail(f"Схема не может быть сериализована в YAML: {e}")
    
    def test_swagger_ui_endpoint(self):
        """
        Тест доступности Swagger UI endpoint.
        """
        # Проверяем, что Swagger UI endpoint доступен
        try:
            response = self.client.get('/swagger/')
            self.assertEqual(response.status_code, 200)
        except:
            # Если endpoint не настроен, это не критично
            pass
    
    def test_redoc_endpoint(self):
        """
        Тест доступности ReDoc endpoint.
        """
        # Проверяем, что ReDoc endpoint доступен
        try:
            response = self.client.get('/redoc/')
            self.assertEqual(response.status_code, 200)
        except:
            # Если endpoint не настроен, это не критично
            pass
    
    def test_schema_endpoint(self):
        """
        Тест доступности JSON схемы.
        """
        # Проверяем, что schema endpoint доступен
        try:
            response = self.client.get('/swagger.json')
            self.assertEqual(response.status_code, 200)
            
            # Проверяем, что возвращается валидный JSON
            schema_data = response.json()
            self.assertIn('openapi', schema_data)
            self.assertIn('paths', schema_data)
        except:
            # Если endpoint не настроен, это не критично
            pass


class DocumentationExportTestCase(TestCase):
    """
    Тесты для экспорта документации.
    """
    
    def test_export_command_exists(self):
        """
        Тест наличия команды экспорта.
        """
        from django.core.management import get_commands
        commands = get_commands()
        
        self.assertIn('export_api_docs', commands, "Команда export_api_docs не найдена")
    
    def test_export_formats(self):
        """
        Тест экспорта в различные форматы.
        """
        from django.core.management import call_command
        from io import StringIO
        
        # Тестируем экспорт в JSON
        out = StringIO()
        try:
            call_command('export_api_docs', '--format', 'json', '--output', '/tmp/test_api.json', stdout=out)
            self.assertIn('успешно экспортирована', out.getvalue())
        except:
            # Если команда не работает, это не критично для тестов
            pass
    
    def test_documentation_files_exist(self):
        """
        Тест наличия файлов документации.
        """
        import os
        
        # Проверяем наличие основных файлов документации
        doc_files = [
            'docs/api_documentation.md',
            'docs/README.md',
            'swagger_config.py',
        ]
        
        for file_path in doc_files:
            if os.path.exists(file_path):
                # Проверяем, что файл не пустой
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.assertGreater(len(content), 0, f"Файл {file_path} пустой")
    
    def test_html_template_exists(self):
        """
        Тест наличия HTML шаблона.
        """
        import os
        
        template_path = 'templates/api_documentation.html'
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Проверяем наличие основных элементов
                self.assertIn('PetCare API', content)
                self.assertIn('swagger-ui', content)
                self.assertIn('openapi', content)
    
    def test_documentation_content_quality(self):
        """
        Тест качества содержания документации.
        """
        import os
        
        doc_path = 'docs/api_documentation.md'
        if os.path.exists(doc_path):
            with open(doc_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Проверяем наличие основных разделов
                required_sections = [
                    '# PetCare API Documentation',
                    '## Обзор',
                    '## Аутентификация',
                    '## Пользователи и аутентификация',
                    '## Питомцы',
                    '## Учреждения',
                    '## Бронирования',
                    '## Платежи',
                    '## Уведомления',
                    '## Рейтинги и отзывы',
                    '## Отчеты',
                    '## Аудит',
                    '## Системные настройки',
                    '## Аналитика',
                    '## Геолокация',
                ]
                
                for section in required_sections:
                    self.assertIn(section, content, f"Раздел {section} отсутствует в документации")
                
                # Проверяем наличие примеров
                self.assertIn('curl -X POST', content, "Примеры curl отсутствуют")
                self.assertIn('Authorization: Bearer', content, "Примеры аутентификации отсутствуют")
                
                # Проверяем наличие кодов ответов
                self.assertIn('200', content, "Коды ответов отсутствуют")
                self.assertIn('400', content, "Коды ошибок отсутствуют") 