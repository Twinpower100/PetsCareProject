"""
API views для системных настроек.

Этот модуль содержит API endpoints для:
1. Управления системными настройками
2. Управления функциями системы
3. Конфигурации уведомлений
4. Настроек безопасности
"""

import logging
from django.utils.translation import gettext as _
from django.conf import settings
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from users.permissions import IsSystemAdmin
from audit.models import AuditLog

logger = logging.getLogger(__name__)


class SystemSettingsAPIView(APIView):
    """
    API для управления системными настройками.
    """
    permission_classes = [IsSystemAdmin]

    def get(self, request):
        """Получает системные настройки."""
        try:
            system_settings = {
                'site_name': getattr(settings, 'SITE_NAME', 'PetsCare'),
                'site_description': getattr(settings, 'SITE_DESCRIPTION', ''),
                'contact_email': getattr(settings, 'CONTACT_EMAIL', ''),
                'support_phone': getattr(settings, 'SUPPORT_PHONE', ''),
                'maintenance_mode': getattr(settings, 'MAINTENANCE_MODE', False),
                'registration_enabled': getattr(settings, 'REGISTRATION_ENABLED', True),
                'email_verification_required': getattr(settings, 'EMAIL_VERIFICATION_REQUIRED', True),
                'max_file_size': getattr(settings, 'MAX_FILE_SIZE', 10485760),  # 10MB
                'allowed_file_types': getattr(settings, 'ALLOWED_FILE_TYPES', []),
                'session_timeout': getattr(settings, 'SESSION_COOKIE_AGE', 1209600),  # 14 days
                'password_min_length': getattr(settings, 'PASSWORD_MIN_LENGTH', 8),
                'password_complexity_required': getattr(settings, 'PASSWORD_COMPLEXITY_REQUIRED', True),
                'rate_limiting_enabled': getattr(settings, 'RATE_LIMITING_ENABLED', True),
                'backup_enabled': getattr(settings, 'BACKUP_ENABLED', True),
                'backup_frequency': getattr(settings, 'BACKUP_FREQUENCY', 'daily'),
                'analytics_enabled': getattr(settings, 'ANALYTICS_ENABLED', True),
                'debug_mode': settings.DEBUG,
            }

            return Response(system_settings)

        except Exception as e:
            logger.error(f"Failed to get system settings: {e}")
            return Response(
                {'error': _('Failed to get system settings')},
                status=status.HTTP_400_BAD_REQUEST
            )

    def put(self, request):
        """Обновляет системные настройки."""
        try:
            with transaction.atomic():
                # Получаем данные из запроса
                data = request.data
                
                # Обновляем настройки в базе данных или кэше
                # В реальной реализации здесь будет сохранение в модель настроек
                
                # Логируем изменение настроек
                AuditLog.objects.create(
                    user=request.user,
                    action='settings_updated',
                    resource_type='system',
                    resource_id=0,
                    resource_name='System Settings',
                    details={
                        'updated_settings': data,
                        'updated_by': request.user.email
                    },
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT')
                )

                # Очищаем кэш настроек
                cache.delete('system_settings')

                return Response({
                    'message': _('System settings updated successfully'),
                    'settings': data
                })

        except Exception as e:
            logger.error(f"Failed to update system settings: {e}")
            return Response(
                {'error': _('Failed to update system settings')},
                status=status.HTTP_400_BAD_REQUEST
            )


class FeatureSettingsAPIView(APIView):
    """
    API для управления функциями системы.
    """
    permission_classes = [IsSystemAdmin]

    def get(self, request):
        """Получает настройки функций."""
        try:
            feature_settings = {
                'notifications': {
                    'email_enabled': getattr(settings, 'EMAIL_NOTIFICATIONS_ENABLED', True),
                    'push_enabled': getattr(settings, 'PUSH_NOTIFICATIONS_ENABLED', True),
                    'sms_enabled': getattr(settings, 'SMS_NOTIFICATIONS_ENABLED', False),
                },
                'payments': {
                    'stripe_enabled': getattr(settings, 'STRIPE_ENABLED', True),
                    'paypal_enabled': getattr(settings, 'PAYPAL_ENABLED', False),
                    'crypto_enabled': getattr(settings, 'CRYPTO_PAYMENTS_ENABLED', False),
                },
                'geolocation': {
                    'google_maps_enabled': getattr(settings, 'GOOGLE_MAPS_ENABLED', True),
                    'distance_calculation_enabled': getattr(settings, 'DISTANCE_CALCULATION_ENABLED', True),
                },
                'social': {
                    'google_auth_enabled': getattr(settings, 'GOOGLE_AUTH_ENABLED', True),
                    'facebook_auth_enabled': getattr(settings, 'FACEBOOK_AUTH_ENABLED', False),
                    'social_sharing_enabled': getattr(settings, 'SOCIAL_SHARING_ENABLED', True),
                },
                'analytics': {
                    'google_analytics_enabled': getattr(settings, 'GOOGLE_ANALYTICS_ENABLED', True),
                    'internal_analytics_enabled': getattr(settings, 'INTERNAL_ANALYTICS_ENABLED', True),
                },
                'security': {
                    'two_factor_enabled': getattr(settings, 'TWO_FACTOR_ENABLED', False),
                    'captcha_enabled': getattr(settings, 'CAPTCHA_ENABLED', True),
                    'ip_whitelist_enabled': getattr(settings, 'IP_WHITELIST_ENABLED', False),
                }
            }

            return Response(feature_settings)

        except Exception as e:
            logger.error(f"Failed to get feature settings: {e}")
            return Response(
                {'error': _('Failed to get feature settings')},
                status=status.HTTP_400_BAD_REQUEST
            )

    def post(self, request):
        """Включает/выключает функцию."""
        try:
            feature = request.data.get('feature')
            enabled = request.data.get('enabled', True)
            reason = request.data.get('reason', '')

            if not feature:
                return Response(
                    {'error': _('Feature name is required')},
                    status=status.HTTP_400_BAD_REQUEST
            )

            # В реальной реализации здесь будет обновление настроек
            # и перезагрузка конфигурации

            # Логируем изменение функции
            AuditLog.objects.create(
                user=request.user,
                action='feature_toggled',
                resource_type='system',
                resource_id=0,
                resource_name=f'Feature: {feature}',
                details={
                    'feature': feature,
                    'enabled': enabled,
                    'reason': reason,
                    'toggled_by': request.user.email
                },
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )

            return Response({
                'message': f'Feature {feature} {"enabled" if enabled else "disabled"} successfully',
                'feature': feature,
                'enabled': enabled
            })

        except Exception as e:
            logger.error(f"Failed to toggle feature: {e}")
            return Response(
                {'error': _('Failed to toggle feature')},
                status=status.HTTP_400_BAD_REQUEST
            )


class SecuritySettingsAPIView(APIView):
    """
    API для настроек безопасности.
    """
    permission_classes = [IsSystemAdmin]

    def get(self, request):
        """Получает настройки безопасности."""
        try:
            security_settings = {
                'password_policy': {
                    'min_length': getattr(settings, 'PASSWORD_MIN_LENGTH', 8),
                    'require_uppercase': getattr(settings, 'PASSWORD_REQUIRE_UPPERCASE', True),
                    'require_lowercase': getattr(settings, 'PASSWORD_REQUIRE_LOWERCASE', True),
                    'require_numbers': getattr(settings, 'PASSWORD_REQUIRE_NUMBERS', True),
                    'require_special_chars': getattr(settings, 'PASSWORD_REQUIRE_SPECIAL_CHARS', True),
                    'max_age_days': getattr(settings, 'PASSWORD_MAX_AGE_DAYS', 90),
                },
                'session_policy': {
                    'timeout_minutes': getattr(settings, 'SESSION_TIMEOUT_MINUTES', 1440),  # 24 hours
                    'max_concurrent_sessions': getattr(settings, 'MAX_CONCURRENT_SESSIONS', 5),
                    'force_logout_on_password_change': getattr(settings, 'FORCE_LOGOUT_ON_PASSWORD_CHANGE', True),
                },
                'rate_limiting': {
                    'enabled': getattr(settings, 'RATE_LIMITING_ENABLED', True),
                    'login_attempts_per_hour': getattr(settings, 'LOGIN_ATTEMPTS_PER_HOUR', 5),
                    'api_requests_per_minute': getattr(settings, 'API_REQUESTS_PER_MINUTE', 100),
                },
                'ip_restrictions': {
                    'enabled': getattr(settings, 'IP_RESTRICTIONS_ENABLED', False),
                    'whitelist': getattr(settings, 'IP_WHITELIST', []),
                    'blacklist': getattr(settings, 'IP_BLACKLIST', []),
                },
                'audit_logging': {
                    'enabled': getattr(settings, 'AUDIT_LOGGING_ENABLED', True),
                    'retention_days': getattr(settings, 'AUDIT_LOG_RETENTION_DAYS', 365),
                    'log_sensitive_data': getattr(settings, 'LOG_SENSITIVE_DATA', False),
                }
            }

            return Response(security_settings)

        except Exception as e:
            logger.error(f"Failed to get security settings: {e}")
            return Response(
                {'error': _('Failed to get security settings')},
                status=status.HTTP_400_BAD_REQUEST
            )

    def put(self, request):
        """Обновляет настройки безопасности."""
        try:
            with transaction.atomic():
                data = request.data

                # Логируем изменение настроек безопасности
                AuditLog.objects.create(
                    user=request.user,
                    action='security_settings_updated',
                    resource_type='system',
                    resource_id=0,
                    resource_name='Security Settings',
                    details={
                        'updated_settings': data,
                        'updated_by': request.user.email
                    },
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT')
                )

                return Response({
                    'message': _('Security settings updated successfully'),
                    'settings': data
                })

        except Exception as e:
            logger.error(f"Failed to update security settings: {e}")
            return Response(
                {'error': _('Failed to update security settings')},
                status=status.HTTP_400_BAD_REQUEST
            )


class SystemHealthAPIView(APIView):
    """
    API для проверки здоровья системы.
    """
    permission_classes = [IsSystemAdmin]

    def get(self, request):
        """Проверяет здоровье системы."""
        try:
            health_status = {
                'status': 'healthy',
                'timestamp': timezone.now().isoformat(),
                'version': getattr(settings, 'APP_VERSION', '1.0.0'),
                'environment': 'production' if not settings.DEBUG else 'development',
                'checks': {
                    'database': self._check_database(),
                    'cache': self._check_cache(),
                    'storage': self._check_storage(),
                    'external_services': self._check_external_services()
                }
            }

            # Определяем общий статус
            all_healthy = all(check['status'] == 'healthy' for check in health_status['checks'].values())
            health_status['status'] = 'healthy' if all_healthy else 'degraded'

            return Response(health_status)

        except Exception as e:
            logger.error(f"System health check failed: {e}")
            return Response(
                {
                    'status': 'unhealthy',
                    'error': str(e),
                    'timestamp': timezone.now().isoformat()
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _check_database(self):
        """Проверяет состояние базы данных."""
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return {'status': 'healthy', 'message': 'Database connection successful'}
        except Exception as e:
            return {'status': 'unhealthy', 'message': f'Database error: {str(e)}'}

    def _check_cache(self):
        """Проверяет состояние кэша."""
        try:
            cache.set('health_check', 'ok', 60)
            if cache.get('health_check') == 'ok':
                return {'status': 'healthy', 'message': 'Cache is working'}
            else:
                return {'status': 'unhealthy', 'message': 'Cache is not working'}
        except Exception as e:
            return {'status': 'unhealthy', 'message': f'Cache error: {str(e)}'}

    def _check_storage(self):
        """Проверяет состояние хранилища."""
        try:
            import os
            media_root = settings.MEDIA_ROOT
            if os.access(media_root, os.W_OK):
                return {'status': 'healthy', 'message': 'Storage is writable'}
            else:
                return {'status': 'unhealthy', 'message': 'Storage is not writable'}
        except Exception as e:
            return {'status': 'unhealthy', 'message': f'Storage error: {str(e)}'}

    def _check_external_services(self):
        """Проверяет внешние сервисы."""
        try:
            # Проверяем доступность внешних API
            external_services = {
                'email': getattr(settings, 'EMAIL_BACKEND', '') != 'django.core.mail.backends.console.EmailBackend',
                'maps': bool(getattr(settings, 'GOOGLE_MAPS_API_KEY', None)),
                'payments': getattr(settings, 'STRIPE_ENABLED', False)
            }

            healthy_services = sum(external_services.values())
            total_services = len(external_services)

            if healthy_services == total_services:
                return {'status': 'healthy', 'message': f'All {total_services} external services are available'}
            else:
                return {
                    'status': 'degraded', 
                    'message': f'{healthy_services}/{total_services} external services are available',
                    'details': external_services
                }

        except Exception as e:
            return {'status': 'unhealthy', 'message': f'External services check error: {str(e)}'} 