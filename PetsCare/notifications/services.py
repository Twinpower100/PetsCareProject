"""
Сервисы для работы с уведомлениями.

Этот модуль содержит сервисы для:
1. Централизованной отправки уведомлений
2. Управления настройками пользователей
3. Планирования отложенных уведомлений
4. Обработки ошибок и retry логики
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import timedelta
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from .models import (
    Notification, NotificationType, NotificationPreference, 
    UserNotificationSettings, NotificationTemplate
)
from push_notifications.models import GCMDevice, APNSDevice, WebPushDevice

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationService:
    """
    Центральный сервис для отправки уведомлений.
    
    Обеспечивает:
    - Единый интерфейс для отправки email, push и in-app уведомлений
    - Retry логику при ошибках отправки
    - Логирование всех попыток отправки
    - Очередь для массовых рассылок
    """
    
    def __init__(self):
        self.max_retries = 3
        self.retry_delay = 60  # секунды
    
    def send_notification(
        self,
        user: User,
        notification_type: str,
        title: str,
        message: str,
        channels: List[str] = None,
        priority: str = 'medium',
        pet=None,
        data: Dict[str, Any] = None,
        scheduled_for: Optional[timezone.datetime] = None
    ) -> Notification:
        """
        Отправляет уведомление пользователю.
        
        Args:
            user: Пользователь-получатель
            notification_type: Тип уведомления
            title: Заголовок уведомления
            message: Текст уведомления
            channels: Каналы доставки (email, push, in_app, all)
            priority: Приоритет уведомления
            pet: Связанный питомец (опционально)
            data: Дополнительные данные
            scheduled_for: Время отложенной отправки
            
        Returns:
            Notification: Созданное уведомление
        """
        try:
            with transaction.atomic():
                # Определяем каналы доставки
                if channels is None:
                    channels = self._get_user_channels(user, notification_type)
                
                # Создаем уведомление
                notification = Notification.objects.create(
                    user=user,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    priority=priority,
                    channel='all' if 'all' in channels else ','.join(channels),
                    pet=pet,
                    data=data or {},
                    scheduled_for=scheduled_for
                )
                
                # Если уведомление не отложенное, отправляем сразу
                if not scheduled_for or scheduled_for <= timezone.now():
                    self._send_notification(notification, channels)
                
                return notification
                
        except Exception as e:
            logger.error(f"Failed to create notification for user {user.id}: {e}")
            raise
    
    def send_bulk_notifications(
        self,
        users: List[User],
        notification_type: str,
        title: str,
        message: str,
        channels: List[str] = None,
        priority: str = 'medium',
        data: Dict[str, Any] = None
    ) -> List[Notification]:
        """
        Отправляет уведомления группе пользователей.
        
        Args:
            users: Список пользователей-получателей
            notification_type: Тип уведомления
            title: Заголовок уведомления
            message: Текст уведомления
            channels: Каналы доставки
            priority: Приоритет уведомления
            data: Дополнительные данные
            
        Returns:
            List[Notification]: Список созданных уведомлений
        """
        notifications = []
        
        for user in users:
            try:
                notification = self.send_notification(
                    user=user,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    channels=channels,
                    priority=priority,
                    data=data
                )
                notifications.append(notification)
            except Exception as e:
                logger.error(f"Failed to send bulk notification to user {user.id}: {e}")
                continue
        
        return notifications
    
    def _get_user_channels(self, user: User, notification_type: str) -> List[str]:
        """
        Получает каналы доставки для пользователя и типа уведомления.
        
        Args:
            user: Пользователь
            notification_type: Тип уведомления
            
        Returns:
            List[str]: Список каналов доставки
        """
        channels = []
        
        # Проверяем обязательные уведомления
        try:
            notification_type_obj = NotificationType.objects.get(code=notification_type)
            if notification_type_obj.is_required:
                return ['email', 'push', 'in_app']
        except NotificationType.DoesNotExist:
            pass
        
        # Получаем настройки пользователя
        preferences = NotificationPreference.objects.filter(
            user=user,
            notification_type__code=notification_type
        )
        
        for preference in preferences:
            if preference.email_enabled:
                channels.append('email')
            if preference.push_enabled:
                channels.append('push')
            if preference.in_app_enabled:
                channels.append('in_app')
        
        # Если настроек нет, используем все каналы
        if not channels:
            channels = ['email', 'push', 'in_app']
        
        return channels
    
    def _send_notification(self, notification: Notification, channels: List[str]):
        """
        Отправляет уведомление через указанные каналы.
        
        Args:
            notification: Уведомление для отправки
            channels: Каналы доставки
        """
        for attempt in range(self.max_retries):
            try:
                if 'email' in channels:
                    self._send_email(notification)
                
                if 'push' in channels:
                    self._send_push(notification)
                
                if 'in_app' in channels:
                    self._send_in_app(notification)
                
                # Отмечаем время отправки
                notification.sent_at = timezone.now()
                notification.save()
                
                logger.info(f"Successfully sent notification {notification.id}")
                break
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed for notification {notification.id}: {e}")
                
                if attempt < self.max_retries - 1:
                    # Ждем перед повторной попыткой
                    import time
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"Failed to send notification {notification.id} after {self.max_retries} attempts")
    
    def _send_email(self, notification: Notification):
        """
        Отправляет email уведомление.
        
        Args:
            notification: Уведомление для отправки
        """
        if not notification.user.email:
            logger.warning(f"User {notification.user.id} has no email address")
            return
        
        try:
            # Получаем HTML шаблон если есть
            html_message = None
            try:
                template = NotificationTemplate.objects.get(
                    code=f"{notification.notification_type}_email",
                    channel='email',
                    is_active=True
                )
                html_message = template.html_body
            except NotificationTemplate.DoesNotExist:
                pass
            
            send_mail(
                subject=notification.title,
                message=notification.message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.user.email],
                html_message=html_message,
                fail_silently=False,
            )
            
            logger.info(f"Email sent to {notification.user.email}")
            
        except Exception as e:
            logger.error(f"Failed to send email to {notification.user.email}: {e}")
            raise
    
    def _send_push(self, notification: Notification):
        """
        Отправляет push-уведомление.
        
        Args:
            notification: Уведомление для отправки
        """
        try:
            # Android (FCM)
            android_devices = GCMDevice.objects.filter(user=notification.user, active=True)
            if android_devices.exists():
                android_devices.send_message(
                    notification.message,
                    title=notification.title,
                    extra=notification.data
                )
                logger.info(f"Push notification sent to {android_devices.count()} Android devices")
            
            # iOS (APNS)
            ios_devices = APNSDevice.objects.filter(user=notification.user, active=True)
            if ios_devices.exists():
                ios_devices.send_message(
                    notification.message,
                    title=notification.title,
                    extra=notification.data
                )
                logger.info(f"Push notification sent to {ios_devices.count()} iOS devices")
            
            # Web Push
            web_devices = WebPushDevice.objects.filter(user=notification.user, active=True)
            if web_devices.exists():
                web_devices.send_message(
                    notification.message,
                    title=notification.title,
                    extra=notification.data
                )
                logger.info(f"Push notification sent to {web_devices.count()} Web devices")
                
        except Exception as e:
            logger.error(f"Failed to send push notification: {e}")
            raise
    
    def _send_in_app(self, notification: Notification):
        """
        Отправляет in-app уведомление.
        
        Args:
            notification: Уведомление для отправки
        """
        # In-app уведомления уже сохранены в базе данных
        # Клиент получает их через API
        logger.info(f"In-app notification {notification.id} ready for delivery")


class PreferenceService:
    """
    Сервис для управления настройками уведомлений пользователей.
    """
    
    def get_user_preferences(self, user: User) -> Dict[str, Any]:
        """
        Получает все настройки уведомлений пользователя.
        
        Args:
            user: Пользователь
            
        Returns:
            Dict[str, Any]: Настройки пользователя
        """
        preferences = {}
        
        # Получаем общие настройки
        general_prefs = NotificationPreference.objects.filter(user=user)
        for pref in general_prefs:
            preferences[pref.notification_type.code] = {
                'email_enabled': pref.email_enabled,
                'push_enabled': pref.push_enabled,
                'in_app_enabled': pref.in_app_enabled,
            }
        
        # Получаем детальные настройки
        detailed_prefs = UserNotificationSettings.objects.filter(user=user, is_enabled=True)
        for pref in detailed_prefs:
            if pref.event_type not in preferences:
                preferences[pref.event_type] = {}
            
            if pref.channel not in preferences[pref.event_type]:
                preferences[pref.event_type][pref.channel] = []
            
            preferences[pref.event_type][pref.channel].append(pref.notification_time)
        
        return preferences
    
    def update_user_preferences(
        self,
        user: User,
        event_type: str,
        channel: str,
        notification_time: str,
        is_enabled: bool
    ) -> UserNotificationSettings:
        """
        Обновляет настройки уведомлений пользователя.
        
        Args:
            user: Пользователь
            event_type: Тип события
            channel: Канал доставки
            notification_time: Время уведомления
            is_enabled: Включено ли уведомление
            
        Returns:
            UserNotificationSettings: Обновленные настройки
        """
        with transaction.atomic():
            settings_obj, created = UserNotificationSettings.objects.get_or_create(
                user=user,
                event_type=event_type,
                channel=channel,
                notification_time=notification_time,
                defaults={'is_enabled': is_enabled}
            )
            
            if not created:
                settings_obj.is_enabled = is_enabled
                settings_obj.save()
            
            return settings_obj
    
    def create_default_preferences(self, user: User):
        """
        Создает настройки по умолчанию для нового пользователя.
        
        Args:
            user: Пользователь
        """
        with transaction.atomic():
            # Создаем настройки для всех типов уведомлений
            notification_types = NotificationType.objects.filter(is_active=True)
            
            for notification_type in notification_types:
                NotificationPreference.objects.get_or_create(
                    user=user,
                    notification_type=notification_type,
                    defaults={
                        'email_enabled': notification_type.default_enabled,
                        'push_enabled': notification_type.default_enabled,
                        'in_app_enabled': notification_type.default_enabled,
                    }
                )
            
            # Создаем детальные настройки
            event_types = ['booking', 'cancellation', 'pet_sitting', 'appointment', 'system']
            channels = ['email', 'push', 'in_app']
            times = ['instant', '30min', '1hour', '2hours', '6hours', '12hours', '24hours']
            
            for event_type in event_types:
                for channel in channels:
                    for time in times:
                        UserNotificationSettings.objects.get_or_create(
                            user=user,
                            event_type=event_type,
                            channel=channel,
                            notification_time=time,
                            defaults={'is_enabled': True}
                        )


class SchedulerService:
    """
    Сервис для планирования отложенных уведомлений.
    """
    
    def schedule_notification(
        self,
        user: User,
        notification_type: str,
        title: str,
        message: str,
        scheduled_for: timezone.datetime,
        channels: List[str] = None,
        priority: str = 'medium',
        pet=None,
        data: Dict[str, Any] = None
    ) -> Notification:
        """
        Планирует отложенное уведомление.
        
        Args:
            user: Пользователь-получатель
            notification_type: Тип уведомления
            title: Заголовок уведомления
            message: Текст уведомления
            scheduled_for: Время отправки
            channels: Каналы доставки
            priority: Приоритет уведомления
            pet: Связанный питомец
            data: Дополнительные данные
            
        Returns:
            Notification: Запланированное уведомление
        """
        notification_service = NotificationService()
        
        return notification_service.send_notification(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            channels=channels,
            priority=priority,
            pet=pet,
            data=data,
            scheduled_for=scheduled_for
        )
    
    def process_scheduled_notifications(self):
        """
        Обрабатывает запланированные уведомления.
        Должен вызываться периодически через Celery.
        """
        now = timezone.now()
        scheduled_notifications = Notification.objects.filter(
            scheduled_for__lte=now,
            sent_at__isnull=True
        )
        
        notification_service = NotificationService()
        
        for notification in scheduled_notifications:
            try:
                channels = notification.channel.split(',') if notification.channel != 'all' else ['all']
                notification_service._send_notification(notification, channels)
                logger.info(f"Processed scheduled notification {notification.id}")
            except Exception as e:
                logger.error(f"Failed to process scheduled notification {notification.id}: {e}")
    
    def schedule_booking_reminders(self, booking):
        """
        Планирует напоминания о бронировании.
        
        Args:
            booking: Объект бронирования
        """
        user = booking.user
        pet = booking.pet
        start_time = booking.start_time
        
        # Получаем настройки пользователя
        preference_service = PreferenceService()
        preferences = preference_service.get_user_preferences(user)
        
        # Планируем напоминания на основе настроек
        if 'booking' in preferences:
            booking_prefs = preferences['booking']
            
            for channel, times in booking_prefs.items():
                for time in times:
                    if time == 'instant':
                        continue
                    
                    # Рассчитываем время напоминания
                    reminder_time = self._calculate_reminder_time(start_time, time)
                    
                    if reminder_time > timezone.now():
                        self.schedule_notification(
                            user=user,
                            notification_type='booking',
                            title=_('Booking Reminder'),
                            message=_('Reminder about your upcoming appointment'),
                            scheduled_for=reminder_time,
                            channels=[channel],
                            pet=pet,
                            data={'booking_id': booking.id}
                        )
    
    def _calculate_reminder_time(self, event_time: timezone.datetime, reminder_time: str) -> timezone.datetime:
        """
        Рассчитывает время напоминания на основе времени события.
        
        Args:
            event_time: Время события
            reminder_time: Время напоминания
            
        Returns:
            timezone.datetime: Время напоминания
        """
        time_mapping = {
            '30min': timedelta(minutes=30),
            '1hour': timedelta(hours=1),
            '2hours': timedelta(hours=2),
            '6hours': timedelta(hours=6),
            '12hours': timedelta(hours=12),
            '24hours': timedelta(hours=24),
        }
        
        if reminder_time in time_mapping:
            return event_time - time_mapping[reminder_time]
        
        return event_time 