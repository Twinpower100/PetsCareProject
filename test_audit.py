#!/usr/bin/env python
import os
import sys
import django

# Добавляем путь к проекту
sys.path.append('PetsCare')

# Настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

try:
    from audit.api_views import UserActionViewSet
    print("✅ UserActionViewSet импортирован успешно")
    
    from audit.models import UserAction
    print("✅ UserAction модель импортирована успешно")
    
    from audit.serializers import UserActionSerializer
    print("✅ UserActionSerializer импортирован успешно")
    
    print("🎉 Все импорты audit работают!")
    
except Exception as e:
    print(f"❌ Ошибка при импорте audit: {e}")
    import traceback
    traceback.print_exc()
