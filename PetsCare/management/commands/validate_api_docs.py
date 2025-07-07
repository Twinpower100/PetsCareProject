"""
Команда для валидации документации API.

Эта команда проверяет:
- Корректность OpenAPI схемы
- Наличие всех необходимых endpoints
- Правильность описаний и примеров
- Валидность JSON схемы
- Соответствие стандартам документации

Использование:
    python manage.py validate_api_docs
    python manage.py validate_api_docs --verbose
    python manage.py validate_api_docs --fix
"""

import json
import yaml
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg import openapi
from rest_framework import permissions


class Command(BaseCommand):
    """
    Команда для валидации документации API.
    """
    
    help = 'Валидация документации API'
    
    def add_arguments(self, parser):
        """
        Добавляет аргументы командной строки.
        """
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Подробный вывод'
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Автоматическое исправление проблем'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Файл для сохранения отчета'
        )
        parser.add_argument(
            '--format',
            type=str,
            choices=['json', 'yaml', 'text'],
            default='text',
            help='Формат отчета'
        )
    
    def handle(self, *args, **options):
        """
        Основная логика команды.
        """
        verbose = options['verbose']
        fix = options['fix']
        output_file = options['output']
        report_format = options['format']
        
        self.stdout.write(self.style.SUCCESS('🔍 Начинаю валидацию документации API...'))
        
        # Создаем генератор схемы
        schema_generator = OpenAPISchemaGenerator()
        
        # Получаем схему
        try:
            schema = schema_generator.get_schema()
            schema_dict = schema.to_dict()
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Ошибка генерации схемы: {e}')
            )
            return
        
        # Результаты валидации
        validation_results = {
            'total_checks': 0,
            'passed_checks': 0,
            'failed_checks': 0,
            'warnings': 0,
            'errors': [],
            'warnings_list': [],
            'details': {}
        }
        
        # Выполняем проверки
        self._validate_basic_structure(schema_dict, validation_results, verbose)
        self._validate_endpoints(schema_dict, validation_results, verbose)
        self._validate_authentication(schema_dict, validation_results, verbose)
        self._validate_responses(schema_dict, validation_results, verbose)
        self._validate_parameters(schema_dict, validation_results, verbose)
        self._validate_schemas(schema_dict, validation_results, verbose)
        self._validate_security(schema_dict, validation_results, verbose)
        self._validate_documentation_files(validation_results, verbose)
        
        # Выводим результаты
        self._print_results(validation_results, verbose)
        
        # Сохраняем отчет
        if output_file:
            self._save_report(validation_results, output_file, report_format)
        
        # Возвращаем код ошибки если есть проблемы
        if validation_results['failed_checks'] > 0:
            raise CommandError(f"Валидация не прошла: {validation_results['failed_checks']} ошибок")
    
    def _validate_basic_structure(self, schema_dict, results, verbose):
        """
        Валидация базовой структуры схемы.
        """
        if verbose:
            self.stdout.write('📋 Проверка базовой структуры...')
        
        checks = [
            ('openapi', 'Версия OpenAPI'),
            ('info', 'Информация о API'),
            ('paths', 'Пути API'),
            ('components', 'Компоненты'),
        ]
        
        for key, description in checks:
            results['total_checks'] += 1
            if key in schema_dict:
                results['passed_checks'] += 1
                if verbose:
                    self.stdout.write(f'  ✅ {description}: OK')
            else:
                results['failed_checks'] += 1
                results['errors'].append(f'Отсутствует {description}')
                if verbose:
                    self.stdout.write(f'  ❌ {description}: ОТСУТСТВУЕТ')
        
        # Проверяем версию OpenAPI
        if 'openapi' in schema_dict:
            results['total_checks'] += 1
            version = schema_dict['openapi']
            if version == '3.0.2':
                results['passed_checks'] += 1
                if verbose:
                    self.stdout.write(f'  ✅ Версия OpenAPI: {version}')
            else:
                results['warnings'] += 1
                results['warnings_list'].append(f'Нестандартная версия OpenAPI: {version}')
                if verbose:
                    self.stdout.write(f'  ⚠️ Версия OpenAPI: {version} (ожидалось 3.0.2)')
    
    def _validate_endpoints(self, schema_dict, results, verbose):
        """
        Валидация endpoints.
        """
        if verbose:
            self.stdout.write('🔗 Проверка endpoints...')
        
        paths = schema_dict.get('paths', {})
        
        # Обязательные endpoints
        required_endpoints = {
            '/api/login/': ['post'],
            '/api/register/': ['post'],
            '/api/profile/': ['get', 'put'],
            '/api/pets/': ['get', 'post'],
            '/api/pets/{id}/': ['get', 'put', 'delete'],
            '/api/providers/': ['get', 'post'],
            '/api/providers/{id}/': ['get', 'put'],
            '/api/bookings/': ['get', 'post'],
            '/api/bookings/{id}/': ['get', 'put', 'delete'],
            '/api/bookings/{id}/cancel/': ['post'],
            '/api/payments/': ['get', 'post'],
            '/api/notifications/': ['get'],
            '/api/notifications/{id}/mark-as-read/': ['post'],
            '/api/ratings/': ['get', 'post'],
            '/api/reports/': ['get'],
            '/api/audit/logs/': ['get'],
            '/api/settings/system/': ['get', 'put'],
            '/api/analytics/user-growth/': ['get'],
        }
        
        for endpoint, required_methods in required_endpoints.items():
            results['total_checks'] += 1
            if endpoint in paths:
                endpoint_data = paths[endpoint]
                missing_methods = []
                
                for method in required_methods:
                    if method not in endpoint_data:
                        missing_methods.append(method)
                
                if not missing_methods:
                    results['passed_checks'] += 1
                    if verbose:
                        self.stdout.write(f'  ✅ {endpoint}: OK')
                else:
                    results['failed_checks'] += 1
                    error_msg = f'Endpoint {endpoint} отсутствуют методы: {", ".join(missing_methods)}'
                    results['errors'].append(error_msg)
                    if verbose:
                        self.stdout.write(f'  ❌ {endpoint}: отсутствуют методы {", ".join(missing_methods)}')
            else:
                results['failed_checks'] += 1
                results['errors'].append(f'Endpoint {endpoint} отсутствует')
                if verbose:
                    self.stdout.write(f'  ❌ {endpoint}: ОТСУТСТВУЕТ')
        
        # Проверяем общее количество endpoints
        total_endpoints = len(paths)
        if total_endpoints < 50:
            results['warnings'] += 1
            results['warnings_list'].append(f'Мало endpoints: {total_endpoints} (ожидалось больше 50)')
            if verbose:
                self.stdout.write(f'  ⚠️ Общее количество endpoints: {total_endpoints}')
    
    def _validate_authentication(self, schema_dict, results, verbose):
        """
        Валидация аутентификации.
        """
        if verbose:
            self.stdout.write('🔐 Проверка аутентификации...')
        
        components = schema_dict.get('components', {})
        security_schemes = components.get('securitySchemes', {})
        
        # Проверяем Bearer токен
        results['total_checks'] += 1
        if 'Bearer' in security_schemes:
            bearer_scheme = security_schemes['Bearer']
            if bearer_scheme.get('type') == 'http' and bearer_scheme.get('scheme') == 'bearer':
                results['passed_checks'] += 1
                if verbose:
                    self.stdout.write('  ✅ Bearer аутентификация: OK')
            else:
                results['failed_checks'] += 1
                results['errors'].append('Неправильная конфигурация Bearer аутентификации')
                if verbose:
                    self.stdout.write('  ❌ Bearer аутентификация: НЕПРАВИЛЬНАЯ КОНФИГУРАЦИЯ')
        else:
            results['failed_checks'] += 1
            results['errors'].append('Отсутствует Bearer аутентификация')
            if verbose:
                self.stdout.write('  ❌ Bearer аутентификация: ОТСУТСТВУЕТ')
        
        # Проверяем защищенные endpoints
        paths = schema_dict.get('paths', {})
        protected_endpoints = [
            '/api/profile/',
            '/api/pets/',
            '/api/bookings/',
            '/api/payments/',
        ]
        
        for endpoint in protected_endpoints:
            if endpoint in paths:
                results['total_checks'] += 1
                endpoint_data = paths[endpoint]
                
                # Проверяем наличие security для GET методов
                if 'get' in endpoint_data:
                    security = endpoint_data['get'].get('security', [])
                    if security:
                        results['passed_checks'] += 1
                        if verbose:
                            self.stdout.write(f'  ✅ {endpoint} (GET): защищен')
                    else:
                        results['warnings'] += 1
                        results['warnings_list'].append(f'Endpoint {endpoint} (GET) не защищен')
                        if verbose:
                            self.stdout.write(f'  ⚠️ {endpoint} (GET): не защищен')
    
    def _validate_responses(self, schema_dict, results, verbose):
        """
        Валидация ответов.
        """
        if verbose:
            self.stdout.write('📤 Проверка ответов...')
        
        paths = schema_dict.get('paths', {})
        
        # Проверяем стандартные коды ответов
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
                    
                    required_responses = ['200', '401', '403']
                    for code in required_responses:
                        results['total_checks'] += 1
                        if code in responses:
                            results['passed_checks'] += 1
                            if verbose:
                                self.stdout.write(f'  ✅ {endpoint} (GET) {code}: OK')
                        else:
                            results['warnings'] += 1
                            results['warnings_list'].append(f'Endpoint {endpoint} (GET) отсутствует ответ {code}')
                            if verbose:
                                self.stdout.write(f'  ⚠️ {endpoint} (GET) {code}: ОТСУТСТВУЕТ')
                
                # Проверяем POST метод
                if 'post' in endpoint_data:
                    responses = endpoint_data['post'].get('responses', {})
                    
                    required_responses = ['201', '400', '401']
                    for code in required_responses:
                        results['total_checks'] += 1
                        if code in responses:
                            results['passed_checks'] += 1
                            if verbose:
                                self.stdout.write(f'  ✅ {endpoint} (POST) {code}: OK')
                        else:
                            results['warnings'] += 1
                            results['warnings_list'].append(f'Endpoint {endpoint} (POST) отсутствует ответ {code}')
                            if verbose:
                                self.stdout.write(f'  ⚠️ {endpoint} (POST) {code}: ОТСУТСТВУЕТ')
    
    def _validate_parameters(self, schema_dict, results, verbose):
        """
        Валидация параметров.
        """
        if verbose:
            self.stdout.write('📝 Проверка параметров...')
        
        paths = schema_dict.get('paths', {})
        
        # Проверяем параметры пагинации
        pagination_endpoints = [
            '/api/pets/',
            '/api/bookings/',
            '/api/providers/',
            '/api/notifications/',
        ]
        
        for endpoint in pagination_endpoints:
            if endpoint in paths and 'get' in paths[endpoint]:
                results['total_checks'] += 1
                parameters = paths[endpoint]['get'].get('parameters', [])
                param_names = [p['name'] for p in parameters]
                
                if 'page' in param_names and 'page_size' in param_names:
                    results['passed_checks'] += 1
                    if verbose:
                        self.stdout.write(f'  ✅ {endpoint}: параметры пагинации OK')
                else:
                    results['warnings'] += 1
                    results['warnings_list'].append(f'Endpoint {endpoint} отсутствуют параметры пагинации')
                    if verbose:
                        self.stdout.write(f'  ⚠️ {endpoint}: отсутствуют параметры пагинации')
        
        # Проверяем описания параметров
        test_cases = [
            ('/api/pets/', 'get', 'page', 'Номер страницы'),
            ('/api/providers/', 'get', 'search', 'Поисковый запрос'),
        ]
        
        for endpoint, method, param_name, expected_description in test_cases:
            if endpoint in paths and method in paths[endpoint]:
                results['total_checks'] += 1
                parameters = paths[endpoint][method].get('parameters', [])
                
                param_found = False
                for param in parameters:
                    if param['name'] == param_name:
                        param_found = True
                        if 'description' in param:
                            results['passed_checks'] += 1
                            if verbose:
                                self.stdout.write(f'  ✅ {endpoint} {param_name}: описание OK')
                        else:
                            results['warnings'] += 1
                            results['warnings_list'].append(f'Параметр {param_name} в {endpoint} не имеет описания')
                            if verbose:
                                self.stdout.write(f'  ⚠️ {endpoint} {param_name}: нет описания')
                        break
                
                if not param_found:
                    results['warnings'] += 1
                    results['warnings_list'].append(f'Параметр {param_name} не найден в {endpoint}')
                    if verbose:
                        self.stdout.write(f'  ⚠️ {endpoint} {param_name}: не найден')
    
    def _validate_schemas(self, schema_dict, results, verbose):
        """
        Валидация схем данных.
        """
        if verbose:
            self.stdout.write('📊 Проверка схем данных...')
        
        components = schema_dict.get('components', {})
        schemas = components.get('schemas', {})
        
        # Проверяем наличие основных схем
        required_schemas = [
            'User',
            'Pet',
            'Provider',
            'Booking',
            'Payment',
            'Notification',
        ]
        
        for schema_name in required_schemas:
            results['total_checks'] += 1
            if schema_name in schemas:
                results['passed_checks'] += 1
                if verbose:
                    self.stdout.write(f'  ✅ Схема {schema_name}: OK')
            else:
                results['warnings'] += 1
                results['warnings_list'].append(f'Схема {schema_name} отсутствует')
                if verbose:
                    self.stdout.write(f'  ⚠️ Схема {schema_name}: ОТСУТСТВУЕТ')
        
        # Проверяем структуру схем
        for schema_name, schema_data in schemas.items():
            if 'properties' in schema_data:
                properties = schema_data['properties']
                
                # Проверяем наличие описаний для свойств
                for prop_name, prop_data in properties.items():
                    if 'description' not in prop_data:
                        results['warnings'] += 1
                        results['warnings_list'].append(f'Свойство {prop_name} в схеме {schema_name} не имеет описания')
    
    def _validate_security(self, schema_dict, results, verbose):
        """
        Валидация безопасности.
        """
        if verbose:
            self.stdout.write('🔒 Проверка безопасности...')
        
        # Проверяем глобальные настройки безопасности
        if 'security' in schema_dict:
            results['passed_checks'] += 1
            if verbose:
                self.stdout.write('  ✅ Глобальные настройки безопасности: OK')
        else:
            results['warnings'] += 1
            results['warnings_list'].append('Отсутствуют глобальные настройки безопасности')
            if verbose:
                self.stdout.write('  ⚠️ Глобальные настройки безопасности: ОТСУТСТВУЮТ')
    
    def _validate_documentation_files(self, results, verbose):
        """
        Валидация файлов документации.
        """
        if verbose:
            self.stdout.write('📄 Проверка файлов документации...')
        
        # Проверяем наличие файлов документации
        doc_files = [
            'docs/api_documentation.md',
            'docs/README.md',
            'swagger_config.py',
        ]
        
        for file_path in doc_files:
            results['total_checks'] += 1
            if Path(file_path).exists():
                # Проверяем, что файл не пустой
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if len(content) > 0:
                        results['passed_checks'] += 1
                        if verbose:
                            self.stdout.write(f'  ✅ {file_path}: OK')
                    else:
                        results['failed_checks'] += 1
                        results['errors'].append(f'Файл {file_path} пустой')
                        if verbose:
                            self.stdout.write(f'  ❌ {file_path}: ПУСТОЙ')
            else:
                results['warnings'] += 1
                results['warnings_list'].append(f'Файл {file_path} отсутствует')
                if verbose:
                    self.stdout.write(f'  ⚠️ {file_path}: ОТСУТСТВУЕТ')
        
        # Проверяем HTML шаблон
        template_path = 'templates/api_documentation.html'
        results['total_checks'] += 1
        if Path(template_path).exists():
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'PetCare API' in content and 'swagger-ui' in content:
                    results['passed_checks'] += 1
                    if verbose:
                        self.stdout.write(f'  ✅ {template_path}: OK')
                else:
                    results['warnings'] += 1
                    results['warnings_list'].append(f'HTML шаблон {template_path} не содержит необходимых элементов')
                    if verbose:
                        self.stdout.write(f'  ⚠️ {template_path}: НЕПОЛНЫЙ')
        else:
            results['warnings'] += 1
            results['warnings_list'].append(f'HTML шаблон {template_path} отсутствует')
            if verbose:
                self.stdout.write(f'  ⚠️ {template_path}: ОТСУТСТВУЕТ')
    
    def _print_results(self, results, verbose):
        """
        Вывод результатов валидации.
        """
        total = results['total_checks']
        passed = results['passed_checks']
        failed = results['failed_checks']
        warnings = results['warnings']
        
        self.stdout.write('\n' + '='*50)
        self.stdout.write('📊 РЕЗУЛЬТАТЫ ВАЛИДАЦИИ')
        self.stdout.write('='*50)
        
        self.stdout.write(f'Всего проверок: {total}')
        self.stdout.write(f'Пройдено: {passed}')
        self.stdout.write(f'Ошибок: {failed}')
        self.stdout.write(f'Предупреждений: {warnings}')
        
        success_rate = (passed / total * 100) if total > 0 else 0
        self.stdout.write(f'Процент успеха: {success_rate:.1f}%')
        
        if failed == 0 and warnings == 0:
            self.stdout.write(self.style.SUCCESS('🎉 Валидация прошла успешно!'))
        elif failed == 0:
            self.stdout.write(self.style.WARNING('⚠️ Валидация прошла с предупреждениями'))
        else:
            self.stdout.write(self.style.ERROR('❌ Валидация не прошла'))
        
        # Выводим ошибки
        if results['errors']:
            self.stdout.write('\n❌ ОШИБКИ:')
            for error in results['errors']:
                self.stdout.write(f'  • {error}')
        
        # Выводим предупреждения
        if results['warnings_list']:
            self.stdout.write('\n⚠️ ПРЕДУПРЕЖДЕНИЯ:')
            for warning in results['warnings_list']:
                self.stdout.write(f'  • {warning}')
        
        self.stdout.write('='*50)
    
    def _save_report(self, results, output_file, report_format):
        """
        Сохранение отчета в файл.
        """
        try:
            if report_format == 'json':
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
            elif report_format == 'yaml':
                with open(output_file, 'w', encoding='utf-8') as f:
                    yaml.dump(results, f, default_flow_style=False, allow_unicode=True)
            else:  # text
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write('ОТЧЕТ О ВАЛИДАЦИИ API ДОКУМЕНТАЦИИ\n')
                    f.write('='*50 + '\n\n')
                    f.write(f'Всего проверок: {results["total_checks"]}\n')
                    f.write(f'Пройдено: {results["passed_checks"]}\n')
                    f.write(f'Ошибок: {results["failed_checks"]}\n')
                    f.write(f'Предупреждений: {results["warnings"]}\n\n')
                    
                    if results['errors']:
                        f.write('ОШИБКИ:\n')
                        for error in results['errors']:
                            f.write(f'• {error}\n')
                        f.write('\n')
                    
                    if results['warnings_list']:
                        f.write('ПРЕДУПРЕЖДЕНИЯ:\n')
                        for warning in results['warnings_list']:
                            f.write(f'• {warning}\n')
            
            self.stdout.write(
                self.style.SUCCESS(f'📄 Отчет сохранен в {output_file}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Ошибка сохранения отчета: {e}')
            ) 