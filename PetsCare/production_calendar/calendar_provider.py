"""
Абстракция источника данных производственного календаря.

- RU: workalendar.europe.Russia (учёт рабочих суббот-переносов).
- DE, FR: workalendar Europe.
- UA, ME, RS: библиотека holidays (только праздники; WEEKEND по weekday).
- US: workalendar.usa (UnitedStates).
"""
from datetime import date
from typing import Dict, Any, Optional, List, Tuple

from .models import (
    DAY_TYPE_WORKING,
    DAY_TYPE_WEEKEND,
    DAY_TYPE_HOLIDAY,
    DAY_TYPE_SHORT_DAY,
    COUNTRY_CHOICES,
)

# Коды стран из COUNTRY_CHOICES
SUPPORTED_COUNTRIES = [c[0] for c in COUNTRY_CHOICES]

# Workalendar: RU, DE, FR, US
WORKALENDAR_COUNTRIES = {'RU', 'DE', 'FR', 'US'}
# Holidays-only: UA, ME, RS (infer WEEKEND by weekday)
HOLIDAYS_ONLY_COUNTRIES = {'UA', 'ME', 'RS'}


def _get_workalendar_holidays_set_and_map(country: str, year: int) -> Tuple[set, Dict[date, str]]:
    """Возвращает (множество дат праздников, словарь дата -> описание) для workalendar."""
    if country == 'RU':
        from workalendar.europe import Russia
        cal = Russia()
    elif country == 'DE':
        from workalendar.europe import Germany
        cal = Germany()
    elif country == 'FR':
        from workalendar.europe import France
        cal = France()
    elif country == 'US':
        from workalendar.usa import UnitedStates
        cal = UnitedStates()
    else:
        return set(), {}
    holidays_list = cal.holidays(year)
    dates_set = {d for d, _ in holidays_list}
    dates_map = {d: label for d, label in holidays_list}
    return dates_set, dates_map


def _get_holidays_lib_map(country: str, year: int) -> Dict[date, str]:
    """Для UA, ME, RS: праздники через библиотеку holidays. Возвращает словарь дата -> название."""
    import holidays as holidays_lib
    country_holidays = holidays_lib.country_holidays(country, years=year, observed=True)
    return dict(country_holidays)


def get_day_info_workalendar(country: str, d: date) -> Dict[str, Any]:
    """
    Статус дня через workalendar (RU, DE, FR, US).
    Учитываются рабочие субботы/воскресенья (переносы) в РФ.
    """
    holidays_set, holidays_map = _get_workalendar_holidays_set_and_map(country, d.year)
    try:
        if country == 'RU':
            from workalendar.europe import Russia
            cal = Russia()
        elif country == 'DE':
            from workalendar.europe import Germany
            cal = Germany()
        elif country == 'FR':
            from workalendar.europe import France
            cal = France()
        elif country == 'US':
            from workalendar.usa import UnitedStates
            cal = UnitedStates()
        else:
            return {
                'day_type': DAY_TYPE_WORKING,
                'description': '',
                'is_transfer': False,
            }
    except Exception:
        return {
            'day_type': DAY_TYPE_WORKING,
            'description': '',
            'is_transfer': False,
        }

    is_working = cal.is_working_day(d)
    if d in holidays_set:
        return {
            'day_type': DAY_TYPE_HOLIDAY,
            'description': holidays_map.get(d, ''),
            'is_transfer': False,
        }
    if not is_working:
        return {
            'day_type': DAY_TYPE_WEEKEND,
            'description': '',
            'is_transfer': False,
        }
    # Рабочий день: если это суббота или воскресенье — перенос (working Saturday/Sunday)
    is_transfer = d.weekday() in (5, 6)  # 5=Saturday, 6=Sunday
    return {
        'day_type': DAY_TYPE_WORKING,
        'description': 'Transfer (working weekend)' if is_transfer else '',
        'is_transfer': is_transfer,
    }


def get_day_info_holidays_only(country: str, d: date) -> Dict[str, Any]:
    """
    Статус дня через holidays (UA, ME, RS): только праздники;
    WEEKEND выводится по weekday() (суббота/воскресенье).
    """
    holidays_map = _get_holidays_lib_map(country, d.year)
    if d in holidays_map:
        return {
            'day_type': DAY_TYPE_HOLIDAY,
            'description': holidays_map.get(d, ''),
            'is_transfer': False,
        }
    if d.weekday() in (5, 6):
        return {
            'day_type': DAY_TYPE_WEEKEND,
            'description': '',
            'is_transfer': False,
        }
    return {
        'day_type': DAY_TYPE_WORKING,
        'description': '',
        'is_transfer': False,
    }


class CalendarProvider:
    """
    Единая точка получения статуса дня по стране и дате.
    """

    @classmethod
    def get_day_info(cls, country: str, d: date) -> Dict[str, Any]:
        """
        Возвращает словарь: day_type, description, is_transfer.
        """
        country = (country or '').upper()[:2]
        if country not in SUPPORTED_COUNTRIES:
            return {
                'day_type': DAY_TYPE_WORKING,
                'description': '',
                'is_transfer': False,
            }
        if country in WORKALENDAR_COUNTRIES:
            return get_day_info_workalendar(country, d)
        if country in HOLIDAYS_ONLY_COUNTRIES:
            return get_day_info_holidays_only(country, d)
        return {
            'day_type': DAY_TYPE_WORKING,
            'description': '',
            'is_transfer': False,
        }
