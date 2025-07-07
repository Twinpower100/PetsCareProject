"""
Команда для создания геопространственных индексов.

Эта команда создает необходимые индексы для оптимизации
геопространственных запросов в базе данных.
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings


class Command(BaseCommand):
    """
    Команда для создания геопространственных индексов.
    
    Создает индексы для оптимизации запросов по координатам,
    расстояниям и геолокации.
    """
    
    help = 'Creates geospatial indexes for optimizing location-based queries'
    
    def add_arguments(self, parser):
        """
        Добавляет аргументы командной строки.
        """
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of existing indexes'
        )
        parser.add_argument(
            '--postgis',
            action='store_true',
            help='Create PostGIS-specific indexes (requires PostGIS extension)'
        )
    
    def handle(self, *args, **options):
        """
        Выполняет создание индексов.
        """
        force = options['force']
        postgis = options['postgis']
        
        self.stdout.write(
            self.style.SUCCESS('Starting geospatial index creation...')
        )
        
        with connection.cursor() as cursor:
            # Создаем базовые индексы для координат
            self._create_basic_indexes(cursor, force)
            
            # Создаем составные индексы
            self._create_composite_indexes(cursor, force)
            
            # Создаем PostGIS индексы если требуется
            if postgis:
                self._create_postgis_indexes(cursor, force)
        
        self.stdout.write(
            self.style.SUCCESS('Geospatial indexes created successfully!')
        )
    
    def _create_basic_indexes(self, cursor, force):
        """
        Создает базовые индексы для координат.
        """
        indexes = [
            {
                'name': 'idx_address_coordinates',
                'table': 'geolocation_address',
                'columns': ['latitude', 'longitude']
            },
            {
                'name': 'idx_location_coordinates',
                'table': 'geolocation_location',
                'columns': ['latitude', 'longitude']
            },
            {
                'name': 'idx_location_history_coordinates',
                'table': 'geolocation_locationhistory',
                'columns': ['latitude', 'longitude']
            }
        ]
        
        for index in indexes:
            self._create_index(cursor, index, force)
    
    def _create_composite_indexes(self, cursor, force):
        """
        Создает составные индексы для оптимизации запросов.
        """
        indexes = [
            {
                'name': 'idx_address_coordinates_status',
                'table': 'geolocation_address',
                'columns': ['latitude', 'longitude', 'validation_status']
            },
            {
                'name': 'idx_address_coordinates_valid',
                'table': 'geolocation_address',
                'columns': ['latitude', 'longitude', 'is_valid']
            },
            {
                'name': 'idx_address_city_region',
                'table': 'geolocation_address',
                'columns': ['city', 'region']
            },
            {
                'name': 'idx_address_postal_code',
                'table': 'geolocation_address',
                'columns': ['postal_code']
            }
        ]
        
        for index in indexes:
            self._create_index(cursor, index, force)
    
    def _create_postgis_indexes(self, cursor, force):
        """
        Создает PostGIS-специфичные индексы.
        """
        # Проверяем наличие PostGIS расширения
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")
        if not cursor.fetchone():
            self.stdout.write(
                self.style.WARNING('PostGIS extension not found. Skipping PostGIS indexes.')
            )
            return
        
        # Создаем геометрическое поле если его нет
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'geolocation_address' 
            AND column_name = 'geom'
        """)
        
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE geolocation_address 
                ADD COLUMN geom geometry(Point, 4326)
            """)
            
            # Обновляем геометрическое поле из координат
            cursor.execute("""
                UPDATE geolocation_address 
                SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            """)
        
        # Создаем GIST индекс для геометрического поля
        self._create_index(cursor, {
            'name': 'idx_address_geom',
            'table': 'geolocation_address',
            'columns': ['geom'],
            'type': 'USING GIST'
        }, force)
    
    def _create_index(self, cursor, index_info, force):
        """
        Создает отдельный индекс.
        """
        name = index_info['name']
        table = index_info['table']
        columns = index_info['columns']
        index_type = index_info.get('type', '')
        
        # Проверяем существование индекса
        cursor.execute("""
            SELECT 1 FROM pg_indexes 
            WHERE indexname = %s
        """, [name])
        
        if cursor.fetchone():
            if force:
                self.stdout.write(f'Dropping existing index: {name}')
                cursor.execute(f'DROP INDEX IF EXISTS {name}')
            else:
                self.stdout.write(f'Index {name} already exists, skipping...')
                return
        
        # Создаем индекс
        columns_str = ', '.join(columns)
        sql = f'CREATE INDEX {name} ON {table} {index_type} ({columns_str})'
        
        try:
            cursor.execute(sql)
            self.stdout.write(
                self.style.SUCCESS(f'Created index: {name}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to create index {name}: {e}')
            ) 