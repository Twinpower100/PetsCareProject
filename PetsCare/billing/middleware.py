"""Middleware для реакции API на уровни billing-блокировки провайдера."""

import json
import logging
import re

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import gettext as _

from providers.models import EmployeeProvider, Provider

from .models import BlockingSystemSettings
from .services import MultiLevelBlockingService

logger = logging.getLogger(__name__)
PROVIDER_PATH_RE = re.compile(r'^/api/v1/providers/(?P<provider_id>\d+)(?:/|$)')
BLOCKING_SKIP_PREFIXES = (
    '/api/v1/login',
    '/api/v1/token',
    '/admin/login',
)


class ProviderBlockingMiddleware(MiddlewareMixin):
    """
    Проверяет провайдера на текущую billing-блокировку и корректирует ответ.

    Продуктовая логика (уровни считаются в MultiLevelBlockingService):
    - Уровень 1: только предупреждение (суммы/просрочка в заголовках ответа), API не режем.
    - Уровень 2: кабинет провайдера (Petscare-web-admin) работает как на L1 — только предупреждение;
      скрытие из общего поиска и запрет онлайн-записи с витрины (Petscare-web) — отдельно:
      451 на поиск провайдеров, 403 на шаги онлайн-бронирования владельца (см. пути ниже).
      Полная «операционная» блокировка кабинета на этом уровне не применяется.
    - Уровень 3: жёсткая блокировка: 403 на почти все запросы, кроме узкого whitelist
      read-only self-service (профиль, список счетов, часть GET /providers/…), чтобы оплатить долг.
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
        if self._should_skip_blocking_check(request):
            return None

        provider = self._get_provider_from_request(request)
        if provider is None or provider.exclude_from_blocking_checks:
            return None

        request.provider_blocking_check_performed = True
        request.blocking_start_time = timezone.now()
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
            or self._extract_provider_id_from_path(request.path)
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

    def _extract_provider_id_from_path(self, path):
        """
        Извлекает provider_id из URL-пути до URL resolving, чтобы middleware
        работал и для JWT/API запросов в process_request.
        """
        match = PROVIDER_PATH_RE.match(path or '')
        if match is None:
            return None
        return match.group('provider_id')

    def _should_skip_blocking_check(self, request) -> bool:
        """
        Явно пропускает auth- и admin-login endpoints без provider context.
        """
        normalized_path = (request.path or '').rstrip('/')
        return any(normalized_path.startswith(prefix) for prefix in BLOCKING_SKIP_PREFIXES)

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
                'debt_info': result.get('debt_info'),
                'overdue_days': result.get('overdue_days'),
                'thresholds': result.get('thresholds'),
            }

        return {
            'is_blocked': False,
            'blocking_level': 0,
            'reasons': [],
            'active_blocking': result.get('active_blocking'),
            'debt_info': result.get('debt_info'),
            'overdue_days': result.get('overdue_days'),
            'thresholds': result.get('thresholds'),
        }

    def _handle_blocked_provider(self, request, provider, blocking_result):
        """
        Применяет HTTP-реакцию в зависимости от уровня блокировки.
        """
        blocking_level = blocking_result['blocking_level']

        # Ожидаемое поведение при долге — не засоряем WARNING в консоли (см. DEBUG).
        if self.settings and self.settings.log_all_checks:
            logger.debug(
                "Billing blocking rejected request for provider=%s level=%s path=%s",
                provider.id,
                blocking_level,
                request.path,
            )

        if blocking_level == 2:
            if self._is_search_request(request):
                return self._create_blocking_response(
                    request,
                    provider,
                    blocking_result,
                    status_code=451,
                    message=_("Provider is hidden from search due to billing debt"),
                )
            if self._is_public_marketplace_booking_path(request):
                return self._create_blocking_response(
                    request,
                    provider,
                    blocking_result,
                    status_code=403,
                    message=_("Online booking for this provider is disabled due to billing debt"),
                )
            # L2: кабинет провайдера и прочие API — только предупреждение (как L1).
            request.provider_blocking_warning = {
                'provider': provider,
                'level': blocking_level,
                'reasons': blocking_result['reasons'],
                'billing_detail': self._serialize_billing_detail(provider, blocking_result),
            }
            return None

        if blocking_level >= 3:
            if self._is_provider_self_service_read_request(request):
                request.provider_blocking_warning = {
                    'provider': provider,
                    'level': blocking_level,
                    'reasons': blocking_result['reasons'],
                    'billing_detail': self._serialize_billing_detail(provider, blocking_result),
                }
                return None
            return self._create_blocking_response(
                request,
                provider,
                blocking_result,
                status_code=403,
                message=_("Provider is blocked due to critical billing debt"),
            )

        # Уровень 1: только предупреждение, без 403.
        request.provider_blocking_warning = {
            'provider': provider,
            'level': blocking_level,
            'reasons': blocking_result['reasons'],
            'billing_detail': self._serialize_billing_detail(provider, blocking_result),
        }
        return None

    def _serialize_billing_detail(self, provider, blocking_result):
        """Сводка для UI: суммы, просрочка в днях, порог следующей ступени (для текстов «если достигнете…»)."""
        debt = blocking_result.get('debt_info') or provider.calculate_debt()
        currency = debt.get('currency')
        currency_code = getattr(currency, 'code', None) or 'EUR'
        overdue_days = blocking_result.get('overdue_days')
        if overdue_days is None:
            overdue_days = provider.get_max_overdue_days()
        th = blocking_result.get('thresholds') or provider.get_blocking_thresholds()
        bl = blocking_result.get('blocking_level')
        next_stage_overdue_days = None
        if bl == 1:
            next_stage_overdue_days = th.get('overdue_days_l2_from')
        elif bl == 2:
            next_stage_overdue_days = th.get('overdue_days_l3_from')

        return {
            'level': blocking_result.get('blocking_level'),
            'total_debt': str(debt['total_debt']),
            'overdue_amount': str(debt['overdue_debt']),
            'overdue_days': int(overdue_days),
            'currency_code': currency_code,
            'next_stage_overdue_days': next_stage_overdue_days,
        }

    def _is_provider_self_service_read_request(self, request) -> bool:
        """
        Разрешает bootstrap/read-only запросы provider admin, чтобы заблокированный
        провайдер мог войти в кабинет, увидеть статус блокировки и оплатить долг.
        """
        if request.method not in {'GET', 'HEAD'}:
            return False

        normalized_path = request.path.rstrip('/')
        if normalized_path in {'/api/v1/profile', '/api/v1/user-roles'}:
            return True
        if normalized_path == '/api/v1/providers' and request.GET.get('brief') == '1':
            return True
        if normalized_path.startswith('/api/v1/providers/'):
            if normalized_path in {'/api/v1/providers/search', '/api/v1/providers/search/map'}:
                return False
            return True
        if normalized_path == '/api/v1/provider-locations' or normalized_path.startswith('/api/v1/provider-locations/'):
            return True
        if normalized_path == '/api/v1/invoices' or normalized_path.startswith('/api/v1/invoices/'):
            return True
        if normalized_path.endswith('/my-permissions'):
            return True
        return False

    def _is_search_request(self, request) -> bool:
        """Определяет публичный поисковый запрос, где нужен 451."""
        return request.method == 'GET' and (
            '/search/' in request.path
            or request.path.endswith('/providers/search/')
            or request.path.endswith('/providers/search/map/')
        )

    def _is_public_marketplace_booking_path(self, request) -> bool:
        """
        Шаги онлайн-бронирования владельца питомца на витрине (Petscare-web), не кабинет провайдера.
        При L2 отключаем только эти цепочки; /api/v1/bookings/ (ViewSet кабинета) сюда не входит.
        """
        path = request.path
        if '/api/v1/booking/search' in path:
            return True
        if '/api/v1/booking/locations/' in path and '/slots/' in path:
            return True
        if '/api/v1/booking/appointments' in path:
            return True
        return False

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
            'billing_detail': self._serialize_billing_detail(provider, blocking_result),
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

        detail = warning.get('billing_detail') or self._serialize_billing_detail(
            warning['provider'],
            {
                'blocking_level': warning['level'],
                'debt_info': warning['provider'].calculate_debt(),
                'overdue_days': warning['provider'].get_max_overdue_days(),
                'thresholds': warning['provider'].get_blocking_thresholds(),
            },
        )
        detail['level'] = warning['level']
        response['X-Provider-Blocking-Detail'] = json.dumps(detail, ensure_ascii=False)

        if response.headers.get('content-type', '').startswith('application/json'):
            try:
                data = json.loads(response.content.decode('utf-8'))
            except (ValueError, UnicodeDecodeError, AttributeError):
                return response

            blocking_warning_body = {
                'level': warning['level'],
                'reasons': warning['reasons'],
                'provider_name': warning['provider'].name,
                'provider_id': warning['provider'].id,
                'billing_detail': detail,
            }
            if isinstance(data, dict):
                data['blocking_warning'] = blocking_warning_body
                response.content = json.dumps(data, ensure_ascii=False).encode('utf-8')
            # Корневой JSON-массив (например DRF list) не модифицируем — детали только в заголовке.

        return response

    def process_exception(self, request, exception):
        """Логирует исключения, связанные с blocking-логикой."""
        if 'provider' in str(exception).lower() or 'blocking' in str(exception).lower():
            logger.error("Blocking-related exception: %s", exception)
        return None


class BlockingLoggingMiddleware(MiddlewareMixin):
    """Логирует длительность и факты отказа по billing-блокировкам."""

    def process_request(self, request):
        return None

    def process_response(self, request, response):
        if hasattr(request, 'blocking_start_time'):
            processing_time = (timezone.now() - request.blocking_start_time).total_seconds()
            if processing_time > 1.0:
                logger.warning("Slow blocking check: %.2fs for %s", processing_time, request.path)

            if response.status_code in [403, 451]:
                logger.debug(
                    "Blocked request: %s %s in %.2fs",
                    request.method,
                    request.path,
                    processing_time,
                )

        return response
