"""
Celery-задачи приложения providers.

Этот модуль содержит фоновые задачи для отчетности provider admin.
"""

from __future__ import annotations

from celery import shared_task
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .models import ProviderLocation, ProviderReportExportJob
from .reporting_services import ProviderLocationReportingService


@shared_task(bind=True)
def generate_provider_report_export_task(self, job_id: int) -> None:
    """
    Генерирует XLSX-файл для async job выгрузки отчета.

    Args:
        self: Celery task instance.
        job_id: Идентификатор ProviderReportExportJob.
    """
    try:
        with transaction.atomic():
            job = (
                ProviderReportExportJob.objects.select_for_update()
                .select_related('provider')
                .get(pk=job_id)
            )
            if job.status != ProviderReportExportJob.STATUS_PENDING:
                return
            job.status = ProviderReportExportJob.STATUS_RUNNING
            job.task_id = getattr(self.request, 'id', '') or ''
            job.started_at = timezone.now()
            job.error_message = ''
            job.version += 1
            job.save(update_fields=['status', 'task_id', 'started_at', 'error_message', 'version', 'updated_at'])

        location = job.location
        if location is None:
            location = ProviderLocation.objects.filter(provider_id=job.provider_id).order_by('name', 'id').first()
        if location is None:
            raise ValueError('No accessible location found for export job.')

        service = ProviderLocationReportingService(
            location=location,
            scope=job.scope,
            language_code=job.language_code,
            start_date=job.start_date,
            end_date=job.end_date,
        )
        content = service.build_xlsx_bytes(job.report_code)
        filename = service.build_xlsx_filename(job.report_code)

        with transaction.atomic():
            job = ProviderReportExportJob.objects.select_for_update().get(pk=job_id)
            if job.status != ProviderReportExportJob.STATUS_RUNNING:
                return
            if job.file:
                job.file.delete(save=False)
            job.filename = filename
            job.file.save(filename, ContentFile(content), save=False)
            job.status = ProviderReportExportJob.STATUS_COMPLETED
            job.completed_at = timezone.now()
            job.error_message = ''
            job.version += 1
            job.save(update_fields=['file', 'filename', 'status', 'completed_at', 'error_message', 'version', 'updated_at'])
    except Exception as exc:
        with transaction.atomic():
            job = ProviderReportExportJob.objects.select_for_update().filter(pk=job_id).first()
            if job is None:
                return
            job.status = ProviderReportExportJob.STATUS_FAILED
            job.completed_at = timezone.now()
            job.error_message = str(exc)[:2000]
            job.version += 1
            job.save(update_fields=['status', 'completed_at', 'error_message', 'version', 'updated_at'])
