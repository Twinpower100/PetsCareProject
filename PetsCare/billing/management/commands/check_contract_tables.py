"""
Management команда для проверки наличия таблиц Contract в базе данных.

Использование:
    python manage.py check_contract_tables
    
Команда проверяет:
1. Существуют ли таблицы Contract в базе данных
2. Есть ли данные в этих таблицах
3. Сколько записей в каждой таблице
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.core.exceptions import ImproperlyConfigured


class Command(BaseCommand):
    help = 'Проверяет наличие таблиц Contract в базе данных и количество записей'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Проверка таблиц Contract в базе данных ===\n'))
        
        # Список таблиц, связанных с Contract
        contract_tables = [
            'billing_contract',
            'billing_contracttype',
            'billing_contractcommission',
            'billing_contractdiscount',
            'billing_contractapprovalhistory',
        ]
        
        # Получаем имя базы данных из настроек
        db_name = connection.settings_dict.get('NAME')
        self.stdout.write(f'База данных: {db_name}\n')
        
        # Проверяем каждую таблицу
        tables_found = []
        tables_with_data = []
        
        with connection.cursor() as cursor:
            # Получаем список всех таблиц в базе данных
            if connection.vendor == 'postgresql':
                cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                    ORDER BY table_name;
                """)
                all_tables = [row[0] for row in cursor.fetchall()]
            elif connection.vendor == 'sqlite':
                cursor.execute("""
                    SELECT name 
                    FROM sqlite_master 
                    WHERE type='table' 
                    AND name NOT LIKE 'sqlite_%'
                    ORDER BY name;
                """)
                all_tables = [row[0] for row in cursor.fetchall()]
            else:
                self.stdout.write(self.style.ERROR(f'Неподдерживаемая СУБД: {connection.vendor}'))
                return
            
            # Проверяем каждую таблицу Contract
            for table_name in contract_tables:
                if table_name in all_tables:
                    tables_found.append(table_name)
                    
                    # Проверяем количество записей
                    try:
                        cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
                        count = cursor.fetchone()[0]
                        
                        if count > 0:
                            tables_with_data.append((table_name, count))
                            self.stdout.write(self.style.WARNING(
                                f'⚠️  Таблица {table_name}: найдено {count} записей'
                            ))
                        else:
                            self.stdout.write(self.style.SUCCESS(
                                f'✅ Таблица {table_name}: пуста (0 записей)'
                            ))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(
                            f'❌ Ошибка при проверке таблицы {table_name}: {str(e)}'
                        ))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        f'✅ Таблица {table_name}: не существует (уже удалена)'
                    ))
        
        # Итоговый отчет
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('=== ИТОГОВЫЙ ОТЧЕТ ===\n'))
        
        if not tables_found:
            self.stdout.write(self.style.SUCCESS(
                '✅ Все таблицы Contract удалены из базы данных!'
            ))
            self.stdout.write(self.style.SUCCESS(
                '✅ Можно создавать миграцию для удаления таблиц.'
            ))
        else:
            if tables_with_data:
                self.stdout.write(self.style.ERROR(
                    f'❌ Найдено {len(tables_with_data)} таблиц с данными:'
                ))
                for table_name, count in tables_with_data:
                    self.stdout.write(self.style.ERROR(
                        f'   - {table_name}: {count} записей'
                    ))
                self.stdout.write('\n⚠️  ВНИМАНИЕ: Перед удалением таблиц нужно мигрировать данные!')
            else:
                self.stdout.write(self.style.SUCCESS(
                    f'✅ Найдено {len(tables_found)} таблиц, но все они пусты.'
                ))
                self.stdout.write(self.style.SUCCESS(
                    '✅ Можно безопасно создавать миграцию для удаления таблиц.'
                ))
        
        self.stdout.write('\n' + '=' * 60)
        
        # Дополнительная проверка: есть ли ссылки на Contract в других таблицах
        self.stdout.write('\n=== Проверка внешних ключей на Contract ===\n')
        
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        tc.table_name, 
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                      ON tc.constraint_name = kcu.constraint_name
                      AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                      ON ccu.constraint_name = tc.constraint_name
                      AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                      AND ccu.table_name LIKE '%contract%'
                      AND tc.table_schema = 'public'
                    ORDER BY tc.table_name, kcu.column_name;
                """)
                
                foreign_keys = cursor.fetchall()
                
                if foreign_keys:
                    self.stdout.write(self.style.WARNING(
                        f'⚠️  Найдено {len(foreign_keys)} внешних ключей, ссылающихся на таблицы Contract:'
                    ))
                    for table_name, column_name, foreign_table, foreign_column in foreign_keys:
                        self.stdout.write(self.style.WARNING(
                            f'   - {table_name}.{column_name} → {foreign_table}.{foreign_column}'
                        ))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        '✅ Внешних ключей, ссылающихся на таблицы Contract, не найдено.'
                    ))
        
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('=== Проверка завершена ==='))

