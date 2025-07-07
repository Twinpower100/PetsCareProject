from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import gettext as _
from .models import ProviderBlocking, Contract, BlockingSystemSettings
from providers.models import Provider
import json
import logging
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class ProviderBlockingMiddleware(MiddlewareMixin):
    """
    Middleware для автоматической блокировки учреждений.
    
    Особенности:
    - Проверка блокировок при каждом запросе
    - Учет настроек системы блокировки
    - Поддержка исключений из автоматических проверок
    - Кэширование результатов проверок
    - Логирование действий
    """
    
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.settings = None
        self._load_settings()
    
    def _load_settings(self):
        """Загружает настройки системы блокировки."""
        try:
            self.settings = BlockingSystemSettings.get_settings()
        except Exception as e:
            logger.warning(f"Could not load blocking settings: {e}")
            self.settings = None
    
    def process_request(self, request):
        """
        Обрабатывает входящий запрос.
        
        Args:
            request: HTTP запрос
            
        Returns:
            HttpResponse или None
        """
        # Проверяем, включена ли система блокировки
        if not self.settings or not self.settings.is_system_enabled:
            return None
        
        # Получаем учреждение из запроса
        provider = self._get_provider_from_request(request)
        if not provider:
            return None
        
        # Проверяем, исключено ли учреждение из автоматических проверок
        if provider.exclude_from_blocking_checks:
            return None
        
        # Проверяем активные блокировки
        blocking_result = self._check_provider_blocking(provider)
        
        if blocking_result['is_blocked']:
            return self._handle_blocked_provider(request, provider, blocking_result)
        
        return None
    
    def _get_provider_from_request(self, request):
        """
        Извлекает учреждение из запроса.
        
        Args:
            request: HTTP запрос
            
        Returns:
            Provider или None
        """
        try:
            # Проверяем различные способы получения учреждения
            provider_id = None
            
            # Из URL параметров
            if 'provider_id' in request.GET:
                provider_id = request.GET.get('provider_id')
            elif 'provider' in request.GET:
                provider_id = request.GET.get('provider')
            
            # Из POST данных
            if not provider_id and request.method == 'POST':
                if 'provider_id' in request.POST:
                    provider_id = request.POST.get('provider_id')
                elif 'provider' in request.POST:
                    provider_id = request.POST.get('provider')
            
            # Из JSON данных
            if not provider_id and request.content_type == 'application/json':
                try:
                    import json
                    data = json.loads(request.body)
                    provider_id = data.get('provider_id') or data.get('provider')
                except (json.JSONDecodeError, AttributeError):
                    pass
            
            # Из пути URL
            if not provider_id:
                path_parts = request.path.split('/')
                for i, part in enumerate(path_parts):
                    if part == 'providers' and i + 1 < len(path_parts):
                        provider_id = path_parts[i + 1]
                        break
            
            if provider_id:
                from providers.models import Provider
                return Provider.objects.get(id=provider_id, is_active=True)
                
        except (ValueError, Provider.DoesNotExist):
            pass
        except Exception as e:
            logger.error(f"Error extracting provider from request: {e}")
        
        return None
    
    def _check_provider_blocking(self, provider):
        """
        Проверяет блокировку учреждения.
        
        Args:
            provider: Объект Provider
            
        Returns:
            dict: Результат проверки
        """
        try:
            # Получаем активные блокировки
            active_blockings = ProviderBlocking.objects.filter(
                provider=provider,
                status='active'
            ).select_related('currency')
            
            if not active_blockings.exists():
                return {
                    'is_blocked': False,
                    'blocking_level': 0,
                    'reasons': []
                }
            
            # Определяем максимальный уровень блокировки
            max_level = 0
            reasons = []
            
            for blocking in active_blockings:
                # Определяем уровень блокировки на основе задолженности
                if blocking.debt_amount > 0:
                    if blocking.overdue_days >= 90:  # Критическая просрочка
                        level = 3
                    elif blocking.overdue_days >= 60:  # Высокая просрочка
                        level = 2
                    elif blocking.overdue_days >= 30:  # Предупреждение
                        level = 1
                    else:
                        level = 0
                    
                    max_level = max(max_level, level)
                    
                    if level > 0:
                        reasons.append(
                            f"Debt: {blocking.debt_amount} {blocking.currency.code}, "
                            f"Overdue: {blocking.overdue_days} days"
                        )
            
            return {
                'is_blocked': max_level > 0,
                'blocking_level': max_level,
                'reasons': reasons,
                'blockings': list(active_blockings)
            }
            
        except Exception as e:
            logger.error(f"Error checking provider blocking: {e}")
            return {
                'is_blocked': False,
                'blocking_level': 0,
                'reasons': [f"Error: {str(e)}"]
            }
    
    def _handle_blocked_provider(self, request, provider, blocking_result):
        """
        Обрабатывает запрос к заблокированному учреждению.
        
        Args:
            request: HTTP запрос
            provider: Объект Provider
            blocking_result: Результат проверки блокировки
            
        Returns:
            HttpResponse: Ответ с информацией о блокировке
        """
        blocking_level = blocking_result['blocking_level']
        
        # Логируем попытку доступа к заблокированному учреждению
        if self.settings and self.settings.log_all_checks:
            logger.warning(
                f"Access attempt to blocked provider {provider.name} "
                f"(level {blocking_level}) from {request.META.get('REMOTE_ADDR', 'unknown')}"
            )
        
        # Определяем тип ответа в зависимости от уровня блокировки
        if blocking_level >= 3:  # Полная блокировка
            return self._create_blocking_response(
                request, provider, blocking_result, 
                status_code=403,
                message=_("Provider is completely blocked due to critical debt")
            )
        elif blocking_level >= 2:  # Исключение из поиска
            return self._create_blocking_response(
                request, provider, blocking_result,
                status_code=403,
                message=_("Provider is excluded from search due to high debt")
            )
        else:  # Уровень 1 - только предупреждение
            # Для уровня 1 разрешаем доступ, но добавляем предупреждение
            request.provider_blocking_warning = {
                'provider': provider,
                'level': blocking_level,
                'reasons': blocking_result['reasons']
            }
            return None
    
    def _create_blocking_response(self, request, provider, blocking_result, status_code, message):
        """
        Создает ответ о блокировке.
        
        Args:
            request: HTTP запрос
            provider: Объект Provider
            blocking_result: Результат проверки блокировки
            status_code: HTTP код ответа
            message: Сообщение о блокировке
            
        Returns:
            HttpResponse: Ответ с информацией о блокировке
        """
        # Определяем формат ответа
        if request.headers.get('accept') == 'application/json' or request.path.startswith('/api/'):
            # JSON ответ для API
            response_data = {
                'error': 'provider_blocked',
                'message': message,
                'provider_id': provider.id,
                'provider_name': provider.name,
                'blocking_level': blocking_result['blocking_level'],
                'reasons': blocking_result['reasons'],
                'blocked_at': timezone.now().isoformat()
            }
            
            return JsonResponse(response_data, status=status_code)
        else:
            # HTML ответ для веб-интерфейса
            from django.shortcuts import render
            context = {
                'provider': provider,
                'blocking_level': blocking_result['blocking_level'],
                'reasons': blocking_result['reasons'],
                'message': message
            }
            
            return render(request, 'billing/provider_blocked.html', context, status=status_code)
    
    def process_response(self, request, response):
        """
        Обрабатывает исходящий ответ.
        
        Args:
            request: HTTP запрос
            response: HTTP ответ
            
        Returns:
            HttpResponse: Обработанный ответ
        """
        # Добавляем предупреждение о блокировке, если есть
        if hasattr(request, 'provider_blocking_warning'):
            warning = request.provider_blocking_warning
            
            # Добавляем заголовок с предупреждением
            response['X-Provider-Blocking-Warning'] = f"Level {warning['level']}: {'; '.join(warning['reasons'])}"
            
            # Для JSON ответов добавляем предупреждение в тело
            if response.headers.get('content-type', '').startswith('application/json'):
                try:
                    import json
                    data = json.loads(response.content)
                    data['blocking_warning'] = {
                        'level': warning['level'],
                        'reasons': warning['reasons'],
                        'provider_name': warning['provider'].name
                    }
                    response.content = json.dumps(data, ensure_ascii=False)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
        
        return response
    
    def process_exception(self, request, exception):
        """
        Обрабатывает исключения.
        
        Args:
            request: HTTP запрос
            exception: Исключение
            
        Returns:
            HttpResponse или None
        """
        # Логируем исключения, связанные с блокировками
        if 'provider' in str(exception).lower() or 'blocking' in str(exception).lower():
            logger.error(f"Blocking-related exception: {exception}")
        
        return None


class BlockingLoggingMiddleware(MiddlewareMixin):
    """
    Middleware для логирования действий блокировки.
    
    Особенности:
    - Логирование всех попыток доступа к заблокированным учреждениям
    - Сбор статистики блокировок
    - Мониторинг производительности
    """
    
    def process_request(self, request):
        """Обрабатывает входящий запрос для логирования."""
        # Добавляем метку времени начала обработки
        request.blocking_start_time = timezone.now()
        return None
    
    def process_response(self, request, response):
        """Обрабатывает исходящий ответ для логирования."""
        # Логируем информацию о блокировках
        if hasattr(request, 'blocking_start_time'):
            processing_time = (timezone.now() - request.blocking_start_time).total_seconds()
            
            # Логируем медленные запросы
            if processing_time > 1.0:  # Более 1 секунды
                logger.warning(f"Slow blocking check: {processing_time:.2f}s for {request.path}")
            
            # Логируем блокировки
            if response.status_code in [403, 451]:  # Заблокированные запросы
                logger.info(
                    f"Blocked request: {request.method} {request.path} "
                    f"from {request.META.get('REMOTE_ADDR', 'unknown')} "
                    f"in {processing_time:.2f}s"
                )
        
        return response


class ProviderBlockingMiddleware(MiddlewareMixin):
    """
    Middleware для многоуровневой блокировки доступа к API учреждений.
    
    Проверяет все запросы к API и применяет разные уровни ограничений:
    1. Информационное уведомление (не блокирует)
    2. Исключение из поиска (блокирует поиск)
    3. Полная блокировка (блокирует все API)
    """
    
    def process_request(self, request):
        # Проверяем только API запросы
        if not request.path.startswith('/api/'):
            return None
            
        # Исключаем некоторые эндпоинты (например, для админов)
        excluded_paths = [
            '/api/admin/',
            '/api/billing/',
            '/api/auth/',
        ]
        
        for excluded_path in excluded_paths:
            if request.path.startswith(excluded_path):
                return None
        
        # Получаем provider_id из запроса
        provider_id = self._get_provider_id_from_request(request)
        
        if provider_id:
            # Проверяем уровень блокировки учреждения
            blocking_level = self._get_provider_blocking_level(provider_id)
            
            if blocking_level >= 3:
                # Полная блокировка - блокируем все API
                return JsonResponse({
                    'error': 'Provider is fully blocked due to outstanding debt',
                    'message': 'Учреждение полностью заблокировано из-за задолженности',
                    'code': 'PROVIDER_FULLY_BLOCKED',
                    'blocking_level': 3
                }, status=403)
            
            elif blocking_level == 2:
                # Исключение из поиска - блокируем только поиск
                if self._is_search_request(request):
                    return JsonResponse({
                        'error': 'Provider is excluded from search due to outstanding debt',
                        'message': 'Учреждение исключено из поиска из-за задолженности',
                        'code': 'PROVIDER_SEARCH_BLOCKED',
                        'blocking_level': 2
                    }, status=403)
            
            elif blocking_level == 1:
                # Информационное уведомление - добавляем заголовок, но не блокируем
                request.META['HTTP_X_PROVIDER_WARNING'] = 'true'
        
        return None
    
    def _get_provider_id_from_request(self, request):
        """
        Извлекает provider_id из различных источников запроса.
        """
        # Из URL параметров
        provider_id = request.GET.get('provider_id') or request.GET.get('provider')
        
        # Из POST/PUT данных
        if not provider_id and request.method in ['POST', 'PUT', 'PATCH']:
            try:
                if request.content_type == 'application/json':
                    data = json.loads(request.body)
                    provider_id = data.get('provider_id') or data.get('provider')
                else:
                    provider_id = request.POST.get('provider_id') or request.POST.get('provider')
            except (json.JSONDecodeError, AttributeError):
                pass
        
        # Из URL path (например, /api/providers/123/services/)
        if not provider_id:
            path_parts = request.path.split('/')
            try:
                # Ищем pattern /api/providers/{id}/
                if 'providers' in path_parts:
                    provider_index = path_parts.index('providers')
                    if provider_index + 1 < len(path_parts):
                        provider_id = path_parts[provider_index + 1]
            except (ValueError, IndexError):
                pass
        
        # Из заголовка Authorization (если используется JWT с provider_id)
        if not provider_id:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                # Здесь можно добавить логику извлечения provider_id из JWT токена
                pass
        
        return provider_id
    
    def _get_provider_blocking_level(self, provider_id):
        """
        Определяет уровень блокировки учреждения.
        
        Returns:
            int: 0 - нет блокировки, 1 - инфо, 2 - исключение из поиска, 3 - полная блокировка
        """
        try:
            # Сначала проверяем активные блокировки
            active_blockings = ProviderBlocking.objects.filter(
                provider_id=provider_id,
                status='active'
            )
            
            if active_blockings.exists():
                # Если есть активная блокировка, возвращаем максимальный уровень
                return 3
            
            # Проверяем договоры учреждения на предмет индивидуальных порогов
            provider = Provider.objects.filter(id=provider_id).first()
            if not provider:
                return 0
            
            # Получаем максимальный уровень блокировки среди всех активных договоров
            max_blocking_level = 0
            for contract in provider.contracts.filter(status='active'):
                blocking_level = contract.get_blocking_level()
                max_blocking_level = max(max_blocking_level, blocking_level)
            
            return max_blocking_level
            
        except (ValueError, TypeError):
            # Если provider_id не является валидным числом
            return 0
    
    def _is_search_request(self, request):
        """
        Проверяет, является ли запрос поисковым.
        """
        search_paths = [
            '/api/providers/search/',
            '/api/providers/filter/',
            '/api/search/',
        ]
        
        # Проверяем URL
        for search_path in search_paths:
            if request.path.startswith(search_path):
                return True
        
        # Проверяем параметры запроса
        search_params = ['search', 'q', 'query', 'filter']
        for param in search_params:
            if param in request.GET:
                return True
        
        # Проверяем метод и путь для типичных поисковых запросов
        if request.method == 'GET' and 'providers' in request.path:
            return True
        
        return False
    
    def _is_provider_blocked(self, provider_id):
        """
        Проверяет, заблокировано ли учреждение (устаревший метод).
        """
        try:
            # Проверяем, существует ли активная блокировка
            return ProviderBlocking.objects.filter(
                provider_id=provider_id,
                status='active'
            ).exists()
        except (ValueError, TypeError):
            # Если provider_id не является валидным числом
            return False 