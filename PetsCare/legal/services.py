"""
Сервисы для работы с юридическими документами.

Этот модуль содержит сервисы для:
1. Генерации персонализированного текста документов для провайдеров
2. Подстановки переменных в документы
3. Получения документов для конкретной страны
"""

import logging
from typing import Dict, Optional, Any, List
from django.utils import timezone
from django.utils.translation import gettext as _
from decimal import Decimal

from .models import LegalDocument, DocumentTranslation, CountryLegalConfig, LegalDocumentType, DocumentAcceptance
from providers.models import Provider
from billing.models import BillingConfig
# УДАЛЕНО: ProviderSpecialTerms - используйте LegalDocument с типом side_letter

logger = logging.getLogger(__name__)


class DocumentGeneratorService:
    """
    Сервис для генерации персонализированного текста юридических документов.
    
    Особенности:
    - Подстановка переменных из BillingConfig или LegalDocument (side_letter)
    - Поддержка мультиязычности
    - Получение документов для конкретной страны
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def get_document_for_provider(
        self,
        provider: Provider,
        document_type_code: str,
        language: str = 'en'
    ) -> Dict[str, Any]:
        """
        Получает документ для провайдера с подстановкой переменных.
        
        Args:
            provider: Провайдер, для которого генерируется документ
            document_type_code: Код типа документа (например, 'global_offer')
            language: Язык документа (например, 'en', 'ru', 'de', 'sr')
            
        Returns:
            dict: Результат с полями:
                - success: bool
                - content: str - HTML контент с подставленными переменными
                - document: LegalDocument - объект документа
                - translation: DocumentTranslation - объект перевода
                - variables: dict - использованные переменные
                - error: str - текст ошибки (если есть)
        """
        try:
            # Получаем конфигурацию для страны провайдера
            country_config = self._get_country_config(provider)
            if not country_config:
                return {
                    'success': False,
                    'error': _('No legal configuration found for provider country')
                }
            
            # Получаем документ нужного типа
            document = self._get_document_by_type(country_config, document_type_code)
            if not document:
                return {
                    'success': False,
                    'error': _('Document of type {type} not found for provider country').format(
                        type=document_type_code
                    )
                }
            
            # Получаем перевод на нужный язык
            translation = document.translations.filter(language=language).first()
            if not translation:
                # Пробуем английский как fallback
                translation = document.translations.filter(language='en').first()
                if not translation:
                    return {
                        'success': False,
                        'error': _('Translation for language {lang} not found').format(lang=language)
                    }
            
            # Получаем переменные для подстановки
            variables = self._get_variables(provider, document)
            
            # Подставляем переменные в контент
            content = self._substitute_variables(translation.content, variables)
            
            return {
                'success': True,
                'content': content,
                'document': document,
                'translation': translation,
                'variables': variables
            }
            
        except Exception as e:
            self.logger.error(f'Error generating document for provider {provider.id}: {str(e)}', exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_global_offer_for_provider(
        self,
        provider: Provider,
        language: str = 'en'
    ) -> Dict[str, Any]:
        """
        Получает глобальную оферту для провайдера.
        
        Args:
            provider: Провайдер
            language: Язык оферты
            
        Returns:
            dict: Результат генерации оферты
        """
        return self.get_document_for_provider(provider, 'global_offer', language)
    
    def get_regional_addendums_for_provider(
        self,
        provider: Provider,
        language: str = 'en'
    ) -> List[Dict[str, Any]]:
        """
        Получает все региональные дополнения для провайдера.
        
        Args:
            provider: Провайдер
            language: Язык дополнений
            
        Returns:
            list: Список результатов генерации дополнений
        """
        try:
            country_config = self._get_country_config(provider)
            if not country_config:
                return []
            
            addendums = country_config.regional_addendums.filter(is_active=True)
            results = []
            
            for addendum in addendums:
                translation = addendum.translations.filter(language=language).first()
                if not translation:
                    translation = addendum.translations.filter(language='en').first()
                    if not translation:
                        continue
                
                variables = self._get_variables(provider, addendum)
                content = self._substitute_variables(translation.content, variables)
                
                results.append({
                    'success': True,
                    'content': content,
                    'document': addendum,
                    'translation': translation,
                    'variables': variables
                })
            
            return results
            
        except Exception as e:
            self.logger.error(f'Error getting regional addendums for provider {provider.id}: {str(e)}', exc_info=True)
            return []
    
    def _get_country_config(self, provider: Provider) -> Optional[CountryLegalConfig]:
        """Получает конфигурацию для страны провайдера"""
        if not provider.country:
            return None
        
        try:
            return CountryLegalConfig.objects.get(country=provider.country)
        except CountryLegalConfig.DoesNotExist:
            return None
    
    def _get_document_by_type(
        self,
        country_config: CountryLegalConfig,
        document_type_code: str
    ) -> Optional[LegalDocument]:
        """Получает документ нужного типа из конфигурации страны"""
        if document_type_code == 'global_offer':
            return country_config.global_offer
        elif document_type_code == 'privacy_policy':
            return country_config.privacy_policy
        elif document_type_code == 'terms_of_service':
            return country_config.terms_of_service
        elif document_type_code == 'cookie_policy':
            return country_config.cookie_policy
        elif document_type_code == 'regional_addendum':
            # Для региональных дополнений возвращаем первое (или None)
            # Используйте get_regional_addendums_for_provider для получения всех
            return country_config.regional_addendums.filter(is_active=True).first()
        
        return None
    
    def _get_variables(
        self,
        provider: Provider,
        document: LegalDocument
    ) -> Dict[str, str]:
        """
        Получает переменные для подстановки в документ.
        
        Приоритет:
        1. LegalDocument с типом side_letter (если есть у провайдера)
        2. BillingConfig из документа
        3. Значения по умолчанию
        """
        variables = {}
        
        # Базовые переменные из BillingConfig документа
        if document.billing_config:
            config = document.billing_config
            variables['commission_percent'] = str(config.commission_percent)
            variables['payment_deferral_days'] = str(config.payment_deferral_days)
            variables['invoice_period_days'] = str(config.invoice_period_days)
        
        # Переопределяем из LegalDocument (side_letter), если есть
        side_letter = provider.legal_documents.filter(
            document_type__code='side_letter',
            is_active=True
        ).first()
        if side_letter and side_letter.document_type.allows_financial_terms:
            if side_letter.commission_percent:
                variables['commission_percent'] = str(side_letter.commission_percent)
            if side_letter.payment_deferral_days:
                variables['payment_deferral_days'] = str(side_letter.payment_deferral_days)
        
        # Переменные из поля variables документа (для аддендумов)
        if document.variables:
            variables.update({k: str(v) for k, v in document.variables.items()})
        
        # Добавляем VAT ставку по стране провайдера, если доступно
        if provider and provider.country:
            try:
                from billing.models import VATRate
                vat_rate = VATRate.get_rate_for_country(provider.country.code)
                if vat_rate is not None:
                    variables['vat_rate'] = str(vat_rate)
            except Exception:
                # Не блокируем генерацию, если ставка не найдена или ошибка БД
                pass
        
        # Переменные из change_notification_days
        variables['change_notification_days'] = str(document.change_notification_days)
        
        return variables
    
    def _substitute_variables(self, text: str, variables: Dict[str, str]) -> str:
        """
        Подставляет переменные в текст.
        
        Args:
            text: Текст с переменными (например, "{{commission_percent}}" или "{{ commission_percent }}")
            variables: Словарь переменных для подстановки
            
        Returns:
            str: Текст с подставленными переменными
        """
        result = text
        for key, value in variables.items():
            # Поддерживаем оба формата: {{key}} и {{ key }} (с пробелами)
            result = result.replace(f'{{{{{key}}}}}', value)  # {{key}}
            result = result.replace(f'{{{{ {key} }}}}', value)  # {{ key }}
        return result
    
    def get_required_documents_for_country(
        self,
        country_code: str
    ) -> Dict[str, Any]:
        """
        Получает все обязательные документы для страны.
        
        Args:
            country_code: Код страны (ISO 3166-1 alpha-2)
            
        Returns:
            dict: Словарь с документами:
                - global_offer: LegalDocument
                - regional_addendums: QuerySet
                - privacy_policy: LegalDocument (опционально)
                - terms_of_service: LegalDocument (опционально)
                - cookie_policy: LegalDocument (опционально)
        """
        try:
            config = CountryLegalConfig.objects.get(country=country_code)
            return {
                'global_offer': config.global_offer,
                'regional_addendums': config.regional_addendums.filter(is_active=True),
                'privacy_policy': config.privacy_policy,
                'terms_of_service': config.terms_of_service,
                'cookie_policy': config.cookie_policy,
            }
        except CountryLegalConfig.DoesNotExist:
            return {
                'global_offer': None,
                'regional_addendums': [],
                'privacy_policy': None,
                'terms_of_service': None,
                'cookie_policy': None,
            }


class DocumentAcceptanceService:
    """
    Сервис для обработки принятия юридических документов.
    
    Особенности:
    - Активация провайдера при принятии оферты
    - Отправка уведомлений
    - Обработка бизнес-логики
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def handle_offer_acceptance(self, acceptance: DocumentAcceptance) -> Dict[str, Any]:
        """
        Обрабатывает принятие оферты провайдером.
        
        Флоу:
        1. Активирует провайдера (activation_status='active', is_active=True)
        2. Отправляет письмо Owner'у об успешной активации провайдера
        
        Args:
            acceptance: DocumentAcceptance - акцепт оферты
            
        Returns:
            dict: Результат обработки с полями:
                - success: bool
                - provider_activated: bool - был ли активирован провайдер
                - email_sent: bool - было ли отправлено письмо
                - error: str - текст ошибки (если есть)
        """
        try:
            # Проверяем, что это оферта провайдера
            if not acceptance.provider:
                return {
                    'success': False,
                    'error': _('Provider is required for offer acceptance')
                }
            
            if not acceptance.document or acceptance.document.document_type.code != 'global_offer':
                return {
                    'success': False,
                    'error': _('Only global offer acceptances are processed here')
                }
            
            provider = acceptance.provider
            provider_activated = False
            email_sent = False
            
            from django.utils import timezone
            from datetime import timedelta
            # Acceptance только что создан (из мастера регистрации) — не меняем статус провайдера и не шлём письмо.
            # Статус уже выставил мастер (active при valid VAT, activation_required при invalid); письмо шлёт _send_registration_emails.
            from_wizard = False
            if getattr(acceptance, 'accepted_at', None):
                age = (timezone.now() - acceptance.accepted_at).total_seconds()
                if age < 60:
                    from_wizard = True
                    self.logger.info(
                        "Skip activation and email for provider %s (acceptance from wizard)",
                        provider.id,
                    )
            
            if not from_wizard:
                # Активируем провайдера, если он еще не активирован (принятие оферты через API/фронт, не мастер)
                if provider.activation_status != 'active':
                    provider.activation_status = 'active'
                    provider.is_active = True
                    provider.save(update_fields=['activation_status', 'is_active'])
                    provider_activated = True
                    self.logger.info(
                        "Provider %s (%s) activated automatically after accepting offer %s",
                        provider.id, provider.name, acceptance.document.version,
                    )
            
            send_email = not from_wizard
            if send_email:
                try:
                    email_result = self._send_activation_email(provider, acceptance)
                    email_sent = email_result.get('success', False)
                except Exception as e:
                    self.logger.error(f"Error sending activation email: {e}", exc_info=True)
            
            return {
                'success': True,
                'provider_activated': provider_activated,
                'email_sent': email_sent
            }
            
        except Exception as e:
            self.logger.error(f'Error handling offer acceptance {acceptance.id}: {str(e)}', exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def _send_activation_email(self, provider: Provider, acceptance: DocumentAcceptance) -> Dict[str, Any]:
        """
        Отправляет письмо Owner'у об успешной активации провайдера.
        
        Args:
            provider: Provider - провайдер
            acceptance: DocumentAcceptance - акцепт оферты
            
        Returns:
            dict: Результат отправки письма
        """
        try:
            from users.models import ProviderAdmin
            from django.core.mail import send_mail
            from django.template.loader import render_to_string
            from django.conf import settings
            from billing.models import BillingManagerProvider
            
            # Получаем админа провайдера (Owner - создатель заявки)
            provider_admin_obj = ProviderAdmin.objects.filter(
                provider=provider,
                is_active=True
            ).select_related('user').first()
            
            if not provider_admin_obj:
                self.logger.warning(f"Provider {provider.id} activated but no active admin found")
                return {'success': False, 'error': 'No active admin found'}
            
            admin_user = provider_admin_obj.user
            
            # Получаем контакты биллинг-менеджера
            billing_manager_contacts = []
            try:
                active_managers = BillingManagerProvider.get_active_managers_for_provider(provider)
                for manager_provider in active_managers:
                    effective_manager = manager_provider.get_effective_manager()
                    if effective_manager and effective_manager.email:
                        billing_manager_contacts.append({
                            'name': effective_manager.get_full_name() or effective_manager.email,
                            'email': effective_manager.email,
                        })
            except Exception as e:
                self.logger.warning(f"Error getting billing manager contacts for provider {provider.id}: {e}")
            
            # Ссылка на приложение «Админка провайдеров»
            admin_login_url = getattr(settings, 'PROVIDER_ADMIN_URL', 'http://localhost:5173')
            
            # Получаем URL инструкции на фронте
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            setup_guide_url = f"{frontend_url}/provider-setup-guide"
            
            # Получаем комиссию из billing_config документа
            commission_percent = '5.00'
            if acceptance.document and acceptance.document.billing_config:
                commission_percent = str(acceptance.document.billing_config.commission_percent)
            
            # Заявка — для списка получателей и языка письма (язык того, кто регистрировал)
            from users.models import ProviderForm
            provider_form = ProviderForm.objects.filter(
                provider_email=provider.email
            ).order_by('-created_at').first()
            
            language = 'en'
            if provider_form:
                raw = (getattr(provider_form, 'language', None) or '').strip()
                if raw:
                    language = raw.split('-')[0].lower()
                if language not in ('en', 'ru', 'de', 'me'):
                    language = 'en'
            from django.utils import translation
            translation.activate(language)
            try:
                # Формируем контекст для шаблона письма (переводы — в активированном языке)
                context = {
                    'provider_name': provider.name,
                    'admin_email': admin_user.email,
                    'admin_first_name': admin_user.first_name or _('User'),
                    'has_password': admin_user.has_usable_password(),
                    'login_method': 'password' if admin_user.has_usable_password() else 'google',
                    'login_email': admin_user.email,
                    'admin_login_url': admin_login_url,
                    'setup_guide_url': setup_guide_url,
                    'billing_manager_contacts': billing_manager_contacts,
                    'offer_version': acceptance.document.version,
                    'commission_percent': commission_percent,
                }
                email_subject = _('Your provider account has been activated')
                email_body = render_to_string('email/provider_offer_accepted.html', context)
            finally:
                translation.deactivate()
            
            # Формируем список получателей:
            # 1. Владелец (created_by) - подавший заявку
            # 2. Админ провайдера (admin_email из ProviderForm) - если отличается
            # 3. Email провайдера (provider.email) - если отличается
            recipients = []
            
            # 1. Владелец (created_by) - подавший заявку
            
            if provider_form and provider_form.created_by and provider_form.created_by.email:
                owner_email = provider_form.created_by.email
                if owner_email.lower() not in [r.lower() for r in recipients]:
                    recipients.append(owner_email)
            
            # 2. Админ провайдера (admin_email из ProviderForm) - если отличается от владельца
            if provider_form and provider_form.admin_email:
                admin_email_lower = provider_form.admin_email.lower()
                if admin_email_lower not in [r.lower() for r in recipients]:
                    recipients.append(provider_form.admin_email)
            
            # 3. Email провайдера (provider.email) - если отличается от всех выше
            if provider.email:
                provider_email_lower = provider.email.lower()
                if provider_email_lower not in [r.lower() for r in recipients]:
                    recipients.append(provider.email)
            
            # Если список пуст (не должно быть, но на всякий случай), используем админа
            if not recipients:
                recipients = [admin_user.email]
            
            for recipient_email in recipients:
                send_mail(
                    subject=email_subject,
                    message='',  # Текстовая версия не нужна, используем HTML
                    html_message=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient_email],
                    fail_silently=False,
                )
                self.logger.info(f"Provider activation email sent to {recipient_email} for provider {provider.id} (after offer acceptance)")
            
            return {'success': True}
            
        except Exception as e:
            self.logger.error(f"Error sending provider activation email (after offer acceptance): {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
