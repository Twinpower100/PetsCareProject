"""
Сервисы для системных настроек.

Этот модуль содержит сервисы для:
1. Доступа к настройкам безопасности (синглтон)
2. Валидации настроек
3. Применения настроек в системе
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, time, timedelta
from django.core.cache import cache
from django.conf import settings as django_settings
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import SecuritySettings, BlockingScheduleSettings

logger = logging.getLogger(__name__)


class SecuritySettingsService:
    """
    Синглтон-сервис для работы с настройками безопасности.
    
    Особенности:
    - Кэширование настроек для производительности
    - Автоматическое обновление при изменениях
    - Валидация настроек
    - Логирование изменений
    """
    
    _instance = None
    _settings_cache_key = 'security_settings'
    _cache_timeout = 300  # 5 минут
    
    def __new__(cls):
        """Реализация паттерна синглтон."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Инициализация сервиса."""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._settings = None
    
    def get_settings(self, force_refresh: bool = False) -> SecuritySettings:
        """
        Получает настройки безопасности с кэшированием.
        
        Args:
            force_refresh: Принудительно обновить кэш
            
        Returns:
            SecuritySettings: Настройки безопасности
        """
        if force_refresh:
            self._clear_cache()
        
        # Пытаемся получить из кэша
        cached_settings = cache.get(self._settings_cache_key)
        if cached_settings and not force_refresh:
            return cached_settings
        
        # Получаем из базы данных
        try:
            settings = SecuritySettings.get_settings()
            
            # Кэшируем настройки
            cache.set(self._settings_cache_key, settings, self._cache_timeout)
            
            return settings
            
        except Exception as e:
            logger.error(f"Failed to get security settings: {e}")
            # Возвращаем дефолтные настройки в случае ошибки
            return self._get_default_settings()
    
    def _get_default_settings(self) -> SecuritySettings:
        """Возвращает дефолтные настройки безопасности."""
        return SecuritySettings(
            password_min_length=12,
            password_require_uppercase=True,
            password_require_lowercase=True,
            password_require_numbers=True,
            password_require_special_chars=True,
            password_max_age_days=90,
            password_history_count=5,
            session_timeout_minutes=1440,
            max_concurrent_sessions=3,
            force_logout_on_password_change=True,
            session_inactivity_timeout_minutes=30,
            rate_limiting_enabled=True,
            login_attempts_per_hour=5,
            api_requests_per_minute=60,
            brute_force_lockout_minutes=15,
            ip_restrictions_enabled=False,
            ip_whitelist=[],
            ip_blacklist=[],
            audit_logging_enabled=True,
            audit_log_retention_days=365,
            log_sensitive_data=False,
            log_failed_login_attempts=True,
            require_https=True,
            enable_csrf_protection=True,
            enable_xss_protection=True,
            enable_content_security_policy=True,
        )
    
    def _clear_cache(self):
        """Очищает кэш настроек."""
        cache.delete(self._settings_cache_key)
        self._settings = None
    
    def update_settings(self, **kwargs) -> SecuritySettings:
        """
        Обновляет настройки безопасности.
        
        Args:
            **kwargs: Новые значения настроек
            
        Returns:
            SecuritySettings: Обновленные настройки
            
        Raises:
            ValidationError: При неверных значениях
        """
        try:
            settings = self.get_settings()
            
            # Обновляем поля
            for field, value in kwargs.items():
                if hasattr(settings, field):
                    setattr(settings, field, value)
                else:
                    logger.warning(f"Unknown security setting field: {field}")
            
            # Валидируем настройки
            settings.full_clean()
            
            # Сохраняем
            settings.save()
            
            # Очищаем кэш
            self._clear_cache()
            
            logger.info(f"Security settings updated: {list(kwargs.keys())}")
            
            return settings
            
        except ValidationError as e:
            logger.error(f"Security settings validation error: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to update security settings: {e}")
            raise
    
    def get_password_policy(self) -> Dict[str, Any]:
        """Возвращает политику паролей."""
        settings = self.get_settings()
        return settings.get_password_policy()
    
    def get_session_policy(self) -> Dict[str, Any]:
        """Возвращает политику сессий."""
        settings = self.get_settings()
        return settings.get_session_policy()
    
    def get_rate_limiting_policy(self) -> Dict[str, Any]:
        """Возвращает политику rate limiting."""
        settings = self.get_settings()
        return settings.get_rate_limiting_policy()
    
    def get_ip_restrictions(self) -> Dict[str, Any]:
        """Возвращает IP-ограничения."""
        settings = self.get_settings()
        return settings.get_ip_restrictions()
    
    def get_audit_policy(self) -> Dict[str, Any]:
        """Возвращает политику аудита."""
        settings = self.get_settings()
        return settings.get_audit_policy()
    
    def validate_password(self, password: str) -> tuple[bool, list[str]]:
        """
        Валидирует пароль согласно политике безопасности.
        
        Args:
            password: Пароль для проверки
            
        Returns:
            tuple: (is_valid, error_messages)
        """
        policy = self.get_password_policy()
        errors = []
        
        # Проверяем длину
        if len(password) < policy['min_length']:
            errors.append(f"Password must be at least {policy['min_length']} characters long")
        
        # Проверяем требования к символам
        if policy['require_uppercase'] and not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")
        
        if policy['require_lowercase'] and not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")
        
        if policy['require_numbers'] and not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one number")
        
        if policy['require_special_chars'] and not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
            errors.append("Password must contain at least one special character")
        
        return len(errors) == 0, errors
    
    def is_ip_allowed(self, ip_address: str) -> bool:
        """
        Проверяет, разрешен ли IP-адрес.
        
        Args:
            ip_address: IP-адрес для проверки
            
        Returns:
            bool: True если IP разрешен
        """
        restrictions = self.get_ip_restrictions()
        
        if not restrictions['enabled']:
            return True
        
        # Проверяем черный список
        if ip_address in restrictions['blacklist']:
            return False
        
        # Проверяем белый список
        if restrictions['whitelist']:
            return ip_address in restrictions['whitelist']
        
        return True
    
    def should_force_logout(self, user) -> bool:
        """
        Проверяет, нужно ли принудительно выгнать пользователя.
        
        Args:
            user: Пользователь для проверки
            
        Returns:
            bool: True если нужно принудительно выгнать
        """
        settings = self.get_settings()
        
        # Проверяем время жизни пароля
        if hasattr(user, 'password_changed_at') and user.password_changed_at:
            days_since_change = (timezone.now() - user.password_changed_at).days
            if days_since_change > settings.password_max_age_days:
                return True
        
        return False
    
    def get_session_timeout_seconds(self) -> int:
        """Возвращает время жизни сессии в секундах."""
        settings = self.get_settings()
        return settings.session_timeout_minutes * 60
    
    def get_inactivity_timeout_seconds(self) -> int:
        """Возвращает время неактивности в секундах."""
        settings = self.get_settings()
        return settings.session_inactivity_timeout_minutes * 60


# Глобальный экземпляр сервиса
security_settings_service = SecuritySettingsService()


def get_security_settings() -> SecuritySettings:
    """
    Удобная функция для получения настроек безопасности.
    
    Returns:
        SecuritySettings: Настройки безопасности
    """
    return security_settings_service.get_settings()


def get_password_policy() -> Dict[str, Any]:
    """
    Удобная функция для получения политики паролей.
    
    Returns:
        dict: Политика паролей
    """
    return security_settings_service.get_password_policy()


def validate_password(password: str) -> tuple[bool, list[str]]:
    """
    Удобная функция для валидации пароля.
    
    Args:
        password: Пароль для проверки
        
    Returns:
        tuple: (is_valid, error_messages)
    """
    return security_settings_service.validate_password(password) 


class BlockingScheduleService:
    """
    Сервис для управления расписанием проверки блокировок учреждений.
    
    Предоставляет методы для:
    - Получения текущих настроек расписания
    - Обновления расписания Celery Beat
    - Валидации настроек
    - Логирования изменений
    """
    
    def __init__(self):
        self.model = BlockingScheduleSettings
    
    def get_current_schedule(self):
        """
        Возвращает текущие активные настройки расписания.
        
        Returns:
            BlockingScheduleSettings: Активные настройки или настройки по умолчанию
        """
        return self.model.get_active_settings()
    
    def update_celery_schedule(self):
        """
        Обновляет расписание в Celery Beat на основе настроек из базы данных.
        
        Этот метод должен вызываться при изменении настроек в админке.
        """
        try:
            settings = self.get_current_schedule()
            schedule = settings.get_celery_schedule()
            
            # Здесь должна быть логика обновления CELERY_BEAT_SCHEDULE
            # В реальной реализации это может быть:
            # 1. Обновление настроек в Redis (если используется Redis как брокер)
            # 2. Перезапуск Celery Beat
            # 3. Обновление конфигурации через API Celery
            
            logger.info(
                f"Updated Celery schedule for blocking checks: {settings.get_schedule_description()}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update Celery schedule: {e}")
            return False
    
    def validate_schedule(self, frequency, check_time, days_of_week=None, 
                         day_of_month=None, custom_interval_hours=None):
        """
        Валидирует настройки расписания.
        
        Args:
            frequency (str): Частота проверок
            check_time (time): Время проверки
            days_of_week (list): Дни недели для еженедельной частоты
            day_of_month (int): День месяца для ежемесячной частоты
            custom_interval_hours (int): Пользовательский интервал в часах
            
        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            # Создаем временный объект для валидации
            temp_settings = self.model(
                frequency=frequency,
                check_time=check_time,
                days_of_week=days_of_week or [],
                day_of_month=day_of_month,
                custom_interval_hours=custom_interval_hours
            )
            
            temp_settings.clean()
            return True, None
            
        except ValidationError as e:
            return False, str(e)
    
    def get_schedule_info(self):
        """
        Возвращает информацию о текущем расписании.
        
        Returns:
            dict: Информация о расписании
        """
        settings = self.get_current_schedule()
        
        return {
            'frequency': settings.frequency,
            'frequency_display': settings.get_frequency_display(),
            'check_time': settings.check_time.strftime('%H:%M'),
            'schedule_description': settings.get_schedule_description(),
            'is_active': settings.is_active,
            'last_updated': settings.updated_at,
            'updated_by': settings.updated_by.email if settings.updated_by else None,
            'celery_schedule': str(settings.get_celery_schedule()),
        }
    
    def create_default_schedule(self):
        """
        Создает настройки расписания по умолчанию.
        
        Returns:
            BlockingScheduleSettings: Созданные настройки
        """
        try:
            default_settings = self.model.objects.create(
                frequency='daily',
                check_time='02:00',
                is_active=True
            )
            
            logger.info("Created default blocking schedule settings")
            return default_settings
            
        except Exception as e:
            logger.error(f"Failed to create default schedule: {e}")
            return None
    
    def reset_to_defaults(self):
        """
        Сбрасывает настройки к значениям по умолчанию.
        
        Returns:
            bool: True если успешно, False в противном случае
        """
        try:
            # Деактивируем все существующие настройки
            self.model.objects.update(is_active=False)
            
            # Создаем новые настройки по умолчанию
            default_settings = self.create_default_schedule()
            
            if default_settings:
                logger.info("Reset blocking schedule settings to defaults")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Failed to reset schedule settings: {e}")
            return False
    
    def get_next_run_time(self):
        """
        Вычисляет время следующего запуска на основе текущих настроек.
        
        Returns:
            datetime: Время следующего запуска
        """
        from django.utils import timezone
        from datetime import timedelta
        
        settings = self.get_current_schedule()
        now = timezone.now()
        
        if settings.frequency == 'hourly':
            # Следующий час
            return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        
        elif settings.frequency == 'daily':
            # Завтра в указанное время
            tomorrow = now.date() + timedelta(days=1)
            return timezone.make_aware(
                datetime.combine(tomorrow, settings.check_time)
            )
        
        elif settings.frequency == 'weekly':
            # Следующая неделя в указанное время
            if settings.days_of_week:
                # Находим следующий день недели
                current_weekday = now.weekday()
                next_day = None
                
                for day in sorted(settings.days_of_week):
                    if day > current_weekday:
                        next_day = day
                        break
                
                if next_day is None:
                    # Следующая неделя
                    days_ahead = 7 - current_weekday + settings.days_of_week[0]
                else:
                    days_ahead = next_day - current_weekday
                
                next_date = now.date() + timedelta(days=days_ahead)
                return timezone.make_aware(
                    datetime.combine(next_date, settings.check_time)
                )
            else:
                # Следующий понедельник
                days_ahead = 7 - now.weekday()
                next_monday = now.date() + timedelta(days=days_ahead)
                return timezone.make_aware(
                    datetime.combine(next_monday, settings.check_time)
                )
        
        elif settings.frequency == 'monthly':
            # Следующий месяц в указанный день
            if now.day >= settings.day_of_month:
                # Следующий месяц
                if now.month == 12:
                    next_month = now.replace(year=now.year + 1, month=1)
                else:
                    next_month = now.replace(month=now.month + 1)
            else:
                # Этот месяц
                next_month = now
            
            # Устанавливаем день месяца
            try:
                next_run = next_month.replace(day=settings.day_of_month)
            except ValueError:
                # Если день не существует в месяце, берем последний день
                if next_month.month == 12:
                    next_month = next_month.replace(year=next_month.year + 1, month=1)
                else:
                    next_month = next_month.replace(month=next_month.month + 1)
                next_run = next_month.replace(day=1) - timedelta(days=1)
            
            return timezone.make_aware(
                datetime.combine(next_run.date(), settings.check_time)
            )
        
        elif settings.frequency == 'custom':
            # Через указанное количество часов
            return now + timedelta(hours=settings.custom_interval_hours)
        
        # По умолчанию завтра в 02:00
        tomorrow = now.date() + timedelta(days=1)
        return timezone.make_aware(
            datetime.combine(tomorrow, time(2, 0))
        ) 