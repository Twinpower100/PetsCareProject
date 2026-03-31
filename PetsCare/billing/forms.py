"""
Формы для административных операций биллинга.
"""

from django import forms
from django.utils.translation import gettext_lazy as _


class GenerateInvoicesForm(forms.Form):
    """
    Форма для ручной генерации счетов по выбранному периоду.
    """

    start_date = forms.DateField(
        label=_('Start Date'),
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    end_date = forms.DateField(
        label=_('End Date'),
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    def clean(self):
        """
        Проверяет корректность диапазона дат.
        """
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and start_date > end_date:
            raise forms.ValidationError(
                _('Start date cannot be later than end date')
            )
        return cleaned_data
