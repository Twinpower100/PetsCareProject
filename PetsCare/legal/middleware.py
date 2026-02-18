"""
Middleware для логирования запросов к legal API.
Используется для отладки проблем с URL-роутингом.
"""
import logging

logger = logging.getLogger(__name__)


class LegalAPILoggingMiddleware:
    """
    Middleware для логирования всех запросов к legal API.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Логируем только запросы к legal API
        if '/api/v1/legal/documents/' in request.path:
            logger.info(f'Legal API request: {request.method} {request.get_full_path()}')
        
        response = self.get_response(request)
        
        if '/api/v1/legal/documents/' in request.path:
            logger.info(f'Legal API response: {response.status_code}')
        
        return response
