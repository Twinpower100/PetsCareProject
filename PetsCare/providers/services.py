"""
Сервисы провайдеров: часы работы локации с учётом недельного расписания, производственного календаря и смен в праздники.
"""
from datetime import time
from typing import Optional, Dict, Any

from production_calendar.models import ProductionCalendar, DAY_TYPE_HOLIDAY

from .models import ProviderLocation, LocationSchedule, HolidayShift, _get_location_country_code


def get_working_hours(
    location: ProviderLocation,
    date,
) -> Dict[str, Any]:
    """
    Определяет, открыта ли локация в указанную дату и в какие часы.

    Логика:
    - Если дата в глобальном календаре — праздник (HOLIDAY): по умолчанию закрыто;
      если есть HolidayShift для (location, date) — открыто в часы из этой смены.
    - Если дата не праздник: используются часы из LocationSchedule по дню недели.

    Returns:
        dict: {'is_open': bool, 'start': time | None, 'end': time | None}
    """
    result = {'is_open': False, 'start': None, 'end': None}
    country = _get_location_country_code(location)
    if not country:
        return result

    cal = ProductionCalendar.objects.filter(
        date=date,
        country=country,
    ).first()

    if cal and cal.day_type == DAY_TYPE_HOLIDAY:
        shift = HolidayShift.objects.filter(
            provider_location=location,
            date=date,
        ).first()
        if shift:
            result['is_open'] = True
            result['start'] = shift.start_time
            result['end'] = shift.end_time
        return result

    weekday = date.weekday()
    schedule = LocationSchedule.objects.filter(
        provider_location=location,
        weekday=weekday,
    ).first()
    if not schedule or schedule.is_closed:
        return result
    if schedule.open_time and schedule.close_time:
        result['is_open'] = True
        result['start'] = schedule.open_time
        result['end'] = schedule.close_time
    return result
