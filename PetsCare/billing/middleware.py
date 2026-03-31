"""Middleware для реакции API на уровни billing-блокировки провайдера."""

import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import gettext as _

from providers.models import EmployeeProvider, Provider

from .models import BlockingSystemSettings
from .services import MultiLevelBlockingService

logger = logging.getLogger(__name__)


class ProviderBlockingMiddleware(MiddlewareMixin):
    """
    Проверяет провайдера на текущую billing-блокировку и корректирует ответ.

    Поведение:
    - уровень 1: запрос проходит, но добавляется warning-header,
    - уровень 2: для поисковых GET-запросов возвращается 451, для остальных 403,
    - уровень 3: всегда 403.
    """

    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.settings = None
        self.blocking_service = MultiLevelBlockingService()
        self._load_settings()

    def _load_settings(self):
        """Загружает настройки системы блокировки."""
        try:
            self.settings = BlockingSystemSettings.get_settings()
        except Exception as exc:
            logger.warning("Could not load blocking settings: %s", exc)
            self.settings = None

    def process_request(self, request):
        """Проверяет запрос до передачи в view."""
        if not self.settings or not self.settings.is_system_enabled:
            return None

        provider = self._get_provider_from_request(request)
        if provider is None or provider.exclude_from_blocking_checks:
            return None

        blocking_result = self._check_provider_blocking(provider)
        if not blocking_result['is_blocked']:
            return None

        return self._handle_blocked_provider(request, provider, blocking_result)

    def _get_provider_from_request(self, request):
        """
        Пытается извлечь провайдера из параметров запроса, URL или роли пользователя.
        """
        provider_id = (
            request.GET.get('provider_id')
            or request.GET.get('provider')
            or getattr(request, 'resolver_match', None) and request.resolver_match.kwargs.get('provider_id')
            or getattr(request, 'resolver_match', None) and request.resolver_match.kwargs.get('pk')
        )

        if provider_id is None and request.method in {'POST', 'PUT', 'PATCH'}:
            provider_id = request.POST.get('provider_id') or request.POST.get('provider')

        if provider_id is None and request.content_type == 'application/json' and request.body:
            try:
                payload = json.loads(request.body)
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            provider_id = payload.get('provider_id') or payload.get('provider')

        if provider_id:
            try:
                return Provider.objects.get(id=provider_id, is_active=True)
            except (Provider.DoesNotExist, ValueError, TypeError):
                return None

        if request.user.is_authenticated:
            managed_provider = request.user.get_managed_providers().order_by('id').first()
            if managed_provider is not None:
                return managed_provider

            employee_provider = EmployeeProvider.get_active_ep_for_user_provider(
                request.user,
                Provider.objects.filter(is_active=True).order_by('id').first(),
            )
            if employee_provider is not None:
                return employee_provider.provider

        return None

    def _check_provider_blocking(self, provider):
        """
        Возвращает нормализованный результат текущей blocking-оценки.
        """
        result = self.blocking_service.check_provider_blocking(provider)
        if result['should_block']:
            return {
                'is_blocked': True,
                'blocking_level': result['blocking_level'],
                'reasons': result['reasons'],
                'active_blocking': result.get('active_blocking'),
            }

        return {
            'is_blocked': False,
            'blocking_level': 0,
            'reasons': [],
            'active_blocking': result.get('active_blocking'),
        }

    def _handle_blocked_provider(self, request, provider, blocking_result):
        """
        Применяет HTTP-реакцию в зависимости от уровня блокировки.
        """
        blocking_level = blocking_result['blocking_level']

        if self.settings and self.settings.log_all_checks:
            logger.warning(
                "Billing blocking rejected request for provider=%s level=%s path=%s",
                provider.id,
                blocking_level,
                request.path,
            )

        if blocking_level >= 3:
            return self._create_blocking_response(
                request,
                provider,
                blocking_result,
                status_code=403,
                message=_("Provider is blocked due to critical billing debt"),
            )

        if blocking_level == 2:
            status_code = 451 if self._is_search_request(request) else 403
            message = (
                _("Provider is hidden from search due to billing debt")
                if status_code == 451
                else _("Provider access is restricted due to billing debt")
            )
            return self._create_blocking_response(
                request,
                provider,
                blocking_result,
                status_code=status_code,
                message=message,
            )

        request.provider_blocking_warning = {
            'provider': provider,
            'level': blocking_level,
            'reasons': blocking_result['reasons'],
        }
        return None

    def _is_search_request(self, request) -> bool:
        """Определяет публичный поисковый запрос, где нужен 451."""
        return request.method == 'GET' and (
            '/search/' in request.path
            or request.path.endswith('/providers/search/')
            or request.path.endswith('/providers/search/map/')
        )

    def _create_blocking_response(self, request, provider, blocking_result, *, status_code, message):
        """
        Создает JSON или HTML ответ о блокировке.
        """
        payload = {
            'error': 'provider_blocked',
            'message': message,
            'provider_id': provider.id,
            'provider_name': provider.name,
            'blocking_level': blocking_result['blocking_level'],
            'reasons': blocking_result['reasons'],
            'blocked_at': timezone.now().isoformat(),
        }

        if request.headers.get('accept') == 'application/json' or request.path.startswith('/api/'):
            return JsonResponse(payload, status=status_code)

        return render(
            request,
            'billing/provider_blocked.html',
            {
                'provider': provider,
                'blocking_level': blocking_result['blocking_level'],
                'reasons': blocking_result['reasons'],
                'message': message,
            },
            status=status_code,
        )

    def process_response(self, request, response):
        """
        Добавляет warning-header и JSON warning для уровня 1.
        """
        if not hasattr(request, 'provider_blocking_warning'):
            return response

        warning = request.provider_blocking_warning
        response['X-Provider-Blocking-Warning'] = (
            f"Level {warning['level']}: {'; '.join(warning['reasons'])}"
        )

        if response.headers.get('content-type', '').startswith('application/json'):
            try:
                data = json.loads(response.content.decode('utf-8'))
            except (ValueError, UnicodeDecodeError, AttributeError):
                return response

            data['blocking_warning'] = {
                'level': warning['level'],
                'reasons': warning['reasons'],
                'provider_name': warning['provider'].name,
            }
            response.content = json.dumps(data, ensure_ascii=False).encode('utf-8')

        return response

    def process_exception(self, request, exception):
        """Логирует исключения, связанные с blocking-логикой."""
        if 'provider' in str(exception).lower() or 'blocking' in str(exception).lower():
            logger.error("Blocking-related exception: %s", exception)
        return None


class BlockingLoggingMiddleware(MiddlewareMixin):
    """Логирует длительность и факты отказа по billing-блокировкам."""

    def process_request(self, request):
        request.blocking_start_time = timezone.now()
        return None

    def process_response(self, request, response):
        if hasattr(request, 'blocking_start_time'):
            processing_time = (timezone.now() - request.blocking_start_time).total_seconds()
            if processing_time > 1.0:
                logger.warning("Slow blocking check: %.2fs for %s", processing_time, request.path)

            if response.status_code in [403, 451]:
                logger.info(
                    "Blocked request: %s %s in %.2fs",
                    request.method,
                    request.path,
                    processing_time,
                )

        return response
