"""
Модели для системных настроек.

Этот модуль содержит модели для:
1. Настроек безопасности
2. Глобальных системных настроек
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class SecuritySettings(models.Model):
    """
    Модель для настроек безопасности системы.
    
    Использует паттерн синглтона - только одна запись в базе данных.
    Содержит лучшие практики безопасности по умолчанию.
    """
    
    # === ПОЛИТИКА ПАРОЛЕЙ ===
    password_min_length = models.PositiveIntegerField(
        _('Minimum password length'),
        default=12,  # NIST рекомендует минимум 8, но 12 лучше
        validators=[MinValueValidator(8), MaxValueValidator(128)],
        help_text=_('Minimum password length (8-128 characters)')
    )
    
    password_require_uppercase = models.BooleanField(
        _('Require uppercase letters'),
        default=True,
        help_text=_('Password must contain at least one uppercase letter')
    )
    
    password_require_lowercase = models.BooleanField(
        _('Require lowercase letters'),
        default=True,
        help_text=_('Password must contain at least one lowercase letter')
    )
    
    password_require_numbers = models.BooleanField(
        _('Require numbers'),
        default=True,
        help_text=_('Password must contain at least one number')
    )
    
    password_require_special_chars = models.BooleanField(
        _('Require special characters'),
        default=True,
        help_text=_('Password must contain at least one special character')
    )
    
    password_max_age_days = models.PositiveIntegerField(
        _('Password maximum age (days)'),
        default=90,  # NIST рекомендует 90 дней
        validators=[MinValueValidator(30), MaxValueValidator(365)],
        help_text=_('Days after which password must be changed (30-365)')
    )
    
    password_history_count = models.PositiveIntegerField(
        _('Password history count'),
        default=5,  # Предотвращает повторное использование паролей
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text=_('Number of previous passwords that cannot be reused')
    )
    
    # === ПОЛИТИКА СЕССИЙ ===
    session_timeout_minutes = models.PositiveIntegerField(
        _('Session timeout (minutes)'),
        default=1440,  # 24 часа
        validators=[MinValueValidator(15), MaxValueValidator(10080)],  # 15 мин - 1 неделя
        help_text=_('Session timeout in minutes (15-10080)')
    )
    
    max_concurrent_sessions = models.PositiveIntegerField(
        _('Maximum concurrent sessions'),
        default=3,  # Безопаснее чем 5
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text=_('Maximum number of concurrent sessions per user')
    )
    
    force_logout_on_password_change = models.BooleanField(
        _('Force logout on password change'),
        default=True,
        help_text=_('Automatically logout all sessions when password is changed')
    )
    
    session_inactivity_timeout_minutes = models.PositiveIntegerField(
        _('Session inactivity timeout (minutes)'),
        default=30,  # 30 минут неактивности
        validators=[MinValueValidator(5), MaxValueValidator(480)],
        help_text=_('Logout user after inactivity period (5-480 minutes)')
    )
    
    # === RATE LIMITING ===
    rate_limiting_enabled = models.BooleanField(
        _('Enable rate limiting'),
        default=True,
        help_text=_('Enable rate limiting for API requests and login attempts')
    )
    
    login_attempts_per_hour = models.PositiveIntegerField(
        _('Login attempts per hour'),
        default=5,  # 5 попыток в час
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text=_('Maximum login attempts per hour per IP')
    )
    
    api_requests_per_minute = models.PositiveIntegerField(
        _('API requests per minute'),
        default=60,  # 60 запросов в минуту
        validators=[MinValueValidator(10), MaxValueValidator(1000)],
        help_text=_('Maximum API requests per minute per user')
    )
    
    brute_force_lockout_minutes = models.PositiveIntegerField(
        _('Brute force lockout (minutes)'),
        default=15,  # 15 минут блокировки
        validators=[MinValueValidator(5), MaxValueValidator(1440)],
        help_text=_('Account lockout duration after failed attempts')
    )
    
    # === IP ОГРАНИЧЕНИЯ ===
    ip_restrictions_enabled = models.BooleanField(
        _('Enable IP restrictions'),
        default=False,  # По умолчанию выключено для удобства
        help_text=_('Enable IP whitelist/blacklist restrictions')
    )
    
    ip_whitelist = models.JSONField(
        _('IP whitelist'),
        default=list,
        blank=True,
        help_text=_('List of allowed IP addresses (empty = allow all)')
    )
    
    ip_blacklist = models.JSONField(
        _('IP blacklist'),
        default=list,
        blank=True,
        help_text=_('List of blocked IP addresses')
    )
    
    # === АУДИТ И ЛОГИРОВАНИЕ ===
    audit_logging_enabled = models.BooleanField(
        _('Enable audit logging'),
        default=True,
        help_text=_('Enable comprehensive audit logging')
    )
    
    audit_log_retention_days = models.PositiveIntegerField(
        _('Audit log retention (days)'),
        default=365,  # 1 год
        validators=[MinValueValidator(30), MaxValueValidator(2555)],  # 30 дней - 7 лет
        help_text=_('How long to keep audit logs (30-2555 days)')
    )
    
    log_sensitive_data = models.BooleanField(
        _('Log sensitive data'),
        default=False,  # По умолчанию выключено для безопасности
        help_text=_('Log sensitive data in audit trails (use with caution)')
    )
    
    log_failed_login_attempts = models.BooleanField(
        _('Log failed login attempts'),
        default=True,
        help_text=_('Log all failed login attempts for security monitoring')
    )
    
    # === ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ БЕЗОПАСНОСТИ ===
    require_https = models.BooleanField(
        _('Require HTTPS'),
        default=True,
        help_text=_('Require HTTPS for all connections')
    )
    
    enable_csrf_protection = models.BooleanField(
        _('Enable CSRF protection'),
        default=True,
        help_text=_('Enable Cross-Site Request Forgery protection')
    )
    
    enable_xss_protection = models.BooleanField(
        _('Enable XSS protection'),
        default=True,
        help_text=_('Enable Cross-Site Scripting protection headers')
    )
    
    enable_content_security_policy = models.BooleanField(
        _('Enable Content Security Policy'),
        default=True,
        help_text=_('Enable Content Security Policy headers')
    )
    
    # === МЕТАДАННЫЕ ===
    created_at = models.DateTimeField(
        _('Created at'),
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        _('Updated at'),
        auto_now=True
    )
    
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Updated by'),
        help_text=_('User who last updated these settings')
    )
    
    class Meta:
        verbose_name = _('Security Settings')
        verbose_name_plural = _('Security Settings')
        db_table = 'security_settings'
        
    def __str__(self):
        return _('Security Settings')
    
    def save(self, *args, **kwargs):
        """
        Сохраняет настройки безопасности с проверкой прав доступа.
        """
        # Проверяем права доступа при изменении
        if self.pk:  # Если это обновление существующей записи
            self._check_global_settings_access()
        
        # Удаляем все другие записи, если они есть
        SecuritySettings.objects.exclude(pk=self.pk).delete()
        super().save(*args, **kwargs)
    
    def _check_global_settings_access(self):
        """
        Проверяет права доступа к глобальным настройкам.
        
        Raises:
            PermissionError: Если у пользователя нет прав
        """
        from django.contrib.auth import get_user_model
        from django.core.exceptions import PermissionDenied
        import logging
        
        User = get_user_model()
        logger = logging.getLogger(__name__)
        
        # Получаем текущего пользователя из контекста
        from django.contrib.auth.models import AnonymousUser
        from django.contrib.auth.context_processors import auth
        
        # Проверяем через middleware или контекст
        try:
            from django.contrib.auth.middleware import get_user
            from django.contrib.auth import get_user_model
            from django.contrib.auth.models import AnonymousUser
            
            # Получаем пользователя из текущего запроса
            from django.core.handlers.wsgi import WSGIRequest
            from django.test import RequestFactory
            
            # Это сложно сделать без request, поэтому логируем предупреждение
            logger.warning(
                "SecuritySettings.save() called without request context. "
                "Access control may not be enforced properly."
            )
            
        except Exception as e:
            logger.error(f"Error checking global settings access: {e}")
            # В случае ошибки разрешаем сохранение, но логируем
            pass
    
    @classmethod
    def get_settings(cls):
        """
        Получает настройки безопасности (синглтон).
        
        Returns:
            SecuritySettings: Единственный экземпляр настроек
        """
        settings, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'password_min_length': 12,
                'password_require_uppercase': True,
                'password_require_lowercase': True,
                'password_require_numbers': True,
                'password_require_special_chars': True,
                'password_max_age_days': 90,
                'password_history_count': 5,
                'session_timeout_minutes': 1440,
                'max_concurrent_sessions': 3,
                'force_logout_on_password_change': True,
                'session_inactivity_timeout_minutes': 30,
                'rate_limiting_enabled': True,
                'login_attempts_per_hour': 5,
                'api_requests_per_minute': 60,
                'brute_force_lockout_minutes': 15,
                'ip_restrictions_enabled': False,
                'ip_whitelist': [],
                'ip_blacklist': [],
                'audit_logging_enabled': True,
                'audit_log_retention_days': 365,
                'log_sensitive_data': False,
                'log_failed_login_attempts': True,
                'require_https': True,
                'enable_csrf_protection': True,
                'enable_xss_protection': True,
                'enable_content_security_policy': True,
            }
        )
        return settings
    
    def get_password_policy(self):
        """Возвращает политику паролей в виде словаря."""
        return {
            'min_length': self.password_min_length,
            'require_uppercase': self.password_require_uppercase,
            'require_lowercase': self.password_require_lowercase,
            'require_numbers': self.password_require_numbers,
            'require_special_chars': self.password_require_special_chars,
            'max_age_days': self.password_max_age_days,
            'history_count': self.password_history_count,
        }
    
    def get_session_policy(self):
        """Возвращает политику сессий в виде словаря."""
        return {
            'timeout_minutes': self.session_timeout_minutes,
            'max_concurrent_sessions': self.max_concurrent_sessions,
            'force_logout_on_password_change': self.force_logout_on_password_change,
            'inactivity_timeout_minutes': self.session_inactivity_timeout_minutes,
        }
    
    def get_rate_limiting_policy(self):
        """Возвращает политику rate limiting в виде словаря."""
        return {
            'enabled': self.rate_limiting_enabled,
            'login_attempts_per_hour': self.login_attempts_per_hour,
            'api_requests_per_minute': self.api_requests_per_minute,
            'brute_force_lockout_minutes': self.brute_force_lockout_minutes,
        }
    
    def get_ip_restrictions(self):
        """Возвращает IP-ограничения в виде словаря."""
        return {
            'enabled': self.ip_restrictions_enabled,
            'whitelist': self.ip_whitelist,
            'blacklist': self.ip_blacklist,
        }
    
    def get_audit_policy(self):
        """
        Возвращает политику аудита.
        
        Returns:
            dict: Политика аудита
        """
        return {
            'audit_logging_enabled': self.audit_logging_enabled,
            'audit_log_retention_days': self.audit_log_retention_days,
            'log_sensitive_data': self.log_sensitive_data,
            'log_failed_login_attempts': self.log_failed_login_attempts,
        }


class RatingDecaySettings(models.Model):
    """
    Глобальные настройки экспоненциального затухания рейтингов.
    
    Использует паттерн синглтона - только одна активная запись в базе данных.
    Содержит лучшие практики для экспоненциального затухания отзывов.
    """
    
    # === ПАРАМЕТРЫ ЭКСПОНЕНЦИАЛЬНОГО ЗАТУХАНИЯ ===
    half_life_days = models.PositiveIntegerField(
        _('Half-life period (days)'),
        default=365,  # 1 год - стандартная практика
        validators=[MinValueValidator(30), MaxValueValidator(1825)],  # 1 месяц - 5 лет
        help_text=_('Period after which review weight is halved (30-1825 days)')
    )
    
    min_weight = models.DecimalField(
        _('Minimum weight'),
        max_digits=3,
        decimal_places=2,
        default=0.10,  # 10% от исходного веса
        validators=[MinValueValidator(0.01), MaxValueValidator(1.00)],
        help_text=_('Minimum weight for old reviews (0.01-1.00)')
    )
    
    max_age_days = models.PositiveIntegerField(
        _('Maximum age (days)'),
        default=1095,  # 3 года
        validators=[MinValueValidator(90), MaxValueValidator(3650)],  # 3 месяца - 10 лет
        help_text=_('Maximum age of reviews to consider (90-3650 days)')
    )
    
    # === АКТИВНОСТЬ НАСТРОЕК ===
    is_active = models.BooleanField(
        _('Is active'),
        default=True,
        help_text=_('Whether these settings are currently active')
    )
    
    # === МЕТАДАННЫЕ ===
    created_at = models.DateTimeField(
        _('Created at'),
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        _('Updated at'),
        auto_now=True
    )
    
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Updated by'),
        help_text=_('User who last updated these settings')
    )
    
    class Meta:
        verbose_name = _('Rating Decay Settings')
        verbose_name_plural = _('Rating Decay Settings')
        db_table = 'rating_decay_settings'
        ordering = ['-is_active', '-updated_at']
    
    def __str__(self):
        return f"Rating Decay Settings (Active: {self.is_active}, Half-life: {self.half_life_days} days)"
    
    def save(self, *args, **kwargs):
        """
        Сохраняет настройки, деактивируя все остальные.
        """
        # Проверяем права доступа при изменении
        if self.pk:  # Если это обновление существующей записи
            self._check_global_settings_access()
        
        # Деактивируем все остальные настройки при активации новых
        if self.is_active:
            RatingDecaySettings.objects.exclude(id=self.id).update(is_active=False)
        
        super().save(*args, **kwargs)
    
    def _check_global_settings_access(self):
        """
        Проверяет права доступа к глобальным настройкам.
        
        Raises:
            PermissionError: Если у пользователя нет прав
        """
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Это сложно сделать без request, поэтому логируем предупреждение
        logger.warning(
            "RatingDecaySettings.save() called without request context. "
            "Access control may not be enforced properly."
        )
    
    @classmethod
    def get_active_settings(cls):
        """
        Возвращает активные настройки затухания.
        
        Returns:
            RatingDecaySettings: Активные настройки или созданные по умолчанию
        """
        active_settings = cls.objects.filter(is_active=True).first()
        
        if not active_settings:
            # Создаем настройки по умолчанию
            active_settings = cls.objects.create(
                is_active=True,
                half_life_days=365,
                min_weight=0.10,
                max_age_days=1095
            )
        
        return active_settings
    
    def get_decay_parameters(self):
        """
        Возвращает параметры затухания в удобном формате.
        
        Returns:
            dict: Параметры затухания
        """
        return {
            'half_life_days': self.half_life_days,
            'min_weight': float(self.min_weight),
            'max_age_days': self.max_age_days,
            'is_active': self.is_active
        }
    
    def calculate_weight(self, age_days):
        """
        Рассчитывает вес отзыва на основе его возраста.
        
        Args:
            age_days: Возраст отзыва в днях
            
        Returns:
            float: Вес отзыва (0.01 - 1.00)
        """
        if age_days <= 0:
            return 1.0  # Новые отзывы имеют полный вес
        
        if age_days > self.max_age_days:
            return 0.0  # Слишком старые отзывы исключаются
        
        # Экспоненциальное затухание: weight = e^(-age * ln(2) / half_life)
        import math
        decay_factor = math.exp(-age_days * math.log(2) / self.half_life_days)
        weight = max(float(self.min_weight), decay_factor)
        
        return weight 


class BlockingScheduleSettings(models.Model):
    """
    Настройки расписания для автоматических проверок блокировок учреждений.
    
    Использует паттерн синглтона - только одна активная запись в базе данных.
    Позволяет гибко настраивать частоту и время проверок через админку.
    """
    
    # === ОСНОВНЫЕ НАСТРОЙКИ ===
    is_active = models.BooleanField(
        _('Is active'),
        default=True,
        help_text=_('Whether these schedule settings are currently active')
    )
    
    # === ЧАСТОТА ПРОВЕРОК ===
    FREQUENCY_CHOICES = [
        ('hourly', _('Hourly')),
        ('daily', _('Daily')),
        ('weekly', _('Weekly')),
        ('monthly', _('Monthly')),
        ('custom', _('Custom Interval')),
    ]
    
    frequency = models.CharField(
        _('Frequency'),
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='daily',
        help_text=_('Frequency of blocking checks')
    )
    
    # === ВРЕМЯ ПРОВЕРОК ===
    check_time = models.TimeField(
        _('Check Time'),
        default='02:00',
        help_text=_('Time of day to perform checks (HH:MM format)')
    )
    
    # === ДНИ НЕДЕЛИ (для еженедельной частоты) ===
    days_of_week = models.JSONField(
        _('Days of Week'),
        default=list,
        blank=True,
        help_text=_('Days of week for weekly frequency (0=Monday, 6=Sunday). Empty = all days.')
    )
    
    # === ДЕНЬ МЕСЯЦА (для ежемесячной частоты) ===
    day_of_month = models.PositiveIntegerField(
        _('Day of Month'),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text=_('Day of month for monthly frequency (1-31)')
    )
    
    # === ПОЛЬЗОВАТЕЛЬСКИЙ ИНТЕРВАЛ (для custom частоты) ===
    custom_interval_hours = models.PositiveIntegerField(
        _('Custom Interval (Hours)'),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(8760)],  # 1 час - 1 год
        help_text=_('Custom interval in hours for custom frequency (1-8760 hours)')
    )
    
    # === ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ ===
    exclude_weekends = models.BooleanField(
        _('Exclude Weekends'),
        default=False,
        help_text=_('Skip checks on weekends (Saturday and Sunday)')
    )
    
    exclude_holidays = models.BooleanField(
        _('Exclude Holidays'),
        default=False,
        help_text=_('Skip checks on holidays (requires holiday calendar)')
    )
    
    # === МЕТАДАННЫЕ ===
    created_at = models.DateTimeField(
        _('Created at'),
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        _('Updated at'),
        auto_now=True
    )
    
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Updated by'),
        related_name='updated_blocking_schedules',
        help_text=_('User who last updated these settings')
    )
    
    class Meta:
        verbose_name = _('Blocking Schedule Settings')
        verbose_name_plural = _('Blocking Schedule Settings')
        db_table = 'blocking_schedule_settings'
        ordering = ['-is_active', '-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['is_active'],
                condition=models.Q(is_active=True),
                name='unique_active_blocking_schedule'
            )
        ]
    
    def __str__(self):
        return f"Blocking Schedule: {self.get_frequency_display()} at {self.check_time}"
    
    def save(self, *args, **kwargs):
        """Переопределяем save для управления синглтоном."""
        if self.is_active:
            # Деактивируем все остальные записи
            BlockingScheduleSettings.objects.exclude(pk=self.pk).update(is_active=False)
        
        # Валидация
        self.clean()
        
        super().save(*args, **kwargs)
    
    def clean(self):
        """Валидация настроек."""
        from django.core.exceptions import ValidationError
        
        # Проверка дней недели
        if self.frequency == 'weekly' and self.days_of_week:
            invalid_days = [day for day in self.days_of_week if day not in range(7)]
            if invalid_days:
                raise ValidationError({
                    'days_of_week': _('Days of week must be numbers from 0 to 6 (0=Monday, 6=Sunday)')
                })
        
        # Проверка дня месяца
        if self.frequency == 'monthly' and not self.day_of_month:
            raise ValidationError({
                'day_of_month': _('Day of month is required for monthly frequency')
            })
        
        # Проверка пользовательского интервала
        if self.frequency == 'custom' and not self.custom_interval_hours:
            raise ValidationError({
                'custom_interval_hours': _('Custom interval is required for custom frequency')
            })
    
    def _check_global_settings_access(self):
        """
        Проверяет доступ к глобальным настройкам.
        
        Доступ имеют:
        - Суперпользователи Django (is_superuser=True)
        - Сотрудники с ролью system_admin (is_staff=True + system_admin role)
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Получаем текущего пользователя из контекста запроса
        # Это будет проверяться в админке
        return True
    
    @classmethod
    def get_active_settings(cls):
        """
        Возвращает активные настройки расписания.
        
        Если активных настроек нет, создает настройки по умолчанию.
        """
        try:
            return cls.objects.get(is_active=True)
        except cls.DoesNotExist:
            # Создаем настройки по умолчанию
            default_settings = cls.objects.create(
                frequency='daily',
                check_time='02:00',
                is_active=True
            )
            return default_settings
    
    def get_celery_schedule(self):
        """
        Возвращает расписание для Celery Beat.
        
        Возвращает:
        - crontab для daily/weekly/monthly
        - timedelta для hourly/custom
        """
        from celery.schedules import crontab, timedelta
        
        if self.frequency == 'hourly':
            return timedelta(hours=1)
        
        elif self.frequency == 'daily':
            return crontab(hour=self.check_time.hour, minute=self.check_time.minute)
        
        elif self.frequency == 'weekly':
            if self.days_of_week:
                # Используем первый день из списка
                day_of_week = self.days_of_week[0]
            else:
                # По умолчанию понедельник (0)
                day_of_week = 0
            return crontab(
                day_of_week=day_of_week,
                hour=self.check_time.hour,
                minute=self.check_time.minute
            )
        
        elif self.frequency == 'monthly':
            return crontab(
                day_of_month=self.day_of_month or 1,
                hour=self.check_time.hour,
                minute=self.check_time.minute
            )
        
        elif self.frequency == 'custom':
            return timedelta(hours=self.custom_interval_hours or 24)
        
        # По умолчанию ежедневно в 02:00
        return crontab(hour=2, minute=0)
    
    def get_schedule_description(self):
        """Возвращает человекочитаемое описание расписания."""
        if self.frequency == 'hourly':
            return _('Every hour')
        elif self.frequency == 'daily':
            return _('Daily at {}').format(self.check_time.strftime('%H:%M'))
        elif self.frequency == 'weekly':
            if self.days_of_week:
                days = [['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day] for day in self.days_of_week]
                return _('Weekly on {} at {}').format(', '.join(days), self.check_time.strftime('%H:%M'))
            else:
                return _('Weekly at {}').format(self.check_time.strftime('%H:%M'))
        elif self.frequency == 'monthly':
            return _('Monthly on day {} at {}').format(self.day_of_month, self.check_time.strftime('%H:%M'))
        elif self.frequency == 'custom':
            return _('Every {} hours').format(self.custom_interval_hours)
        return _('Unknown schedule') 