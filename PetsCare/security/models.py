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


# === НОВЫЕ МОДЕЛИ ДЛЯ СИСТЕМЫ ПОЛИТИК БЕЗОПАСНОСТИ ===

class SecurityPolicy(models.Model):
    """Модель для определения политик безопасности"""
    
    POLICY_TYPES = [
        ('password', _('Password Policy')),
        ('session', _('Session Policy')),
        ('access', _('Access Policy')),
        ('data', _('Data Classification Policy')),
        ('network', _('Network Policy')),
        ('compliance', _('Compliance Policy')),
    ]
    
    SEVERITY_LEVELS = [
        ('low', _('Low')),
        ('medium', _('Medium')),
        ('high', _('High')),
        ('critical', _('Critical')),
    ]
    
    ACTION_CHOICES = [
        ('warn', _('Warning')),
        ('block', _('Block Access')),
        ('lockout', _('Account Lockout')),
        ('force_password_change', _('Force Password Change')),
        ('notify_admin', _('Notify Administrator')),
        ('log_violation', _('Log Violation')),
        ('terminate_session', _('Terminate Session')),
    ]
    
    name = models.CharField(
        _('Policy Name'),
        max_length=100,
        unique=True
    )
    
    policy_type = models.CharField(
        _('Policy Type'),
        max_length=20,
        choices=POLICY_TYPES
    )
    
    description = models.TextField(
        _('Description')
    )
    
    severity = models.CharField(
        _('Severity'),
        max_length=20,
        choices=SEVERITY_LEVELS,
        default='medium'
    )
    
    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )
    
    # Параметры политики (JSON)
    parameters = models.JSONField(
        _('Policy Parameters'),
        default=dict,
        help_text=_('Policy-specific parameters in JSON format')
    )
    
    # Действия при нарушении
    violation_actions = models.JSONField(
        _('Violation Actions'),
        default=list,
        help_text=_('List of actions to take on violation')
    )
    
    # Применимость к ролям
    applicable_roles = models.JSONField(
        _('Applicable Roles'),
        default=list,
        help_text=_('List of user roles this policy applies to')
    )
    
    # Применимость к группам пользователей
    applicable_groups = models.JSONField(
        _('Applicable Groups'),
        default=list,
        help_text=_('List of user groups this policy applies to')
    )
    
    # Исключения
    exceptions = models.JSONField(
        _('Exceptions'),
        default=list,
        help_text=_('List of exceptions (IPs, users, etc.)')
    )
    
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_policies',
        verbose_name=_('Created By')
    )
    
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_policies',
        verbose_name=_('Updated By')
    )
    
    class Meta:
        verbose_name = _('Security Policy')
        verbose_name_plural = _('Security Policies')
        db_table = 'security_policies'
        ordering = ['policy_type', 'name']
        indexes = [
            models.Index(fields=['policy_type', 'is_active']),
            models.Index(fields=['severity', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_policy_type_display()})"
    
    def get_parameters(self):
        """Получить параметры политики"""
        return self.parameters
    
    def get_violation_actions(self):
        """Получить действия при нарушении"""
        return self.violation_actions
    
    def is_applicable_to_user(self, user):
        """Проверить, применима ли политика к пользователю"""
        if not self.is_active:
            return False
        
        # Проверить исключения
        if user.email in self.exceptions.get('users', []):
            return False
        
        if user.id in self.exceptions.get('user_ids', []):
            return False
        
        # Проверить роли
        if self.applicable_roles:
            user_roles = [role.name for role in user.user_types.all()]
            if not any(role in user_roles for role in self.applicable_roles):
                return False
        
        # Проверить группы
        if self.applicable_groups:
            user_groups = [group.name for group in user.groups.all()]
            if not any(group in user_groups for group in self.applicable_groups):
                return False
        
        return True


class PolicyViolation(models.Model):
    """Модель для записи нарушений политик безопасности"""
    
    VIOLATION_STATUS = [
        ('detected', _('Detected')),
        ('investigating', _('Under Investigation')),
        ('resolved', _('Resolved')),
        ('false_positive', _('False Positive')),
        ('escalated', _('Escalated')),
    ]
    
    policy = models.ForeignKey(
        SecurityPolicy,
        on_delete=models.CASCADE,
        verbose_name=_('Policy')
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_('User')
    )
    
    violation_type = models.CharField(
        _('Violation Type'),
        max_length=50
    )
    
    description = models.TextField(
        _('Description')
    )
    
    severity = models.CharField(
        _('Severity'),
        max_length=20,
        choices=SecurityPolicy.SEVERITY_LEVELS
    )
    
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=VIOLATION_STATUS,
        default='detected'
    )
    
    # Контекст нарушения
    context_data = models.JSONField(
        _('Context Data'),
        default=dict,
        help_text=_('Additional context about the violation')
    )
    
    # IP адрес и другие детали
    ip_address = models.GenericIPAddressField(
        _('IP Address'),
        null=True,
        blank=True
    )
    
    user_agent = models.TextField(
        _('User Agent'),
        blank=True
    )
    
    request_path = models.CharField(
        _('Request Path'),
        max_length=500,
        blank=True
    )
    
    detected_at = models.DateTimeField(
        _('Detected At'),
        auto_now_add=True
    )
    
    resolved_at = models.DateTimeField(
        _('Resolved At'),
        null=True,
        blank=True
    )
    
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_violations',
        verbose_name=_('Resolved By')
    )
    
    notes = models.TextField(
        _('Notes'),
        blank=True
    )
    
    # Автоматические действия
    actions_taken = models.JSONField(
        _('Actions Taken'),
        default=list,
        help_text=_('List of actions taken in response to violation')
    )
    
    class Meta:
        verbose_name = _('Policy Violation')
        verbose_name_plural = _('Policy Violations')
        db_table = 'security_policy_violations'
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['policy', 'user']),
            models.Index(fields=['status', 'detected_at']),
            models.Index(fields=['severity', 'detected_at']),
        ]
    
    def __str__(self):
        return f"{self.policy.name} violation by {self.user.email} ({self.get_severity_display()})"
    
    def resolve(self, resolved_by=None, notes='', status='resolved'):
        """Разрешить нарушение"""
        self.status = status
        self.resolved_at = timezone.now()
        self.resolved_by = resolved_by
        if notes:
            self.notes = notes
        self.save()
        logger.info(f"Policy violation {self.id} resolved by {resolved_by}")
    
    def add_action_taken(self, action, details=None):
        """Добавить выполненное действие"""
        action_record = {
            'action': action,
            'timestamp': timezone.now().isoformat(),
            'details': details or {}
        }
        self.actions_taken.append(action_record)
        self.save()


class SessionPolicy(models.Model):
    """Модель для политик управления сессиями"""
    
    name = models.CharField(
        _('Policy Name'),
        max_length=100,
        unique=True
    )
    
    description = models.TextField(
        _('Description')
    )
    
    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )
    
    # Параметры сессий
    max_session_duration_hours = models.PositiveIntegerField(
        _('Max Session Duration (hours)'),
        default=24,
        help_text=_('Maximum session duration in hours')
    )
    
    max_concurrent_sessions = models.PositiveIntegerField(
        _('Max Concurrent Sessions'),
        default=3,
        help_text=_('Maximum number of concurrent sessions per user')
    )
    
    inactivity_timeout_minutes = models.PositiveIntegerField(
        _('Inactivity Timeout (minutes)'),
        default=30,
        help_text=_('Session timeout after inactivity')
    )
    
    force_logout_on_password_change = models.BooleanField(
        _('Force Logout on Password Change'),
        default=True
    )
    
    # Дополнительные параметры
    parameters = models.JSONField(
        _('Additional Parameters'),
        default=dict
    )
    
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )
    
    class Meta:
        verbose_name = _('Session Policy')
        verbose_name_plural = _('Session Policies')
        db_table = 'security_session_policies'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class AccessPolicy(models.Model):
    """Модель для политик контроля доступа"""
    
    ACCESS_TYPES = [
        ('ip_based', _('IP-based Access')),
        ('time_based', _('Time-based Access')),
        ('role_based', _('Role-based Access')),
        ('resource_based', _('Resource-based Access')),
        ('conditional', _('Conditional Access')),
    ]
    
    name = models.CharField(
        _('Policy Name'),
        max_length=100,
        unique=True
    )
    
    description = models.TextField(
        _('Description')
    )
    
    access_type = models.CharField(
        _('Access Type'),
        max_length=20,
        choices=ACCESS_TYPES
    )
    
    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )
    
    # Параметры доступа
    allowed_ips = models.JSONField(
        _('Allowed IPs'),
        default=list,
        help_text=_('List of allowed IP addresses')
    )
    
    allowed_time_ranges = models.JSONField(
        _('Allowed Time Ranges'),
        default=list,
        help_text=_('List of allowed time ranges')
    )
    
    allowed_roles = models.JSONField(
        _('Allowed Roles'),
        default=list,
        help_text=_('List of allowed user roles')
    )
    
    allowed_resources = models.JSONField(
        _('Allowed Resources'),
        default=list,
        help_text=_('List of allowed resources/endpoints')
    )
    
    conditions = models.JSONField(
        _('Access Conditions'),
        default=dict,
        help_text=_('Additional access conditions')
    )
    
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )
    
    class Meta:
        verbose_name = _('Access Policy')
        verbose_name_plural = _('Access Policies')
        db_table = 'security_access_policies'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_access_type_display()})"


class DataClassificationPolicy(models.Model):
    """Модель для политик классификации данных"""
    
    CLASSIFICATION_LEVELS = [
        ('public', _('Public')),
        ('internal', _('Internal')),
        ('confidential', _('Confidential')),
        ('restricted', _('Restricted')),
        ('secret', _('Secret')),
    ]
    
    name = models.CharField(
        _('Policy Name'),
        max_length=100,
        unique=True
    )
    
    description = models.TextField(
        _('Description')
    )
    
    classification_level = models.CharField(
        _('Classification Level'),
        max_length=20,
        choices=CLASSIFICATION_LEVELS
    )
    
    is_active = models.BooleanField(
        _('Is Active'),
        default=True
    )
    
    # Правила классификации
    classification_rules = models.JSONField(
        _('Classification Rules'),
        default=list,
        help_text=_('Rules for data classification')
    )
    
    # Требования к обработке
    handling_requirements = models.JSONField(
        _('Handling Requirements'),
        default=dict,
        help_text=_('Requirements for handling classified data')
    )
    
    # Ограничения доступа
    access_restrictions = models.JSONField(
        _('Access Restrictions'),
        default=dict,
        help_text=_('Access restrictions for classified data')
    )
    
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )
    
    class Meta:
        verbose_name = _('Data Classification Policy')
        verbose_name_plural = _('Data Classification Policies')
        db_table = 'security_data_classification_policies'
        ordering = ['classification_level', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.get_classification_level_display()})"
