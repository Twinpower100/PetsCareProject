"""
Конфигурация приложения billing.

Этот модуль содержит настройки приложения billing:
1. Автоматическое поле по умолчанию
2. Имя приложения
3. Отображаемое имя
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BillingConfig(AppConfig):
    """
    Конфигурация приложения billing.
    
    Особенности:
    - Управление платежами
    - История транзакций
    - Выставление счетов
    - Интеграция с платежными системами
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'billing'
    verbose_name = _('Billing')
    
    def ready(self):
        """Подключаем сигналы при инициализации приложения."""
        from . import signals  # noqa
        from . import translation  # noqa - загружаем настройки переводов для modeltranslation