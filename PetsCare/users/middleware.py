"""
Middleware для синхронизации выбранного языка пользователя.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

User = get_user_model()

SUPPORTED_LANGUAGE_CODES = {'en', 'ru', 'me', 'de'}


def normalize_language_code(raw_value: str | None) -> str | None:
    """
    Нормализует код языка до поддерживаемого короткого значения.
    """
    if not raw_value:
        return None

    normalized_value = raw_value.split('-')[0].strip().lower()
    if normalized_value not in SUPPORTED_LANGUAGE_CODES:
        return None
    return normalized_value


class PreferredLanguageMiddleware:
    """
    Сохраняет активный язык интерфейса для авторизованного пользователя.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        Сохраняет язык из текущего запроса до выполнения view.
        """
        user = getattr(request, 'user', None)
        language_code = normalize_language_code(getattr(request, 'LANGUAGE_CODE', None))

        if user and user.is_authenticated and language_code and user.preferred_language != language_code:
            User.objects.filter(pk=user.pk).update(preferred_language=language_code)
            user.preferred_language = language_code

        return self.get_response(request)
