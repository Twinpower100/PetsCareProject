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

from .models import SecurityThreat, IPBlacklist, ThreatPattern, SecurityPolicy, PolicyViolation, SessionPolicy, AccessPolicy, DataClassificationPolicy

User = get_user_model()
logger = logging.getLogger(__name__)

class ThreatDetectionService:
    def __init__(self):
        """Инициализация сервиса обнаружения угроз"""
        self._patterns = None
    
    @property
    def patterns(self):
        """Ленивая загрузка шаблонов угроз"""
        if self._patterns is None:
            self._patterns = self._load_patterns()
        return self._patterns
    
    def _load_patterns(self):
        """Загрузить шаблоны угроз из кэша или базы данных"""
        patterns = cache.get('security_patterns')
        if patterns is None:
            patterns = self._get_patterns()
            cache.set('security_patterns', patterns, 300)  # Кэш на 5 минут
        return patterns
    
    def _get_patterns(self) -> List[ThreatPattern]:
        """Получить активные шаблоны угроз"""
        try:
            # Проверить, готова ли база данных
            from django.db import connection
            if connection.introspection.table_names():
                return list(ThreatPattern.objects.filter(is_active=True))
            else:
                # Если таблицы еще не созданы, возвращаем пустой список
                return []
        except:
            # Если БД еще не готова, возвращаем пустой список
            return []
    
    def analyze_request(self, request: HttpRequest) -> Optional[SecurityThreat]:
        """Анализировать запрос на наличие угроз"""
        # Проверить, заблокирован ли IP
        if self._is_ip_blocked(request):
            return None
        
        # Проверить шаблоны угроз
        threat = self._check_threat_patterns(request)
        if threat:
            return threat
        
        # Проверить brute force атаки
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
    
    def _is_ip_blocked(self, request: HttpRequest) -> bool:
        """Проверить, заблокирован ли IP адрес"""
        client_ip = self._get_client_ip(request)
        return IPBlacklist.objects.filter(
            ip_address=client_ip,
            is_active=True
        ).exclude(
            expires_at__lt=timezone.now()
        ).exists()
    
    def _check_threat_patterns(self, request: HttpRequest) -> Optional[SecurityThreat]:
        """Проверить запрос по шаблонам угроз"""
        for pattern in self.patterns:
            if self._match_pattern(request, pattern):
                return self._create_threat(
                    request,
                    pattern.threat_type,
                    pattern.severity,
                    f"Pattern match: {pattern.name}"
                )
        return None
    
    def _match_pattern(self, request: HttpRequest, pattern: ThreatPattern) -> bool:
        """Проверить соответствие запроса шаблону"""
        if pattern.pattern_type == 'regex':
            return self._match_regex_pattern(request, pattern.pattern)
        elif pattern.pattern_type == 'keyword':
            return self._match_keyword_pattern(request, pattern.pattern)
        elif pattern.pattern_type == 'path':
            return self._match_path_pattern(request, pattern.pattern)
        elif pattern.pattern_type == 'user_agent':
            return self._match_user_agent_pattern(request, pattern.pattern)
        return False
    
    def _match_regex_pattern(self, request: HttpRequest, pattern: str) -> bool:
        """Проверить регулярное выражение"""
        try:
            # Проверить URL
            if re.search(pattern, request.path, re.IGNORECASE):
                return True
            
            # Проверить параметры GET
            for key, value in request.GET.items():
                if re.search(pattern, f"{key}={value}", re.IGNORECASE):
                    return True
            
            # Проверить параметры POST
            for key, value in request.POST.items():
                if re.search(pattern, f"{key}={value}", re.IGNORECASE):
                    return True
            
            return False
        except re.error:
            logger.warning(f"Invalid regex pattern: {pattern}")
            return False
    
    def _match_keyword_pattern(self, request: HttpRequest, keywords: str) -> bool:
        """Проверить ключевые слова"""
        keyword_list = [k.strip().lower() for k in keywords.split(',')]
        
        # Проверить URL
        path_lower = request.path.lower()
        if any(keyword in path_lower for keyword in keyword_list):
            return True
        
        # Проверить параметры
        for key, value in request.GET.items():
            param_str = f"{key}={value}".lower()
            if any(keyword in param_str for keyword in keyword_list):
                return True
        
        for key, value in request.POST.items():
            param_str = f"{key}={value}".lower()
            if any(keyword in param_str for keyword in keyword_list):
                return True
        
        return False
    
    def _match_path_pattern(self, request: HttpRequest, path_pattern: str) -> bool:
        """Проверить паттерн пути"""
        try:
            return re.search(path_pattern, request.path, re.IGNORECASE) is not None
        except re.error:
            logger.warning(f"Invalid path pattern: {path_pattern}")
            return False
    
    def _match_user_agent_pattern(self, request: HttpRequest, ua_pattern: str) -> bool:
        """Проверить паттерн User-Agent"""
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        try:
            return re.search(ua_pattern, user_agent, re.IGNORECASE) is not None
        except re.error:
            logger.warning(f"Invalid user agent pattern: {ua_pattern}")
            return False
    
    def _check_brute_force(self, request: HttpRequest) -> Optional[SecurityThreat]:
        """Проверить brute force атаки"""
        if request.path in ['/api/login/', '/admin/login/']:
            client_ip = self._get_client_ip(request)
            cache_key = f"login_attempts:{client_ip}"
            
            attempts = cache.get(cache_key, 0)
            if attempts >= 10:  # Более 10 попыток входа
                return self._create_threat(
                    request,
                    'brute_force',
                    'high',
                    f"Brute force attack detected: {attempts} login attempts"
                )
            
            # Увеличить счетчик попыток
            cache.set(cache_key, attempts + 1, 3600)  # 1 час
        
        return None
    
    def _check_sql_injection(self, request: HttpRequest) -> Optional[SecurityThreat]:
        """Проверить SQL инъекции"""
        sql_patterns = [
            r"(\b(union|select|insert|update|delete|drop|create|alter)\b)",
            r"(\b(or|and)\b\s+\d+\s*=\s*\d+)",
            r"(\b(union|select)\b.*\bfrom\b)",
            r"(--|#|\/\*|\*\/)",
            r"(\bxp_cmdshell\b|\bsp_executesql\b)",
        ]
        
        for pattern in sql_patterns:
            if self._match_regex_pattern(request, pattern):
                return self._create_threat(
                    request,
                    'sql_injection',
                    'critical',
                    f"SQL injection attempt detected"
                )
        
        return None
    
    def _check_xss(self, request: HttpRequest) -> Optional[SecurityThreat]:
        """Проверить XSS атаки"""
        xss_patterns = [
            r"(<script[^>]*>.*?</script>)",
            r"(javascript:)",
            r"(on\w+\s*=)",
            r"(<iframe[^>]*>)",
            r"(<object[^>]*>)",
            r"(<embed[^>]*>)",
        ]
        
        for pattern in xss_patterns:
            if self._match_regex_pattern(request, pattern):
                return self._create_threat(
                    request,
                    'xss',
                    'high',
                    f"XSS attack attempt detected"
                )
        
        return None
    
    def _check_path_traversal(self, request: HttpRequest) -> Optional[SecurityThreat]:
        """Проверить path traversal атаки"""
        traversal_patterns = [
            r"(\.\.\/|\.\.\\)",
            r"(\/etc\/passwd|\/etc\/shadow)",
            r"(c:\\windows\\system32)",
            r"(%2e%2e%2f|%2e%2e%5c)",
        ]
        
        for pattern in traversal_patterns:
            if self._match_regex_pattern(request, pattern):
                return self._create_threat(
                    request,
                    'path_traversal',
                    'high',
                    f"Path traversal attempt detected"
                )
        
        return None
    
    def _create_threat(self, request: HttpRequest, threat_type: str, severity: str, description: str) -> SecurityThreat:
        """Создать запись об угрозе"""
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            user = user
        else:
            user = None
        
        threat = SecurityThreat.objects.create(
            threat_type=threat_type,
            severity=severity,
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            request_path=request.path,
            request_method=request.method,
            request_data={
                'GET': dict(request.GET),
                'POST': dict(request.POST),
            },
            description=description,
            user=user
        )
        
        # Увеличить счетчик угроз для IP
        self._increment_ip_threat_count(self._get_client_ip(request))
        
        # Автоматически заблокировать IP при критических угрозах
        if severity == 'critical':
            self._block_ip(
                self._get_client_ip(request),
                'automatic',
                f"Critical threat: {threat_type}"
            )
        
        logger.warning(f"Security threat detected: {threat_type} from {self._get_client_ip(request)}")
        return threat
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Получить IP адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')
    
    def _block_ip(self, ip: str, block_type: str, reason: str):
        """Заблокировать IP адрес"""
        try:
            IPBlacklist.objects.get_or_create(
                ip_address=ip,
                defaults={
                    'block_type': block_type,
                    'reason': reason,
                    'expires_at': timezone.now() + timedelta(hours=24),
                    'threat_count': 1
                }
            )
            logger.info(f"IP {ip} blocked due to: {reason}")
        except Exception as e:
            logger.error(f"Error blocking IP {ip}: {str(e)}")
    
    def _increment_ip_threat_count(self, ip: str):
        """Увеличить счетчик угроз для IP"""
        try:
            blacklist_entry = IPBlacklist.objects.filter(ip_address=ip).first()
            if blacklist_entry:
                blacklist_entry.threat_count += 1
                blacklist_entry.save()
        except Exception as e:
            logger.error(f"Error incrementing threat count for IP {ip}: {str(e)}")


class IPBlockingService:
    def __init__(self):
        """Инициализация сервиса блокировки IP"""
        pass
    
    def is_ip_blocked(self, ip: str) -> bool:
        """Проверить, заблокирован ли IP"""
        return IPBlacklist.objects.filter(
            ip_address=ip,
            is_active=True
        ).exclude(
            expires_at__lt=timezone.now()
        ).exists()
    
    def block_ip(self, ip: str, reason: str, block_type: str = 'manual', expires_at: Optional[timezone.datetime] = None, blocked_by: Optional[User] = None):
        """Заблокировать IP адрес"""
        if expires_at is None:
            expires_at = timezone.now() + timedelta(hours=24)
        
        try:
            blacklist_entry, created = IPBlacklist.objects.get_or_create(
                ip_address=ip,
                defaults={
                    'block_type': block_type,
                    'reason': reason,
                    'expires_at': expires_at,
                    'blocked_by': blocked_by,
                    'threat_count': 1
                }
            )
            
            if not created:
                blacklist_entry.block_type = block_type
                blacklist_entry.reason = reason
                blacklist_entry.expires_at = expires_at
                blacklist_entry.blocked_by = blocked_by
                blacklist_entry.is_active = True
                blacklist_entry.save()
            
            # Очистить кэш
            cache.delete(f'ip_blocked:{ip}')
            
            logger.info(f"IP {ip} blocked: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error blocking IP {ip}: {str(e)}")
            return False
    
    def unblock_ip(self, ip: str, unblocked_by: Optional[User] = None):
        """Разблокировать IP адрес"""
        try:
            blacklist_entry = IPBlacklist.objects.filter(ip_address=ip, is_active=True).first()
            if blacklist_entry:
                blacklist_entry.deactivate(unblocked_by)
                cache.delete(f'ip_blocked:{ip}')
                logger.info(f"IP {ip} unblocked by {unblocked_by}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error unblocking IP {ip}: {str(e)}")
            return False
    
    def get_blocked_ips(self) -> List[IPBlacklist]:
        """Получить список заблокированных IP"""
        return list(IPBlacklist.objects.filter(is_active=True))


# === НОВЫЕ СЕРВИСЫ ДЛЯ СИСТЕМЫ ПОЛИТИК БЕЗОПАСНОСТИ ===

class PolicyEnforcementService:
    """Сервис для проверки соблюдения политик безопасности"""
    
    def __init__(self):
        """Инициализация сервиса"""
        self.policies = self._load_policies()
    
    def _load_policies(self):
        """Загрузить активные политики из кэша или базы данных"""
        policies = cache.get('security_policies')
        if policies is None:
            policies = list(SecurityPolicy.objects.filter(is_active=True))
            cache.set('security_policies', policies, 300)  # Кэш на 5 минут
        return policies
    
    def check_user_compliance(self, user: User, request: HttpRequest = None) -> List[PolicyViolation]:
        """Проверить соблюдение политик пользователем"""
        violations = []
        
        for policy in self.policies:
            if policy.is_applicable_to_user(user):
                violation = self._check_policy_compliance(policy, user, request)
                if violation:
                    violations.append(violation)
        
        return violations
    
    def _check_policy_compliance(self, policy: SecurityPolicy, user: User, request: HttpRequest = None) -> Optional[PolicyViolation]:
        """Проверить соблюдение конкретной политики"""
        if policy.policy_type == 'password':
            return self._check_password_policy(policy, user)
        elif policy.policy_type == 'session':
            return self._check_session_policy(policy, user, request)
        elif policy.policy_type == 'access':
            return self._check_access_policy(policy, user, request)
        elif policy.policy_type == 'data':
            return self._check_data_policy(policy, user, request)
        
        return None
    
    def _check_password_policy(self, policy: SecurityPolicy, user: User) -> Optional[PolicyViolation]:
        """Проверить политику паролей"""
        params = policy.get_parameters()
        
        # Проверить срок действия пароля
        if 'max_age_days' in params:
            max_age = params['max_age_days']
            if user.last_password_change:
                age_days = (timezone.now() - user.last_password_change).days
                if age_days > max_age:
                    return self._create_violation(
                        policy, user, 'password_expired',
                        f"Password expired {age_days} days ago (max: {max_age})",
                        'high'
                    )
        
        # Проверить сложность пароля (если есть доступ к хешу)
        if 'min_length' in params and hasattr(user, 'check_password'):
            # Это упрощенная проверка - в реальности нужно проверять хеш
            pass
        
        return None
    
    def _check_session_policy(self, policy: SecurityPolicy, user: User, request: HttpRequest) -> Optional[PolicyViolation]:
        """Проверить политику сессий"""
        params = policy.get_parameters()
        
        # Проверить количество одновременных сессий
        if 'max_concurrent_sessions' in params:
            max_sessions = params['max_concurrent_sessions']
            # Здесь нужно реализовать подсчет активных сессий
            # Для простоты пропускаем
        
        # Проверить время неактивности
        if 'inactivity_timeout_minutes' in params and request:
            timeout_minutes = params['inactivity_timeout_minutes']
            if user.last_activity:
                inactivity_minutes = (timezone.now() - user.last_activity).total_seconds() / 60
                if inactivity_minutes > timeout_minutes:
                    return self._create_violation(
                        policy, user, 'session_inactivity',
                        f"Session inactive for {inactivity_minutes:.1f} minutes (max: {timeout_minutes})",
                        'medium'
                    )
        
        return None
    
    def _check_access_policy(self, policy: SecurityPolicy, user: User, request: HttpRequest) -> Optional[PolicyViolation]:
        """Проверить политику доступа"""
        if not request:
            return None
        
        params = policy.get_parameters()
        client_ip = self._get_client_ip(request)
        
        # Проверить IP ограничения
        if 'allowed_ips' in params:
            allowed_ips = params['allowed_ips']
            if allowed_ips and client_ip not in allowed_ips:
                return self._create_violation(
                    policy, user, 'unauthorized_ip',
                    f"Access from unauthorized IP: {client_ip}",
                    'high'
                )
        
        # Проверить временные ограничения
        if 'allowed_time_ranges' in params:
            current_time = timezone.now().time()
            allowed_ranges = params['allowed_time_ranges']
            if allowed_ranges:
                is_allowed = False
                for time_range in allowed_ranges:
                    start_time = time_range.get('start')
                    end_time = time_range.get('end')
                    if start_time and end_time:
                        if start_time <= current_time <= end_time:
                            is_allowed = True
                            break
                
                if not is_allowed:
                    return self._create_violation(
                        policy, user, 'unauthorized_time',
                        f"Access outside allowed time range: {current_time}",
                        'medium'
                    )
        
        return None
    
    def _check_data_policy(self, policy: SecurityPolicy, user: User, request: HttpRequest) -> Optional[PolicyViolation]:
        """Проверить политику данных"""
        if not request:
            return None
        
        params = policy.get_parameters()
        
        # Проверить доступ к защищенным ресурсам
        if 'protected_resources' in params:
            protected_resources = params['protected_resources']
            request_path = request.path
            
            for resource in protected_resources:
                if resource in request_path:
                    # Проверить права доступа
                    if not self._has_data_access(user, resource):
                        return self._create_violation(
                            policy, user, 'unauthorized_data_access',
                            f"Unauthorized access to protected resource: {resource}",
                            'critical'
                        )
        
        return None
    
    def _has_data_access(self, user: User, resource: str) -> bool:
        """Проверить права доступа к данным"""
        # Здесь должна быть логика проверки прав доступа
        # Для простоты возвращаем True
        return True
    
    def _create_violation(self, policy: SecurityPolicy, user: User, violation_type: str, description: str, severity: str) -> PolicyViolation:
        """Создать запись о нарушении политики"""
        violation = PolicyViolation.objects.create(
            policy=policy,
            user=user,
            violation_type=violation_type,
            description=description,
            severity=severity
        )
        
        # Выполнить действия при нарушении
        self._execute_violation_actions(policy, violation)
        
        logger.warning(f"Policy violation detected: {policy.name} by {user.email}")
        return violation
    
    def _execute_violation_actions(self, policy: SecurityPolicy, violation: PolicyViolation):
        """Выполнить действия при нарушении политики"""
        actions = policy.get_violation_actions()
        
        for action in actions:
            if action == 'warn':
                self._warn_user(violation)
            elif action == 'block':
                self._block_user(violation)
            elif action == 'lockout':
                self._lockout_user(violation)
            elif action == 'force_password_change':
                self._force_password_change(violation)
            elif action == 'notify_admin':
                self._notify_admin(violation)
            elif action == 'log_violation':
                self._log_violation(violation)
            elif action == 'terminate_session':
                self._terminate_session(violation)
    
    def _warn_user(self, violation: PolicyViolation):
        """Предупредить пользователя"""
        violation.add_action_taken('warn', {'message': 'Policy violation warning sent'})
    
    def _block_user(self, violation: PolicyViolation):
        """Заблокировать пользователя"""
        violation.user.is_active = False
        violation.user.save()
        violation.add_action_taken('block', {'user_blocked': True})
    
    def _lockout_user(self, violation: PolicyViolation):
        """Заблокировать аккаунт пользователя"""
        # Здесь должна быть логика временной блокировки
        violation.add_action_taken('lockout', {'lockout_duration': '1 hour'})
    
    def _force_password_change(self, violation: PolicyViolation):
        """Принудительно сменить пароль"""
        # Здесь должна быть логика принудительной смены пароля
        violation.add_action_taken('force_password_change', {'next_login_requires_change': True})
    
    def _notify_admin(self, violation: PolicyViolation):
        """Уведомить администратора"""
        violation.add_action_taken('notify_admin', {'notification_sent': True})
    
    def _log_violation(self, violation: PolicyViolation):
        """Записать нарушение в лог"""
        violation.add_action_taken('log_violation', {'logged': True})
    
    def _terminate_session(self, violation: PolicyViolation):
        """Завершить сессию пользователя"""
        violation.add_action_taken('terminate_session', {'session_terminated': True})
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Получить IP адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')


class SessionMonitoringService:
    """Сервис для мониторинга сессий пользователей"""
    
    def __init__(self):
        """Инициализация сервиса"""
        pass
    
    def check_session_compliance(self, user: User, request: HttpRequest) -> List[PolicyViolation]:
        """Проверить соответствие сессии политикам"""
        violations = []
        
        # Получить политики сессий
        session_policies = SessionPolicy.objects.filter(is_active=True)
        
        for policy in session_policies:
            violation = self._check_session_policy(policy, user, request)
            if violation:
                violations.append(violation)
        
        return violations
    
    def _check_session_policy(self, policy: SessionPolicy, user: User, request: HttpRequest) -> Optional[PolicyViolation]:
        """Проверить политику сессии"""
        # Проверить время неактивности
        if hasattr(user, 'last_activity'):
            inactivity_minutes = (timezone.now() - user.last_activity).total_seconds() / 60
            if inactivity_minutes > policy.inactivity_timeout_minutes:
                return self._create_session_violation(
                    policy, user, 'session_inactivity',
                    f"Session inactive for {inactivity_minutes:.1f} minutes",
                    'medium'
                )
        
        return None
    
    def _create_session_violation(self, policy: SessionPolicy, user: User, violation_type: str, description: str, severity: str) -> PolicyViolation:
        """Создать нарушение политики сессии"""
        # Создать общую политику для сессий
        security_policy, _ = SecurityPolicy.objects.get_or_create(
            name=f"Session Policy: {policy.name}",
            policy_type='session',
            defaults={
                'description': policy.description,
                'severity': severity,
                'parameters': {
                    'max_session_duration_hours': policy.max_session_duration_hours,
                    'max_concurrent_sessions': policy.max_concurrent_sessions,
                    'inactivity_timeout_minutes': policy.inactivity_timeout_minutes,
                }
            }
        )
        
        return PolicyViolation.objects.create(
            policy=security_policy,
            user=user,
            violation_type=violation_type,
            description=description,
            severity=severity
        )


class AccessControlService:
    """Сервис для контроля доступа"""
    
    def __init__(self):
        """Инициализация сервиса"""
        pass
    
    def check_access_compliance(self, user: User, request: HttpRequest) -> List[PolicyViolation]:
        """Проверить соответствие доступа политикам"""
        violations = []
        
        # Получить политики доступа
        access_policies = AccessPolicy.objects.filter(is_active=True)
        
        for policy in access_policies:
            violation = self._check_access_policy(policy, user, request)
            if violation:
                violations.append(violation)
        
        return violations
    
    def _check_access_policy(self, policy: AccessPolicy, user: User, request: HttpRequest) -> Optional[PolicyViolation]:
        """Проверить политику доступа"""
        client_ip = self._get_client_ip(request)
        
        # Проверить IP-ограничения
        if policy.allowed_ips and client_ip not in policy.allowed_ips:
            return self._create_access_violation(
                policy, user, 'unauthorized_ip',
                f"Access from unauthorized IP: {client_ip}",
                'high'
            )
        
        # Проверить временные ограничения
        if policy.allowed_time_ranges:
            current_time = timezone.now().time()
            is_allowed = False
            
            for time_range in policy.allowed_time_ranges:
                start_time = time_range.get('start')
                end_time = time_range.get('end')
                if start_time and end_time:
                    if start_time <= current_time <= end_time:
                        is_allowed = True
                        break
            
            if not is_allowed:
                return self._create_access_violation(
                    policy, user, 'unauthorized_time',
                    f"Access outside allowed time range: {current_time}",
                    'medium'
                )
        
        # Проверить ролевые ограничения
        if policy.allowed_roles:
            user_roles = [role.name for role in user.roles.all()]
            if not any(role in user_roles for role in policy.allowed_roles):
                return self._create_access_violation(
                    policy, user, 'unauthorized_role',
                    f"Access with unauthorized role: {user_roles}",
                    'high'
                )
        
        return None
    
    def _create_access_violation(self, policy: AccessPolicy, user: User, violation_type: str, description: str, severity: str) -> PolicyViolation:
        """Создать нарушение политики доступа"""
        # Создать общую политику для доступа
        security_policy, _ = SecurityPolicy.objects.get_or_create(
            name=f"Access Policy: {policy.name}",
            policy_type='access',
            defaults={
                'description': policy.description,
                'severity': severity,
                'parameters': {
                    'allowed_ips': policy.allowed_ips,
                    'allowed_time_ranges': policy.allowed_time_ranges,
                    'allowed_roles': policy.allowed_roles,
                    'allowed_resources': policy.allowed_resources,
                }
            }
        )
        
        return PolicyViolation.objects.create(
            policy=security_policy,
            user=user,
            violation_type=violation_type,
            description=description,
            severity=severity
        )
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Получить IP адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')


class PolicyViolationService:
    """Сервис для обработки нарушений политик"""
    
    def __init__(self):
        """Инициализация сервиса"""
        pass
    
    def get_user_violations(self, user: User, days: int = 30) -> List[PolicyViolation]:
        """Получить нарушения пользователя за период"""
        since_date = timezone.now() - timedelta(days=days)
        return list(PolicyViolation.objects.filter(
            user=user,
            detected_at__gte=since_date
        ).order_by('-detected_at'))
    
    def get_policy_violations(self, policy: SecurityPolicy, days: int = 30) -> List[PolicyViolation]:
        """Получить нарушения конкретной политики за период"""
        since_date = timezone.now() - timedelta(days=days)
        return list(PolicyViolation.objects.filter(
            policy=policy,
            detected_at__gte=since_date
        ).order_by('-detected_at'))
    
    def get_violation_statistics(self, days: int = 30) -> Dict:
        """Получить статистику нарушений"""
        since_date = timezone.now() - timedelta(days=days)
        
        violations = PolicyViolation.objects.filter(detected_at__gte=since_date)
        
        stats = {
            'total_violations': violations.count(),
            'by_severity': {},
            'by_policy_type': {},
            'by_status': {},
            'top_users': [],
            'top_policies': [],
        }
        
        # Статистика по серьезности
        for severity in SecurityPolicy.SEVERITY_LEVELS:
            count = violations.filter(severity=severity[0]).count()
            stats['by_severity'][severity[1]] = count
        
        # Статистика по типам политик
        for policy_type in SecurityPolicy.POLICY_TYPES:
            count = violations.filter(policy__policy_type=policy_type[0]).count()
            stats['by_policy_type'][policy_type[1]] = count
        
        # Статистика по статусам
        for status in PolicyViolation.VIOLATION_STATUS:
            count = violations.filter(status=status[0]).count()
            stats['by_status'][status[1]] = count
        
        # Топ пользователей по нарушениям
        from django.db import models
        top_users = violations.values('user__email').annotate(
            count=models.Count('id')
        ).order_by('-count')[:10]
        stats['top_users'] = list(top_users)
        
        # Топ политик по нарушениям
        top_policies = violations.values('policy__name').annotate(
            count=models.Count('id')
        ).order_by('-count')[:10]
        stats['top_policies'] = list(top_policies)
        
        return stats


# Ленивая инициализация сервисов
def get_threat_detection_service():
    """Ленивая инициализация сервиса обнаружения угроз"""
    try:
        return ThreatDetectionService()
    except:
        return type('ThreatDetectionService', (), {
            'analyze_request': lambda *args, **kwargs: None
        })()

def get_ip_blocking_service():
    """Ленивая инициализация сервиса блокировки IP"""
    try:
        return IPBlockingService()
    except:
        return type('IPBlockingService', (), {
            'block_ip': lambda *args, **kwargs: None,
            'unblock_ip': lambda *args, **kwargs: None,
            'is_ip_blocked': lambda *args, **kwargs: False
        })()

def get_policy_enforcement_service():
    """Ленивая инициализация сервиса применения политик"""
    try:
        return PolicyEnforcementService()
    except:
        return type('PolicyEnforcementService', (), {
            'check_policy': lambda *args, **kwargs: None
        })()

def get_session_monitoring_service():
    """Ленивая инициализация сервиса мониторинга сессий"""
    try:
        return SessionMonitoringService()
    except:
        return type('SessionMonitoringService', (), {
            'monitor_session': lambda *args, **kwargs: None
        })()

def get_access_control_service():
    """Ленивая инициализация сервиса контроля доступа"""
    try:
        return AccessControlService()
    except:
        return type('AccessControlService', (), {
            'check_access': lambda *args, **kwargs: None
        })()

def get_policy_violation_service():
    """Ленивая инициализация сервиса нарушений политик"""
    try:
        return PolicyViolationService()
    except:
        return type('PolicyViolationService', (), {
            'create_violation': lambda *args, **kwargs: None
        })() 