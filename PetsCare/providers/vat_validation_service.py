"""
Сервис для валидации VAT ID через VIES API.

Этот модуль содержит функции для проверки валидности VAT ID
для стран ЕС через официальный VIES API Еврокомиссии.
"""

import logging
import requests
from typing import Dict, Optional, Tuple
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

# URL VIES API
VIES_API_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{country_code}/vat/{vat_number}"

# Время кэширования результатов (в секундах)
CACHE_VALID_DURATION = 86400  # 24 часа для валидных VAT ID
CACHE_INVALID_DURATION = 3600  # 1 час для невалидных VAT ID


def validate_vat_id_vies(country_code: str, vat_id: str) -> Dict[str, any]:
    """
    Проверяет валидность VAT ID через VIES API.
    
    Args:
        country_code: Код страны (ISO 3166-1 alpha-2, например 'DE')
        vat_id: VAT ID без префикса страны (например, '123456789')
        
    Returns:
        dict: Результат проверки:
            {
                'is_valid': bool,
                'company_name': str | None,
                'address': str | None,
                'error': str | None,
                'cached': bool
            }
    """
    # Нормализация VAT ID (удаление префикса страны, если есть)
    vat_clean = vat_id.upper().strip()
    if vat_clean.startswith(country_code.upper()):
        vat_clean = vat_clean[len(country_code.upper()):]
    
    # Проверка кэша
    cache_key = f'vat_validation_{country_code}_{vat_clean}'
    cached_result = cache.get(cache_key)
    if cached_result:
        logger.info(f"VAT ID {country_code}{vat_clean} found in cache")
        cached_result['cached'] = True
        return cached_result
    
    # Формируем URL для запроса
    url = VIES_API_URL.format(country_code=country_code, vat_number=vat_clean)
    
    try:
        # Отправляем запрос к VIES API
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('isValid', False):
                # VAT ID валидный
                result = {
                    'is_valid': True,
                    'company_name': data.get('name', ''),
                    'address': data.get('address', ''),
                    'error': None,
                    'cached': False,
                    'request_date': data.get('requestDate', ''),
                }
                
                # Кэшируем валидный результат на 24 часа
                cache.set(cache_key, result, CACHE_VALID_DURATION)
                logger.info(f"VAT ID {country_code}{vat_clean} is valid: {result.get('company_name')}")
                return result
            else:
                # VAT ID невалидный
                error_message = data.get('userError', 'INVALID_INPUT')
                result = {
                    'is_valid': False,
                    'company_name': None,
                    'address': None,
                    'error': error_message,
                    'cached': False,
                    'request_date': data.get('requestDate', ''),
                }
                
                # Кэшируем невалидный результат на 1 час
                cache.set(cache_key, result, CACHE_INVALID_DURATION)
                logger.warning(f"VAT ID {country_code}{vat_clean} is invalid: {error_message}")
                return result
        else:
            # Ошибка API
            error_message = f"VIES API returned status {response.status_code}"
            result = {
                'is_valid': False,
                'company_name': None,
                'address': None,
                'error': error_message,
                'cached': False,
                'request_date': None,
            }
            logger.error(f"VIES API error for {country_code}{vat_clean}: {error_message}")
            return result
            
    except requests.Timeout:
        error_message = "VIES API timeout"
        result = {
            'is_valid': False,
            'company_name': None,
            'address': None,
            'error': error_message,
            'cached': False,
            'request_date': None,
        }
        logger.error(f"VIES API timeout for {country_code}{vat_clean}")
        return result
        
    except requests.RequestException as e:
        error_message = f"VIES API request failed: {str(e)}"
        result = {
            'is_valid': False,
            'company_name': None,
            'address': None,
            'error': error_message,
            'cached': False,
            'request_date': None,
        }
        logger.error(f"VIES API request failed for {country_code}{vat_clean}: {error_message}")
        return result
        
    except Exception as e:
        error_message = f"Unexpected error: {str(e)}"
        result = {
            'is_valid': False,
            'company_name': None,
            'address': None,
            'error': error_message,
            'cached': False,
            'request_date': None,
        }
        logger.exception(f"Unexpected error validating VAT ID {country_code}{vat_clean}")
        return result


def check_vat_id_format(country_code: str, vat_id: str) -> Tuple[bool, Optional[str]]:
    """
    Проверяет формат VAT ID для страны ЕС.
    
    Args:
        country_code: Код страны
        vat_id: VAT ID для проверки
        
    Returns:
        tuple: (валидный, сообщение об ошибке)
    """
    from .validation_rules import validate_vat_id_eu
    return validate_vat_id_eu(vat_id, country_code)
