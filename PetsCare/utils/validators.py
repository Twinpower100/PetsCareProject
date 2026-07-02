"""
Общие валидаторы для моделей и сериализаторов.
"""

from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _


@deconstructible
class LettersDigitsSpacesHyphensValidator:
    """
    Проверяет, что строка содержит только буквы Unicode, цифры, пробелы и дефисы.
    """

    def __init__(self, message=None, code='invalid'):
        """Сохраняет сообщение и код ошибки для сериализации в миграциях."""
        self.message = message or _('Value can only contain letters, digits, spaces, and hyphens.')
        self.code = code

    def __call__(self, value):
        """Валидирует значение посимвольно, не ограничиваясь ASCII-латиницей."""
        text = str(value or '')
        invalid_chars = [
            char
            for char in text
            if not (char.isalpha() or char.isdigit() or char.isspace() or char == '-')
        ]
        if invalid_chars:
            raise ValidationError(self.message, code=self.code, params={'value': value})

    def __eq__(self, other):
        """Сравнивает валидаторы при генерации миграций Django."""
        return (
            isinstance(other, LettersDigitsSpacesHyphensValidator)
            and self.message == other.message
            and self.code == other.code
        )
