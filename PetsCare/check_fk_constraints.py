"""
Скрипт для проверки и исправления внешних ключей в базе данных.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

from django.db import connection

def check_and_fix_fk():
    """Проверяет и исправляет внешние ключи, ссылающиеся на auth_user вместо users_user."""
    with connection.cursor() as cursor:
        # Проверяем все внешние ключи, которые ссылаются на auth_user
        cursor.execute("""
            SELECT 
                conname as constraint_name,
                conrelid::regclass as table_name,
                confrelid::regclass as referenced_table
            FROM pg_constraint 
            WHERE contype = 'f' 
            AND confrelid::regclass::text = 'auth_user'
            AND conrelid::regclass::text LIKE 'billing_%';
        """)
        
        constraints = cursor.fetchall()
        
        if not constraints:
            print("✓ Все внешние ключи в billing ссылаются на правильную таблицу (users_user)")
            return
        
        print(f"Найдено {len(constraints)} неправильных внешних ключей:")
        for constraint_name, table_name, referenced_table in constraints:
            print(f"  - {constraint_name} в таблице {table_name} ссылается на {referenced_table}")
        
        # Исправляем каждый внешний ключ
        for constraint_name, table_name, referenced_table in constraints:
            # Получаем информацию о колонке
            cursor.execute("""
                SELECT 
                    a.attname as column_name
                FROM pg_constraint c
                JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
                WHERE c.conname = %s;
            """, [constraint_name])
            
            column_info = cursor.fetchone()
            if not column_info:
                print(f"  ⚠ Не удалось найти колонку для {constraint_name}")
                continue
            
            column_name = column_info[0]
            
            # Удаляем старый внешний ключ
            print(f"  Удаляем {constraint_name}...")
            cursor.execute(f"""
                ALTER TABLE {table_name} 
                DROP CONSTRAINT IF EXISTS {constraint_name};
            """)
            
            # Создаем новый внешний ключ на users_user
            new_constraint_name = constraint_name.replace('_fk_auth_user', '_fk_users_use')
            print(f"  Создаем {new_constraint_name}...")
            cursor.execute(f"""
                ALTER TABLE {table_name} 
                ADD CONSTRAINT {new_constraint_name} 
                FOREIGN KEY ({column_name}) 
                REFERENCES users_user(id) 
                DEFERRABLE INITIALLY DEFERRED;
            """)
            
            print(f"  ✓ Исправлен {constraint_name} -> {new_constraint_name}")
        
        print("\n✓ Все внешние ключи исправлены!")

if __name__ == '__main__':
    check_and_fix_fk()

