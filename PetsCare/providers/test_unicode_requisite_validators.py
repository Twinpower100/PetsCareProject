"""
Регрессионные тесты Unicode-валидации реквизитов провайдера.
"""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from providers.models import Provider
from users.models import ProviderForm


class UnicodeRequisiteValidatorTest(SimpleTestCase):
    """
    Проверяет поддержку букв из всех пользовательских языков в реквизитах.
    """

    def test_provider_requisite_fields_accept_unicode_letters(self):
        """Поля провайдера принимают немецкие, русские и черногорские буквы."""
        samples = [
            'Muller ÄÖÜ äöü ß 123-45',
            'Straße ČĆŠĐŽ čćšđž 987',
            'Провайдер Ёж 321-00',
        ]
        for field_name in ('tax_id', 'registration_number'):
            field = Provider._meta.get_field(field_name)
            for value in samples:
                with self.subTest(model='Provider', field=field_name, value=value):
                    self.assertEqual(field.clean(value, None), value)

    def test_provider_form_requisite_fields_accept_unicode_letters(self):
        """Поля заявки провайдера используют ту же Unicode-валидацию."""
        samples = [
            'Muller ÄÖÜ äöü ß 123-45',
            'Straße ČĆŠĐŽ čćšđž 987',
            'Провайдер Ёж 321-00',
        ]
        for field_name in ('tax_id', 'registration_number'):
            field = ProviderForm._meta.get_field(field_name)
            for value in samples:
                with self.subTest(model='ProviderForm', field=field_name, value=value):
                    self.assertEqual(field.clean(value, None), value)

    def test_requisite_fields_reject_unsupported_punctuation(self):
        """Поля по-прежнему отклоняют символы вне разрешённого формата."""
        for model in (Provider, ProviderForm):
            for field_name in ('tax_id', 'registration_number'):
                field = model._meta.get_field(field_name)
                with self.subTest(model=model.__name__, field=field_name):
                    with self.assertRaises(ValidationError):
                        field.clean('Muller GmbH #42', None)
