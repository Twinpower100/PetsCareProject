from modeltranslation.translator import register, TranslationOptions
from .models import Service

@register(Service)
class ServiceTranslationOptions(TranslationOptions):
    """
    Опции перевода для модели Service.
    Переводятся поля name и description.
    """
    fields = ('name', 'description',) 