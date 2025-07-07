from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings

class Report(models.Model):
    """
    Модель для хранения отчетов.
    """
    name = models.CharField(_('Name'), max_length=255)
    type = models.CharField(_('Type'), max_length=50)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_('Created By')
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    data = models.JSONField(_('Data'), default=dict)

    class Meta:
        verbose_name = _('Report')
        verbose_name_plural = _('Reports')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.type})"


class ReportTemplate(models.Model):
    """
    Модель для хранения шаблонов отчетов.
    """
    name = models.CharField(_('Name'), max_length=255)
    type = models.CharField(_('Type'), max_length=50)
    is_active = models.BooleanField(_('Is Active'), default=True)
    template = models.JSONField(_('Template'), default=dict)

    class Meta:
        verbose_name = _('Report Template')
        verbose_name_plural = _('Report Templates')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.type})"


class ReportSchedule(models.Model):
    """
    Модель для планирования автоматической генерации отчетов.
    """
    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        verbose_name=_('Report')
    )
    frequency = models.CharField(_('Frequency'), max_length=50)
    last_run = models.DateTimeField(_('Last Run'), null=True, blank=True)
    next_run = models.DateTimeField(_('Next Run'), null=True, blank=True)
    is_active = models.BooleanField(_('Is Active'), default=True)

    class Meta:
        verbose_name = _('Report Schedule')
        verbose_name_plural = _('Report Schedules')
        ordering = ['-next_run']

    def __str__(self):
        return f"{self.report.name} ({self.frequency})" 