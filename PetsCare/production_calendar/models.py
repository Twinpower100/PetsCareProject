"""
Модели глобального производственного календаря (Level 1).

Хранит официальный статус дня (рабочий, выходной, праздник, сокращённый)
по странам. Позволяет ручные правки админом (is_manually_corrected),
которые не перезаписываются при синхронизации.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


# Поддерживаемые страны (ISO 3166-1 alpha-2)
COUNTRY_CHOICES = [
    ('RU', _('Russia')),
    ('UA', _('Ukraine')),
    ('ME', _('Montenegro')),
    ('RS', _('Serbia')),
    ('DE', _('Germany')),
    ('FR', _('France')),
    ('US', _('United States')),
]

# Тип дня
DAY_TYPE_WORKING = 'WORKING'
DAY_TYPE_WEEKEND = 'WEEKEND'
DAY_TYPE_HOLIDAY = 'HOLIDAY'
DAY_TYPE_SHORT_DAY = 'SHORT_DAY'

DAY_TYPE_CHOICES = [
    (DAY_TYPE_WORKING, _('Working day')),
    (DAY_TYPE_WEEKEND, _('Weekend')),
    (DAY_TYPE_HOLIDAY, _('Public holiday')),
    (DAY_TYPE_SHORT_DAY, _('Short day (pre-holiday)')),
]


class ProductionCalendar(models.Model):
    """
    Официальный статус дня для страны.
    Уникальность: (date, country). Ручные правки защищены флагом is_manually_corrected.
    """
    date = models.DateField(_('Date'), db_index=True)
    country = models.CharField(
        _('Country'),
        max_length=2,
        choices=COUNTRY_CHOICES,
        db_index=True,
    )
    day_type = models.CharField(
        _('Day type'),
        max_length=20,
        choices=DAY_TYPE_CHOICES,
        default=DAY_TYPE_WORKING,
    )
    is_transfer = models.BooleanField(
        _('Is transfer'),
        default=False,
        help_text=_('True if this is a working Saturday transferred from another date (e.g. RU).'),
    )
    description = models.CharField(
        _('Description'),
        max_length=255,
        blank=True,
        help_text=_('E.g. "New Year", "Transfer from May 2".'),
    )
    is_manually_corrected = models.BooleanField(
        _('Manually corrected'),
        default=False,
        help_text=_('If True, sync scripts must NOT overwrite this record.'),
    )

    class Meta:
        verbose_name = _('Production calendar day')
        verbose_name_plural = _('Production calendar')
        constraints = [
            models.UniqueConstraint(
                fields=['date', 'country'],
                name='production_calendar_date_country_uniq',
            ),
        ]
        ordering = ['date', 'country']

    def __str__(self):
        return f'{self.date.isoformat()} {self.get_country_display()} — {self.get_day_type_display()}'
