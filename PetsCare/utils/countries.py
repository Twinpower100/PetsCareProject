"""
Утилиты для работы со странами и региональными союзами.

Содержит константы и функции для определения принадлежности стран к региональным союзам:
- EU (European Union) - Европейский Союз
- EEA (European Economic Area) - Европейская экономическая зона
- EFTA (European Free Trade Association) - Европейская ассоциация свободной торговли
- EAEU (Eurasian Economic Union) - Евразийский экономический союз

Источник данных для ЕС: https://european-union.europa.eu/principles-countries-history/country-profiles_en
Последнее обновление: 2024-01-01
"""

# Страны-члены Европейского Союза (27 стран, после Brexit)
EU_COUNTRIES = {
    'AT',  # Австрия
    'BE',  # Бельгия
    'BG',  # Болгария
    'HR',  # Хорватия
    'CY',  # Кипр
    'CZ',  # Чехия
    'DK',  # Дания
    'EE',  # Эстония
    'FI',  # Финляндия
    'FR',  # Франция
    'DE',  # Германия
    'GR',  # Греция
    'HU',  # Венгрия
    'IE',  # Ирландия
    'IT',  # Италия
    'LV',  # Латвия
    'LT',  # Литва
    'LU',  # Люксембург
    'MT',  # Мальта
    'NL',  # Нидерланды
    'PL',  # Польша
    'PT',  # Португалия
    'RO',  # Румыния
    'SK',  # Словакия
    'SI',  # Словения
    'ES',  # Испания
    'SE',  # Швеция
}

# Страны EEA (EU + Исландия, Лихтенштейн, Норвегия)
EEA_COUNTRIES = EU_COUNTRIES | {
    'IS',  # Исландия
    'LI',  # Лихтенштейн
    'NO',  # Норвегия
}

# Страны EFTA (Исландия, Лихтенштейн, Норвегия, Швейцария)
EFTA_COUNTRIES = {
    'IS',  # Исландия
    'LI',  # Лихтенштейн
    'NO',  # Норвегия
    'CH',  # Швейцария
}

# Страны ЕАЭС (Евразийский экономический союз)
EAEU_COUNTRIES = {
    'AM',  # Армения
    'BY',  # Беларусь
    'KZ',  # Казахстан
    'KG',  # Кыргызстан
    'RU',  # Россия
}


def is_eu_country(country_code):
    """
    Проверяет, является ли страна членом Европейского Союза.
    
    Args:
        country_code: ISO 3166-1 alpha-2 код страны (например, 'DE', 'FR')
        
    Returns:
        bool: True если страна в ЕС, False иначе
    """
    if not country_code:
        return False
    return country_code.upper() in EU_COUNTRIES


def is_eea_country(country_code):
    """
    Проверяет, является ли страна членом Европейской экономической зоны (EEA).
    
    Args:
        country_code: ISO 3166-1 alpha-2 код страны
        
    Returns:
        bool: True если страна в EEA, False иначе
    """
    if not country_code:
        return False
    return country_code.upper() in EEA_COUNTRIES


def is_efta_country(country_code):
    """
    Проверяет, является ли страна членом EFTA.
    
    Args:
        country_code: ISO 3166-1 alpha-2 код страны
        
    Returns:
        bool: True если страна в EFTA, False иначе
    """
    if not country_code:
        return False
    return country_code.upper() in EFTA_COUNTRIES


def is_eaeu_country(country_code):
    """
    Проверяет, является ли страна членом Евразийского экономического союза (ЕАЭС).
    
    Args:
        country_code: ISO 3166-1 alpha-2 код страны
        
    Returns:
        bool: True если страна в ЕАЭС, False иначе
    """
    if not country_code:
        return False
    return country_code.upper() in EAEU_COUNTRIES


def get_region_code(country_code):
    """
    Получает код региона для RegionalAddendum на основе страны.
    
    Args:
        country_code: ISO 3166-1 alpha-2 код страны (str или django_countries.Country)
        
    Returns:
        str: Код региона ('EU', 'RU', 'UA', 'EAEU', etc.) или None
    """
    if not country_code:
        return None
    # django_countries.Country не имеет .upper(); берём код строкой
    if hasattr(country_code, 'code'):
        country_code = country_code.code
    country_code = str(country_code).upper()
    
    # Проверяем по приоритету
    if is_eu_country(country_code):
        return 'EU'
    elif country_code == 'RU':
        return 'RU'
    elif country_code == 'UA':
        return 'UA'
    elif is_eaeu_country(country_code):
        return 'EAEU'
    else:
        return None

