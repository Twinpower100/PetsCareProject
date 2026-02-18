import logging
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseTooManyRequests
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import timedelta

from .services import get_threat_detection_service, get_ip_blocking_service, get_policy_enforcement_service, get_session_monitoring_service, get_access_control_service
from .models import SecurityThreat

logger = logging.getLogger(__name__)

class SecurityMonitoringMiddleware(MiddlewareMixin):
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.get_response = get_response
    
    def process_request(self, request: HttpRequest):
        """Обработка входящего запроса"""
        # Проверить, является ли путь исключенным
        if self._is_exempt_path(request.path):
            return None
        
        # Проверить блокировку IP
        if self._is_ip_blocked(request):
            return self._blocked_response(request)
        
        # Проверить rate limiting
        if self._is_rate_limited(request):
            return self._rate_limited_response(request)
        
        # Анализ угроз безопасности
        threat = get_threat_detection_service().analyze_request(request)
        if threat:
            logger.warning(f"Security threat detected: {threat.threat_type} from {threat.ip_address}")
            # Можно заблокировать доступ при критических угрозах
            if threat.severity == 'critical':
                return self._blocked_response(request)
        
        # Проверить политики безопасности для авторизованных пользователей
        if hasattr(request, 'user') and request.user.is_authenticated:
            self._check_security_policies(request)
        
        return None
    
    def process_response(self, request: HttpRequest, response: HttpResponse):
        """Обработка исходящего ответа"""
        # Добавить заголовки безопасности
        response = self._add_security_headers(response)
        
        # Логировать подозрительные ответы
        self._log_suspicious_response(request, response)
        
        return response
    
    def _is_exempt_path(self, path: str) -> bool:
        """Проверить, является ли путь исключенным из проверок безопасности"""
        exempt_paths = getattr(settings, 'SECURITY_EXEMPT_PATHS', [])
        return any(path.startswith(exempt) for exempt in exempt_paths)
    
    def _is_ip_blocked(self, request: HttpRequest) -> bool:
        """Проверить, заблокирован ли IP адрес"""
        client_ip = self._get_client_ip(request)
        return get_ip_blocking_service().is_ip_blocked(client_ip)
    
    def _is_rate_limited(self, request: HttpRequest) -> bool:
        """Проверить rate limiting"""
        rate_limit_paths = getattr(settings, 'SECURITY_RATE_LIMIT_PATHS', {})
        
        for path, config in rate_limit_paths.items():
            if request.path.startswith(path):
                limit = config.get('limit', 10)
                window = config.get('window', 300)  # секунды
                
                client_ip = self._get_client_ip(request)
                cache_key = f"rate_limit:{client_ip}:{path}"
                
                requests = cache.get(cache_key, 0)
                if requests >= limit:
                    return True
                
                cache.set(cache_key, requests + 1, window)
                break
        
        return False
    
    def _blocked_response(self, request: HttpRequest) -> HttpResponse:
        """Ответ для заблокированных запросов"""
        return HttpResponseForbidden(
            _("Access denied. Your IP address has been blocked due to security violations."),
            content_type="text/plain"
        )
    
    def _rate_limited_response(self, request: HttpRequest) -> HttpResponse:
        """Ответ для запросов, превысивших лимит"""
        return HttpResponseTooManyRequests(
            _("Too many requests. Please try again later."),
            content_type="text/plain"
        )
    
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
        
        # Content Security Policy
        csp_parts = []
        
        # Default source
        default_src = getattr(settings, 'CSP_DEFAULT_SRC', ["'self'"])
        if default_src:
            csp_parts.append(f"default-src {' '.join(default_src)}")
        
        # Script source
        script_src = getattr(settings, 'CSP_SCRIPT_SRC', ["'self'"])
        if script_src:
            csp_parts.append(f"script-src {' '.join(script_src)}")
        
        # Style source
        style_src = getattr(settings, 'CSP_STYLE_SRC', ["'self'"])
        if style_src:
            csp_parts.append(f"style-src {' '.join(style_src)}")
        
        # Image source
        img_src = getattr(settings, 'CSP_IMG_SRC', ["'self'"])
        if img_src:
            csp_parts.append(f"img-src {' '.join(img_src)}")
        
        # Font source
        font_src = getattr(settings, 'CSP_FONT_SRC', ["'self'"])
        if font_src:
            csp_parts.append(f"font-src {' '.join(font_src)}")
        
        # Connect source
        connect_src = getattr(settings, 'CSP_CONNECT_SRC', ["'self'"])
        if connect_src:
            csp_parts.append(f"connect-src {' '.join(connect_src)}")
        
        # Frame ancestors
        frame_ancestors = getattr(settings, 'CSP_FRAME_ANCESTORS', ["'none'"])
        if frame_ancestors:
            csp_parts.append(f"frame-ancestors {' '.join(frame_ancestors)}")
        
        if csp_parts:
            response['Content-Security-Policy'] = '; '.join(csp_parts)
        
        return response
    
    def _log_suspicious_response(self, request: HttpRequest, response: HttpResponse):
        """Логировать подозрительные ответы"""
        # Логировать 4xx и 5xx ошибки
        if response.status_code >= 400:
            client_ip = self._get_client_ip(request)
            logger.warning(
                f"Suspicious response: {response.status_code} for {request.path} "
                f"from {client_ip} (User-Agent: {request.META.get('HTTP_USER_AGENT', 'Unknown')})"
            )
        
        # Логировать попытки сканирования
        if self._is_scanning_attempt(request):
            client_ip = self._get_client_ip(request)
            logger.warning(
                f"Potential scanning attempt detected from {client_ip} "
                f"for {request.path}"
            )
    
    def _is_scanning_attempt(self, request: HttpRequest) -> bool:
        """Определить попытку сканирования"""
        suspicious_paths = [
            '/admin', '/wp-admin', '/phpmyadmin', '/mysql', '/sql',
            '/config', '/.env', '/.git', '/backup', '/test',
            '/api/v1', '/api/v2', '/swagger', '/docs'
        ]
        
        return any(suspicious in request.path.lower() for suspicious in suspicious_paths)
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Получить IP адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')
    
    def _check_security_policies(self, request: HttpRequest):
        """Проверить политики безопасности для пользователя"""
        try:
            # Проверить соблюдение политик
            violations = get_policy_enforcement_service().check_user_compliance(request.user, request)
            
            # Проверить политики сессий
            session_violations = get_session_monitoring_service().check_session_compliance(request.user, request)
            violations.extend(session_violations)
            
            # Проверить политики доступа
            access_violations = get_access_control_service().check_access_compliance(request.user, request)
            violations.extend(access_violations)
            
            # Логировать нарушения
            for violation in violations:
                logger.warning(
                    f"Policy violation detected: {violation.policy.name} "
                    f"by {violation.user.email} - {violation.description}"
                )
                
                # При критических нарушениях можно заблокировать доступ
                if violation.severity == 'critical':
                    logger.critical(
                        f"Critical policy violation: {violation.policy.name} "
                        f"by {violation.user.email} - immediate action required"
                    )
        
        except Exception as e:
            logger.error(f"Error checking security policies: {str(e)}")


class SecurityAuditMiddleware(MiddlewareMixin):
    def process_request(self, request: HttpRequest):
        """Аудит входящих запросов"""
        if self._should_audit_request(request):
            self._log_request(request)
    
    def _should_audit_request(self, request: HttpRequest) -> bool:
        """Определить, нужно ли аудировать запрос"""
        # Аудировать только авторизованные запросы
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return False
        
        # Аудировать запросы к важным ресурсам
        important_paths = [
            '/admin/', '/api/', '/users/', '/pets/', '/providers/',
            '/bookings/', '/billing/', '/settings/'
        ]
        
        return any(request.path.startswith(path) for path in important_paths)
    
    def _log_request(self, request: HttpRequest):
        """Записать запрос в аудит"""
        try:
            client_ip = self._get_client_ip(request)
            user_email = request.user.email if request.user.is_authenticated else 'anonymous'
            
            audit_data = {
                'timestamp': timezone.now().isoformat(),
                'user': user_email,
                'ip_address': client_ip,
                'method': request.method,
                'path': request.path,
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'referer': request.META.get('HTTP_REFERER', ''),
                'query_params': dict(request.GET),
                'post_data': dict(request.POST) if request.method == 'POST' else {},
            }
            
            logger.info(f"Security audit: {audit_data}")
            
        except Exception as e:
            logger.error(f"Error logging security audit: {str(e)}")
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Получить IP адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0') 