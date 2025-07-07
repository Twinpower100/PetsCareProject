"""
Команда для экспорта документации API в различные форматы.

Эта команда позволяет экспортировать документацию API в форматы:
- JSON (OpenAPI 3.0)
- YAML (OpenAPI 3.0)
- HTML (Swagger UI)
- PDF (через wkhtmltopdf)
- Markdown

Использование:
    python manage.py export_api_docs --format json --output docs/api.json
    python manage.py export_api_docs --format yaml --output docs/api.yaml
    python manage.py export_api_docs --format html --output docs/api.html
    python manage.py export_api_docs --format markdown --output docs/api.md
    python manage.py export_api_docs --format all --output docs/
"""

import json
import os
import yaml
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.urls import get_resolver
from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg.views import get_schema_view
from rest_framework import permissions
import requests
from datetime import datetime


class PetCareSchemaGenerator(OpenAPISchemaGenerator):
    """
    Кастомный генератор схемы для PetCare API.
    
    Добавляет дополнительную информацию и примеры для документации.
    """
    
    def get_schema(self, request=None, public=False):
        """
        Генерирует схему OpenAPI с дополнительной информацией.
        """
        schema = super().get_schema(request, public)
        
        # Добавляем информацию о серверах
        schema.servers = [
            openapi.Server(
                url="https://api.petscare.com/api/v1",
                description="Production server"
            ),
            openapi.Server(
                url="https://staging-api.petscare.com/api/v1",
                description="Staging server"
            ),
            openapi.Server(
                url="http://localhost:8000/api/v1",
                description="Development server"
            )
        ]
        
        # Добавляем глобальные параметры
        schema.components.parameters = {
            'page': openapi.Parameter(
                name='page',
                in_=openapi.IN_QUERY,
                description='Номер страницы',
                type=openapi.TYPE_INTEGER,
                default=1
            ),
            'page_size': openapi.Parameter(
                name='page_size',
                in_=openapi.IN_QUERY,
                description='Размер страницы (максимум 100)',
                type=openapi.TYPE_INTEGER,
                default=20
            ),
            'search': openapi.Parameter(
                name='search',
                in_=openapi.IN_QUERY,
                description='Поисковый запрос',
                type=openapi.TYPE_STRING
            ),
            'ordering': openapi.Parameter(
                name='ordering',
                in_=openapi.IN_QUERY,
                description='Поле для сортировки (префикс - для обратной сортировки)',
                type=openapi.TYPE_STRING
            )
        }
        
        # Добавляем глобальные ответы
        schema.components.responses = {
            '400': openapi.Response(
                description='Ошибка валидации',
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'error': openapi.Schema(type=openapi.TYPE_STRING),
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'details': openapi.Schema(type=openapi.TYPE_OBJECT)
                    }
                )
            ),
            '401': openapi.Response(
                description='Не авторизован',
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'error': openapi.Schema(type=openapi.TYPE_STRING),
                        'message': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            ),
            '403': openapi.Response(
                description='Доступ запрещен',
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'error': openapi.Schema(type=openapi.TYPE_STRING),
                        'message': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            ),
            '404': openapi.Response(
                description='Ресурс не найден',
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'error': openapi.Schema(type=openapi.TYPE_STRING),
                        'message': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            ),
            '429': openapi.Response(
                description='Превышен лимит запросов',
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'error': openapi.Schema(type=openapi.TYPE_STRING),
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'retry_after': openapi.Schema(type=openapi.TYPE_INTEGER)
                    }
                )
            ),
            '500': openapi.Response(
                description='Внутренняя ошибка сервера',
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'error': openapi.Schema(type=openapi.TYPE_STRING),
                        'message': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            )
        }
        
        return schema


class Command(BaseCommand):
    """
    Команда для экспорта документации API.
    """
    
    help = 'Экспорт документации API в различные форматы'
    
    def add_arguments(self, parser):
        """
        Добавляет аргументы командной строки.
        """
        parser.add_argument(
            '--format',
            type=str,
            choices=['json', 'yaml', 'html', 'markdown', 'pdf', 'all'],
            default='json',
            help='Формат экспорта (по умолчанию: json)'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Путь к файлу или директории для сохранения'
        )
        parser.add_argument(
            '--include-examples',
            action='store_true',
            help='Включить примеры запросов и ответов'
        )
        parser.add_argument(
            '--include-descriptions',
            action='store_true',
            help='Включить подробные описания'
        )
        parser.add_argument(
            '--pretty',
            action='store_true',
            help='Форматированный вывод (для JSON)'
        )
        parser.add_argument(
            '--template',
            type=str,
            help='Путь к HTML шаблону для экспорта'
        )
    
    def handle(self, *args, **options):
        """
        Основная логика команды.
        """
        format_type = options['format']
        output_path = options['output']
        include_examples = options['include_examples']
        include_descriptions = options['include_descriptions']
        pretty = options['pretty']
        template = options['template']
        
        # Создаем схему
        schema_view = get_schema_view(
            openapi.Info(
                title="PetCare API",
                default_version='v1',
                description=self._get_api_description(),
                terms_of_service="https://www.petscare.com/terms/",
                contact=openapi.Contact(
                    email="api-support@petscare.com",
                    name="PetCare API Support",
                    url="https://docs.petscare.com/api"
                ),
                license=openapi.License(
                    name="MIT License",
                    url="https://opensource.org/licenses/MIT"
                ),
            ),
            public=True,
            permission_classes=(permissions.AllowAny,),
            generator_class=PetCareSchemaGenerator,
        )
        
        # Получаем схему
        schema = schema_view.schema_generator.get_schema()
        
        # Определяем путь для сохранения
        if not output_path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            if format_type == 'all':
                output_path = f'docs/api_export_{timestamp}'
            else:
                output_path = f'docs/api.{format_type}'
        
        # Создаем директорию если нужно
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Экспортируем в выбранном формате
        if format_type == 'all':
            self._export_all_formats(schema, output_path, include_examples, include_descriptions, pretty)
        else:
            self._export_format(schema, format_type, output_path, include_examples, include_descriptions, pretty, template)
        
        self.stdout.write(
            self.style.SUCCESS(f'Документация API успешно экспортирована в {output_path}')
        )
    
    def _get_api_description(self):
        """
        Возвращает описание API.
        """
        return """
        # PetCare API Documentation
        
        Полный REST API для системы управления уходом за питомцами.
        
        ## Основные возможности:
        
        ### Пользователи и аутентификация
        - Регистрация и аутентификация пользователей
        - Управление профилями
        - Система ролей и инвайтов
        
        ### Питомцы
        - Управление питомцами и их документами
        - Медицинские записи
        - Система доступа к картам питомцев
        
        ### Учреждения и сотрудники
        - Управление учреждениями
        - Управление сотрудниками и расписаниями
        - Система услуг и цен
        
        ### Бронирования и платежи
        - Создание и управление бронированиями
        - Система платежей
        - Автоматическое планирование
        
        ### Уведомления и отчеты
        - Система уведомлений (email, push, in-app)
        - Отчеты по доходам, загруженности, задолженностям
        - Аналитика и статистика
        
        ### Безопасность и аудит
        - Система аудита всех действий
        - Логирование и мониторинг
        - Управление безопасностью
        
        ## Аутентификация
        
        API использует JWT токены для аутентификации. Для получения токена используйте endpoint `/api/login/`.
        
        ## Коды ответов
        
        - `200` - Успешный запрос
        - `201` - Ресурс создан
        - `400` - Ошибка валидации
        - `401` - Не авторизован
        - `403` - Доступ запрещен
        - `404` - Ресурс не найден
        - `500` - Внутренняя ошибка сервера
        
        ## Ограничения
        
        - **Лимит запросов**: 1000 запросов в час для аутентифицированных пользователей
        - **Размер файлов**: до 10MB для изображений, до 50MB для документов
        - **Пагинация**: по умолчанию 20 элементов, максимум 100 на страницу
        
        ## Поддержка
        
        - **Email**: api-support@petscare.com
        - **Документация**: https://docs.petscare.com/api
        - **Статус API**: https://status.petscare.com
        """
    
    def _export_all_formats(self, schema, output_path, include_examples, include_descriptions, pretty):
        """
        Экспортирует документацию во все форматы.
        """
        formats = ['json', 'yaml', 'html', 'markdown']
        
        for fmt in formats:
            file_path = Path(output_path) / f'api.{fmt}'
            self._export_format(schema, fmt, str(file_path), include_examples, include_descriptions, pretty)
    
    def _export_format(self, schema, format_type, output_path, include_examples, include_descriptions, pretty, template=None):
        """
        Экспортирует документацию в конкретном формате.
        """
        if format_type == 'json':
            self._export_json(schema, output_path, pretty)
        elif format_type == 'yaml':
            self._export_yaml(schema, output_path)
        elif format_type == 'html':
            self._export_html(schema, output_path, template)
        elif format_type == 'markdown':
            self._export_markdown(schema, output_path, include_examples, include_descriptions)
        elif format_type == 'pdf':
            self._export_pdf(schema, output_path)
    
    def _export_json(self, schema, output_path, pretty):
        """
        Экспортирует схему в JSON формате.
        """
        schema_dict = schema.to_dict()
        
        if pretty:
            json_content = json.dumps(schema_dict, indent=2, ensure_ascii=False)
        else:
            json_content = json.dumps(schema_dict, ensure_ascii=False)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(json_content)
    
    def _export_yaml(self, schema, output_path):
        """
        Экспортирует схему в YAML формате.
        """
        schema_dict = schema.to_dict()
        yaml_content = yaml.dump(schema_dict, default_flow_style=False, allow_unicode=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)
    
    def _export_html(self, schema, output_path, template=None):
        """
        Экспортирует схему в HTML формате.
        """
        if template:
            # Используем кастомный шаблон
            with open(template, 'r', encoding='utf-8') as f:
                template_content = f.read()
            
            # Заменяем плейсхолдеры
            schema_dict = schema.to_dict()
            html_content = template_content.replace(
                '{{schema}}', 
                json.dumps(schema_dict, indent=2)
            )
        else:
            # Используем стандартный Swagger UI
            html_content = self._generate_swagger_html(schema)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
    
    def _generate_swagger_html(self, schema):
        """
        Генерирует HTML с Swagger UI.
        """
        schema_dict = schema.to_dict()
        schema_json = json.dumps(schema_dict)
        
        return f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PetCare API Documentation</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@4.15.5/swagger-ui.css" />
    <style>
        html {{
            box-sizing: border-box;
            overflow: -moz-scrollbars-vertical;
            overflow-y: scroll;
        }}
        *, *:before, *:after {{
            box-sizing: inherit;
        }}
        body {{
            margin:0;
            background: #fafafa;
        }}
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@4.15.5/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@4.15.5/swagger-ui-standalone-preset.js"></script>
    <script>
        window.onload = function() {{
            const ui = SwaggerUIBundle({{
                spec: {schema_json},
                dom_id: '#swagger-ui',
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIStandalonePreset
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                layout: "StandaloneLayout",
                validatorUrl: null,
                docExpansion: "list",
                filter: true,
                showExtensions: true,
                showCommonExtensions: true,
                syntaxHighlight: {{
                    theme: "monokai"
                }},
                tryItOutEnabled: true,
                persistAuthorization: true
            }});
        }};
    </script>
</body>
</html>
"""
    
    def _export_markdown(self, schema, output_path, include_examples, include_descriptions):
        """
        Экспортирует схему в Markdown формате.
        """
        schema_dict = schema.to_dict()
        
        markdown_content = []
        markdown_content.append("# PetCare API Documentation\n")
        markdown_content.append(f"*Генерировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
        
        # Информация о API
        info = schema_dict.get('info', {})
        markdown_content.append(f"## {info.get('title', 'API')} v{info.get('version', '1.0')}\n")
        markdown_content.append(f"{info.get('description', '')}\n")
        
        # Серверы
        servers = schema_dict.get('servers', [])
        if servers:
            markdown_content.append("## Серверы\n")
            for server in servers:
                markdown_content.append(f"- **{server.get('description', 'Server')}**: `{server.get('url', '')}`\n")
            markdown_content.append("")
        
        # Пути
        paths = schema_dict.get('paths', {})
        if paths:
            markdown_content.append("## Endpoints\n")
            
            # Группируем по тегам
            endpoints_by_tag = {}
            for path, methods in paths.items():
                for method, details in methods.items():
                    if method.upper() in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
                        tags = details.get('tags', ['default'])
                        for tag in tags:
                            if tag not in endpoints_by_tag:
                                endpoints_by_tag[tag] = []
                            endpoints_by_tag[tag].append((path, method.upper(), details))
            
            # Выводим по тегам
            for tag in sorted(endpoints_by_tag.keys()):
                markdown_content.append(f"### {tag.title()}\n")
                
                for path, method, details in sorted(endpoints_by_tag[tag]):
                    summary = details.get('summary', '')
                    description = details.get('description', '')
                    
                    markdown_content.append(f"#### {method} {path}\n")
                    if summary:
                        markdown_content.append(f"**{summary}**\n")
                    if description and include_descriptions:
                        markdown_content.append(f"{description}\n")
                    
                    # Параметры
                    parameters = details.get('parameters', [])
                    if parameters:
                        markdown_content.append("**Параметры:**\n")
                        for param in parameters:
                            param_name = param.get('name', '')
                            param_type = param.get('in', '')
                            param_required = param.get('required', False)
                            param_desc = param.get('description', '')
                            
                            required_text = " (обязательный)" if param_required else ""
                            markdown_content.append(f"- `{param_name}` ({param_type}){required_text}: {param_desc}\n")
                    
                    # Примеры
                    if include_examples:
                        examples = details.get('examples', {})
                        if examples:
                            markdown_content.append("**Примеры:**\n")
                            for example_name, example_data in examples.items():
                                markdown_content.append(f"```json\n{json.dumps(example_data.get('value', {}), indent=2)}\n```\n")
                    
                    markdown_content.append("---\n")
        
        # Компоненты
        components = schema_dict.get('components', {})
        if components:
            markdown_content.append("## Компоненты\n")
            
            # Схемы
            schemas = components.get('schemas', {})
            if schemas:
                markdown_content.append("### Схемы данных\n")
                for schema_name, schema_data in schemas.items():
                    markdown_content.append(f"#### {schema_name}\n")
                    properties = schema_data.get('properties', {})
                    if properties:
                        for prop_name, prop_data in properties.items():
                            prop_type = prop_data.get('type', '')
                            prop_desc = prop_data.get('description', '')
                            markdown_content.append(f"- `{prop_name}` ({prop_type}): {prop_desc}\n")
                    markdown_content.append("")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(''.join(markdown_content))
    
    def _export_pdf(self, schema, output_path):
        """
        Экспортирует схему в PDF формате.
        """
        # Сначала экспортируем в HTML
        html_path = output_path.replace('.pdf', '.html')
        self._export_html(schema, html_path)
        
        try:
            # Пытаемся конвертировать в PDF с помощью wkhtmltopdf
            import subprocess
            result = subprocess.run([
                'wkhtmltopdf',
                '--encoding', 'utf-8',
                '--page-size', 'A4',
                '--margin-top', '20mm',
                '--margin-right', '20mm',
                '--margin-bottom', '20mm',
                '--margin-left', '20mm',
                html_path,
                output_path
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                # Удаляем временный HTML файл
                os.remove(html_path)
                self.stdout.write(
                    self.style.SUCCESS('PDF успешно создан с помощью wkhtmltopdf')
                )
            else:
                raise CommandError(f'Ошибка wkhtmltopdf: {result.stderr}')
                
        except FileNotFoundError:
            self.stdout.write(
                self.style.WARNING(
                    'wkhtmltopdf не найден. PDF не создан. '
                    'Установите wkhtmltopdf для создания PDF файлов.'
                )
            )
            # Оставляем HTML файл как альтернативу
            self.stdout.write(
                self.style.SUCCESS(f'HTML файл сохранен: {html_path}')
            ) 