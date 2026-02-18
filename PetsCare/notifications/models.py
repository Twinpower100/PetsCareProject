"""
Модели для работы с уведомлениями.

Этот модуль содержит модели для:
1. Управления типами уведомлений
2. Создания шаблонов уведомлений
3. Настройки предпочтений пользователей
4. Отправки уведомлений
5. Управления напоминаниями
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from pets.models import Pet
from catalog.models import Service
# ProviderService удален - используйте ProviderLocationService
from push_notifications.models import GCMDevice, APNSDevice, WebPushDevice
from decouple import config

User = get_user_model()


class NotificationType(models.Model):
    """
    Модель для определения типов уведомлений в системе.
    Используется для категоризации уведомлений и управления настройками пользователей.
    
    Атрибуты:
        name (str): Название типа уведомления
        code (str): Уникальный код типа (используется в системе)
        description (str): Описание типа уведомления
        is_active (bool): Активен ли тип уведомления
        default_enabled (bool): Включен ли тип по умолчанию для новых пользователей
        is_required (bool): Обязательное уведомление (не настраивается пользователем)
    """
    name = models.CharField(_('Name'), max_length=100)
    name_en = models.CharField(
        _('Name (English)'),
        max_length=100,
        blank=True,
        help_text=_('Name in English')
    )
    name_ru = models.CharField(
        _('Name (Russian)'),
        max_length=100,
        blank=True,
        help_text=_('Name in Russian')
    )
    name_me = models.CharField(
        _('Name (Montenegrian)'),
        max_length=100,
        blank=True,
        help_text=_('Name in Montenegrian')
    )
    name_de = models.CharField(
        _('Name (German)'),
        max_length=100,
        blank=True,
        help_text=_('Name in German')
    )
    code = models.CharField(_('Code'), max_length=50, unique=True)
    description = models.TextField(_('Description'), blank=True)
    description_en = models.TextField(
        _('Description (English)'),
        blank=True,
        help_text=_('Description in English')
    )
    description_ru = models.TextField(
        _('Description (Russian)'),
        blank=True,
        help_text=_('Description in Russian')
    )
    description_me = models.TextField(
        _('Description (Montenegrian)'),
        blank=True,
        help_text=_('Description in Montenegrian')
    )
    description_de = models.TextField(
        _('Description (German)'),
        blank=True,
        help_text=_('Description in German')
    )
    is_active = models.BooleanField(_('Is Active'), default=True)
    default_enabled = models.BooleanField(_('Default Enabled'), default=True)
    is_required = models.BooleanField(_('Is Required'), default=False, 
                                    help_text=_('Required notifications cannot be disabled by users'))

    class Meta:
        verbose_name = _('Notification Type')
        verbose_name_plural = _('Notification Types')
        ordering = ['name']

    def __str__(self):
        """
        Возвращает строковое представление типа уведомления.
        Returns:
            str: Название типа уведомления
        """
        return self.get_localized_name()
    
    def get_localized_name(self, language_code=None):
        """
        Получает локализованное название типа уведомления.
        
        Args:
            language_code: Код языка (en, ru, me, de). Если None, используется текущий язык.
            
        Returns:
            str: Локализованное название
        """
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()
        
        if language_code == 'en' and self.name_en:
            return self.name_en
        elif language_code == 'ru' and self.name_ru:
            return self.name_ru
        elif language_code == 'me' and self.name_me:
            return self.name_me
        elif language_code == 'de' and self.name_de:
            return self.name_de
        else:
            return self.name
    
    def get_localized_description(self, language_code=None):
        """
        Получает локализованное описание типа уведомления.
        
        Args:
            language_code: Код языка (en, ru, me, de). Если None, используется текущий язык.
            
        Returns:
            str: Локализованное описание
        """
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()
        
        if language_code == 'en' and self.description_en:
            return self.description_en
        elif language_code == 'ru' and self.description_ru:
            return self.description_ru
        elif language_code == 'me' and self.description_me:
            return self.description_me
        elif language_code == 'de' and self.description_de:
            return self.description_de
        else:
            return self.description


class NotificationTemplate(models.Model):
    """
    Шаблон уведомления.
    Содержит текст и настройки для разных каналов доставки (email, push).
    """
    name = models.CharField(_('Name'), max_length=100)
    name_en = models.CharField(
        _('Name (English)'),
        max_length=100,
        blank=True,
        help_text=_('Name in English')
    )
    name_ru = models.CharField(
        _('Name (Russian)'),
        max_length=100,
        blank=True,
        help_text=_('Name in Russian')
    )
    name_me = models.CharField(
        _('Name (Montenegrian)'),
        max_length=100,
        blank=True,
        help_text=_('Name in Montenegrian')
    )
    name_de = models.CharField(
        _('Name (German)'),
        max_length=100,
        blank=True,
        help_text=_('Name in German')
    )
    code = models.CharField(_('Code'), max_length=50, unique=True)
    subject = models.CharField(_('Subject'), max_length=200, blank=True)
    subject_en = models.CharField(
        _('Subject (English)'),
        max_length=200,
        blank=True,
        help_text=_('Subject in English')
    )
    subject_ru = models.CharField(
        _('Subject (Russian)'),
        max_length=200,
        blank=True,
        help_text=_('Subject in Russian')
    )
    subject_me = models.CharField(
        _('Subject (Montenegrian)'),
        max_length=200,
        blank=True,
        help_text=_('Subject in Montenegrian')
    )
    subject_de = models.CharField(
        _('Subject (German)'),
        max_length=200,
        blank=True,
        help_text=_('Subject in German')
    )
    body = models.TextField(_('Body'))
    body_en = models.TextField(
        _('Body (English)'),
        blank=True,
        help_text=_('Body in English')
    )
    body_ru = models.TextField(
        _('Body (Russian)'),
        blank=True,
        help_text=_('Body in Russian')
    )
    body_me = models.TextField(
        _('Body (Montenegrian)'),
        blank=True,
        help_text=_('Body in Montenegrian')
    )
    body_de = models.TextField(
        _('Body (German)'),
        blank=True,
        help_text=_('Body in German')
    )
    html_body = models.TextField(_('HTML Body'), blank=True, 
                               help_text=_('HTML version of the email body'))
    html_body_en = models.TextField(
        _('HTML Body (English)'),
        blank=True,
        help_text=_('HTML Body in English')
    )
    html_body_ru = models.TextField(
        _('HTML Body (Russian)'),
        blank=True,
        help_text=_('HTML Body in Russian')
    )
    html_body_me = models.TextField(
        _('HTML Body (Montenegrian)'),
        blank=True,
        help_text=_('HTML Body in Montenegrian')
    )
    html_body_de = models.TextField(
        _('HTML Body (German)'),
        blank=True,
        help_text=_('HTML Body in German')
    )
    channel = models.CharField(
        _('Channel'),
        max_length=10,
        choices=[
            ('email', _('Email')),
            ('push', _('Push Notification')),
            ('in_app', _('In-App Notification')),
        ]
    )
    is_active = models.BooleanField(_('Is Active'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Notification Template')
        verbose_name_plural = _('Notification Templates')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_localized_name()} ({self.channel})"
    
    def get_localized_name(self, language_code=None):
        """
        Получает локализованное название шаблона уведомления.
        
        Args:
            language_code: Код языка (en, ru, me, de). Если None, используется текущий язык.
            
        Returns:
            str: Локализованное название
        """
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()
        
        if language_code == 'en' and self.name_en:
            return self.name_en
        elif language_code == 'ru' and self.name_ru:
            return self.name_ru
        elif language_code == 'me' and self.name_me:
            return self.name_me
        elif language_code == 'de' and self.name_de:
            return self.name_de
        else:
            return self.name
    
    def get_localized_subject(self, language_code=None):
        """
        Получает локализованную тему уведомления.
        
        Args:
            language_code: Код языка (en, ru, me, de). Если None, используется текущий язык.
            
        Returns:
            str: Локализованная тема
        """
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()
        
        if language_code == 'en' and self.subject_en:
            return self.subject_en
        elif language_code == 'ru' and self.subject_ru:
            return self.subject_ru
        elif language_code == 'me' and self.subject_me:
            return self.subject_me
        elif language_code == 'de' and self.subject_de:
            return self.subject_de
        else:
            return self.subject
    
    def get_localized_body(self, language_code=None):
        """
        Получает локализованное тело уведомления.
        
        Args:
            language_code: Код языка (en, ru, me, de). Если None, используется текущий язык.
            
        Returns:
            str: Локализованное тело
        """
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()
        
        if language_code == 'en' and self.body_en:
            return self.body_en
        elif language_code == 'ru' and self.body_ru:
            return self.body_ru
        elif language_code == 'me' and self.body_me:
            return self.body_me
        elif language_code == 'de' and self.body_de:
            return self.body_de
        else:
            return self.body
    
    def get_localized_html_body(self, language_code=None):
        """
        Получает локализованное HTML тело уведомления.
        
        Args:
            language_code: Код языка (en, ru, me, de). Если None, используется текущий язык.
            
        Returns:
            str: Локализованное HTML тело
        """
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()
        
        if language_code == 'en' and self.html_body_en:
            return self.html_body_en
        elif language_code == 'ru' and self.html_body_ru:
            return self.html_body_ru
        elif language_code == 'me' and self.html_body_me:
            return self.html_body_me
        elif language_code == 'de' and self.html_body_de:
            return self.html_body_de
        else:
            return self.html_body


class NotificationPreference(models.Model):
    """
    Модель для хранения настроек уведомлений пользователя.
    Определяет, какие типы уведомлений и через какие каналы получает пользователь.
    
    Атрибуты:
        user (ForeignKey): Связь с пользователем
        notification_type (ForeignKey): Связь с типом уведомления
        email_enabled (bool): Включены ли email-уведомления
        push_enabled (bool): Включены ли push-уведомления
        in_app_enabled (bool): Включены ли in-app уведомления
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_('User'),
        related_name='notification_preferences'
    )
    notification_type = models.ForeignKey(
        NotificationType,
        on_delete=models.CASCADE,
        verbose_name=_('Notification Type'),
        related_name='preferences'
    )
    email_enabled = models.BooleanField(_('Email Enabled'), default=True)
    push_enabled = models.BooleanField(_('Push Enabled'), default=True)
    in_app_enabled = models.BooleanField(_('In-App Enabled'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Notification Preference')
        verbose_name_plural = _('Notification Preferences')
        unique_together = ('user', 'notification_type')
        ordering = ['-created_at']

    def __str__(self):
        """
        Возвращает строковое представление настроек уведомлений.
        
        Returns:
            str: Строка в формате "Пользователь - Тип уведомления"
        """
        return f"{self.user} - {self.notification_type}"


class UserNotificationSettings(models.Model):
    """
    Детальные настройки уведомлений пользователя.
    Определяет каналы и время уведомления для каждого типа события.
    """
    NOTIFICATION_EVENTS = [
        ('booking', _('Booking')),
        ('cancellation', _('Cancellation')),
        ('pet_sitting', _('Pet Sitting')),
        ('appointment', _('Appointment')),
        ('system', _('System')),
    ]
    
    NOTIFICATION_CHANNELS = [
        ('email', _('Email')),
        ('push', _('Push Notification')),
        ('in_app', _('In-App Notification')),
    ]
    
    NOTIFICATION_TIMES = [
        ('instant', _('Instant')),
        ('30min', _('30 minutes before')),
        ('1hour', _('1 hour before')),
        ('2hours', _('2 hours before')),
        ('6hours', _('6 hours before')),
        ('12hours', _('12 hours before')),
        ('24hours', _('24 hours before')),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='detailed_notification_settings',
        verbose_name=_('User')
    )
    event_type = models.CharField(
        _('Event Type'),
        max_length=20,
        choices=NOTIFICATION_EVENTS
    )
    channel = models.CharField(
        _('Channel'),
        max_length=10,
        choices=NOTIFICATION_CHANNELS
    )
    notification_time = models.CharField(
        _('Notification Time'),
        max_length=10,
        choices=NOTIFICATION_TIMES,
        default='instant'
    )
    is_enabled = models.BooleanField(_('Is Enabled'), default=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('User Notification Setting')
        verbose_name_plural = _('User Notification Settings')
        unique_together = ['user', 'event_type', 'channel', 'notification_time']
        ordering = ['user', 'event_type', 'channel']

    def __str__(self):
        return f"{self.user} - {self.event_type} - {self.channel} - {self.notification_time}"


class Notification(models.Model):
    """
    Основная модель для уведомлений.
    Содержит информацию об уведомлении и методы для его отправки.
    
    Атрибуты:
        user (ForeignKey): Получатель уведомления
        pet (ForeignKey): Связанный питомец (опционально)
        notification_type (str): Тип уведомления
        title (str): Заголовок уведомления
        message (str): Текст уведомления
        priority (str): Приоритет (low/medium/high)
        channel (str): Канал доставки (email/push/in_app/all)
        is_read (bool): Прочитано ли уведомление
        scheduled_for (DateTime): Время отправки (для отложенных уведомлений)
        data (JSON): Дополнительные данные для уведомления
    """
    NOTIFICATION_TYPES = (
        ('reminder', _('Reminder')),
        ('appointment', _('Appointment')),
        ('medical', _('Medical')),
        ('system', _('System')),
        ('booking', _('Booking')),
        ('cancellation', _('Cancellation')),
        ('pet_sitting', _('Pet Sitting')),
        ('role_invite', _('Role Invite')),
        ('email_verification', _('Email Verification')),
        ('password_reset', _('Password Reset')),
    )

    PRIORITY_CHOICES = (
        ('low', _('Low')),
        ('medium', _('Medium')),
        ('high', _('High')),
    )

    CHANNEL_CHOICES = (
        ('email', _('Email')),
        ('push', _('Push')),
        ('in_app', _('In-App')),
        ('all', _('All Channels')),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_('User')
    )
    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('Pet')
    )
    notification_type = models.CharField(
        _('Notification Type'),
        max_length=20,
        choices=NOTIFICATION_TYPES
    )
    title = models.CharField(_('Title'), max_length=200)
    message = models.TextField(_('Message'))
    priority = models.CharField(
        _('Priority'),
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='medium'
    )
    channel = models.CharField(
        _('Channel'),
        max_length=10,
        choices=CHANNEL_CHOICES,
        default='all'
    )
    is_read = models.BooleanField(_('Is Read'), default=False)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    scheduled_for = models.DateTimeField(
        _('Scheduled For'),
        null=True,
        blank=True
    )
    sent_at = models.DateTimeField(
        _('Sent At'),
        null=True,
        blank=True
    )
    data = models.JSONField(_('Data'), default=dict, blank=True)

    class Meta:
        verbose_name = _('Notification')
        verbose_name_plural = _('Notifications')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['scheduled_for']),
            models.Index(fields=['notification_type']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление уведомления.
        
        Returns:
            str: Строка в формате "Пользователь - Тип уведомления"
        """
        return f"{self.user} - {self.notification_type}"

    def send(self):
        """
        Отправляет уведомление через выбранные каналы.
        В зависимости от настроек channel отправляет через email, push и/или in-app.
        """
        if self.channel in ['email', 'all']:
            self.send_email()
        if self.channel in ['push', 'all']:
            self.send_push()
        if self.channel in ['in_app', 'all']:
            self.send_in_app()
        
        # Отмечаем время отправки
        self.sent_at = timezone.now()
        self.save()

    def send_email(self):
        """
        Отправляет уведомление по email.
        Использует стандартную функцию Django send_mail.
        """
        from django.core.mail import send_mail
        from django.conf import settings
        
        if self.user.email:
            try:
                send_mail(
                    subject=self.title,
                    message=self.message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[self.user.email],
                    fail_silently=True,
                )
            except Exception as e:
                # Логируем ошибку отправки email
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send email notification {self.id}: {e}")

    def send_push(self):
        """
        Отправляет push-уведомление.
        Поддерживает три платформы:
        - Android (через FCM)
        - iOS (через APNS)
        - Web (через Web Push API)
        """
        try:
            # Android (FCM)
            android_devices = GCMDevice.objects.filter(user=self.user, active=True)
            if android_devices.exists():
                android_devices.send_message(
                    self.message,
                    title=self.title,
                    extra=self.data
                )

            # iOS (APNS)
            ios_devices = APNSDevice.objects.filter(user=self.user, active=True)
            if ios_devices.exists():
                ios_devices.send_message(
                    self.message,
                    title=self.title,
                    extra=self.data
                )

            # Web Push
            web_devices = WebPushDevice.objects.filter(user=self.user, active=True)
            if web_devices.exists():
                web_devices.send_message(
                    self.message,
                    title=self.title,
                    extra=self.data
                )
        except Exception as e:
            # Логируем ошибку отправки push-уведомления
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send push notification {self.id}: {e}")

    def send_in_app(self):
        """
        Отправляет in-app уведомление.
        Уведомление уже создано в базе данных, 
        клиент должен получить его через API.
        """
        # In-app уведомления не требуют дополнительной отправки,
        # так как они уже сохранены в базе данных
        # Клиент получает их через API
        pass


class Reminder(models.Model):
    """
    Модель для напоминаний о процедурах для питомцев.
    
    Атрибуты:
        pet (ForeignKey): Питомец, для которого создано напоминание
        service (ForeignKey): Услуга/процедура
        title (str): Название напоминания
        description (str): Описание напоминания
        procedure_type (str): Тип процедуры (обязательная/необязательная)
        frequency (str): Частота напоминаний
        interval_days (int): Интервал в днях для произвольной частоты
        start_date (Date): Дата начала напоминаний
        end_date (Date): Дата окончания напоминаний
        is_active (bool): Активно ли напоминание
        last_notified (DateTime): Время последнего уведомления
        next_notification (DateTime): Время следующего уведомления
    """
    FREQUENCY_CHOICES = (
        ('daily', _('Daily')),
        ('weekly', _('Weekly')),
        ('monthly', _('Monthly')),
        ('yearly', _('Yearly')),
        ('custom', _('Custom interval')),
    )

    PROCEDURE_TYPE_CHOICES = (
        ('mandatory', _('Mandatory')),
        ('optional', _('Optional')),
    )

    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        verbose_name=_('Pet')
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        verbose_name=_('Service')
    )
    title = models.CharField(_('Title'), max_length=200)
    description = models.TextField(_('Description'))
    procedure_type = models.CharField(
        _('Procedure Type'),
        max_length=10, 
        choices=PROCEDURE_TYPE_CHOICES, 
        default='optional',
        help_text=_('Procedure type (mandatory/optional)')
    )
    frequency = models.CharField(
        _('Frequency'),
        max_length=10,
        choices=FREQUENCY_CHOICES
    )
    interval_days = models.IntegerField(
        _('Interval Days'),
        null=True,
        blank=True
    )
    start_date = models.DateField(_('Start Date'))
    end_date = models.DateField(
        _('End Date'),
        null=True,
        blank=True
    )
    is_active = models.BooleanField(_('Is Active'), default=True)
    last_notified = models.DateTimeField(
        _('Last Notified'),
        null=True,
        blank=True
    )
    next_notification = models.DateTimeField(
        _('Next Notification'),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _('Reminder')
        verbose_name_plural = _('Reminders')
        ordering = ['next_notification']
        indexes = [
            models.Index(fields=['next_notification']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.title} - {self.pet.name}"

    def calculate_next_notification(self):
        """
        Рассчитывает дату следующего уведомления на основе частоты.
        """
        if not self.is_active:
            return None

        if self.frequency == 'daily':
            return timezone.now() + timezone.timedelta(days=1)
        elif self.frequency == 'weekly':
            return timezone.now() + timezone.timedelta(weeks=1)
        elif self.frequency == 'monthly':
            return timezone.now() + timezone.timedelta(days=30)
        elif self.frequency == 'yearly':
            return timezone.now() + timezone.timedelta(days=365)
        elif self.frequency == 'custom' and self.interval_days:
            return timezone.now() + timezone.timedelta(days=self.interval_days)
        return None

    def save(self, *args, **kwargs):
        """
        При сохранении обновляет дату следующего уведомления.
        """
        if self.is_active and not self.next_notification:
            self.next_notification = self.calculate_next_notification()
        super().save(*args, **kwargs)


class NotificationRule(models.Model):
    """
    Модель для гибких правил уведомлений.
    Позволяет администраторам создавать настраиваемые связи между событиями и уведомлениями.
    
    Атрибуты:
        event_type (str): Тип события (booking_created, booking_cancelled, etc.)
        condition (str): Условие срабатывания (Python-выражение)
        template (ForeignKey): Шаблон уведомления
        priority (str): Приоритет правила (low, medium, high, critical)
        channels (list): Каналы доставки (email, push, in_app)
        is_active (bool): Активность правила
        inheritance (str): Наследование (global, user_specific)
        created_by (ForeignKey): Создатель правила
        created_at (DateTime): Дата создания
        updated_at (DateTime): Дата обновления
    """
    EVENT_TYPES = [
        ('booking_created', _('Booking Created')),
        ('booking_cancelled', _('Booking Cancelled')),
        ('booking_updated', _('Booking Updated')),
        ('booking_completed', _('Booking Completed')),
        ('price_changed', _('Price Changed')),
        ('review_added', _('Review Added')),
        ('payment_received', _('Payment Received')),
        ('payment_failed', _('Payment Failed')),
        ('provider_blocked', _('Provider Blocked')),
        ('provider_unblocked', _('Provider Unblocked')),
        ('role_invite_sent', _('Role Invite Sent')),
        ('role_invite_accepted', _('Role Invite Accepted')),
        ('role_invite_expired', _('Role Invite Expired')),
        ('pet_sitting_request', _('Pet Sitting Request')),
        ('pet_sitting_accepted', _('Pet Sitting Accepted')),
        ('pet_sitting_completed', _('Pet Sitting Completed')),
    ]
    
    PRIORITY_CHOICES = [
        ('low', _('Low')),
        ('medium', _('Medium')),
        ('high', _('High')),
        ('critical', _('Critical')),
    ]
    
    INHERITANCE_CHOICES = [
        ('global', _('Global')),
        ('user_specific', _('User Specific')),
    ]
    
    event_type = models.CharField(
        _('Event Type'),
        max_length=50,
        choices=EVENT_TYPES,
        help_text=_('Type of event that triggers the notification')
    )
    condition = models.TextField(
        _('Condition'),
        help_text=_('Python expression for evaluating when to trigger the notification')
    )
    template = models.ForeignKey(
        NotificationTemplate,
        on_delete=models.CASCADE,
        verbose_name=_('Template'),
        help_text=_('Notification template to use')
    )
    priority = models.CharField(
        _('Priority'),
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='medium',
        help_text=_('Priority level of the notification')
    )
    channels = models.JSONField(
        _('Channels'),
        default=list,
        help_text=_('List of delivery channels (email, push, in_app)')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether the rule is active')
    )
    inheritance = models.CharField(
        _('Inheritance'),
        max_length=15,
        choices=INHERITANCE_CHOICES,
        default='global',
        help_text=_('Global rule or user-specific override')
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('User'),
        help_text=_('User for user-specific rules (null for global rules)')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('Created By'),
        related_name='created_notification_rules'
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    version = models.PositiveIntegerField(
        _('Version'),
        default=1,
        help_text=_('Version number for optimistic locking')
    )
    
    class Meta:
        verbose_name = _('Notification Rule')
        verbose_name_plural = _('Notification Rules')
        ordering = ['priority', '-created_at']
        indexes = [
            models.Index(fields=['event_type', 'is_active']),
            models.Index(fields=['priority']),
            models.Index(fields=['inheritance', 'user']),
        ]
        unique_together = [
            ('event_type', 'condition', 'template', 'inheritance', 'user'),
        ]
    
    def save(self, *args, **kwargs):
        """
        Переопределяет метод save для автоматического увеличения версии.
        """
        if self.pk:  # Обновление существующего правила
            self.version += 1
        super().save(*args, **kwargs)
    
    def __str__(self):
        """
        Возвращает строковое представление правила уведомления.
        Returns:
            str: Описание правила
        """
        if self.user:
            return f"{self.get_event_type_display()} -> {self.template.name} (User: {self.user})"
        return f"{self.get_event_type_display()} -> {self.template.name} (Global)"
    
    def evaluate_condition(self, context):
        """
        Оценивает условие правила с заданным контекстом.
        
        Args:
            context (dict): Контекст для оценки условия
            
        Returns:
            bool: True если условие выполняется, False иначе
            
        Raises:
            Exception: При ошибке в оценке условия
        """
        try:
            # Безопасная оценка Python-выражения
            # Ограничиваем доступ только к безопасным переменным
            safe_vars = {
                'user': context.get('user'),
                'booking': context.get('booking'),
                'service': context.get('service'),
                'provider': context.get('provider'),
                'pet': context.get('pet'),
                'amount': context.get('amount'),
                'hours_before_start': context.get('hours_before_start'),
                'price_increase_percent': context.get('price_increase_percent'),
                'True': True,
                'False': False,
                'None': None,
            }
            
            # Выполняем условие в безопасном контексте
            result = eval(self.condition, {"__builtins__": {}}, safe_vars)
            return bool(result)
            
        except Exception as e:
            # Логируем ошибку и возвращаем False
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error evaluating notification rule condition: {e}")
            return False
    
    def get_channels(self):
        """
        Возвращает список каналов доставки.
        Returns:
            list: Список каналов
        """
        if isinstance(self.channels, list):
            return self.channels
        return []
    
    def is_global(self):
        """
        Проверяет, является ли правило глобальным.
        Returns:
            bool: True если правило глобальное
        """
        return self.inheritance == 'global' and self.user is None
    
    def is_user_specific(self):
        """
        Проверяет, является ли правило пользовательским.
        Returns:
            bool: True если правило пользовательское
        """
        return self.inheritance == 'user_specific' and self.user is not None


class ReminderSettings(models.Model):
    """
    Модель для настройки индивидуальных напоминаний о бронированиях.
    Позволяет пользователям настраивать время и частоту напоминаний.
    
    Атрибуты:
        user (ForeignKey): Пользователь
        reminder_time_before_booking (int): Время напоминания до бронирования (в минутах)
        multiple_reminders (bool): Поддержка множественных напоминаний
        reminder_intervals (list): Интервалы для множественных напоминаний (в минутах)
        is_active (bool): Активны ли настройки
        created_at (DateTime): Дата создания
        updated_at (DateTime): Дата обновления
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_('User'),
        related_name='reminder_settings'
    )
    reminder_time_before_booking = models.PositiveIntegerField(
        _('Reminder Time Before Booking'),
        default=120,  # 2 часа по умолчанию
        help_text=_('Time in minutes before booking to send reminder')
    )
    multiple_reminders = models.BooleanField(
        _('Multiple Reminders'),
        default=False,
        help_text=_('Enable multiple reminders for the same booking')
    )
    reminder_intervals = models.JSONField(
        _('Reminder Intervals'),
        default=list,
        blank=True,
        help_text=_('List of reminder intervals in minutes (e.g., [1440, 120] for 1 day and 2 hours)')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether these reminder settings are active')
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Reminder Settings')
        verbose_name_plural = _('Reminder Settings')
        unique_together = ['user']
        ordering = ['-updated_at']

    def __str__(self):
        """
        Возвращает строковое представление настроек напоминаний.
        
        Returns:
            str: Описание настроек пользователя
        """
        return f"Reminder settings for {self.user.email}"

    def get_reminder_intervals(self):
        """
        Возвращает список интервалов напоминаний.
        Если множественные напоминания отключены, возвращает только основной интервал.
        
        Returns:
            list: Список интервалов в минутах
        """
        if self.multiple_reminders and self.reminder_intervals:
            return sorted(self.reminder_intervals, reverse=True)  # Сортируем по убыванию
        return [self.reminder_time_before_booking]

    def get_next_reminder_time(self, booking_start_time):
        """
        Вычисляет время следующего напоминания для бронирования.
        
        Args:
            booking_start_time (datetime): Время начала бронирования
            
        Returns:
            datetime: Время следующего напоминания
        """
        from django.utils import timezone
        now = timezone.now()
        
        intervals = self.get_reminder_intervals()
        
        for interval in intervals:
            reminder_time = booking_start_time - timezone.timedelta(minutes=interval)
            if reminder_time > now:
                return reminder_time
        
        return None

    def should_send_reminder(self, booking_start_time, last_reminder_time=None):
        """
        Проверяет, нужно ли отправить напоминание для бронирования.
        
        Args:
            booking_start_time (datetime): Время начала бронирования
            last_reminder_time (datetime): Время последнего напоминания
            
        Returns:
            bool: True если нужно отправить напоминание
        """
        from django.utils import timezone
        now = timezone.now()
        
        intervals = self.get_reminder_intervals()
        
        for interval in intervals:
            reminder_time = booking_start_time - timezone.timedelta(minutes=interval)
            
            # Проверяем, что время напоминания прошло, но не слишком давно
            if reminder_time <= now <= reminder_time + timezone.timedelta(minutes=15):
                # Если это множественное напоминание, проверяем, что не отправляли недавно
                if last_reminder_time:
                    time_since_last = now - last_reminder_time
                    if time_since_last < timezone.timedelta(minutes=30):
                        continue
                return True
        
        return False

    def save(self, *args, **kwargs):
        """
        Переопределяет метод сохранения для валидации данных.
        """
        # Убеждаемся, что основной интервал включен в множественные
        if self.multiple_reminders and self.reminder_intervals:
            if self.reminder_time_before_booking not in self.reminder_intervals:
                self.reminder_intervals.append(self.reminder_time_before_booking)
        
        super().save(*args, **kwargs)
