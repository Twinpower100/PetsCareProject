"""
Сервисы для работы с публичной офертой.

Этот модуль содержит сервисы для:
1. Проверки VAT номеров через VIES API
"""

import logging
from typing import Dict, Optional, Any
from django.utils import timezone
from django.utils.translation import gettext as _
import requests
# УДАЛЕНО: PublicOffer и RegionalAddendum - модели удалены
# Используйте LegalDocument из приложения legal
# from .models import PublicOffer, RegionalAddendum
from providers.models import Provider

logger = logging.getLogger(__name__)


class VATVerificationService:
    """
    Сервис для проверки VAT номеров через VIES API (Европейский Союз).
    
    VIES (VAT Information Exchange System) - официальный шлюз Еврокомиссии
    для проверки VAT-номеров компаний в ЕС.
    
    API Endpoint: https://ec.europa.eu/taxation_customs/vies/checkVatService.wsdl
    SOAP API (также доступен REST через сторонние обертки)
    
    Особенности:
    - Бесплатный API
    - Проверка только для стран ЕС
    - Возвращает валидность, название компании, адрес
    - Обработка ошибок API (недоступность, неверный формат и т.д.)
    """
    
    # VIES API endpoint (SOAP)
    VIES_SOAP_URL = 'https://ec.europa.eu/taxation_customs/vies/checkVatService.wsdl'
    
    # Альтернативный REST endpoint (через сторонний сервис)
    # Используем REST для простоты, так как SOAP требует дополнительных библиотек
    VIES_REST_URL = 'https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{country_code}/vat/{vat_number}'
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def verify_vat_number(self, country_code: str, vat_number: str) -> Dict[str, Any]:
        """
        Проверяет VAT номер через VIES API.
        
        Args:
            country_code: ISO 3166-1 alpha-2 код страны (например, 'DE', 'PL')
            vat_number: VAT номер без префикса страны (например, '12345678' для PL12345678)
            
        Returns:
            dict: Результат проверки с полями:
                - valid: bool - валиден ли VAT номер
                - name: str - название компании (если валидно)
                - address: str - адрес компании (если валидно)
                - request_date: str - дата запроса
                - error: str - текст ошибки (если есть)
        """
        if not country_code or not vat_number:
            return {
                'valid': False,
                'error': _('Country code and VAT number are required')
            }
        
        # Убираем префикс страны из VAT номера, если он есть
        vat_number = vat_number.upper().strip()
        if vat_number.startswith(country_code.upper()):
            vat_number = vat_number[len(country_code):]
        
        # Проверяем, что страна в ЕС
        from utils.countries import is_eu_country
        if not is_eu_country(country_code):
            return {
                'valid': False,
                'error': _('VAT verification is only available for EU countries')
            }
        
        try:
            # Используем REST API VIES (более простой, чем SOAP)
            url = self.VIES_REST_URL.format(
                country_code=country_code.upper(),
                vat_number=vat_number
            )
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # VIES API возвращает структуру:
            # {
            #   "valid": true/false,
            #   "name": "COMPANY NAME",
            #   "address": "ADDRESS",
            #   "requestDate": "2024-01-01",
            #   "requestIdentifier": "..."
            # }
            
            result = {
                'valid': data.get('valid', False),
                'name': data.get('name', ''),
                'address': data.get('address', ''),
                'request_date': data.get('requestDate', ''),
                'error': None
            }
            
            if not result['valid']:
                result['error'] = _('VAT number is not valid')
            
            self.logger.info(
                f'VAT verification for {country_code}{vat_number}: '
                f'valid={result["valid"]}, name={result["name"]}'
            )
            
            return result
            
        except requests.exceptions.Timeout:
            self.logger.error(f'VAT verification timeout for {country_code}{vat_number}')
            return {
                'valid': False,
                'error': _('VAT verification service is temporarily unavailable (timeout)')
            }
        except requests.exceptions.RequestException as e:
            self.logger.error(f'VAT verification error for {country_code}{vat_number}: {e}')
            return {
                'valid': False,
                'error': _('VAT verification service error: {error}').format(error=str(e))
            }
        except Exception as e:
            self.logger.error(f'Unexpected error during VAT verification: {e}')
            return {
                'valid': False,
                'error': _('Unexpected error during VAT verification')
            }
    
    def verify_and_save(self, provider: Provider) -> Dict[str, Any]:
        """
        Проверяет VAT номер провайдера и сохраняет результат в БД.
        
        Args:
            provider: Объект Provider с заполненными country и vat_number
            
        Returns:
            dict: Результат проверки (см. verify_vat_number)
        """
        if not provider.country or not provider.vat_number:
            return {
                'valid': False,
                'error': _('Provider country and VAT number are required')
            }
        
        # Проверяем через VIES
        result = self.verify_vat_number(
            country_code=provider.country.code,
            vat_number=provider.vat_number
        )
        
        # Сохраняем результат в БД
        provider.vat_verified = result['valid']
        if result['valid']:
            provider.vat_verification_date = timezone.now()
        else:
            provider.vat_verification_date = None
        
        provider.save(update_fields=['vat_verified', 'vat_verification_date'])
        
        return result

# УДАЛЕНО: OfferGeneratorService - используйте DocumentGeneratorService из приложения legal

