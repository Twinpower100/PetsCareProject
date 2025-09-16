import json
import time
from typing import Dict, Any, Optional, List
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.core.cache import cache
from django.db import transaction
from django.utils.translation import gettext as _

from .models import UserAction, SecurityAudit, AuditSettings


class LoggingService:
    """
    Сервис для централизованного логирования действий пользователей.
    
    Обеспечивает автоматическое логирование всех операций
    в системе для обеспечения прозрачности и контроля.
    """
    
    def __init__(self):
        """Инициализация сервиса логирования"""
        self._settings = None
    
    @property
    def settings(self):
        """Ленивая загрузка настроек аудита"""
        if self._settings is None:
            try:
                # Ленивая инициализация - только при первом обращении
                from django.db import connection
                if connection.introspection.table_names():
                    self._settings = AuditSettings.get_settings()
                else:
                    # Если таблицы еще не созданы, используем значения по умолчанию
                    self._settings = type('Settings', (), {
                        'logging_enabled': True,
                        'security_audit_enabled': True,
                        'log_retention_days': 365,
                        'security_audit_retention_days': 2555,
                        'log_http_requests': True,
                        'log_database_changes': True,
                        'log_business_operations': True,
                        'log_system_events': True,
                    })()
            except:
                # Если БД еще не готова, используем дефолтные настройки
                from django.conf import settings
                self._settings = type('Settings', (), {
                    'logging_enabled': getattr(settings, 'AUDIT_LOGGING_ENABLED', True),
                    'security_audit_enabled': getattr(settings, 'AUDIT_SECURITY_ENABLED', True),
                })()
        return self._settings
    
    def log_action(self, user: Optional[Any], action_type: str, 
                  content_object: Optional[Any] = None, details: Dict[str, Any] = None,
                  request: Optional[Any] = None, execution_time: float = None) -> UserAction:
        """
        Логирует действие пользователя.
        
        Args:
            user: Пользователь, выполнивший действие
            action_type: Тип действия
            content_object: Объект, с которым связано действие
            details: Дополнительные детали
            request: HTTP запрос (для извлечения метаданных)
            execution_time: Время выполнения в секундах
            
        Returns:
            Созданная запись лога
        """
        if not self.settings.logging_enabled:
            return None
        
        # Подготавливаем данные для логирования
        log_data = {
            'user': user,
            'action_type': action_type,
            'details': details or {},
            'execution_time': execution_time,
        }
        
        # Добавляем информацию об объекте
        if content_object:
            log_data['content_type'] = ContentType.objects.get_for_model(content_object)
            log_data['object_id'] = content_object.id
        
        # Добавляем информацию из запроса
        if request:
            log_data.update(self._extract_request_data(request))
        
        # Создаем запись лога
        return UserAction.objects.create(**log_data)
    
    def log_http_request(self, request, response, execution_time: float) -> Optional[UserAction]:
        """
        Логирует HTTP запрос.
        
        Args:
            request: HTTP запрос
            response: HTTP ответ
            execution_time: Время выполнения в секундах
            
        Returns:
            Созданная запись лога или None
        """
        if not self.settings.log_http_requests:
            return None
        
        # Определяем тип действия
        action_type = self._determine_action_type(request)
        
        # Получаем пользователя
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            user = user
        else:
            user = None
        
        # Логируем действие
        return self.log_action(
            user=user,
            action_type=action_type,
            details={
                'method': request.method,
                'url': request.get_full_path(),
                'status_code': response.status_code,
                'content_length': len(response.content) if hasattr(response, 'content') else 0,
            },
            request=request,
            execution_time=execution_time
        )
    
    def log_business_operation(self, user: Any, operation: str, 
                             content_object: Any = None, details: Dict[str, Any] = None) -> UserAction:
        """
        Логирует бизнес-операцию.
        
        Args:
            user: Пользователь
            operation: Название операции
            content_object: Объект операции
            details: Детали операции
            
        Returns:
            Созданная запись лога
        """
        if not self.settings.log_business_operations:
            return None
        
        return self.log_action(
            user=user,
            action_type=operation,
            content_object=content_object,
            details=details or {}
        )
    
    def log_system_event(self, event: str, details: Dict[str, Any] = None) -> UserAction:
        """
        Логирует системное событие.
        
        Args:
            event: Название события
            details: Детали события
            
        Returns:
            Созданная запись лога
        """
        if not self.settings.log_system_events:
            return None
        
        return self.log_action(
            user=None,
            action_type='system',
            details={
                'event': event,
                **(details or {})
            }
        )
    
    def _extract_request_data(self, request) -> Dict[str, Any]:
        """
        Извлекает данные из HTTP запроса.
        
        Args:
            request: HTTP запрос
            
        Returns:
            Словарь с данными запроса
        """
        return {
            'ip_address': self._get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'http_method': request.method,
            'url': request.get_full_path(),
            'session_key': request.session.session_key if hasattr(request, 'session') else '',
        }
    
    def _get_client_ip(self, request) -> str:
        """
        Получает IP-адрес клиента.
        
        Args:
            request: HTTP запрос
            
        Returns:
            IP-адрес клиента
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _determine_action_type(self, request) -> str:
        """
        Определяет тип действия по HTTP методу.
        
        Args:
            request: HTTP запрос
            
        Returns:
            Тип действия
        """
        method = request.method.upper()
        
        if method == 'GET':
            return 'view'
        elif method == 'POST':
            return 'create'
        elif method == 'PUT':
            return 'update'
        elif method == 'PATCH':
            return 'update'
        elif method == 'DELETE':
            return 'delete'
        else:
            return 'system'


class SecurityAuditService:
    """
    Сервис для аудита критически важных операций безопасности.
    
    Обеспечивает отслеживание изменений в системе безопасности
    и критически важных операций для обеспечения контроля.
    """
    
    def __init__(self):
        """Инициализация сервиса аудита"""
        self._settings = None
    
    @property
    def settings(self):
        """Ленивая загрузка настроек аудита"""
        if self._settings is None:
            try:
                # Ленивая инициализация - только при первом обращении
                from django.db import connection
                if connection.introspection.table_names():
                    self._settings = AuditSettings.get_settings()
                else:
                    # Если таблицы еще не созданы, используем значения по умолчанию
                    self._settings = type('Settings', (), {
                        'logging_enabled': True,
                        'security_audit_enabled': True,
                        'log_retention_days': 365,
                        'security_audit_retention_days': 2555,
                        'log_http_requests': True,
                        'log_database_changes': True,
                        'log_business_operations': True,
                        'log_system_events': True,
                    })()
            except:
                # Если БД еще не готова, используем дефолтные настройки
                self._settings = type('Settings', (), {
                    'logging_enabled': True,
                    'security_audit_enabled': True,
                    'log_retention_days': 365,
                    'security_audit_retention_days': 2555,
                    'log_http_requests': True,
                    'log_database_changes': True,
                    'log_business_operations': True,
                    'log_system_events': True,
                })()
        return self._settings
    
    def audit_role_change(self, user: Any, target_user: Any, 
                         old_roles: List[str], new_roles: List[str],
                         reason: str = '', is_critical: bool = False) -> SecurityAudit:
        """
        Аудирует изменение ролей пользователя.
        
        Args:
            user: Пользователь, изменивший роли
            target_user: Пользователь, чьи роли изменились
            old_roles: Старые роли
            new_roles: Новые роли
            reason: Причина изменения
            is_critical: Критическая операция
            
        Returns:
            Запись аудита
        """
        if not self.settings.security_audit_enabled:
            return None
        
        return SecurityAudit.objects.create(
            user=user,
            audit_type='role_change',
            content_object=target_user,
            details={
                'target_user_id': target_user.id,
                'target_user_email': target_user.email,
            },
            old_values={'roles': old_roles},
            new_values={'roles': new_roles},
            reason=reason,
            is_critical=is_critical
        )
    
    def audit_invite_management(self, user: Any, invite: Any, action: str,
                               reason: str = '') -> SecurityAudit:
        """
        Аудирует управление инвайтами.
        
        Args:
            user: Пользователь, выполнивший действие
            invite: Инвайт
            action: Действие (create, accept, reject, delete)
            reason: Причина
            
        Returns:
            Запись аудита
        """
        if not self.settings.security_audit_enabled:
            return None
        
        return SecurityAudit.objects.create(
            user=user,
            audit_type='invite_management',
            content_object=invite,
            details={
                'action': action,
                'invite_type': getattr(invite, 'invite_type', ''),
                'invite_email': getattr(invite, 'email', ''),
            },
            old_values={},
            new_values={'action': action},
            reason=reason,
            is_critical=True
        )
    
    def audit_financial_operation(self, user: Any, operation: str,
                                amount: float, currency: str,
                                content_object: Any = None,
                                details: Dict[str, Any] = None) -> SecurityAudit:
        """
        Аудирует финансовую операцию.
        
        Args:
            user: Пользователь
            operation: Тип операции
            amount: Сумма
            currency: Валюта
            content_object: Объект операции
            details: Детали операции
            
        Returns:
            Запись аудита
        """
        if not self.settings.security_audit_enabled:
            return None
        
        return SecurityAudit.objects.create(
            user=user,
            audit_type='financial_operation',
            content_object=content_object,
            details={
                'operation': operation,
                'amount': amount,
                'currency': currency,
                **(details or {})
            },
            old_values={},
            new_values={
                'operation': operation,
                'amount': amount,
                'currency': currency,
            },
            reason=f"Financial operation: {operation}",
            is_critical=True
        )
    
    def audit_blocking_operation(self, user: Any, target: Any, action: str,
                               reason: str, duration: str = None) -> SecurityAudit:
        """
        Аудирует операцию блокировки/разблокировки.
        
        Args:
            user: Пользователь, выполнивший действие
            target: Цель блокировки
            action: Действие (block, unblock)
            reason: Причина
            duration: Длительность блокировки
            
        Returns:
            Запись аудита
        """
        if not self.settings.security_audit_enabled:
            return None
        
        return SecurityAudit.objects.create(
            user=user,
            audit_type='blocking_operation',
            content_object=target,
            details={
                'action': action,
                'duration': duration,
                'target_type': target.__class__.__name__,
            },
            old_values={'blocked': action == 'unblock'},
            new_values={'blocked': action == 'block'},
            reason=reason,
            is_critical=True
        )
    
    def audit_ownership_transfer(self, user: Any, pet: Any,
                               old_owner: Any, new_owner: Any,
                               reason: str = '') -> SecurityAudit:
        """
        Аудирует передачу прав владения питомцем.
        
        Args:
            user: Пользователь, выполнивший передачу
            pet: Питомец
            old_owner: Старый владелец
            new_owner: Новый владелец
            reason: Причина передачи
            
        Returns:
            Запись аудита
        """
        if not self.settings.security_audit_enabled:
            return None
        
        return SecurityAudit.objects.create(
            user=user,
            audit_type='ownership_transfer',
            content_object=pet,
            details={
                'pet_id': pet.id,
                'pet_name': getattr(pet, 'name', ''),
            },
            old_values={'owner_id': old_owner.id, 'owner_email': old_owner.email},
            new_values={'owner_id': new_owner.id, 'owner_email': new_owner.email},
            reason=reason,
            is_critical=True
        )
    
    def audit_suspicious_activity(self, user: Any, activity_type: str,
                                details: Dict[str, Any], risk_level: str = 'medium') -> SecurityAudit:
        """
        Аудирует подозрительную активность.
        
        Args:
            user: Пользователь
            activity_type: Тип активности
            details: Детали активности
            risk_level: Уровень риска
            
        Returns:
            Запись аудита
        """
        if not self.settings.security_audit_enabled:
            return None
        
        return SecurityAudit.objects.create(
            user=user,
            audit_type='suspicious_activity',
            content_object=user,
            details={
                'activity_type': activity_type,
                'risk_level': risk_level,
                **details
            },
            old_values={},
            new_values={'activity_type': activity_type, 'risk_level': risk_level},
            reason=f"Suspicious activity detected: {activity_type}",
            is_critical=True
        )


class AuditMiddleware:
    """
    Middleware для автоматического логирования HTTP запросов.
    
    Перехватывает все HTTP запросы и автоматически логирует их
    для обеспечения полного контроля над активностью пользователей.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.logging_service = LoggingService()
    
    def __call__(self, request):
        # Засекаем время начала
        start_time = time.time()
        
        # Обрабатываем запрос
        response = self.get_response(request)
        
        # Вычисляем время выполнения
        execution_time = time.time() - start_time
        
        # Логируем запрос
        self.logging_service.log_http_request(request, response, execution_time)
        
        return response 