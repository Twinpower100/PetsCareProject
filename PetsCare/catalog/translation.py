# Модель Service использует ручные языковые поля (name_en, name_ru, и т.д.)
# вместо автоматических полей от modeltranslation.
# Поэтому регистрация для перевода не требуется.
# from modeltranslation.translator import register, TranslationOptions
# from .models import Service
#
# @register(Service)
# class ServiceTranslationOptions(TranslationOptions):
#     """
#     Опции перевода для модели Service.
#     Переводятся поля name и description.
#     """
#     fields = ('name', 'description',) 