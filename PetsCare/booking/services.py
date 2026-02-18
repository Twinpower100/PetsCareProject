"""
Services for the booking module.

Этот модуль содержит сервисы для безопасных операций с бронированиями.
Основной компонент - BookingTransactionService для защиты от конкурентного доступа.
"""

from django.db import transaction, models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from typing import Optional, List, Dict, Any
import logging
from datetime import timedelta, time, date, datetime

from .models import Booking, TimeSlot, BookingStatus, BookingAutoCompleteSettings
from pets.models import Pet
from providers.models import Employee, Provider, Schedule, LocationSchedule, ProviderLocationService, ProviderLocation
from catalog.models import Service
from users.models import User

logger = logging.getLogger(__name__)


class BookingTransactionService:
    """
    Сервис для безопасных операций с бронированиями.
    
    Обеспечивает защиту от конкурентного доступа при создании,
    изменении и отмене бронирований через транзакционные блоки.
    """
    
    @staticmethod
    def _validate_business_rules(booking_data: Dict) -> None:
        """
        Валидация бизнес-правил для бронирования.
        
        Args:
            booking_data: Данные бронирования
            
        Raises:
            ValidationError: Если нарушены бизнес-правила
        """
        from datetime import timedelta
        
        start_time = booking_data['start_time']
        end_time = booking_data['end_time']
        provider = booking_data['provider']
        employee = booking_data['employee']
        
        # 1. Проверка минимального времени для отмены (если это отмена)
        if 'is_cancellation' in booking_data and booking_data['is_cancellation']:
            time_until_booking = start_time - timezone.now()
            min_cancellation_hours = getattr(provider, 'min_cancellation_hours', 2)
            
            if time_until_booking < timedelta(hours=min_cancellation_hours):
                raise ValidationError(
                    _("Cannot cancel booking less than {} hours before").format(min_cancellation_hours)
                )
        
        # 2. Проверка максимального времени для бронирования
        max_booking_days = getattr(provider, 'max_booking_days', 30)
        if start_time > timezone.now() + timedelta(days=max_booking_days):
            raise ValidationError(
                _("Cannot book more than {} days in advance").format(max_booking_days)
            )
        
        # 3. Проверка минимального времени для бронирования
        min_booking_hours = getattr(provider, 'min_booking_hours', 1)
        if start_time < timezone.now() + timedelta(hours=min_booking_hours):
            raise ValidationError(
                _("Cannot book less than {} hours in advance").format(min_booking_hours)
            )
        
        # 4. Проверка доступности сотрудника
        if not BookingAvailabilityService._is_employee_available(employee, start_time, end_time):
            raise ValidationError(_("Employee is not available at this time"))
        
        # 5. Проверка максимальной нагрузки сотрудника
        workload = BookingAvailabilityService.get_employee_workload(employee, start_time.date())
        max_daily_hours = getattr(employee, 'max_daily_hours', 8)
        
        if workload['total_hours'] + (end_time - start_time).total_seconds() / 3600 > max_daily_hours:
            raise ValidationError(_("Employee would exceed maximum daily workload"))
    
    @staticmethod
    @transaction.atomic
    def create_booking(
        user: User,
        pet: Pet,
        provider: Provider,
        employee: Employee,
        service: Service,
        start_time: timezone.datetime,
        end_time: timezone.datetime,
        price: float,
        notes: str = ""
    ) -> Booking:
        """
        Создает бронирование с защитой от конкурентного доступа.
        
        Args:
            user: Пользователь, создающий бронирование
            pet: Питомец для бронирования
            provider: Учреждение
            employee: Сотрудник
            service: Услуга
            start_time: Время начала
            end_time: Время окончания
            price: Стоимость
            notes: Заметки
            provider_location: Локация провайдера (опционально)
            
        Returns:
            Booking: Созданное бронирование
            
        Raises:
            ValidationError: Если слот уже занят
        """
        # Валидация бизнес-правил
        booking_data = {
            'start_time': start_time,
            'end_time': end_time,
            'provider': provider,
            'employee': employee,
            'is_cancellation': False
        }
        BookingTransactionService._validate_business_rules(booking_data)
        
        # Проверяем доступность на лету
        # Получаем provider_location из booking_data, если есть
        provider_location = booking_data.get('provider_location')
        if not BookingAvailabilityService.check_slot_availability(
            employee, provider, start_time, end_time, provider_location
        ):
            raise ValidationError(_("Slot is not available, please refresh search"))
        
        # Дополнительная проверка с блокировкой для конкурентного доступа
        conflicting_booking = Booking.objects.select_for_update().filter(
            employee=employee,
            start_time__lt=end_time,
            end_time__gt=start_time,
            status__name__in=['active', 'pending_confirmation']
        ).first()
        
        if conflicting_booking:
            raise ValidationError(_("Slot is already occupied, please refresh search"))
        
        # Получаем статус "active"
        active_status = BookingStatus.objects.get(name='active')
        
        # Создаем бронирование
        booking = Booking.objects.create(
            user=user,
            pet=pet,
            provider=provider,
            provider_location=provider_location,
            employee=employee,
            service=service,
            status=active_status,
            start_time=start_time,
            end_time=end_time,
            price=price,
            notes=notes,
            code=BookingTransactionService._generate_booking_code()
        )
        
        logger.info(_("Booking created successfully: {}").format(booking.id))
        return booking
    
    @staticmethod
    @transaction.atomic
    def cancel_booking(booking_id: int, cancelled_by: User, reason: str = "") -> Booking:
        """
        Отменяет бронирование с освобождением слота.
        
        Args:
            booking_id: ID бронирования
            cancelled_by: Пользователь, отменяющий бронирование
            reason: Причина отмены
            
        Returns:
            Booking: Обновленное бронирование
            
        Raises:
            ValidationError: Если бронирование не найдено или уже отменено
        """
        # Блокируем бронирование для изменения
        booking = Booking.objects.select_for_update().get(id=booking_id)
        
        if booking.status.name in ['cancelled_by_client', 'cancelled_by_provider', 'completed']:
            raise ValidationError(_("Booking is already cancelled or completed"))
        
        # Валидация бизнес-правил для отмены
        booking_data = {
            'start_time': booking.start_time,
            'end_time': booking.end_time,
            'provider': booking.provider,
            'employee': booking.employee,
            'is_cancellation': True
        }
        BookingTransactionService._validate_business_rules(booking_data)
        
        # Получаем статус отмены
        if cancelled_by == booking.user:
            cancel_status = BookingStatus.objects.get(name='cancelled_by_client')
        else:
            cancel_status = BookingStatus.objects.get(name='cancelled_by_provider')
        
        # Обновляем статус
        booking.status = cancel_status
        booking.save()
        
        # Слот автоматически освобождается при отмене бронирования
        # Дополнительных действий не требуется
        
        # Создаем запись об отмене
        from .models import BookingCancellation
        BookingCancellation.objects.create(
            booking=booking,
            cancelled_by=cancelled_by,
            reason=reason
        )
        
        logger.info(_("Booking cancelled: {}").format(booking.id))
        return booking
    
    @staticmethod
    @transaction.atomic
    def update_booking(
        booking_id: int,
        new_start_time: Optional[timezone.datetime] = None,
        new_end_time: Optional[timezone.datetime] = None,
        new_employee: Optional[Employee] = None,
        new_service: Optional[Service] = None,
        new_price: Optional[float] = None,
        new_notes: Optional[str] = None
    ) -> Booking:
        """
        Обновляет бронирование с проверкой доступности нового слота.
        
        Args:
            booking_id: ID бронирования
            new_start_time: Новое время начала
            new_end_time: Новое время окончания
            new_employee: Новый сотрудник
            new_service: Новая услуга
            new_price: Новая цена
            new_notes: Новые заметки
            
        Returns:
            Booking: Обновленное бронирование
            
        Raises:
            ValidationError: Если новый слот недоступен
        """
        # Блокируем бронирование для изменения
        booking = Booking.objects.select_for_update().get(id=booking_id)
        
        if booking.status.name in ['cancelled_by_client', 'cancelled_by_provider', 'completed']:
            raise ValidationError(_("Cannot update cancelled or completed booking"))
        
        # Если меняется время или сотрудник, проверяем доступность нового слота
        if (new_start_time or new_end_time or new_employee) and booking.status.name in ['active', 'pending_confirmation']:
            start_time = new_start_time or booking.start_time
            end_time = new_end_time or booking.end_time
            employee = new_employee or booking.employee
            
            # Проверяем доступность нового слота
            conflicting_booking = Booking.objects.filter(
                employee=employee,
                start_time__lt=end_time,
                end_time__gt=start_time,
                status__name__in=['active', 'pending_confirmation']
            ).exclude(id=booking_id).first()
            
            if conflicting_booking:
                raise ValidationError(_("New slot is already occupied, please refresh search"))
        
        # Обновляем поля
        if new_start_time is not None:
            booking.start_time = new_start_time
        if new_end_time is not None:
            booking.end_time = new_end_time
        if new_employee is not None:
            booking.employee = new_employee
        if new_service is not None:
            booking.service = new_service
        if new_price is not None:
            booking.price = new_price
        if new_notes is not None:
            booking.notes = new_notes
        
        booking.save()
        
        logger.info(_("Booking updated: {}").format(booking.id))
        return booking
    
    @staticmethod
    def check_slot_availability(
        employee: Employee,
        provider: Provider,
        start_time: timezone.datetime,
        end_time: timezone.datetime
    ) -> bool:
        """
        Проверяет доступность слота без блокировки.
        
        Args:
            employee: Сотрудник
            provider: Учреждение
            start_time: Время начала
            end_time: Время окончания
            
        Returns:
            bool: True если слот доступен
        """
        # Проверяем существующие бронирования
        conflicting_booking = Booking.objects.filter(
            employee=employee,
            start_time__lt=end_time,
            end_time__gt=start_time,
            status__name__in=['active', 'pending_confirmation']
        ).first()
        
        if conflicting_booking:
            return False
        
        # Проверяем доступность слота
        slot = TimeSlot.objects.filter(
            employee=employee,
            provider=provider,
            start_time=start_time,
            end_time=end_time,
            is_available=True
        ).first()
        
        return slot is not None
    
    @staticmethod
    def _generate_booking_code() -> str:
        """
        Генерирует уникальный код бронирования.
        
        Returns:
            str: Уникальный код
        """
        import random
        import string
        
        while True:
            # Генерируем код из 8 символов
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            
            # Проверяем уникальность
            if not Booking.objects.filter(code=code).exists():
                return code 


class BookingCompletionService:
    """Сервис для завершения бронирований"""
    
    @staticmethod
    def complete_booking(booking, user, status='completed'):
        """
        Завершить бронирование
        
        Args:
            booking: Объект бронирования
            user: Пользователь, завершающий бронирование
            status: Статус завершения
        """
        with transaction.atomic():
            booking.complete_booking(user, status)
            
            # Отправляем уведомления
            BookingCompletionService._send_completion_notifications(booking, user)
    
    @staticmethod
    def cancel_booking(booking, user, reason=''):
        """
        Отменить бронирование
        
        Args:
            booking: Объект бронирования
            user: Пользователь, отменяющий бронирование
            reason: Причина отмены
        """
        with transaction.atomic():
            booking.cancel_booking(user, reason)
            
            # Отправляем уведомления
            BookingCompletionService._send_cancellation_notifications(booking, user)
    
    @staticmethod
    def auto_complete_bookings():
        """
        Автоматическое завершение "зависших" бронирований
        """
        settings = BookingAutoCompleteSettings.get_settings()
        
        if not settings.auto_complete_enabled:
            return
        
        # Вычисляем диапазон дат для проверки
        today = timezone.now().date()
        start_date = today - timedelta(days=settings.auto_complete_days)
        end_date = today - timedelta(days=1)  # Вчера включительно
        
        # Находим "зависшие" бронирования
        stale_bookings = Booking.objects.filter(
            status__name='confirmed',
            start_time__date__range=[start_date, end_date],
            completed_at__isnull=True,
            cancelled_at__isnull=True
        )
        
        # Системный пользователь для автоматических операций
        system_user = BookingCompletionService._get_system_user()
        
        completed_count = 0
        for booking in stale_bookings:
            try:
                with transaction.atomic():
                    booking.complete_booking(system_user, settings.auto_complete_status)
                    completed_count += 1
                    
                    # Отправляем уведомление о автоматическом завершении
                    BookingCompletionService._send_auto_completion_notification(booking)
                    
            except Exception as e:
                # Логируем ошибку, но продолжаем обработку других бронирований
                logger.error(_("Error auto-completing booking {}: {}").format(booking.id, e))
        
        return completed_count
    
    @staticmethod
    def _get_system_user():
        """Получить системного пользователя для автоматических операций"""
        try:
            return User.objects.get(username='system')
        except User.DoesNotExist:
            # Создаем системного пользователя, если его нет
            return User.objects.create_user(
                username='system',
                email='system@petscare.com',
                password='system_password_123',
                is_active=False  # Неактивный пользователь
            )
    
    @staticmethod
    def _send_completion_notifications(booking, user):
        """Отправить уведомления о завершении бронирования"""
        from notifications.models import Notification
        from users.models import ProviderAdmin
        
        provider = booking.provider
        if not provider and booking.provider_location:
            provider = booking.provider_location.provider
        
        # Email уведомление (уже есть в signals.py)
        
        # Push-уведомление клиенту
        Notification.objects.create(
            user=booking.user,
            pet=booking.pet,
            title=_("Booking Completed"),
            message=_("Your booking for {} has been completed").format(booking.service.name),
            notification_type='appointment',
            channel='both',
            priority='medium',
            data={
                'booking_id': booking.id,
                'service_name': booking.service.name,
                'provider_name': booking.provider.name,
                'completed_by': user.get_full_name() or user.username
            }
        )
    
    @staticmethod
    def _send_cancellation_notifications(booking, user):
        """Отправить уведомления об отмене бронирования"""
        from notifications.models import Notification
        
        # Определяем тип отмены
        if user.has_role('pet_owner') and user == booking.user:
            # Отменил клиент - уведомляем специалиста и админа учреждения
            Notification.objects.create(
                user=booking.employee.user,
                title=_("Booking Cancelled by Client"),
                message=_("Client cancelled booking for {}").format(booking.service.name),
                notification_type='appointment',
                channel='both',
                priority='medium',
                data={
                    'booking_id': booking.id,
                    'client_name': booking.user.get_full_name() or booking.user.username,
                    'cancellation_reason': booking.cancellation_reason
                }
            )
            
            # Уведомляем админа учреждения
            if provider:
                provider_admins = ProviderAdmin.objects.filter(
                    provider=provider,
                    is_active=True
                ).select_related('user')
                for provider_admin in provider_admins:
                    Notification.objects.create(
                        user=provider_admin.user,
                        title=_("Booking Cancelled by Client"),
                        message=_("Client cancelled booking at your facility"),
                        notification_type='appointment',
                        channel='both',
                        priority='medium',
                        data={
                            'booking_id': booking.id,
                            'client_name': booking.user.get_full_name() or booking.user.username,
                            'employee_name': booking.employee.user.get_full_name() or booking.employee.user.username
                        }
                    )
        else:
            # Отменил админ - уведомляем клиента
            Notification.objects.create(
                user=booking.user,
                pet=booking.pet,
                title=_("Booking Cancelled"),
                message=_("Your booking for {} has been cancelled").format(booking.service.name),
                notification_type='appointment',
                channel='both',
                priority='high',
                data={
                    'booking_id': booking.id,
                    'service_name': booking.service.name,
                    'provider_name': booking.provider.name,
                    'cancelled_by': user.get_full_name() or user.username,
                    'cancellation_reason': booking.cancellation_reason
                }
            )
    
    @staticmethod
    def _send_auto_completion_notification(booking):
        """Отправить уведомление о автоматическом завершении"""
        from notifications.models import Notification
        
        # Уведомляем админа учреждения о автоматическом завершении
        if provider:
            provider_admins = ProviderAdmin.objects.filter(
                provider=provider,
                is_active=True
            ).select_related('user')
            for provider_admin in provider_admins:
                Notification.objects.create(
                    user=provider_admin.user,
                    title=_("Booking Auto-Completed"),
                    message=_("Booking was automatically completed by system"),
                    notification_type='system',
                    channel='both',
                    priority='low',
                    data={
                        'booking_id': booking.id,
                        'client_name': booking.user.get_full_name() or booking.user.username,
                        'employee_name': booking.employee.user.get_full_name() or booking.employee.user.username,
                        'service_name': booking.service.name
                    }
                )


class BookingReportService:
    """Сервис для генерации отчетов по отменам"""
    
    @staticmethod
    def get_cancellations_report(start_date, end_date, providers=None, user=None):
        """
        Получить отчет по отменам бронирований
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            providers: Список учреждений (для ограничения доступа)
            user: Пользователь, запрашивающий отчет
            
        Returns:
            QuerySet с отмененными бронированиями
        """
        queryset = Booking.objects.filter(
            cancelled_at__range=[start_date, end_date],
            status__name__in=['cancelled_by_client', 'cancelled_by_provider']
        ).select_related(
            'user', 'pet', 'provider', 'service', 'cancelled_by'
        )
        
        # Ограничиваем доступ по учреждениям
        if providers is not None:
            queryset = queryset.filter(provider__in=providers)
        
        return queryset.order_by('-cancelled_at')
    
    @staticmethod
    def get_cancellation_statistics(start_date, end_date, providers=None):
        """
        Получить статистику по отменам
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            providers: Список учреждений
            
        Returns:
            Словарь со статистикой
        """
        queryset = BookingReportService.get_cancellations_report(
            start_date, end_date, providers
        )
        
        total_cancellations = queryset.count()
        
        # Статистика по инициаторам отмен
        client_cancellations = queryset.filter(
            status__name='cancelled_by_client'
        ).count()
        
        provider_cancellations = queryset.filter(
            status__name='cancelled_by_provider'
        ).count()
        
        # Статистика по учреждениям
        provider_stats = queryset.values('provider__name').annotate(
            count=models.Count('id')
        ).order_by('-count')
        
        # Статистика по услугам
        service_stats = queryset.values('service__name').annotate(
            count=models.Count('id')
        ).order_by('-count')
        
        return {
            'total_cancellations': total_cancellations,
            'client_cancellations': client_cancellations,
            'provider_cancellations': provider_cancellations,
            'provider_stats': list(provider_stats),
            'service_stats': list(service_stats),
        } 


class BookingAvailabilityService:
    """
    Сервис для расчета доступности слотов на лету.
    
    Вместо создания предварительных тайм-слотов, рассчитываем доступность
    на основе существующих бронирований и расписания сотрудников.
    """
    
    @staticmethod
    def check_slot_availability(
        employee: Employee,
        provider: Provider,
        start_time: timezone.datetime,
        end_time: timezone.datetime,
        provider_location=None
    ) -> bool:
        """
        Проверяет доступность слота на лету.
        
        Args:
            employee: Сотрудник
            provider: Учреждение
            start_time: Время начала
            end_time: Время окончания
            provider_location: Локация провайдера (опционально)
            
        Returns:
            bool: True если слот доступен
        """
        # 1. Проверяем существующие бронирования
        conflicting_bookings = Booking.objects.filter(
            employee=employee,
            start_time__lt=end_time,
            end_time__gt=start_time,
            status__name__in=['active', 'pending_confirmation']
        )
        
        # Если указана локация, фильтруем по ней
        if provider_location:
            conflicting_bookings = conflicting_bookings.filter(provider_location=provider_location)
        
        if conflicting_bookings.exists():
            return False
        
        # 2. Проверяем рабочее время учреждения
        if not BookingAvailabilityService._is_provider_working(provider, start_time, end_time, provider_location):
            return False
        
        # 3. Проверяем доступность сотрудника
        if not BookingAvailabilityService._is_employee_available(employee, start_time, end_time, provider_location):
            return False
        
        return True
    
    @staticmethod
    def get_available_slots(
        employee: Employee,
        provider: Provider,
        date: date,
        service: Service = None,
        service_duration_minutes: int = None,
        provider_location=None
    ) -> List[Dict]:
        """
        Получает доступные слоты для сотрудника на конкретную дату.
        
        Args:
            employee: Сотрудник
            provider: Учреждение
            date: Дата
            service: Услуга (для получения времени оказания)
            service_duration_minutes: Длительность услуги в минутах (если не указана услуга)
            provider_location: Локация провайдера (опционально)
            
        Returns:
            List[Dict]: Список доступных слотов
        """
        from providers.models import Schedule, ProviderLocationService
        
        # Определяем длительность услуги из локации провайдера
        if service and not service_duration_minutes:
            # Если указана локация, используем её
            if provider_location:
                try:
                    location_service = ProviderLocationService.objects.filter(
                        location=provider_location,
                        service=service,
                        is_active=True
                    ).first()
                    if location_service:
                        service_duration_minutes = location_service.duration_minutes
                        tech_break_minutes = getattr(location_service, 'tech_break_minutes', 0)
                        total_slot_duration = service_duration_minutes + tech_break_minutes
                    else:
                        service_duration_minutes = 60
                        total_slot_duration = 60
                except Exception:
                    service_duration_minutes = 60
                    total_slot_duration = 60
            else:
                # Используем первую найденную локацию провайдера с этой услугой
                try:
                    location_service = ProviderLocationService.objects.filter(
                        location__provider=provider,
                        location__is_active=True,
                        service=service,
                        is_active=True
                    ).first()
                    if location_service:
                        service_duration_minutes = location_service.duration_minutes
                        tech_break_minutes = getattr(location_service, 'tech_break_minutes', 0)
                        total_slot_duration = service_duration_minutes + tech_break_minutes
                    else:
                        service_duration_minutes = 60
                        total_slot_duration = 60
                except Exception:
                    service_duration_minutes = 60
                    total_slot_duration = 60
        
        if not service_duration_minutes:
            service_duration_minutes = 60
            total_slot_duration = 60
        
        # Получаем день недели
        weekday = date.weekday()
        
        # Получаем расписание сотрудника на этот день недели
        # Если указана локация, фильтруем по ней
        schedule_query = Schedule.objects.filter(
            employee=employee,
            day_of_week=weekday,
            is_working=True
        )
        
        if provider_location:
            schedule_query = schedule_query.filter(provider_location=provider_location)
        
        try:
            schedule = schedule_query.get()
        except Schedule.DoesNotExist:
            return []
        
        # Получаем существующие бронирования
        existing_bookings = Booking.objects.filter(
            employee=employee,
            start_time__date=date,
            status__name__in=['active', 'pending_confirmation']
        ).order_by('start_time')
        
        available_slots = []
        
        # Создаем datetime объекты для начала и конца рабочего дня
        work_start = timezone.make_aware(
            datetime.combine(date, schedule.start_time)
        )
        work_end = timezone.make_aware(
            datetime.combine(date, schedule.end_time)
        )
        
        # Учитываем перерыв
        if schedule.break_start and schedule.break_end:
            break_start = timezone.make_aware(
                datetime.combine(date, schedule.break_start)
            )
            break_end = timezone.make_aware(
                datetime.combine(date, schedule.break_end)
            )
        else:
            break_start = break_end = None
        
        # Разбиваем рабочий день на слоты
        current_time = work_start
        while current_time + timedelta(minutes=total_slot_duration) <= work_end:
            slot_end_time = current_time + timedelta(minutes=total_slot_duration)
            
            # Проверяем, что слот не пересекается с перерывом
            if not BookingAvailabilityService._slot_overlaps_break(current_time, slot_end_time, schedule):
                available_slots.append({
                    'start_time': current_time,
                    'end_time': slot_end_time,
                    'service_duration_minutes': service_duration_minutes,
                    'tech_break_minutes': tech_break_minutes,
                    'total_duration_minutes': total_slot_duration
                })
            
            current_time += timedelta(minutes=total_slot_duration)
        
        return available_slots
    
    @staticmethod
    def _is_provider_working(
        provider: Provider, 
        start_time: timezone.datetime, 
        end_time: timezone.datetime,
        provider_location: Optional[ProviderLocation] = None
    ) -> bool:
        """
        Проверяет, работает ли локация в указанное время.
        
        Args:
            provider: Учреждение
            start_time: Время начала
            end_time: Время окончания
            provider_location: Локация провайдера (обязательно для проверки расписания)
            
        Returns:
            bool: True если локация работает
        """
        # Если локация не указана, не можем проверить расписание
        if not provider_location:
            return True  # Если локация не указана, считаем что работает
        
        # Получаем день недели
        weekday = start_time.weekday()
        
        # Получаем рабочие часы локации
        try:
            location_schedule = LocationSchedule.objects.get(
                provider_location=provider_location,
                weekday=weekday
            )
            
            if location_schedule.is_closed:
                return False
            
            if not location_schedule.open_time or not location_schedule.close_time:
                return True  # Если время не указано, считаем что работает
            
            # Проверяем, что время попадает в рабочие часы
            start_time_only = start_time.time()
            end_time_only = end_time.time()
            
            return (location_schedule.open_time <= start_time_only and 
                    location_schedule.close_time >= end_time_only)
                    
        except LocationSchedule.DoesNotExist:
            # Если нет настроек, считаем что работает
            return True
    
    @staticmethod
    def _is_employee_available(
        employee: Employee, 
        start_time: timezone.datetime, 
        end_time: timezone.datetime,
        provider_location=None
    ) -> bool:
        """
        Проверяет, доступен ли сотрудник в указанное время.
        
        Args:
            employee: Сотрудник
            start_time: Время начала
            end_time: Время окончания
            provider_location: Локация провайдера (опционально, для фильтрации расписания)
            
        Returns:
            bool: True если сотрудник доступен
        """
        from providers.models import Schedule
        
        # Получаем день недели
        weekday = start_time.weekday()
        
        # Проверяем расписание сотрудника
        # Если указана локация, фильтруем по ней
        schedule_query = Schedule.objects.filter(
            employee=employee,
            day_of_week=weekday,
            is_working=True
        )
        
        if provider_location:
            schedule_query = schedule_query.filter(provider_location=provider_location)
        
        try:
            schedule = schedule_query.get()
            
            # Проверяем, попадает ли время в рабочие часы
            start_time_only = start_time.time()
            end_time_only = end_time.time()
            
            if not (schedule.start_time <= start_time_only and schedule.end_time >= end_time_only):
                return False
            
            # Проверяем перерыв
            if schedule.break_start and schedule.break_end:
                if (start_time_only < schedule.break_end and end_time_only > schedule.break_start):
                    return False
            
            return True
            
        except Schedule.DoesNotExist:
            # Если нет расписания, считаем что недоступен
            return False
    
    @staticmethod
    def get_employee_workload(employee: Employee, date: date) -> Dict:
        """
        Получает нагрузку сотрудника на конкретную дату.
        
        Args:
            employee: Сотрудник
            date: Дата
            
        Returns:
            Dict: Информация о нагрузке
        """
        bookings = Booking.objects.filter(
            employee=employee,
            start_time__date=date,
            status__name__in=['active', 'pending_confirmation']
        )
        
        total_hours = 0
        for booking in bookings:
            duration = booking.end_time - booking.start_time
            total_hours += duration.total_seconds() / 3600
        
        return {
            'total_bookings': bookings.count(),
            'total_hours': total_hours,
            'bookings': list(bookings.values('id', 'service__name', 'start_time', 'end_time'))
        } 


class EmployeeAutoBookingService:
    """
    Сервис для автоматического выбора и бронирования работника.
    
    Автоматически находит свободного работника для услуги в указанное время
    и создает бронирование с транзакционной защитой.
    """
    
    @staticmethod
    @transaction.atomic
    def auto_book_employee(
        user: User,
        pet: Pet,
        provider: Provider,
        service: Service,
        start_time: timezone.datetime,
        end_time: timezone.datetime,
        price: float,
        notes: str = ""
    ) -> Optional[Booking]:
        """
        Автоматически выбирает и бронирует работника для услуги.
        
        Args:
            user: Пользователь, создающий бронирование
            pet: Питомец
            provider: Учреждение
            service: Услуга
            start_time: Время начала
            end_time: Время окончания
            price: Стоимость
            notes: Примечания
            
        Returns:
            Booking: Созданное бронирование или None если работник не найден
        """
        # Находим подходящего работника
        employee = EmployeeAutoBookingService._find_available_employee(
            provider, service, start_time, end_time
        )
        
        if not employee:
            return None
        
        # Создаем бронирование с найденным работником
        return BookingTransactionService.create_booking(
            user=user,
            pet=pet,
            provider=provider,
            employee=employee,
            service=service,
            start_time=start_time,
            end_time=end_time,
            price=price,
            notes=notes
        )
    
    @staticmethod
    def _find_available_employee(
        provider: Provider,
        service: Service,
        start_time: timezone.datetime,
        end_time: timezone.datetime
    ) -> Optional[Employee]:
        """
        Находит доступного работника для услуги в указанное время.
        
        Args:
            provider: Учреждение
            service: Услуга
            start_time: Время начала
            end_time: Время окончания
            
        Returns:
            Employee: Подходящий работник или None
        """
        from providers.models import EmployeeProvider
        
        # Получаем работников учреждения, оказывающих данную услугу
        employees = EmployeeAutoBookingService._get_employees_for_service(
            provider, service
        )
        
        if not employees:
            return None
        
        # Проверяем доступность каждого работника
        available_employees = []
        
        for employee in employees:
            # Блокируем запись работника для проверки доступности
            with transaction.atomic():
                employee = Employee.objects.select_for_update().get(id=employee.id)
                
                # Проверяем доступность слота
                is_available = BookingAvailabilityService.check_slot_availability(
                    employee=employee,
                    provider=provider,
                    start_time=start_time,
                    end_time=end_time
                )
                
                if is_available:
                    # Рассчитываем загруженность работника
                    workload = EmployeeAutoBookingService._calculate_employee_workload(
                        employee, start_time.date()
                    )
                    
                    available_employees.append({
                        'employee': employee,
                        'workload': workload,
                        'rating': EmployeeAutoBookingService._get_employee_rating(employee)
                    })
        
        if not available_employees:
            return None
        
        # Выбираем работника по приоритету: наименьшая загруженность, затем лучший рейтинг
        available_employees.sort(key=lambda x: (x['workload'], -x['rating']))
        
        return available_employees[0]['employee']
    
    @staticmethod
    def _get_employees_for_service(provider: Provider, service: Service) -> List[Employee]:
        """
        Получает список работников учреждения, оказывающих данную услугу.
        
        Args:
            provider: Учреждение
            service: Услуга
            
        Returns:
            List[Employee]: Список работников
        """
        from providers.models import EmployeeProvider, ProviderLocationService
        
        # Проверяем, что провайдер может оказывать эту услугу (через available_category_levels)
        # Услуга должна быть в категориях уровня 0 провайдера или их потомках
        if not provider.available_category_levels.filter(
            id=service.id
        ).exists() and not provider.available_category_levels.filter(
            id__in=service.get_ancestors().values_list('id', flat=True)
        ).exists():
            # Проверяем через локации (fallback)
            if not ProviderLocationService.objects.filter(
                location__provider=provider,
                location__is_active=True,
                service=service,
                is_active=True
            ).exists():
                return []
        
        # Получаем активных работников учреждения
        employee_providers = EmployeeProvider.objects.filter(
            provider=provider,
            is_active=True,
            start_date__lte=timezone.now().date(),
            end_date__isnull=True
        ).select_related('employee')
        
        employees = []
        
        for ep in employee_providers:
            employee = ep.employee
            
            # Проверяем, назначен ли работник на эту услугу
            if hasattr(employee, 'services') and service in employee.services.all():
                employees.append(employee)
            elif not hasattr(employee, 'services'):
                # Если у работника нет ограничений по услугам, считаем что может оказывать любую
                employees.append(employee)
        
        return employees
    
    @staticmethod
    def _calculate_employee_workload(employee: Employee, date: date) -> int:
        """
        Рассчитывает загруженность работника на конкретную дату.
        
        Args:
            employee: Работник
            date: Дата
            
        Returns:
            int: Количество часов работы в этот день
        """
        # Получаем все бронирования работника на эту дату
        bookings = Booking.objects.filter(
            employee=employee,
            start_time__date=date,
            status__name__in=['active', 'pending_confirmation']
        )
        
        total_hours = 0
        
        for booking in bookings:
            duration = booking.end_time - booking.start_time
            total_hours += duration.total_seconds() / 3600  # Конвертируем в часы
        
        return total_hours
    
    @staticmethod
    def _get_employee_rating(employee: Employee) -> float:
        """
        Получает рейтинг работника.
        
        Args:
            employee: Работник
            
        Returns:
            float: Рейтинг работника (0.0 - 5.0)
        """
        # Здесь должна быть логика получения рейтинга работника
        # Пока возвращаем базовый рейтинг
        return getattr(employee, 'rating', 4.0)
    
    @staticmethod
    def get_available_employees_with_slots(
        provider: Provider,
        service: Service,
        date: date,
        service_duration_minutes: int = None
    ) -> List[Dict]:
        """
        Получает список доступных работников с их свободными слотами.
        
        Args:
            provider: Учреждение
            service: Услуга
            date: Дата
            service_duration_minutes: Длительность услуги в минутах
            
        Returns:
            List[Dict]: Список работников с их доступными слотами
        """
        employees = EmployeeAutoBookingService._get_employees_for_service(provider, service)
        
        result = []
        
        for employee in employees:
            # Получаем доступные слоты для работника
            available_slots = BookingAvailabilityService.get_available_slots(
                employee=employee,
                provider=provider,
                date=date,
                service=service,
                service_duration_minutes=service_duration_minutes
            )
            
            if available_slots:
                result.append({
                    'employee': employee,
                    'available_slots': available_slots,
                    'workload': EmployeeAutoBookingService._calculate_employee_workload(employee, date),
                    'rating': EmployeeAutoBookingService._get_employee_rating(employee)
                })
        
        # Сортируем по загруженности и рейтингу
        result.sort(key=lambda x: (x['workload'], -x['rating']))
        
        return result 