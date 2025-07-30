import logging
from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from .services import threat_detection_service, ip_blocking_service
from .models import SecurityThreat

logger = logging.getLogger(__name__)


class SecurityMonitoringMiddleware(MiddlewareMixin):
    """Middleware для мониторинга безопасности и обнаружения угроз"""
    
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.exempt_paths = getattr(settings, 'SECURITY_EXEMPT_PATHS', [
            '/admin/jsi18n/',
            '/static/',
            '/media/',
            '/favicon.ico',
        ])
        self.rate_limit_paths = getattr(settings, 'SECURITY_RATE_LIMIT_PATHS', {
            '/api/login/': {'limit': 10, 'window': 300},  # 10 попыток за 5 минут
            '/api/register/': {'limit': 5, 'window': 3600},  # 5 попыток за час
        })
    
    def process_request(self, request: HttpRequest):
        """Обработать входящий запрос"""
        try:
            # Пропустить исключенные пути
            if self._is_exempt_path(request.path):
                return None
            
            # Проверить IP в черном списке
            if self._is_ip_blocked(request):
                return self._blocked_response(request)
            
            # Проверить rate limiting
            if self._is_rate_limited(request):
                return self._rate_limited_response(request)
            
            # Анализировать запрос на угрозы
            threat = threat_detection_service.analyze_request(request)
            if threat:
                # Если обнаружена критическая угроза, заблокировать IP
                if threat.severity == 'critical':
                    ip_blocking_service.block_ip(
                        threat.ip_address,
                        f"Critical threat detected: {threat.threat_type}",
                        'automatic'
                    )
                    return self._blocked_response(request)
                
                # Для других угроз просто логируем
                logger.warning(f"Security threat detected: {threat.threat_type} from {threat.ip_address}")
            
            return None
            
        except Exception as e:
            logger.error(f"Error in SecurityMonitoringMiddleware: {e}")
            return None
    
    def process_response(self, request: HttpRequest, response: HttpResponse):
        """Обработать исходящий ответ"""
        try:
            # Добавить заголовки безопасности
            response = self._add_security_headers(response)
            
            # Логировать подозрительные ответы
            if response.status_code in [403, 404, 500]:
                self._log_suspicious_response(request, response)
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing response in SecurityMonitoringMiddleware: {e}")
            return response
    
    def _is_exempt_path(self, path: str) -> bool:
        """Проверить, является ли путь исключенным"""
        for exempt_path in self.exempt_paths:
            if path.startswith(exempt_path):
                return True
        return False
    
    def _is_ip_blocked(self, request: HttpRequest) -> bool:
        """Проверить, заблокирован ли IP"""
        try:
            ip = self._get_client_ip(request)
            return ip_blocking_service.is_ip_blocked(ip)
        except Exception as e:
            logger.error(f"Error checking IP block status: {e}")
            return False
    
    def _is_rate_limited(self, request: HttpRequest) -> bool:
        """Проверить rate limiting"""
        try:
            path = request.path
            if path not in self.rate_limit_paths:
                return False
            
            ip = self._get_client_ip(request)
            limit_config = self.rate_limit_paths[path]
            
            cache_key = f'rate_limit_{path}_{ip}'
            current_count = cache.get(cache_key, 0)
            
            if current_count >= limit_config['limit']:
                return True
            
            # Увеличить счетчик
            cache.set(cache_key, current_count + 1, limit_config['window'])
            return False
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return False
    
    def _blocked_response(self, request: HttpRequest) -> HttpResponse:
        """Создать ответ для заблокированного IP"""
        from django.http import HttpResponseForbidden
        
        response = HttpResponseForbidden(
            content="Access denied. Your IP address has been blocked due to suspicious activity.",
            content_type="text/plain"
        )
        response['X-Blocked-IP'] = self._get_client_ip(request)
        return response
    
    def _rate_limited_response(self, request: HttpRequest) -> HttpResponse:
        """Создать ответ для превышения rate limit"""
        from django.http import HttpResponseTooManyRequests
        
        response = HttpResponseTooManyRequests(
            content="Too many requests. Please try again later.",
            content_type="text/plain"
        )
        response['Retry-After'] = '300'  # 5 минут
        return response
    
    def _add_security_headers(self, response: HttpResponse) -> HttpResponse:
        """Добавить заголовки безопасности"""
        # X-Content-Type-Options
        response['X-Content-Type-Options'] = 'nosniff'
        
        # X-Frame-Options
        response['X-Frame-Options'] = 'DENY'
        
        # X-XSS-Protection
        response['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer-Policy
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Content-Security-Policy (базовая)
        csp_policy = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
        response['Content-Security-Policy'] = csp_policy
        
        return response
    
    def _log_suspicious_response(self, request: HttpRequest, response: HttpResponse):
        """Логировать подозрительные ответы"""
        try:
            ip = self._get_client_ip(request)
            
            # Создать запись об угрозе для подозрительных ответов
            if response.status_code == 403:
                threat_type = 'unauthorized_access'
                severity = 'medium'
                description = f"403 Forbidden response for {request.path}"
            elif response.status_code == 404:
                # Проверить, не является ли это попыткой сканирования
                if self._is_scanning_attempt(request):
                    threat_type = 'suspicious_ip'
                    severity = 'low'
                    description = f"Potential scanning attempt: {request.path}"
                else:
                    return  # Обычная 404, не логируем
            elif response.status_code == 500:
                threat_type = 'other'
                severity = 'low'
                description = f"500 Internal Server Error for {request.path}"
            else:
                return
            
            # Создать угрозу
            SecurityThreat.objects.create(
                threat_type=threat_type,
                severity=severity,
                ip_address=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                request_path=request.path,
                request_method=request.method,
                description=description
            )
            
        except Exception as e:
            logger.error(f"Error logging suspicious response: {e}")
    
    def _is_scanning_attempt(self, request: HttpRequest) -> bool:
        """Проверить, является ли это попыткой сканирования"""
        suspicious_paths = [
            '/admin', '/wp-admin', '/phpmyadmin', '/mysql', '/sql',
            '/config', '/backup', '/.env', '/.git', '/.htaccess',
            '/robots.txt', '/sitemap.xml', '/test', '/debug',
        ]
        
        path_lower = request.path.lower()
        return any(suspicious in path_lower for suspicious in suspicious_paths)
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Получить IP-адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        return ip


class SecurityAuditMiddleware(MiddlewareMixin):
    """Middleware для аудита безопасности"""
    
    def process_request(self, request: HttpRequest):
        """Логировать запросы для аудита"""
        try:
            # Логировать только важные запросы
            if self._should_audit_request(request):
                self._log_request(request)
        except Exception as e:
            logger.error(f"Error in SecurityAuditMiddleware: {e}")
        
        return None
    
    def _should_audit_request(self, request: HttpRequest) -> bool:
        """Определить, нужно ли аудировать запрос"""
        audit_paths = [
            '/api/login/', '/api/register/', '/api/admin/',
            '/admin/', '/api/users/', '/api/settings/',
        ]
        
        return any(request.path.startswith(path) for path in audit_paths)
    
    def _log_request(self, request: HttpRequest):
        """Логировать запрос"""
        try:
            ip = self._get_client_ip(request)
            user = getattr(request, 'user', None)
            user_id = user.id if user and user.is_authenticated else None
            
            log_data = {
                'timestamp': timezone.now().isoformat(),
                'ip_address': ip,
                'user_id': user_id,
                'method': request.method,
                'path': request.path,
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'referer': request.META.get('HTTP_REFERER', ''),
            }
            
            logger.info(f"Security audit: {log_data}")
            
        except Exception as e:
            logger.error(f"Error logging request: {e}")
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Получить IP-адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        return ip 