#!/usr/bin/env python
"""
Скрипт для исправления проблемы с django_admin_log
"""
import os
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

from django.db import connection, transaction
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model

User = get_user_model()

def fix_admin_log():
    """Исправляет проблему с django_admin_log и другими таблицами"""
    with connection.cursor() as cursor:
        # Список таблиц, которые могут ссылаться на auth_user
        tables_to_fix = [
            'django_admin_log',
            'user_analytics_userconversion',
            'user_analytics_useractivity',
            'user_analytics_userengagement',
            'user_analytics_userbehavior',
            'user_analytics_userretention'
        ]
        
        for table_name in tables_to_fix:
            print(f"\n=== Обрабатываем таблицу: {table_name} ===")
            
            # Проверяем, существует ли таблица
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = %s
                )
            """, [table_name])
            
            if not cursor.fetchone()[0]:
                print(f"Таблица {table_name} не существует, пропускаем")
                continue
            
            # Проверяем текущие ограничения
            cursor.execute("""
                SELECT tc.constraint_name, tc.table_name, kcu.column_name, 
                       ccu.table_name AS referenced_table_name, ccu.column_name AS referenced_column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
                WHERE tc.table_name = %s AND kcu.column_name = 'user_id'
            """, [table_name])
            constraints = cursor.fetchall()
            print("Текущие ограничения:", constraints)
            
            # Удаляем только ограничения, которые ссылаются на auth_user
            unique_constraints = set()
            for constraint in constraints:
                constraint_name = constraint[0]
                referenced_table = constraint[3]
                if referenced_table == 'auth_user':
                    unique_constraints.add(constraint_name)
            
            for constraint_name in unique_constraints:
                print(f"Удаляем ограничение: {constraint_name}")
                try:
                    cursor.execute(f"ALTER TABLE {table_name} DROP CONSTRAINT {constraint_name}")
                except Exception as e:
                    print(f"Ошибка при удалении ограничения {constraint_name}: {e}")
            
            # Очищаем записи с несуществующими пользователями
            print("Очищаем записи с несуществующими пользователями...")
            cursor.execute(f"""
                DELETE FROM {table_name} 
                WHERE user_id NOT IN (SELECT id FROM users_user)
            """)
            deleted_count = cursor.rowcount
            print(f"Удалено {deleted_count} записей с несуществующими пользователями")
            
            # Проверяем, существует ли уже правильное ограничение
            cursor.execute(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.table_name = '{table_name}' 
                    AND kcu.column_name = 'user_id'
                    AND ccu.table_name = 'users_user'
                )
            """)
            
            constraint_exists = cursor.fetchone()[0]
            
            if not constraint_exists:
                # Добавляем новое ограничение на users_user
                print("Добавляем новое ограничение на users_user")
                try:
                    cursor.execute(f"""
                        ALTER TABLE {table_name} 
                        ADD CONSTRAINT {table_name}_user_id_fk 
                        FOREIGN KEY (user_id) REFERENCES users_user(id) 
                        ON DELETE CASCADE
                    """)
                except Exception as e:
                    print(f"Ошибка при добавлении ограничения: {e}")
            else:
                print("Правильное ограничение уже существует")
            
            print(f"Ограничения для {table_name} исправлены!")
        
        print("\n=== Все ограничения исправлены! ===")

if __name__ == "__main__":
    fix_admin_log()
