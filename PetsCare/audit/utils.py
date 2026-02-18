from functools import wraps
from django.utils.translation import gettext as _
from django.db import transaction

from .services import LoggingService, SecurityAuditService

# Инициализируем сервисы
logging_service = LoggingService()
audit_service = SecurityAuditService()


def log_user_action(action_type, details=None):
    """
    Декоратор для логирования действий пользователей.
    
    Args:
        action_type: Тип действия для логирования
        details: Дополнительные детали (опционально)
    
    Returns:
        Декоратор функции
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # Получаем пользователя из запроса
            user = getattr(request, 'user', None)
            
            # Выполняем функцию
            result = func(request, *args, **kwargs)
            
            # Логируем действие
            logging_service.log_action(
                user=user,
                action_type=action_type,
                details=details or {},
                request=request
            )
            
            return result
        return wrapper
    return decorator


def audit_security_operation(audit_type, is_critical=False):
    """
    Декоратор для аудита критически важных операций.
    
    Args:
        audit_type: Тип аудита
        is_critical: Критическая операция
    
    Returns:
        Декоратор функции
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # Получаем пользователя из запроса
            user = getattr(request, 'user', None)
            
            # Выполняем функцию
            result = func(request, *args, **kwargs)
            
            # Аудируем операцию
            audit_service.audit_suspicious_activity(
                user=user,
                activity_type=audit_type,
                details={'function': func.__name__},
                risk_level='high' if is_critical else 'medium'
            )
            
            return result
        return wrapper
    return decorator


def log_business_operation(operation_name):
    """
    Декоратор для логирования бизнес-операций.
    
    Args:
        operation_name: Название операции
    
    Returns:
        Декоратор функции
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Выполняем функцию
            result = func(*args, **kwargs)
            
            # Извлекаем пользователя из аргументов (если есть)
            user = None
            for arg in args:
                if hasattr(arg, 'user'):
                    user = arg.user
                    break
            
            # Логируем бизнес-операцию
            logging_service.log_business_operation(
                user=user,
                operation=operation_name,
                details={'function': func.__name__}
            )
            
            return result
        return wrapper
    return decorator


def audit_financial_operation(operation_type):
    """
    Декоратор для аудита финансовых операций.
    
    Args:
        operation_type: Тип финансовой операции
    
    Returns:
        Декоратор функции
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Выполняем функцию
            result = func(*args, **kwargs)
            
            # Извлекаем данные для аудита
            amount = kwargs.get('amount', 0)
            currency = kwargs.get('currency', 'USD')
            user = kwargs.get('user')
            
            # Аудируем финансовую операцию
            audit_service.audit_financial_operation(
                user=user,
                operation=operation_type,
                amount=amount,
                currency=currency,
                details={'function': func.__name__}
            )
            
            return result
        return wrapper
    return decorator


def log_database_changes(model_class):
    """
    Декоратор для логирования изменений в базе данных.
    
    Args:
        model_class: Класс модели для отслеживания
    
    Returns:
        Декоратор функции
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Выполняем функцию
            result = func(*args, **kwargs)
            
            # Логируем изменение в базе данных
            logging_service.log_system_event(
                'database_change',
                {
                    'model': model_class.__name__,
                    'function': func.__name__,
                    'result_type': type(result).__name__
                }
            )
            
            return result
        return wrapper
    return decorator


def audit_role_changes():
    """
    Декоратор для аудита изменений ролей пользователей.
    
    Returns:
        Декоратор функции
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # Получаем данные до изменения
            user_id = kwargs.get('user_id')
            if user_id:
                from users.models import User
                try:
                    user = User.objects.get(id=user_id)
                    old_roles = list(user.user_types.all().values_list('name', flat=True))
                except User.DoesNotExist:
                    old_roles = []
            else:
                old_roles = []
            
            # Выполняем функцию
            result = func(request, *args, **kwargs)
            
            # Получаем новые роли
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    new_roles = list(user.user_types.all().values_list('name', flat=True))
                    
                    # Аудируем изменение ролей
                    if old_roles != new_roles:
                        audit_service.audit_role_change(
                            user=request.user,
                            target_user=user,
                            old_roles=old_roles,
                            new_roles=new_roles,
                            reason=_('Role change via API'),
                            is_critical=True
                        )
                except User.DoesNotExist:
                    pass
            
            return result
        return wrapper
    return decorator


def log_api_request():
    """
    Декоратор для логирования API запросов.
    
    Returns:
        Декоратор функции
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # Засекаем время начала
            import time
            start_time = time.time()
            
            # Выполняем функцию
            result = func(request, *args, **kwargs)
            
            # Вычисляем время выполнения
            execution_time = time.time() - start_time
            
            # Логируем API запрос
            logging_service.log_action(
                user=getattr(request, 'user', None),
                action_type='api_request',
                details={
                    'endpoint': request.path,
                    'method': request.method,
                    'status_code': getattr(result, 'status_code', 200),
                    'execution_time': execution_time
                },
                request=request,
                execution_time=execution_time
            )
            
            return result
        return wrapper
    return decorator


def audit_suspicious_activity(activity_type, risk_level='medium'):
    """
    Декоратор для аудита подозрительной активности.
    
    Args:
        activity_type: Тип подозрительной активности
        risk_level: Уровень риска ('low', 'medium', 'high')
    
    Returns:
        Декоратор функции
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # Выполняем функцию
            result = func(request, *args, **kwargs)
            
            # Аудируем подозрительную активность
            audit_service.audit_suspicious_activity(
                user=getattr(request, 'user', None),
                activity_type=activity_type,
                details={
                    'function': func.__name__,
                    'endpoint': request.path,
                    'method': request.method
                },
                risk_level=risk_level
            )
            
            return result
        return wrapper
    return decorator


class AuditContext:
    """
    Контекстный менеджер для аудита операций.
    
    Позволяет логировать и аудировать операции в блоке кода.
    """
    
    def __init__(self, operation_name, user=None, is_critical=False):
        """
        Инициализация контекста аудита.
        
        Args:
            operation_name: Название операции
            user: Пользователь, выполняющий операцию
            is_critical: Критическая операция
        """
        self.operation_name = operation_name
        self.user = user
        self.is_critical = is_critical
        self.start_time = None
    
    def __enter__(self):
        """Вход в контекст"""
        import time
        self.start_time = time.time()
        
        # Логируем начало операции
        logging_service.log_action(
            user=self.user,
            action_type='operation_start',
            details={'operation': self.operation_name}
        )
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Выход из контекста"""
        import time
        
        # Вычисляем время выполнения
        execution_time = time.time() - self.start_time
        
        # Определяем результат операции
        if exc_type is None:
            result = 'success'
        else:
            result = 'error'
        
        # Логируем завершение операции
        logging_service.log_action(
            user=self.user,
            action_type='operation_end',
            details={
                'operation': self.operation_name,
                'result': result,
                'execution_time': execution_time
            }
        )
        
        # Если операция критическая, аудируем её
        if self.is_critical:
            audit_service.audit_suspicious_activity(
                user=self.user,
                activity_type=f'critical_operation_{result}',
                details={
                    'operation': self.operation_name,
                    'execution_time': execution_time
                },
                risk_level='high'
            )
        
        # Возвращаем False, чтобы исключения не подавлялись
        return False 