import re
import logging
from typing import Dict, List, Optional, Tuple
from django.core.cache import cache
from django.utils import timezone
from django.http import HttpRequest
from django.contrib.auth import get_user_model
from django.conf import settings
from datetime import timedelta
import json

from .models import SecurityThreat, IPBlacklist, ThreatPattern

User = get_user_model()
logger = logging.getLogger(__name__)


class ThreatDetectionService:
    """Сервис для обнаружения угроз безопасности"""
    
    def __init__(self):
        self.cache_timeout = 300  # 5 минут
        self._load_patterns()
    
    def _load_patterns(self):
        """Загрузить активные шаблоны угроз из базы данных"""
        try:
            self.patterns = list(ThreatPattern.objects.filter(is_active=True))
            cache.set('security_patterns', self.patterns, self.cache_timeout)
        except Exception as e:
            logger.error(f"Failed to load threat patterns: {e}")
            self.patterns = []
    
    def _get_patterns(self) -> List[ThreatPattern]:
        """Получить шаблоны угроз (из кэша или базы)"""
        patterns = cache.get('security_patterns')
        if patterns is None:
            self._load_patterns()
            patterns = self.patterns
        return patterns
    
    def analyze_request(self, request: HttpRequest) -> Optional[SecurityThreat]:
        """Анализировать HTTP запрос на предмет угроз"""
        try:
            # Проверить IP в черном списке
            if self._is_ip_blocked(request):
                return self._create_threat(
                    request, 'unauthorized_access', 'high',
                    f"Request from blocked IP: {self._get_client_ip(request)}"
                )
            
            # Проверить шаблоны угроз
            threat = self._check_threat_patterns(request)
            if threat:
                return threat
            
            # Проверить брутфорс атаки
            threat = self._check_brute_force(request)
            if threat:
                return threat
            
            # Проверить SQL инъекции
            threat = self._check_sql_injection(request)
            if threat:
                return threat
            
            # Проверить XSS атаки
            threat = self._check_xss(request)
            if threat:
                return threat
            
            # Проверить path traversal
            threat = self._check_path_traversal(request)
            if threat:
                return threat
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing request for threats: {e}")
            return None
    
    def _is_ip_blocked(self, request: HttpRequest) -> bool:
        """Проверить, заблокирован ли IP-адрес"""
        ip = self._get_client_ip(request)
        cache_key = f'ip_blacklist_{ip}'
        
        # Проверить кэш
        is_blocked = cache.get(cache_key)
        if is_blocked is not None:
            return is_blocked
        
        # Проверить базу данных
        try:
            blacklist_entry = IPBlacklist.objects.filter(
                ip_address=ip,
                is_active=True
            ).first()
            
            if blacklist_entry:
                # Проверить срок действия
                if blacklist_entry.is_expired():
                    blacklist_entry.deactivate()
                    is_blocked = False
                else:
                    is_blocked = True
            else:
                is_blocked = False
            
            # Кэшировать результат
            cache.set(cache_key, is_blocked, self.cache_timeout)
            return is_blocked
            
        except Exception as e:
            logger.error(f"Error checking IP blacklist: {e}")
            return False
    
    def _check_threat_patterns(self, request: HttpRequest) -> Optional[SecurityThreat]:
        """Проверить запрос по шаблонам угроз"""
        patterns = self._get_patterns()
        
        for pattern in patterns:
            if self._match_pattern(request, pattern):
                return self._create_threat(
                    request, pattern.threat_type, pattern.severity,
                    f"Matched threat pattern: {pattern.name} - {pattern.description}"
                )
        
        return None
    
    def _match_pattern(self, request: HttpRequest, pattern: ThreatPattern) -> bool:
        """Проверить соответствие запроса шаблону"""
        try:
            if pattern.pattern_type == 'regex':
                return self._match_regex_pattern(request, pattern.pattern)
            elif pattern.pattern_type == 'keyword':
                return self._match_keyword_pattern(request, pattern.pattern)
            elif pattern.pattern_type == 'path':
                return self._match_path_pattern(request, pattern.pattern)
            elif pattern.pattern_type == 'user_agent':
                return self._match_user_agent_pattern(request, pattern.pattern)
            return False
        except Exception as e:
            logger.error(f"Error matching pattern {pattern.name}: {e}")
            return False
    
    def _match_regex_pattern(self, request: HttpRequest, pattern: str) -> bool:
        """Проверить соответствие регулярному выражению"""
        try:
            # Проверить URL
            if re.search(pattern, request.path, re.IGNORECASE):
                return True
            
            # Проверить GET параметры
            if re.search(pattern, str(request.GET), re.IGNORECASE):
                return True
            
            # Проверить POST данные
            if request.method == 'POST':
                if re.search(pattern, str(request.POST), re.IGNORECASE):
                    return True
            
            # Проверить заголовки
            if re.search(pattern, str(request.headers), re.IGNORECASE):
                return True
            
            return False
        except re.error:
            return False
    
    def _match_keyword_pattern(self, request: HttpRequest, keywords: str) -> bool:
        """Проверить наличие ключевых слов"""
        keyword_list = [kw.strip().lower() for kw in keywords.split(',')]
        
        # Проверить URL
        path_lower = request.path.lower()
        if any(kw in path_lower for kw in keyword_list):
            return True
        
        # Проверить GET параметры
        get_str = str(request.GET).lower()
        if any(kw in get_str for kw in keyword_list):
            return True
        
        # Проверить POST данные
        if request.method == 'POST':
            post_str = str(request.POST).lower()
            if any(kw in post_str for kw in keyword_list):
                return True
        
        return False
    
    def _match_path_pattern(self, request: HttpRequest, path_pattern: str) -> bool:
        """Проверить соответствие пути"""
        return path_pattern.lower() in request.path.lower()
    
    def _match_user_agent_pattern(self, request: HttpRequest, ua_pattern: str) -> bool:
        """Проверить соответствие User-Agent"""
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        return ua_pattern.lower() in user_agent
    
    def _check_brute_force(self, request: HttpRequest) -> Optional[SecurityThreat]:
        """Проверить брутфорс атаки"""
        # Проверяем только для логина
        if not request.path.endswith('/login/') or request.method != 'POST':
            return None
        
        ip = self._get_client_ip(request)
        cache_key = f'login_attempts_{ip}'
        
        # Получить количество попыток входа
        attempts = cache.get(cache_key, 0)
        
        # Увеличить счетчик
        attempts += 1
        cache.set(cache_key, attempts, 300)  # 5 минут
        
        # Проверить лимит (10 попыток за 5 минут)
        if attempts >= 10:
            # Создать угрозу
            threat = self._create_threat(
                request, 'brute_force', 'high',
                f"Brute force attack detected: {attempts} login attempts from {ip}"
            )
            
            # Добавить IP в черный список
            self._block_ip(ip, 'automatic', f"Brute force attack: {attempts} attempts")
            
            return threat
        
        return None
    
    def _check_sql_injection(self, request: HttpRequest) -> Optional[SecurityThreat]:
        """Проверить SQL инъекции"""
        sql_patterns = [
            r"(\b(union|select|insert|update|delete|drop|create|alter)\b)",
            r"(\b(or|and)\b\s+\d+\s*[=<>])",
            r"(--|#|\/\*|\*\/)",
            r"(\b(exec|execute|xp_|sp_)\b)",
            r"(\b(script|javascript|vbscript)\b)",
        ]
        
        request_data = str(request.GET) + str(request.POST) + request.path
        
        for pattern in sql_patterns:
            if re.search(pattern, request_data, re.IGNORECASE):
                return self._create_threat(
                    request, 'sql_injection', 'critical',
                    f"SQL injection attempt detected: {pattern}"
                )
        
        return None
    
    def _check_xss(self, request: HttpRequest) -> Optional[SecurityThreat]:
        """Проверить XSS атаки"""
        xss_patterns = [
            r"<script[^>]*>",
            r"javascript:",
            r"on\w+\s*=",
            r"<iframe[^>]*>",
            r"<object[^>]*>",
            r"<embed[^>]*>",
        ]
        
        request_data = str(request.GET) + str(request.POST)
        
        for pattern in xss_patterns:
            if re.search(pattern, request_data, re.IGNORECASE):
                return self._create_threat(
                    request, 'xss', 'high',
                    f"XSS attempt detected: {pattern}"
                )
        
        return None
    
    def _check_path_traversal(self, request: HttpRequest) -> Optional[SecurityThreat]:
        """Проверить path traversal атаки"""
        traversal_patterns = [
            r"\.\.\/",
            r"\.\.\\",
            r"\/etc\/passwd",
            r"\/proc\/",
            r"\/sys\/",
            r"\/dev\/",
        ]
        
        path = request.path
        
        for pattern in traversal_patterns:
            if re.search(pattern, path, re.IGNORECASE):
                return self._create_threat(
                    request, 'path_traversal', 'high',
                    f"Path traversal attempt detected: {pattern}"
                )
        
        return None
    
    def _create_threat(self, request: HttpRequest, threat_type: str, severity: str, description: str) -> SecurityThreat:
        """Создать запись об угрозе"""
        try:
            # Получить пользователя, если аутентифицирован
            user = getattr(request, 'user', None)
            if user and not user.is_authenticated:
                user = None
            
            # Собрать данные запроса
            request_data = {
                'headers': dict(request.headers),
                'get_params': dict(request.GET),
                'post_params': dict(request.POST) if request.method == 'POST' else {},
                'method': request.method,
                'path': request.path,
            }
            
            # Создать угрозу
            threat = SecurityThreat.objects.create(
                threat_type=threat_type,
                severity=severity,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                request_path=request.path,
                request_method=request.method,
                request_data=request_data,
                description=description,
                user=user
            )
            
            # Увеличить счетчик угроз для IP
            self._increment_ip_threat_count(self._get_client_ip(request))
            
            logger.warning(f"Security threat detected: {threat_type} from {self._get_client_ip(request)}")
            
            return threat
            
        except Exception as e:
            logger.error(f"Error creating security threat: {e}")
            return None
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Получить IP-адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        return ip
    
    def _block_ip(self, ip: str, block_type: str, reason: str):
        """Заблокировать IP-адрес"""
        try:
            # Проверить, не заблокирован ли уже
            if IPBlacklist.objects.filter(ip_address=ip, is_active=True).exists():
                return
            
            # Создать блокировку
            blacklist_entry = IPBlacklist.objects.create(
                ip_address=ip,
                block_type=block_type,
                reason=reason,
                expires_at=timezone.now() + timedelta(hours=24)  # 24 часа
            )
            
            # Кэшировать блокировку
            cache.set(f'ip_blacklist_{ip}', True, self.cache_timeout)
            
            logger.warning(f"IP {ip} blocked due to: {reason}")
            
        except Exception as e:
            logger.error(f"Error blocking IP {ip}: {e}")
    
    def _increment_ip_threat_count(self, ip: str):
        """Увеличить счетчик угроз для IP"""
        try:
            blacklist_entry = IPBlacklist.objects.filter(
                ip_address=ip,
                is_active=True
            ).first()
            
            if blacklist_entry:
                blacklist_entry.threat_count += 1
                blacklist_entry.save()
                
                # Если много угроз, продлить блокировку
                if blacklist_entry.threat_count >= 5:
                    blacklist_entry.expires_at = timezone.now() + timedelta(days=7)
                    blacklist_entry.save()
                    
        except Exception as e:
            logger.error(f"Error incrementing threat count for IP {ip}: {e}")


class IPBlockingService:
    """Сервис для управления блокировкой IP-адресов"""
    
    def __init__(self):
        self.cache_timeout = 300  # 5 минут
    
    def is_ip_blocked(self, ip: str) -> bool:
        """Проверить, заблокирован ли IP"""
        cache_key = f'ip_blacklist_{ip}'
        
        # Проверить кэш
        is_blocked = cache.get(cache_key)
        if is_blocked is not None:
            return is_blocked
        
        # Проверить базу данных
        try:
            blacklist_entry = IPBlacklist.objects.filter(
                ip_address=ip,
                is_active=True
            ).first()
            
            if blacklist_entry:
                # Проверить срок действия
                if blacklist_entry.is_expired():
                    blacklist_entry.deactivate()
                    is_blocked = False
                else:
                    is_blocked = True
            else:
                is_blocked = False
            
            # Кэшировать результат
            cache.set(cache_key, is_blocked, self.cache_timeout)
            return is_blocked
            
        except Exception as e:
            logger.error(f"Error checking IP block status: {e}")
            return False
    
    def block_ip(self, ip: str, reason: str, block_type: str = 'manual', 
                 expires_at: Optional[timezone.datetime] = None, blocked_by: Optional[User] = None):
        """Заблокировать IP-адрес"""
        try:
            # Проверить, не заблокирован ли уже
            if IPBlacklist.objects.filter(ip_address=ip, is_active=True).exists():
                return False
            
            # Создать блокировку
            blacklist_entry = IPBlacklist.objects.create(
                ip_address=ip,
                block_type=block_type,
                reason=reason,
                expires_at=expires_at,
                blocked_by=blocked_by
            )
            
            # Кэшировать блокировку
            cache.set(f'ip_blacklist_{ip}', True, self.cache_timeout)
            
            logger.info(f"IP {ip} blocked by {blocked_by} due to: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error blocking IP {ip}: {e}")
            return False
    
    def unblock_ip(self, ip: str, unblocked_by: Optional[User] = None):
        """Разблокировать IP-адрес"""
        try:
            blacklist_entry = IPBlacklist.objects.filter(
                ip_address=ip,
                is_active=True
            ).first()
            
            if blacklist_entry:
                blacklist_entry.deactivate()
                logger.info(f"IP {ip} unblocked by {unblocked_by}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error unblocking IP {ip}: {e}")
            return False
    
    def get_blocked_ips(self) -> List[IPBlacklist]:
        """Получить список заблокированных IP"""
        try:
            return list(IPBlacklist.objects.filter(is_active=True).order_by('-blocked_at'))
        except Exception as e:
            logger.error(f"Error getting blocked IPs: {e}")
            return []


# Глобальные экземпляры сервисов
threat_detection_service = ThreatDetectionService()
ip_blocking_service = IPBlockingService() 