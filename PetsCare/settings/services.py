"""
Сервисы для системных настроек.

Этот модуль содержит сервисы для:
1. Доступа к настройкам безопасности (синглтон)
2. Валидации настроек
3. Применения настроек в системе
"""

import logging
from typing import Dict, Any, Optional
from django.core.cache import cache
from django.conf import settings as django_settings
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import SecuritySettings

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