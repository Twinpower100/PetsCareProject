from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ProductionCalendarConfig(AppConfig):
    """Глобальный производственный календарь: статусы дней по странам."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'production_calendar'
    verbose_name = _('Production Calendar')
