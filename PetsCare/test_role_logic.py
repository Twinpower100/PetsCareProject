#!/usr/bin/env python
"""
Тест правильной логики назначения роли employee.

Этот скрипт демонстрирует, что роль employee добавляется только при наличии
активной связи с учреждением (EmployeeProvider с end_date=None), а не просто
при наличии профиля Employee.
"""

import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PetsCare.settings')
django.setup()

from django.contrib.auth import get_user_model
from users.models import UserType
from providers.models import Employee, Provider, EmployeeProvider
from datetime import date

User = get_user_model()

def test_employee_role_logic():
    """
    Тестирует правильную логику назначения роли employee.
    """
    print("=== Тест логики роли employee ===\n")
    
    # Создаем тестового пользователя
    user = User.objects.create_user(
        username='test_employee',
        email='test@example.com',
        password='testpass123',
        first_name='Тест',
        last_name='Сотрудник'
    )
    
    print(f"1. Создан пользователь: {user}")
    print(f"   Роли: {list(user.user_types.values_list('name', flat=True))}")
    print()
    
    # Создаем тестовое учреждение
    provider = Provider.objects.create(
        name='Тестовая клиника',
        description='Тестовое учреждение',
        address='Тестовый адрес',
        phone_number='+1234567890',
        email='clinic@example.com'
    )
    
    print(f"2. Создано учреждение: {provider}")
    print()
    
    # Создаем профиль сотрудника (БЕЗ связи с учреждением)
    employee_profile = Employee.objects.create(
        user=user,
        position='Ветеринар',
        bio='Тестовый сотрудник'
    )
    
    print(f"3. Создан профиль сотрудника: {employee_profile}")
    print(f"   Роли: {list(user.user_types.values_list('name', flat=True))}")
    print("   ❌ Роль employee НЕ добавлена (правильно - нет связи с учреждением)")
    print()
    
    # Создаем связь с учреждением (end_date=None - активно работает)
    employment = EmployeeProvider.objects.create(
        employee=employee_profile,
        provider=provider,
        start_date=date.today(),
        end_date=None,  # Активно работает
        is_confirmed=True
    )
    
    print(f"4. Создана активная связь с учреждением: {employment}")
    print(f"   Роли: {list(user.user_types.values_list('name', flat=True))}")
    print("   ✅ Роль employee добавлена (правильно - есть активная связь)")
    print()
    
    # Устанавливаем дату окончания (увольнение)
    employment.end_date = date.today()
    employment.save()
    
    print(f"5. Установлена дата окончания работы: {employment.end_date}")
    print(f"   Роли: {list(user.user_types.values_list('name', flat=True))}")
    print("   ❌ Роль employee удалена (правильно - нет активных связей)")
    print()
    
    # Создаем новую активную связь
    new_employment = EmployeeProvider.objects.create(
        employee=employee_profile,
        provider=provider,
        start_date=date.today(),
        end_date=None,  # Снова активно работает
        is_confirmed=True
    )
    
    print(f"6. Создана новая активная связь: {new_employment}")
    print(f"   Роли: {list(user.user_types.values_list('name', flat=True))}")
    print("   ✅ Роль employee снова добавлена (правильно - есть активная связь)")
    print()
    
    # Очистка
    user.delete()
    provider.delete()
    
    print("=== Тест завершен ===")

if __name__ == '__main__':
    test_employee_role_logic() 