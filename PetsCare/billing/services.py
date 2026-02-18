"""
Сервисы для работы с биллингом и блокировкой учреждений.

Этот модуль содержит сервисы для:
1. Многоуровневой блокировки учреждений по задолженности
2. Управления уведомлениями о блокировке
3. Интеграции с договорами и правилами блокировки
"""

import logging
from decimal import Decimal
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings
import requests
from typing import Dict, Optional, Any
from .models import (
    BlockingRule, ProviderBlocking, BlockingNotification,
    BillingManagerProvider, BlockingSystemSettings
)
from providers.models import Provider

logger = logging.getLogger(__name__)


class MultiLevelBlockingService:
    """
    Сервис для многоуровневой блокировки учреждений.
    
    Особенности:
    - Проверка задолженности по договорам
    - Применение различных уровней блокировки
    - Учет настроек системы блокировки
    - Поддержка исключений из автоматических проверок
    - Интеграция с уведомлениями
    """
    
    def __init__(self):
        self.settings = BlockingSystemSettings.get_settings()
    
    def check_provider_blocking(self, provider):
        """
        Проверяет необходимость блокировки учреждения.
        
        Args:
            provider: Объект Provider
            
        Returns:
            dict: Результат проверки
        """
        # Проверяем, исключено ли учреждение из автоматических проверок
        if provider.exclude_from_blocking_checks:
            return {
                'should_block': False,
                'reason': 'Provider excluded from automatic blocking checks',
                'exclusion_reason': provider.blocking_exclusion_reason
            }
        
        # Проверяем наличие активной оферты
        if not provider.has_active_offer_acceptance():
            return {
                'should_block': False,
                'reason': 'No active offer acceptance found'
            }
        
        # Проверяем провайдера на блокировку
        result = self._check_provider_offer_blocking(provider)
        
        return {
            'should_block': result['should_block'],
            'blocking_level': result['blocking_level'],
            'reasons': [result['reason']] if result['reason'] else [],
            'provider': provider
        }
    
    def _check_provider_offer_blocking(self, provider):
        """
        Проверяет необходимость блокировки провайдера на основе оферты и Invoice.
        
        Args:
            provider: Объект Provider
            
        Returns:
            dict: Результат проверки
        """
        # Рассчитываем задолженность через Invoice
        debt_info = provider.calculate_debt()
        total_debt = debt_info['total_debt']
        overdue_debt = debt_info['overdue_debt']
        
        # Получаем максимальное количество дней просрочки
        max_overdue_days = provider.get_max_overdue_days()
        
        # Получаем пороги блокировки
        thresholds = provider.get_blocking_thresholds()
        
        # Проверяем пороги блокировки
        blocking_level = 0
        reason = None
        
        # Проверка по сумме задолженности
        if thresholds['debt_threshold'] and total_debt > thresholds['debt_threshold']:
            blocking_level = max(blocking_level, 3)
            reason = _("Debt threshold exceeded: %(debt)s > %(threshold)s") % {
                'debt': total_debt,
                'threshold': thresholds['debt_threshold']
            }
        
        # Проверка по дням просрочки
        if thresholds['overdue_threshold_3'] and max_overdue_days >= thresholds['overdue_threshold_3']:
            blocking_level = max(blocking_level, 3)
            reason = _("Critical overdue: %(days)s days >= %(threshold)s") % {
                'days': max_overdue_days,
                'threshold': thresholds['overdue_threshold_3']
            }
        elif thresholds['overdue_threshold_2'] and max_overdue_days >= thresholds['overdue_threshold_2']:
            blocking_level = max(blocking_level, 2)
            reason = _("High overdue: %(days)s days >= %(threshold)s") % {
                'days': max_overdue_days,
                'threshold': thresholds['overdue_threshold_2']
            }
        elif thresholds['overdue_threshold_1'] and max_overdue_days >= thresholds['overdue_threshold_1']:
            blocking_level = max(blocking_level, 1)
            reason = _("Information overdue: %(days)s days >= %(threshold)s") % {
                'days': max_overdue_days,
                'threshold': thresholds['overdue_threshold_1']
            }
        
        return {
            'should_block': blocking_level > 0,
            'blocking_level': blocking_level,
            'reason': reason,
            'total_debt': total_debt,
            'overdue_days': max_overdue_days,
            'provider': provider
        }
    
    def apply_blocking(self, provider, blocking_level, reasons):
        """
        Применяет блокировку к учреждению.
        
        Args:
            provider: Объект Provider
            blocking_level: Уровень блокировки (1-3)
            reasons: Список причин блокировки
            
        Returns:
            ProviderBlocking: Созданная запись блокировки
        """
        # Рассчитываем задолженность для блокировки
        debt_info = provider.calculate_debt()
        
        # Создаем запись блокировки
        blocking = ProviderBlocking.objects.create(
            provider=provider,
            blocking_rule=None,  # Будет создано автоматически
            status='active',
            debt_amount=debt_info['total_debt'],
            overdue_days=provider.get_max_overdue_days(),
            currency=debt_info['currency'],
            notes=_("Automatic blocking level %(level)s: %(reasons)s") % {
                'level': blocking_level,
                'reasons': '; '.join(reasons)
            }
        )
        
        # Создаем уведомления
        self._create_notifications(blocking, blocking_level)
        
        # Логируем действие
        if self.settings.log_all_checks:
            self._log_blocking_action(blocking, blocking_level, reasons)
        
        return blocking
    
    def _create_notifications(self, blocking, blocking_level):
        """
        Создает уведомления о блокировке.
        
        Args:
            blocking: Объект ProviderBlocking
            blocking_level: Уровень блокировки
        """
        # Получаем получателей уведомлений
        recipients = blocking.provider.get_notification_recipients()
        
        # Создаем уведомления с задержкой
        for recipient in recipients:
            notification = BlockingNotification.objects.create(
                provider_blocking=blocking,
                notification_type='blocking_activated',
                status='pending',
                recipient_email=recipient.get('email'),
                recipient_phone=recipient.get('phone'),
                subject=_("Provider Blocking — Level %(level)s") % {'level': blocking_level},
                message=self._generate_notification_message(blocking, blocking_level)
            )
    
    def _generate_notification_message(self, blocking, blocking_level):
        """
        Генерирует текст уведомления о блокировке.
        
        Args:
            blocking: Объект ProviderBlocking
            blocking_level: Уровень блокировки
            
        Returns:
            str: Текст уведомления
        """
        level_descriptions = {
            1: "Information notification",
            2: "Exclusion from search",
            3: "Full blocking"
        }
        
        return f"""
Provider: {blocking.provider.name}
Blocking Level: {blocking_level} ({level_descriptions.get(blocking_level, 'Unknown')})
Debt Amount: {blocking.debt_amount} {blocking.currency.code}
Overdue Days: {blocking.overdue_days}
Blocked At: {blocking.blocked_at}
Notes: {blocking.notes}
        """.strip()
    
    def _log_blocking_action(self, blocking, blocking_level, reasons):
        """
        Логирует действие блокировки.
        
        Args:
            blocking: Объект ProviderBlocking
            blocking_level: Уровень блокировки
            reasons: Список причин
        """
        import logging
        logger = logging.getLogger('blocking')
        
        logger.info(
            f"Provider {blocking.provider.name} blocked at level {blocking_level}. "
            f"Reasons: {'; '.join(reasons)}. "
            f"Debt: {blocking.debt_amount} {blocking.currency.code}, "
            f"Overdue: {blocking.overdue_days} days"
        )
    
    def resolve_blocking(self, blocking, resolved_by=None, notes=''):
        """
        Снимает блокировку с учреждения.
        
        Args:
            blocking: Объект ProviderBlocking
            resolved_by: Пользователь, снявший блокировку
            notes: Примечания
            
        Returns:
            ProviderBlocking: Обновленная запись блокировки
        """
        blocking.resolve(resolved_by, notes)
        
        # Создаем уведомление о снятии блокировки
        self._create_resolution_notification(blocking)
        
        # Логируем действие
        if self.settings.log_resolutions:
            self._log_resolution_action(blocking, resolved_by)
        
        return blocking
    
    def _create_resolution_notification(self, blocking):
        """
        Создает уведомление о снятии блокировки.
        
        Args:
            blocking: Объект ProviderBlocking
        """
        recipients = blocking.provider.get_notification_recipients()
        
        for recipient in recipients:
            notification = BlockingNotification.objects.create(
                provider_blocking=blocking,
                notification_type='blocking_resolved',
                status='pending',
                recipient_email=recipient.get('email'),
                recipient_phone=recipient.get('phone'),
                subject=_("Provider Blocking Resolved"),
                message=_("Blocking for provider %(provider)s has been resolved.") % {
                    'provider': blocking.provider.name
                }
            )
    
    def _log_resolution_action(self, blocking, resolved_by):
        """
        Логирует снятие блокировки.
        
        Args:
            blocking: Объект ProviderBlocking
            resolved_by: Пользователь, снявший блокировку
        """
        import logging
        logger = logging.getLogger('blocking')
        
        resolved_by_name = resolved_by.get_full_name() if resolved_by else 'System'
        
        logger.info(
            f"Provider {blocking.provider.name} blocking resolved by {resolved_by_name}. "
            f"Resolution date: {blocking.resolved_at}"
        )
    
    def check_all_providers(self):
        """
        Проверяет все учреждения на необходимость блокировки.
        
        Returns:
            dict: Статистика проверки
        """
        from providers.models import Provider
        
        # Получаем все активные учреждения
        providers = Provider.objects.filter(
            is_active=True,
            exclude_from_blocking_checks=False
        )
        
        stats = {
            'total_providers': providers.count(),
            'checked_providers': 0,
            'blocked_providers': 0,
            'warnings': 0,
            'errors': []
        }
        
        for provider in providers:
            try:
                result = self.check_provider_blocking(provider)
                stats['checked_providers'] += 1
                
                if result['should_block']:
                    # Применяем блокировку
                    blocking = self.apply_blocking(
                        provider,
                        result['blocking_level'],
                        result['reasons']
                    )
                    stats['blocked_providers'] += 1
                    
                    # Если уровень блокировки 1, считаем как предупреждение
                    if result['blocking_level'] == 1:
                        stats['warnings'] += 1
                        
            except Exception as e:
                stats['errors'].append(f"Error checking provider {provider.name}: {str(e)}")
        
        return stats 


# Функции уведомлений для workflow согласования контрактов удалены - используется LegalDocument и DocumentAcceptance 