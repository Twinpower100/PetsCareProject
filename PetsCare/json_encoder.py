"""
Кастомный JSON encoder для Django моделей.
"""
import json
from django.db import models
from django.core.serializers.json import DjangoJSONEncoder


class ModelJSONEncoder(DjangoJSONEncoder):
    """
    Кастомный JSON encoder, который умеет сериализовать Django модели.
    """
    
    def default(self, obj):
        """
        Переопределяет стандартное поведение для Django моделей.
        """
        if isinstance(obj, models.Model):
            # Если модель имеет метод to_dict, используем его
            if hasattr(obj, 'to_dict'):
                return obj.to_dict()
            # Иначе возвращаем только pk и строковое представление
            return {
                'pk': obj.pk,
                'model': obj._meta.label,
                'str': str(obj),
            }
        return super().default(obj)


# Глобальная функция для безопасной JSON сериализации
def safe_json_dumps(obj, **kwargs):
    """
    Безопасная JSON сериализация с поддержкой Django моделей.
    """
    return json.dumps(obj, cls=ModelJSONEncoder, **kwargs)
