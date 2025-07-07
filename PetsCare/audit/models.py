from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from users.models import User


class UserAction(models.Model):
    """
    Модель для логирования всех действий пользователей.
    
    Централизованное логирование всех операций в системе
    для обеспечения прозрачности и контроля.
    """
    
    # Типы действий
    ACTION_TYPES = [
        ('create', _('Create')),
        ('update', _('Update')),
        ('delete', _('Delete')),
        ('login', _('Login')),
        ('logout', _('Logout')),
        ('view', _('View')),
        ('export', _('Export')),
        ('import', _('Import')),
        ('block', _('Block')),
        ('unblock', _('Unblock')),
        ('invite', _('Invite')),
        ('accept', _('Accept')),
        ('reject', _('Reject')),
        ('transfer', _('Transfer')),
        ('payment', _('Payment')),
        ('refund', _('Refund')),
        ('booking', _('Booking')),
        ('cancel', _('Cancel')),
        ('review', _('Review')),
        ('complaint', _('Complaint')),
        ('system', _('System')),
    ]
    
    # Пользователь, выполнивший действие
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('User'),
        related_name='actions'
    )
    
    # Тип действия
    action_type = models.CharField(
        max_length=20,
        choices=ACTION_TYPES,
        verbose_name=_('Action Type')
    )
    
    # Объект, с которым связано действие (через ContentType)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('Content Type')
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Object ID')
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Детали действия
    details = models.JSONField(
        default=dict,
        verbose_name=_('Details'),
        help_text=_('Additional details about the action')
    )
    
    # IP-адрес пользователя
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_('IP Address')
    )
    
    # User-Agent браузера
    user_agent = models.TextField(
        blank=True,
        verbose_name=_('User Agent')
    )
    
    # HTTP метод запроса
    http_method = models.CharField(
        max_length=10,
        blank=True,
        verbose_name=_('HTTP Method')
    )
    
    # URL запроса
    url = models.URLField(
        blank=True,
        verbose_name=_('URL')
    )
    
    # Статус ответа
    status_code = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Status Code')
    )
    
    # Время выполнения запроса (в секундах)
    execution_time = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_('Execution Time (seconds)')
    )
    
    # Временная метка
    timestamp = models.DateTimeField(
        default=timezone.now,
        verbose_name=_('Timestamp')
    )
    
    # Сессия пользователя
    session_key = models.CharField(
        max_length=40,
        blank=True,
        verbose_name=_('Session Key')
    )
    
    class Meta:
        verbose_name = _('User Action')
        verbose_name_plural = _('User Actions')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action_type', 'timestamp']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['ip_address', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.action_type} - {self.timestamp}"
    
    @property
    def object_name(self):
        """Возвращает название объекта, с которым связано действие"""
        if self.content_object:
            return str(self.content_object)
        return f"{self.content_type} #{self.object_id}" if self.content_type else ""


class SecurityAudit(models.Model):
    """
    Модель для аудита критически важных операций безопасности.
    
    Специализированная модель для отслеживания изменений
    в системе безопасности и критически важных операций.
    """
    
    # Типы аудита
    AUDIT_TYPES = [
        ('role_change', _('Role Change')),
        ('permission_change', _('Permission Change')),
        ('invite_management', _('Invite Management')),
        ('financial_operation', _('Financial Operation')),
        ('blocking_operation', _('Blocking Operation')),
        ('moderation_action', _('Moderation Action')),
        ('ownership_transfer', _('Ownership Transfer')),
        ('suspicious_activity', _('Suspicious Activity')),
        ('system_config', _('System Configuration')),
    ]
    
    # Пользователь, выполнивший действие
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('User'),
        related_name='security_audits'
    )
    
    # Тип аудита
    audit_type = models.CharField(
        max_length=30,
        choices=AUDIT_TYPES,
        verbose_name=_('Audit Type')
    )
    
    # Объект, с которым связано действие
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('Content Type')
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Object ID')
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Детали операции
    details = models.JSONField(
        default=dict,
        verbose_name=_('Details'),
        help_text=_('Detailed information about the security operation')
    )
    
    # Старые значения (для отслеживания изменений)
    old_values = models.JSONField(
        default=dict,
        verbose_name=_('Old Values'),
        help_text=_('Previous values before the change')
    )
    
    # Новые значения
    new_values = models.JSONField(
        default=dict,
        verbose_name=_('New Values'),
        help_text=_('New values after the change')
    )
    
    # Причина изменения
    reason = models.TextField(
        blank=True,
        verbose_name=_('Reason'),
        help_text=_('Reason for the security operation')
    )
    
    # IP-адрес
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_('IP Address')
    )
    
    # Временная метка
    timestamp = models.DateTimeField(
        default=timezone.now,
        verbose_name=_('Timestamp')
    )
    
    # Флаг критичности
    is_critical = models.BooleanField(
        default=False,
        verbose_name=_('Is Critical'),
        help_text=_('Mark as critical security operation')
    )
    
    # Статус проверки
    review_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', _('Pending')),
            ('reviewed', _('Reviewed')),
            ('approved', _('Approved')),
            ('rejected', _('Rejected')),
        ],
        default='pending',
        verbose_name=_('Review Status')
    )
    
    # Кто проверил
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Reviewed By'),
        related_name='reviewed_audits'
    )
    
    # Комментарий проверяющего
    review_comment = models.TextField(
        blank=True,
        verbose_name=_('Review Comment')
    )
    
    class Meta:
        verbose_name = _('Security Audit')
        verbose_name_plural = _('Security Audits')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['audit_type', 'timestamp']),
            models.Index(fields=['is_critical', 'timestamp']),
            models.Index(fields=['review_status', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.audit_type} - {self.timestamp}"
    
    @property
    def object_name(self):
        """Возвращает название объекта"""
        if self.content_object:
            return str(self.content_object)
        return f"{self.content_type} #{self.object_id}" if self.content_type else ""


class AuditSettings(models.Model):
    """
    Настройки системы аудита и логирования.
    
    Глобальные настройки для управления системой аудита.
    """
    
    # Включение логирования
    logging_enabled = models.BooleanField(
        default=True,
        verbose_name=_('Logging Enabled')
    )
    
    # Включение аудита безопасности
    security_audit_enabled = models.BooleanField(
        default=True,
        verbose_name=_('Security Audit Enabled')
    )
    
    # Период хранения логов (в днях)
    log_retention_days = models.PositiveIntegerField(
        default=365,
        verbose_name=_('Log Retention (days)'),
        help_text=_('How long to keep logs in database')
    )
    
    # Период хранения аудита безопасности (в днях)
    security_audit_retention_days = models.PositiveIntegerField(
        default=2555,  # 7 лет
        verbose_name=_('Security Audit Retention (days)'),
        help_text=_('How long to keep security audit records')
    )
    
    # Логирование HTTP запросов
    log_http_requests = models.BooleanField(
        default=True,
        verbose_name=_('Log HTTP Requests')
    )
    
    # Логирование изменений в базе данных
    log_database_changes = models.BooleanField(
        default=True,
        verbose_name=_('Log Database Changes')
    )
    
    # Логирование бизнес-операций
    log_business_operations = models.BooleanField(
        default=True,
        verbose_name=_('Log Business Operations')
    )
    
    # Логирование системных событий
    log_system_events = models.BooleanField(
        default=True,
        verbose_name=_('Log System Events')
    )
    
    # Минимальный уровень логирования
    min_log_level = models.CharField(
        max_length=10,
        choices=[
            ('DEBUG', 'DEBUG'),
            ('INFO', 'INFO'),
            ('WARNING', 'WARNING'),
            ('ERROR', 'ERROR'),
        ],
        default='INFO',
        verbose_name=_('Minimum Log Level')
    )
    
    # Автоматическая очистка старых логов
    auto_cleanup_enabled = models.BooleanField(
        default=True,
        verbose_name=_('Auto Cleanup Enabled')
    )
    
    # Частота автоматической очистки (в днях)
    cleanup_frequency_days = models.PositiveIntegerField(
        default=7,
        verbose_name=_('Cleanup Frequency (days)')
    )
    
    # Уведомления о критических операциях
    critical_operation_notifications = models.BooleanField(
        default=True,
        verbose_name=_('Critical Operation Notifications')
    )
    
    # Email для уведомлений
    notification_email = models.EmailField(
        blank=True,
        verbose_name=_('Notification Email')
    )
    
    # Временная метка последнего обновления
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )
    
    class Meta:
        verbose_name = _('Audit Setting')
        verbose_name_plural = _('Audit Settings')
    
    def __str__(self):
        return f"Audit Settings - {self.updated_at}"
    
    @classmethod
    def get_settings(cls):
        """Получает настройки аудита (создает по умолчанию, если не существует)"""
        settings, created = cls.objects.get_or_create(
            id=1,
            defaults={
                'logging_enabled': True,
                'security_audit_enabled': True,
                'log_retention_days': 365,
                'security_audit_retention_days': 2555,
                'log_http_requests': True,
                'log_database_changes': True,
                'log_business_operations': True,
                'log_system_events': True,
                'min_log_level': 'INFO',
                'auto_cleanup_enabled': True,
                'cleanup_frequency_days': 7,
                'critical_operation_notifications': True,
            }
        )
        return settings
