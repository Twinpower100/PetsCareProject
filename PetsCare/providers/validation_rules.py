"""
Правила валидации реквизитов провайдера по странам.

Используется библиотека python-stdnum для форматов, где она доступна.
Рынок: РФ (RU), Германия (DE), Украина (UA), Черногория (ME).

Таблица: реквизиты, валидируемые через stdnum по странам
----------------------------------------------------------------------
Страна | Поле           | stdnum модуль           | Длина/формат
----------------------------------------------------------------------
RU     | tax_id (ИНН)   | stdnum.ru.inn           | 10 цифр (юрл.) / 12 (ИП)
RU     | vat_number     | —                       | в РФ не EU VAT
RU     | iban           | stdnum.iban             | при указании
----------------------------------------------------------------------
DE     | tax_id         | stdnum.de.stnr          | Steuernummer 10–11 цифр
DE     | vat_number     | stdnum.eu.vat           | DE + 9 цифр (11 с кодом)
DE     | iban           | stdnum.iban             | DE + 22 символа
----------------------------------------------------------------------
UA     | tax_id         | stdnum.ua.edrpou       | 8 цифр (ЄДРПОУ)
UA     | tax_id         | stdnum.ua.rntrc        | 10 цифр (РНОКПП)
UA     | vat_number     | —                       | не EU VAT
UA     | iban           | stdnum.iban             | UA + до 29 символов
----------------------------------------------------------------------
ME     | tax_id (PIB)   | stdnum.me.pib          | 8 цифр
ME     | vat_number     | —                       | не EU VAT
ME     | iban           | stdnum.iban             | ME + до 29 символов
----------------------------------------------------------------------
"""

import re
from typing import Dict, Optional, Callable, Any

try:
    from stdnum.eu import vat as eu_vat  # EU VAT ID (DE и др. страны ЕС)
    from stdnum import iban as stdnum_iban
    STDNUM_AVAILABLE = True
except ImportError:
    STDNUM_AVAILABLE = False
    eu_vat = None
    stdnum_iban = None

try:
    from stdnum.ru import inn as stdnum_ru_inn
except ImportError:
    stdnum_ru_inn = None

try:
    from stdnum.de import stnr as stdnum_de_stnr
except ImportError:
    stdnum_de_stnr = None

try:
    from stdnum.ua import edrpou as stdnum_ua_edrpou
    from stdnum.ua import rntrc as stdnum_ua_rntrc
except ImportError:
    stdnum_ua_edrpou = None
    stdnum_ua_rntrc = None

try:
    from stdnum.me import pib as stdnum_me_pib
except ImportError:
    stdnum_me_pib = None

try:
    from stdnum import bic as stdnum_bic  # SWIFT/BIC
except ImportError:
    stdnum_bic = None

try:
    from stdnum.de import handelsregisternummer as stdnum_de_hr
except ImportError:
    stdnum_de_hr = None

try:
    from stdnum.ru import ogrn as stdnum_ru_ogrn
except ImportError:
    stdnum_ru_ogrn = None


def _validate_inn_ru_manual(inn: str) -> tuple[bool, Optional[str]]:
    """
    Валидация ИНН для России.
    
    Args:
        inn: ИНН для проверки
        
    Returns:
        tuple: (валидный, сообщение об ошибке)
    """
    # Удаляем пробелы и дефисы
    inn_clean = re.sub(r'[\s-]', '', inn)
    
    # Проверка длины
    if len(inn_clean) == 10:
        # ИНН для юрлиц (10 цифр)
        if not inn_clean.isdigit():
            return False, "ИНН должен содержать только цифры"
        # Проверка контрольной суммы для 10-значного ИНН
        # Алгоритм проверки контрольной суммы ИНН
        coefficients_10 = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum = sum(int(inn_clean[i]) * coefficients_10[i] for i in range(9)) % 11
        if checksum == 10:
            checksum = 0
        if checksum != int(inn_clean[9]):
            return False, "Неверная контрольная сумма ИНН"
        return True, None
    elif len(inn_clean) == 12:
        # ИНН для ИП (12 цифр)
        if not inn_clean.isdigit():
            return False, "ИНН должен содержать только цифры"
        # Проверка контрольных сумм для 12-значного ИНН
        coefficients_12_1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        coefficients_12_2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        
        checksum_1 = sum(int(inn_clean[i]) * coefficients_12_1[i] for i in range(10)) % 11
        if checksum_1 == 10:
            checksum_1 = 0
        if checksum_1 != int(inn_clean[10]):
            return False, "Неверная контрольная сумма ИНН (первая)"
        
        checksum_2 = sum(int(inn_clean[i]) * coefficients_12_2[i] for i in range(11)) % 11
        if checksum_2 == 10:
            checksum_2 = 0
        if checksum_2 != int(inn_clean[11]):
            return False, "Неверная контрольная сумма ИНН (вторая)"
        
        return True, None
    else:
        return False, "ИНН должен содержать 10 цифр (для юрлиц) или 12 цифр (для ИП)"


def validate_inn_ru(inn: str) -> tuple[bool, Optional[str]]:
    """ИНН РФ: stdnum.ru.inn при наличии, иначе ручная проверка."""
    if stdnum_ru_inn:
        try:
            stdnum_ru_inn.validate(inn)
            return True, None
        except Exception as e:
            return False, str(e) if str(e) else "Неверный ИНН"
    return _validate_inn_ru_manual(inn)


def validate_kpp_ru(kpp: str) -> tuple[bool, Optional[str]]:
    """
    Валидация КПП для России.
    
    Args:
        kpp: КПП для проверки
        
    Returns:
        tuple: (валидный, сообщение об ошибке)
    """
    kpp_clean = re.sub(r'[\s-]', '', kpp)
    
    if len(kpp_clean) != 9:
        return False, "КПП должен содержать 9 цифр"
    
    if not kpp_clean.isdigit():
        return False, "КПП должен содержать только цифры"
    
    return True, None


def validate_vat_id_eu(vat_id: str, country_code: str) -> tuple[bool, Optional[str]]:
    """
    Валидация формата VAT ID для стран ЕС (в т.ч. DE: 11 символов = DE + 9 цифр).
    
    Использует stdnum.eu.vat для всех стран ЕС (DE, AT, FR, PL и т.д.).
    Если библиотека недоступна — fallback на ручную валидацию.
    """
    if STDNUM_AVAILABLE and eu_vat:
        try:
            # stdnum.eu.vat.validate() проверяет формат EU VAT ID
            # Формат: страна + номер (например, DE123456789)
            # Если номер без префикса страны, добавляем его
            vat_clean = re.sub(r'[\s-]', '', vat_id).upper()
            if not vat_clean.startswith(country_code.upper()):
                vat_clean = f"{country_code.upper()}{vat_clean}"
            
            # validate() возвращает нормализованный VAT ID или выбрасывает исключение
            eu_vat.validate(vat_clean)
            return True, None
        except Exception as e:
            # stdnum может выбросить различные исключения при невалидном формате
            error_msg = str(e) if str(e) else f"Неверный формат VAT ID для страны {country_code}"
            return False, error_msg
    
    # Fallback на ручную валидацию, если библиотека не установлена
    vat_clean = re.sub(r'[\s-]', '', vat_id).upper()
    
    # Проверка формата по странам ЕС
    country_formats = {
        'DE': (9, r'^DE\d{9}$'),  # Германия: DE + 9 цифр
        'FR': (11, r'^FR\d{11}$'),  # Франция: FR + 11 цифр
        'IT': (11, r'^IT\d{11}$'),  # Италия: IT + 11 цифр
        'ES': (11, r'^ES\d{11}$'),  # Испания: ES + 11 цифр
        'NL': (12, r'^NL\d{9}[A-Z0-9]{2}B\d{2}$'),  # Нидерланды: NL + 9 цифр + 2 символа + B + 2 цифры
        'PL': (10, r'^PL\d{10}$'),  # Польша: PL + 10 цифр
        'BE': (10, r'^BE\d{10}$'),  # Бельгия: BE + 10 цифр
        'AT': (9, r'^ATU\d{8}$'),  # Австрия: ATU + 8 цифр
        'DK': (8, r'^DK\d{8}$'),  # Дания: DK + 8 цифр
        'SE': (12, r'^SE\d{12}$'),  # Швеция: SE + 12 цифр
    }
    
    if country_code not in country_formats:
        # Общий формат для других стран ЕС: код страны (2 буквы) + 9 цифр
        pattern = rf'^{country_code}\d{{9}}$'
        if not re.match(pattern, vat_clean):
            return False, f"VAT ID должен иметь формат: {country_code} + 9 цифр"
        return True, None
    
    length, pattern = country_formats[country_code]
    
    if not re.match(pattern, vat_clean):
        return False, f"Неверный формат VAT ID для страны {country_code}"
    
    return True, None


def validate_iban(iban: str, country_code: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """
    Валидация формата IBAN.
    
    Использует библиотеку python-stdnum согласно плану (FunctionalDesign.md).
    Если библиотека недоступна, используется fallback на ручную валидацию.
    
    Args:
        iban: IBAN для проверки
        country_code: Код страны (опционально, для проверки префикса)
        
    Returns:
        tuple: (валидный, сообщение об ошибке)
    """
    # Используем python-stdnum, если доступна
    if STDNUM_AVAILABLE and stdnum_iban:
        try:
            # stdnum.iban.validate() проверяет формат и контрольную сумму IBAN
            # Возвращает нормализованный IBAN или выбрасывает исключение
            validated_iban = stdnum_iban.validate(iban)
            
            # Проверка префикса страны, если указан
            if country_code:
                iban_clean = validated_iban.upper()
                if not iban_clean.startswith(country_code.upper()):
                    return False, f"IBAN должен начинаться с кода страны {country_code.upper()}"
            
            return True, None
        except Exception as e:
            # stdnum может выбросить различные исключения при невалидном формате
            error_msg = str(e) if str(e) else "Неверный формат IBAN"
            return False, error_msg
    
    # Fallback на ручную валидацию, если библиотека не установлена
    iban_clean = re.sub(r'[\s-]', '', iban).upper()
    
    # Общий формат IBAN: 2 буквы (код страны) + 2 цифры (контрольная сумма) + до 30 символов
    if len(iban_clean) < 15 or len(iban_clean) > 34:
        return False, "IBAN должен содержать от 15 до 34 символов"
    
    if not re.match(r'^[A-Z]{2}\d{2}[A-Z0-9]+$', iban_clean):
        return False, "IBAN должен начинаться с 2 букв (код страны), затем 2 цифры, затем буквы и цифры"
    
    # Проверка префикса страны, если указан
    if country_code and not iban_clean.startswith(country_code.upper()):
        return False, f"IBAN должен начинаться с кода страны {country_code.upper()}"
    
    # Проверка контрольной суммы IBAN (MOD-97-10)
    # Перемещаем первые 4 символа в конец
    iban_rearranged = iban_clean[4:] + iban_clean[:4]
    
    # Заменяем буквы на числа (A=10, B=11, ..., Z=35)
    iban_numeric = ''
    for char in iban_rearranged:
        if char.isdigit():
            iban_numeric += char
        else:
            iban_numeric += str(ord(char) - ord('A') + 10)
    
    # Вычисляем остаток от деления на 97
    remainder = int(iban_numeric) % 97
    
    if remainder != 1:
        return False, "Неверная контрольная сумма IBAN"
    
    return True, None


def validate_swift_bic(swift: str) -> tuple[bool, Optional[str]]:
    """
    Валидация формата SWIFT/BIC. stdnum.bic при наличии, иначе ручная проверка.
    """
    if stdnum_bic:
        try:
            stdnum_bic.validate(swift)
            return True, None
        except Exception as e:
            return False, str(e) if str(e) else "Неверный формат SWIFT/BIC"
    swift_clean = re.sub(r'[\s-]', '', swift).upper()
    if len(swift_clean) not in [8, 11]:
        return False, "SWIFT/BIC должен содержать 8 или 11 символов"
    if not re.match(r'^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$', swift_clean):
        return False, "Неверный формат SWIFT/BIC"
    return True, None


def validate_edrpou_ua(edrpou: str) -> tuple[bool, Optional[str]]:
    """
    Валидация ЄДРПОУ для Украины.
    
    Args:
        edrpou: ЄДРПОУ для проверки
        
    Returns:
        tuple: (валидный, сообщение об ошибке)
    """
    edrpou_clean = re.sub(r'[\s-]', '', edrpou)
    
    if len(edrpou_clean) != 8:
        return False, "ЄДРПОУ должен содержать 8 цифр"
    
    if not edrpou_clean.isdigit():
        return False, "ЄДРПОУ должен содержать только цифры"
    
    return True, None


def validate_inn_ua(inn: str) -> tuple[bool, Optional[str]]:
    """
    Валидация ИНН для ФОП в Украине (10 цифр, РНОКПП).
    """
    inn_clean = re.sub(r'[\s-]', '', inn)
    if len(inn_clean) != 10:
        return False, "ИНН ФОП должен содержать 10 цифр"
    if not inn_clean.isdigit():
        return False, "ИНН ФОП должен содержать только цифры"
    return True, None


def validate_tax_id_ua(value: str) -> tuple[bool, Optional[str]]:
    """
    Tax ID Украина: 8 цифр — ЄДРПОУ (stdnum.ua.edrpou), 10 цифр — РНОКПП (stdnum.ua.rntrc).
    """
    clean = re.sub(r'[\s-]', '', value)
    if len(clean) == 8:
        if stdnum_ua_edrpou:
            try:
                stdnum_ua_edrpou.validate(value)
                return True, None
            except Exception as e:
                return False, str(e) if str(e) else "Неверный ЄДРПОУ"
        return validate_edrpou_ua(value)
    if len(clean) == 10:
        if stdnum_ua_rntrc:
            try:
                stdnum_ua_rntrc.validate(value)
                return True, None
            except Exception as e:
                return False, str(e) if str(e) else "Неверный ИНН ФОП"
        return validate_inn_ua(value)
    return False, "8 цифр (ЄДРПОУ) или 10 цифр (ИНН ФОП)"


def _validate_pib_me_manual(pib: str) -> tuple[bool, Optional[str]]:
    """Ручная проверка PIB (8 цифр)."""
    pib_clean = re.sub(r'[\s-]', '', pib)
    if len(pib_clean) != 8:
        return False, "PIB должен содержать 8 цифр"
    if not pib_clean.isdigit():
        return False, "PIB должен содержать только цифры"
    return True, None


def validate_pib_me(pib: str) -> tuple[bool, Optional[str]]:
    """PIB Черногории: stdnum.me.pib при наличии, иначе ручная проверка."""
    if stdnum_me_pib:
        try:
            stdnum_me_pib.validate(pib)
            return True, None
        except Exception as e:
            return False, str(e) if str(e) else "Неверный PIB"
    return _validate_pib_me_manual(pib)


def _validate_steuernummer_de_manual(steuer_id: str) -> tuple[bool, Optional[str]]:
    """Ручная проверка Steuernummer (10–11 цифр)."""
    clean = re.sub(r'[\s-]', '', steuer_id)
    if not clean.isdigit():
        return False, "Steuernummer: только цифры (пробелы и дефисы допускаются)"
    if len(clean) not in (10, 11):
        return False, "Steuernummer: 10 или 11 цифр"
    return True, None


def validate_steuernummer_de(steuer_id: str) -> tuple[bool, Optional[str]]:
    """
    Валидация Steuernummer (налоговый номер) для Германии.
    stdnum.de.stnr при наличии, иначе ручная проверка.
    """
    if stdnum_de_stnr:
        try:
            stdnum_de_stnr.validate(steuer_id)
            return True, None
        except Exception as e:
            return False, str(e) if str(e) else "Неверный Steuernummer"
    return _validate_steuernummer_de_manual(steuer_id)


def validate_tax_id_at(tax_id: str) -> tuple[bool, Optional[str]]:
    """
    Валидация Steuernummer / UID (без префикса ATU) для Австрии.
    Отдельно от USt-IdNr. (VAT): ATU + 8 цифр валидируется в validate_vat_id_eu.
    
    Args:
        tax_id: налоговый идентификатор для проверки
        
    Returns:
        tuple: (валидный, сообщение об ошибке)
    """
    clean = re.sub(r'[\s-]', '', tax_id)
    if not clean.isdigit():
        return False, "Steuernummer/UID: только цифры"
    if len(clean) < 8 or len(clean) > 10:
        return False, "Steuernummer/UID: 8–10 цифр"
    return True, None


def validate_siren_siret_fr(tax_id: str) -> tuple[bool, Optional[str]]:
    """
    Валидация SIREN (9 цифр) или SIRET (14 цифр) для Франции.
    Отдельно от TVA intracommunautaire (VAT): FR + 11 цифр.
    Допустимы цифры и пробелы (модель не допускает точку).
    
    Args:
        tax_id: SIREN или SIRET для проверки
        
    Returns:
        tuple: (валидный, сообщение об ошибке)
    """
    clean = re.sub(r'[\s-]', '', tax_id)
    if not clean.isdigit():
        return False, "SIREN/SIRET: только цифры"
    if len(clean) == 9:
        return True, None  # SIREN
    if len(clean) == 14:
        return True, None  # SIRET
    return False, "SIREN (9 chiffres) ou SIRET (14 chiffres)"


def validate_nip_pl(tax_id: str) -> tuple[bool, Optional[str]]:
    """
    Валидация NIP (налоговый идентификатор) для Польши.
    Отдельно от VAT (USt-IdNr.): VAT = PL + 10 цифр (PL + NIP).
    
    Args:
        tax_id: NIP для проверки
        
    Returns:
        tuple: (валидный, сообщение об ошибке)
    """
    clean = re.sub(r'[\s\-]', '', tax_id)
    if not clean.isdigit():
        return False, "NIP: только 10 цифр"
    if len(clean) != 10:
        return False, "NIP: 10 цифр (например, 1234567890 или 123-456-78-90)"
    return True, None


# Регистрационный номер: DE (Handelsregisternummer), RU (OGRN). Для UA, ME — только обязательность и max_length.
OUR_COUNTRIES = ('DE', 'RU', 'UA', 'ME')
REGISTRATION_NUMBER_MAX_LENGTH = 100  # как в модели Provider


def validate_registration_number_de(value: str) -> tuple[bool, Optional[str]]:
    """Регистрационный номер Германии: Handelsregisternummer (HRA/HRB + номер)."""
    if stdnum_de_hr:
        try:
            stdnum_de_hr.validate(value)
            return True, None
        except Exception as e:
            return False, str(e) if str(e) else "Неверный формат регистрационного номера (Handelsregisternummer)"
    # Без stdnum: допускаем непустое значение, только max_length
    v = (value or '').strip()
    if not v:
        return False, "Регистрационный номер обязателен"
    if len(v) > REGISTRATION_NUMBER_MAX_LENGTH:
        return False, f"Максимум {REGISTRATION_NUMBER_MAX_LENGTH} символов"
    return True, None


def validate_registration_number_ru(value: str) -> tuple[bool, Optional[str]]:
    """Регистрационный номер РФ: ОГРН (13 цифр) или ОГРНИП (15 цифр)."""
    if stdnum_ru_ogrn:
        try:
            stdnum_ru_ogrn.validate(value)
            return True, None
        except Exception as e:
            return False, str(e) if str(e) else "Неверный формат ОГРН/ОГРНИП"
    clean = re.sub(r'[\s\-]', '', value or '')
    if not clean.isdigit():
        return False, "ОГРН/ОГРНИП: только цифры"
    if len(clean) == 13:
        return True, None  # ОГРН юрлица (контрольная сумма при наличии stdnum)
    if len(clean) == 15:
        return True, None  # ОГРНИП
    return False, "ОГРН: 13 цифр (юрлицо) или ОГРНИП: 15 цифр (ИП)"


def validate_registration_number_ua_me(value: str) -> tuple[bool, Optional[str]]:
    """UA, ME: только обязательность и ограничение длины (без формата 3–50)."""
    v = (value or '').strip()
    if not v:
        return False, "Регистрационный номер обязателен"
    if len(v) > REGISTRATION_NUMBER_MAX_LENGTH:
        return False, f"Максимум {REGISTRATION_NUMBER_MAX_LENGTH} символов"
    return True, None


# Правила валидации по странам
REQUISITES_VALIDATION_RULES: Dict[str, Dict[str, Dict[str, Any]]] = {
    'DE': {
        'tax_id': {
            'required': False,
            'conditional': {'is_vat_payer': True},
            'validator': validate_steuernummer_de,
            'format_description': {
                'en': 'Steuernummer: 10-11 digits (e.g., 12345678901), not VAT ID',
                'ru': 'Steuernummer: 10-11 цифр (например, 12345678901), не USt-IdNr.',
                'de': 'Steuernummer: 10–11 Ziffern (z.B. 12345678901), nicht USt-IdNr.',
                'me': 'Steuernummer: 10-11 cifara (npr. 12345678901), ne USt-IdNr.'
            }
        },
        'vat_number': {
            'required': True,
            'conditional': {'is_vat_payer': True},
            'validator': lambda x, c: validate_vat_id_eu(x, c),
            'format_description': {
                'en': 'VAT ID: DE + 9 digits (e.g., DE123456789)',
                'ru': 'USt-IdNr.: DE + 9 цифр (например, DE123456789)',
                'de': 'USt-IdNr.: DE + 9 Ziffern (z.B. DE123456789)',
                'me': 'USt-IdNr.: DE + 9 cifara (npr. DE123456789)'
            }
        },
        'iban': {
            'required': True,
            'conditional': {'is_vat_payer': True},  # Обязателен только если плательщик НДС
            'validator': lambda x, country='DE': validate_iban(x, country),
            'format_description': {
                'en': 'DE + 22 characters (e.g., DE89370400440532013000)',
                'ru': 'DE + 22 символа (например, DE89370400440532013000)',
                'de': 'DE + 22 Zeichen (z.B. DE89370400440532013000)',
                'me': 'DE + 22 karaktera (npr. DE89370400440532013000)'
            }
        },
        'registration_number': {
            'required': True,
            'validator': validate_registration_number_de,
            'format_description': {
                'en': 'Handelsregisternummer (e.g. HRB 12345, HRA 67890)',
                'ru': 'Номер в торговом реестре (напр. HRB 12345, HRA 67890)',
                'de': 'Handelsregisternummer (z.B. HRB 12345, HRA 67890)',
                'me': 'Broj u trgovačkom registru (npr. HRB 12345)'
            }
        },
        'kpp': {
            'required': False
        }
    },
    'RU': {
        'tax_id': {
            'required': True,
            'validator': validate_inn_ru,
            'format_description': {
                'en': '10 digits (legal entities) or 12 digits (sole proprietors) with checksum',
                'ru': '10 цифр (юрлица) или 12 цифр (ИП) с контрольной суммой',
                'de': '10 Ziffern (juristische Person) oder 12 Ziffern (Einzelunternehmer) mit Prüfsumme',
                'me': '10 cifara (pravna lica) ili 12 cifara (preduzetnik) sa kontrolnom cifrom',
            }
        },
        'registration_number': {
            'required': True,
            'validator': validate_registration_number_ru,
            'format_description': {
                'en': 'OGRN: 13 digits (legal entity) or OGRNIP: 15 digits (sole proprietor)',
                'ru': 'ОГРН: 13 цифр (юрлицо) или ОГРНИП: 15 цифр (ИП)',
                'de': 'OGRN: 13 Ziffern (jur. Person) oder OGRNIP: 15 Ziffern (Einzelunternehmer)',
                'me': 'OGRN: 13 cifara (pravno lice) ili OGRNIP: 15 cifara (preduzetnik)'
            }
        },
        'kpp': {
            'required': True,
            'conditional': {'organization_type__icontains': 'ООО'},  # Обязателен только для ООО
            'validator': validate_kpp_ru,
            'format_description': {
                'en': '9 digits (e.g., 770701001)',
                'ru': '9 цифр (например, 770701001)',
                'de': '9 Ziffern (z.B. 770701001)',
                'me': '9 cifara (npr. 770701001)',
            }
        },
        'vat_number': {
            'required': False
        },
        'iban': {
            'required': False
        }
    },
    'UA': {
        'tax_id': {
            'required': True,
            'validator': validate_tax_id_ua,
            'format_description': {
                'en': '8 digits (EDRPOU) or 10 digits (tax ID for sole proprietors)',
                'ru': '8 цифр (ЄДРПОУ) или 10 цифр (ИНН ФОП)',
                'de': '8 Ziffern (ЄДРПОУ) oder 10 Ziffern (Steuernummer für FOP)',
                'me': '8 cifara (ЄДРПОУ) ili 10 cifara (PIB za preduzetnike)',
            }
        },
        'registration_number': {
            'required': True,
            'validator': validate_registration_number_ua_me,
            'format_description': {
                'en': 'Registration number (up to 100 characters)',
                'ru': 'Регистрационный номер (до 100 символов)',
                'de': 'Registrierungsnummer (bis zu 100 Zeichen)',
                'me': 'Registracioni broj (do 100 karaktera)'
            }
        },
        'vat_number': {
            'required': False
        },
        'iban': {
            'required': False,  # Опционально
            'validator': lambda x, country='UA': validate_iban(x, country),
            'format_description': {
                'en': 'UA + up to 29 characters',
                'ru': 'UA + до 29 символов',
                'de': 'UA + bis zu 29 Zeichen',
                'me': 'UA + do 29 karaktera',
            }
        },
        'kpp': {
            'required': False
        }
    },
    'ME': {
        'tax_id': {
            'required': True,
            'validator': validate_pib_me,
            'format_description': {
                'en': '8 digits (e.g., 12345678)',
                'ru': '8 цифр (например, 12345678)',
                'de': '8 Ziffern (z.B. 12345678)',
                'me': '8 cifara (npr. 12345678)',
            }
        },
        'registration_number': {
            'required': True,
            'validator': validate_registration_number_ua_me,
            'format_description': {
                'en': 'Registration number (up to 100 characters)',
                'ru': 'Регистрационный номер (до 100 символов)',
                'de': 'Registrierungsnummer (bis zu 100 Zeichen)',
                'me': 'Registracioni broj (do 100 karaktera)'
            }
        },
        'vat_number': {
            'required': False
        },
        'iban': {
            'required': False,  # Опционально
            'validator': lambda x, country='ME': validate_iban(x, country),
            'format_description': {
                'en': 'ME + up to 29 characters',
                'ru': 'ME + до 29 символов',
                'de': 'ME + bis zu 29 Zeichen',
                'me': 'ME + do 29 karaktera',
            }
        },
        'kpp': {
            'required': False
        }
    },
    'AT': {
        'tax_id': {
            'required': True,
            'validator': validate_tax_id_at,
            'format_description': 'Steuernummer/UID: 8–10 Ziffern (ohne ATU), nicht USt-IdNr.'
        },
        'vat_number': {
            'required': True,
            'conditional': {'is_vat_payer': True},
            'validator': lambda x, c: validate_vat_id_eu(x, c),
            'format_description': 'USt-IdNr.: ATU + 8 Ziffern (z.B. ATU12345678)'
        },
        'registration_number': {
            'required': True,
            'validator': None,
            'format_description': 'Buchstaben, Ziffern, Bindestriche (3–50 Zeichen)'
        },
        'iban': {
            'required': True,
            'conditional': {'is_vat_payer': True},
            'validator': lambda x, c: validate_iban(x, c),
            'format_description': 'AT, 20 Zeichen'
        },
        'kpp': {'required': False}
    },
    'FR': {
        'tax_id': {
            'required': True,
            'validator': validate_siren_siret_fr,
            'format_description': 'SIREN (9 chiffres) ou SIRET (14 chiffres), pas le n° TVA'
        },
        'vat_number': {
            'required': True,
            'conditional': {'is_vat_payer': True},
            'validator': lambda x, c: validate_vat_id_eu(x, c),
            'format_description': 'TVA intracommunautaire: FR + 11 chiffres (z.B. FR12345678901)'
        },
        'registration_number': {
            'required': True,
            'validator': None,
            'format_description': 'Buchstaben, Ziffern, Bindestriche (3–50 Zeichen)'
        },
        'iban': {
            'required': True,
            'conditional': {'is_vat_payer': True},
            'validator': lambda x, c: validate_iban(x, c),
            'format_description': 'FR, 27 Zeichen'
        },
        'kpp': {'required': False}
    },
    'PL': {
        'tax_id': {
            'required': True,
            'validator': validate_nip_pl,
            'format_description': 'NIP: 10 Ziffern (z.B. 1234567890), VAT = PL + NIP'
        },
        'vat_number': {
            'required': True,
            'conditional': {'is_vat_payer': True},
            'validator': lambda x, c: validate_vat_id_eu(x, c),
            'format_description': 'USt-IdNr.: PL + 10 Ziffern (z.B. PL1234567890), entspricht PL + NIP'
        },
        'registration_number': {
            'required': True,
            'validator': None,
            'format_description': 'Buchstaben, Ziffern, Bindestriche (3–50 Zeichen)'
        },
        'iban': {
            'required': True,
            'conditional': {'is_vat_payer': True},
            'validator': lambda x, c: validate_iban(x, c),
            'format_description': 'PL, 28 Zeichen'
        },
        'kpp': {'required': False}
    },
}


def get_validation_rules(country_code: str) -> Dict[str, Dict[str, Any]]:
    """
    Получает правила валидации для указанной страны.
    
    Args:
        country_code: Код страны (ISO 3166-1 alpha-2)
        
    Returns:
        dict: Правила валидации для страны или пустой словарь
    """
    return REQUISITES_VALIDATION_RULES.get(country_code, {})


def get_format_description(field_name: str, country_code: str, language: str = 'en') -> str:
    """
    Получает локализованное описание формата поля реквизита.
    
    Args:
        field_name: Название поля (tax_id, vat_number, iban, registration_number, kpp)
        country_code: Код страны (ISO 3166-1 alpha-2)
        language: Код языка (en, ru, de, me). По умолчанию 'en'
        
    Returns:
        str: Локализованное описание формата или пустая строка
    """
    rules = get_validation_rules(country_code)
    field_rules = rules.get(field_name, {})
    format_desc = field_rules.get('format_description', '')
    
    # Если format_description - это словарь с языками, возвращаем нужный язык
    if isinstance(format_desc, dict):
        return format_desc.get(language, format_desc.get('en', ''))
    
    # Если это строка (старый формат), возвращаем как есть
    return format_desc if isinstance(format_desc, str) else ''


# Примеры для подсказки поля "Название организации" (зависят только от языка UI)
ORGANIZATION_NAME_HINTS: Dict[str, str] = {
    'en': 'Example: Happy Paws Veterinary Clinic, Cozy Pet Hotel, Paws & Care Grooming',
    'ru': 'Пример: Ветеринарная клиника «Добрые лапы», Зоогостиница «Уютный хвост», Груминг-студия «Лапки & Care»',
    'de': 'Beispiel: Tierarztpraxis „Happy Paws“, Tierhotel „Cozy Pet“, Pflegesalon „Paws & Care“',
    'me': 'Primjer: Veterinarska ambulanta „Srećne Šape“, Pet-hotel „Udoban Ljubimac“, Grooming salon „Šape & Care“',
}


def validate_requisite_field(
    field_name: str,
    value: str,
    country_code: str,
    **context
) -> tuple[bool, Optional[str]]:
    """
    Валидирует поле реквизита по правилам для страны.
    
    Args:
        field_name: Название поля (tax_id, vat_number, iban, kpp, registration_number)
        value: Значение для проверки
        country_code: Код страны
        **context: Дополнительный контекст (is_vat_payer, organization_type и т.д.)
        
    Returns:
        tuple: (валидный, сообщение об ошибке)
    """
    rules = get_validation_rules(country_code)
    
    if field_name not in rules:
        # Если правил нет для этого поля, используем общую валидацию
        if field_name == 'registration_number':
            # Общая валидация для registration_number
            if not value or len(value.strip()) < 3:
                return False, "Registration Number должен содержать минимум 3 символа"
            if len(value) > 50:
                return False, "Registration Number должен содержать максимум 50 символов"
            return True, None
        return True, None  # Поле не требует специальной валидации
    
    field_rules = rules[field_name]
    
    # Проверка обязательности
    if field_rules.get('required', False):
        if not value or not value.strip():
            return False, f"{field_name} обязателен для страны {country_code}"
        
        # Проверка условной обязательности
        if 'conditional' in field_rules:
            conditional = field_rules['conditional']
            condition_met = True
            
            for key, expected_value in conditional.items():
                if key == 'is_vat_payer':
                    if context.get('is_vat_payer') != expected_value:
                        condition_met = False
                        break
                elif key == 'organization_type__icontains':
                    org_type = context.get('organization_type', '')
                    if expected_value.lower() not in org_type.lower():
                        condition_met = False
                        break
            
            if not condition_met:
                # Поле не требуется при данных условиях
                return True, None
    
    # Проверка формата через валидатор
    if field_rules.get('validator'):
        validator = field_rules['validator']
        try:
            if callable(validator):
                return validator(value, country_code) if validator.__code__.co_argcount > 1 else validator(value)
        except Exception as e:
            return False, f"Ошибка валидации: {str(e)}"
    
    # Общая валидация для registration_number
    if field_name == 'registration_number':
        if len(value.strip()) < 3:
            return False, "Registration Number должен содержать минимум 3 символа"
        if len(value) > 50:
            return False, "Registration Number должен содержать максимум 50 символов"
    
    return True, None
