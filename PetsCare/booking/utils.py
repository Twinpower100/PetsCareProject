from django.utils.translation import gettext_lazy as _
from datetime import datetime, timedelta
from decimal import Decimal
from .models import Booking, BookingStatus

def check_booking_availability(provider, employee, start_time, end_time, exclude_booking_id=None):
    """
    Проверяет доступность временного слота для бронирования.
    
    Args:
        provider: Поставщик услуг
        employee: Сотрудник
        start_time: Время начала
        end_time: Время окончания
        exclude_booking_id: ID бронирования для исключения из проверки (при обновлении)
    
    Returns:
        bool: True если слот доступен, False в противном случае
    """
    # Проверяем, что время окончания позже времени начала
    if end_time <= start_time:
        return False
    
    # Получаем все бронирования, которые пересекаются с указанным временным слотом
    overlapping_bookings = Booking.objects.filter(
        provider=provider,
        employee=employee,
        start_time__lt=end_time,
        end_time__gt=start_time
    )
    
    # Исключаем текущее бронирование при обновлении
    if exclude_booking_id:
        overlapping_bookings = overlapping_bookings.exclude(id=exclude_booking_id)
    
    # Проверяем статусы бронирований
    active_statuses = ['active', 'pending_confirmation']
    overlapping_bookings = overlapping_bookings.filter(
        status__name__in=active_statuses
    )
    
    # Если есть пересекающиеся бронирования, слот занят
    return not overlapping_bookings.exists()

def calculate_booking_price(service, start_time, end_time):
    """
    Рассчитывает стоимость бронирования.
    
    Args:
        service: Услуга
        start_time: Время начала
        end_time: Время окончания
    
    Returns:
        Decimal: Стоимость бронирования
    """
    # Рассчитываем продолжительность в часах
    duration = (end_time - start_time).total_seconds() / 3600
    
    # Рассчитываем стоимость
    service_price = getattr(service, 'price', None)
    if service_price is None:
        return Decimal('0.00')
    return service_price * Decimal(str(duration))

def update_booking_status(booking, new_status_name):
    """
    Обновляет статус бронирования.
    
    Args:
        booking: Бронирование
        new_status_name: Название нового статуса
    
    Raises:
        ValueError: Если переход между статусами невозможен
    """
    # Получаем новый статус
    try:
        new_status = BookingStatus.objects.get(name=new_status_name)
    except BookingStatus.DoesNotExist:
        raise ValueError(_('Invalid status name.'))
    
    # Проверяем допустимость перехода между статусами
    current_status = booking.status.name
    valid_transitions = {
        'pending_confirmation': ['active', 'cancelled_by_client', 'cancelled_by_provider'],
        'active': ['completed', 'cancelled_by_client', 'cancelled_by_provider', 'no_show_by_client', 'no_show_by_provider'],
        'completed': [],
        'cancelled_by_client': [],
        'cancelled_by_provider': [],
        'no_show_by_client': [],
        'no_show_by_provider': []
    }
    
    if new_status_name not in valid_transitions.get(current_status, []):
        raise ValueError(_('Invalid status transition.'))
    
    # Обновляем статус
    booking.status = new_status
    booking.save()

def get_available_time_slots(provider_id, employee_id, date, duration):
    """
    Получает список доступных временных слотов.
    
    Args:
        provider_id: ID поставщика услуг
        employee_id: ID сотрудника
        date: Дата
        duration: Продолжительность в часах
    
    Returns:
        list: Список доступных временных слотов
    """
    # Преобразуем дату в datetime
    try:
        date = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        raise ValueError(_('Invalid date format.'))
    
    # Определяем рабочие часы
    work_start = date.replace(hour=9, minute=0)  # 9:00
    work_end = date.replace(hour=18, minute=0)   # 18:00
    
    # Получаем все бронирования на указанную дату
    bookings = Booking.objects.filter(
        provider_id=provider_id,
        employee_id=employee_id,
        start_time__date=date,
        status__name__in=['active', 'pending_confirmation']
    ).order_by('start_time')
    
    # Инициализируем список доступных слотов
    available_slots = []
    current_time = work_start
    
    # Проверяем каждый временной слот
    while current_time + timedelta(hours=duration) <= work_end:
        slot_end = current_time + timedelta(hours=duration)
        
        # Проверяем, не пересекается ли слот с существующими бронированиями
        is_available = True
        for booking in bookings:
            if (current_time < booking.end_time and slot_end > booking.start_time):
                is_available = False
                current_time = booking.end_time
                break
        
        if is_available:
            available_slots.append({
                'start': current_time.strftime('%H:%M'),
                'end': slot_end.strftime('%H:%M')
            })
            current_time += timedelta(minutes=30)  # Следующий слот через 30 минут
        else:
            current_time += timedelta(minutes=30)
    
    return available_slots 