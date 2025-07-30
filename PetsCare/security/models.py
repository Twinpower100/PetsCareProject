from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.core.cache import cache
import logging
from django.utils import timezone

User = get_user_model()
logger = logging.getLogger(__name__)


class SecurityThreat(models.Model):
    """Модель для записи попыток взлома и угроз безопасности"""
    
    THREAT_TYPES = [
        ('brute_force', _('Brute Force Attack')),
        ('sql_injection', _('SQL Injection')),
        ('xss', _('Cross-Site Scripting')),
        ('path_traversal', _('Path Traversal')),
        ('rate_limit', _('Rate Limit Exceeded')),
        ('suspicious_ip', _('Suspicious IP Activity')),
        ('failed_login', _('Failed Login Attempt')),
        ('unauthorized_access', _('Unauthorized Access')),
        ('other', _('Other')),
    ]
    
    SEVERITY_LEVELS = [
        ('low', _('Low')),
        ('medium', _('Medium')),
        ('high', _('High')),
        ('critical', _('Critical')),
    ]
    
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('resolved', _('Resolved')),
        ('false_positive', _('False Positive')),
    ]
    
    threat_type = models.CharField(
        _('Threat Type'),
        max_length=50,
        choices=THREAT_TYPES,
        help_text=_('Type of security threat detected')
    )
    
    severity = models.CharField(
        _('Severity'),
        max_length=20,
        choices=SEVERITY_LEVELS,
        default='medium',
        help_text=_('Severity level of the threat')
    )
    
    ip_address = models.GenericIPAddressField(
        _('IP Address'),
        help_text=_('IP address of the threat source')
    )
    
    user_agent = models.TextField(
        _('User Agent'),
        blank=True,
        help_text=_('User agent string from the request')
    )
    
    request_path = models.CharField(
        _('Request Path'),
        max_length=500,
        help_text=_('Requested URL path')
    )
    
    request_method = models.CharField(
        _('Request Method'),
        max_length=10,
        help_text=_('HTTP method used')
    )
    
    request_data = models.JSONField(
        _('Request Data'),
        blank=True,
        null=True,
        help_text=_('Request data (headers, body, etc.)')
    )
    
    description = models.TextField(
        _('Description'),
        help_text=_('Detailed description of the threat')
    )
    
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        help_text=_('Current status of the threat')
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('User'),
        help_text=_('User associated with the threat (if authenticated)')
    )
    
    detected_at = models.DateTimeField(
        _('Detected At'),
        auto_now_add=True,
        help_text=_('When the threat was detected')
    )
    
    resolved_at = models.DateTimeField(
        _('Resolved At'),
        null=True,
        blank=True,
        help_text=_('When the threat was resolved')
    )
    
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_threats',
        verbose_name=_('Resolved By'),
        help_text=_('User who resolved the threat')
    )
    
    notes = models.TextField(
        _('Notes'),
        blank=True,
        help_text=_('Additional notes about the threat')
    )
    
    class Meta:
        verbose_name = _('Security Threat')
        verbose_name_plural = _('Security Threats')
        db_table = 'security_threats'
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['threat_type', 'detected_at']),
            models.Index(fields=['ip_address', 'detected_at']),
            models.Index(fields=['severity', 'status']),
        ]
    
    def __str__(self):
        return f"{self.get_threat_type_display()} - {self.ip_address} - {self.detected_at}"
    
    def resolve(self, resolved_by=None, notes=''):
        """Разрешить угрозу"""
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        self.resolved_by = resolved_by
        if notes:
            self.notes = notes
        self.save()
    
    def mark_false_positive(self, resolved_by=None, notes=''):
        """Пометить как ложное срабатывание"""
        self.status = 'false_positive'
        self.resolved_at = timezone.now()
        self.resolved_by = resolved_by
        if notes:
            self.notes = notes
        self.save()


class IPBlacklist(models.Model):
    """Модель для заблокированных IP-адресов"""
    
    BLOCK_TYPES = [
        ('manual', _('Manual Block')),
        ('automatic', _('Automatic Block')),
        ('temporary', _('Temporary Block')),
    ]
    
    ip_address = models.GenericIPAddressField(
        _('IP Address'),
        unique=True,
        help_text=_('Blocked IP address')
    )
    
    block_type = models.CharField(
        _('Block Type'),
        max_length=20,
        choices=BLOCK_TYPES,
        default='automatic',
        help_text=_('Type of IP block')
    )
    
    reason = models.TextField(
        _('Reason'),
        help_text=_('Reason for blocking this IP')
    )
    
    blocked_at = models.DateTimeField(
        _('Blocked At'),
        auto_now_add=True,
        help_text=_('When the IP was blocked')
    )
    
    expires_at = models.DateTimeField(
        _('Expires At'),
        null=True,
        blank=True,
        help_text=_('When the block expires (null for permanent)')
    )
    
    blocked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Blocked By'),
        help_text=_('User who blocked this IP')
    )
    
    threat_count = models.PositiveIntegerField(
        _('Threat Count'),
        default=0,
        help_text=_('Number of threats from this IP')
    )
    
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this block is currently active')
    )
    
    class Meta:
        verbose_name = _('IP Blacklist')
        verbose_name_plural = _('IP Blacklist')
        db_table = 'security_ip_blacklist'
        ordering = ['-blocked_at']
        indexes = [
            models.Index(fields=['ip_address', 'is_active']),
            models.Index(fields=['expires_at', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.ip_address} - {self.get_block_type_display()}"
    
    def is_expired(self):
        """Проверить, истек ли срок блокировки"""
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at
    
    def deactivate(self, deactivated_by=None):
        """Деактивировать блокировку"""
        self.is_active = False
        self.save()
        # Очистить кэш
        cache.delete(f'ip_blacklist_{self.ip_address}')


class ThreatPattern(models.Model):
    """Модель для шаблонов угроз"""
    
    PATTERN_TYPES = [
        ('regex', _('Regular Expression')),
        ('keyword', _('Keyword')),
        ('path', _('Path Pattern')),
        ('user_agent', _('User Agent Pattern')),
    ]
    
    name = models.CharField(
        _('Name'),
        max_length=100,
        help_text=_('Name of the threat pattern')
    )
    
    pattern_type = models.CharField(
        _('Pattern Type'),
        max_length=20,
        choices=PATTERN_TYPES,
        help_text=_('Type of pattern matching')
    )
    
    pattern = models.TextField(
        _('Pattern'),
        help_text=_('Pattern to match against requests')
    )
    
    threat_type = models.CharField(
        _('Threat Type'),
        max_length=50,
        choices=SecurityThreat.THREAT_TYPES,
        help_text=_('Type of threat this pattern detects')
    )
    
    severity = models.CharField(
        _('Severity'),
        max_length=20,
        choices=SecurityThreat.SEVERITY_LEVELS,
        default='medium',
        help_text=_('Severity level for matches')
    )
    
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this pattern is active')
    )
    
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of what this pattern detects')
    )
    
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True,
        help_text=_('When this pattern was created')
    )
    
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True,
        help_text=_('When this pattern was last updated')
    )
    
    class Meta:
        verbose_name = _('Threat Pattern')
        verbose_name_plural = _('Threat Patterns')
        db_table = 'security_threat_patterns'
        ordering = ['name']
        indexes = [
            models.Index(fields=['pattern_type', 'is_active']),
            models.Index(fields=['threat_type', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.get_pattern_type_display()}"
