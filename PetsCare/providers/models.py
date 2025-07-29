"""
Models for the providers module.

Этот модуль содержит модели для управления провайдерами услуг в системе PetsCare.

Основные компоненты:
1. Provider - учреждения (ветклиники, груминг-салоны и т.д.)
2. Employee - специалисты (ветеринары, грумеры и т.д.)
3. EmployeeProvider - связь между специалистами и учреждениями
4. Schedule - расписание работы специалистов
5. ProviderService - связь между учреждениями и услугами
6. ProviderSchedule - расписание работы учреждений
7. EmployeeWorkSlot - рабочие слоты сотрудников
8. SchedulePattern - шаблоны расписаний
9. PatternDay - описание рабочих дней в шаблоне

Особенности реализации:
- Использование геолокации для поиска ближайших провайдеров
- Система подтверждения сотрудников
- Гибкое управление расписаниями
- Поддержка различных типов рабочих слотов
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
from catalog.models import Service
import googlemaps
from geopy.distance import geodesic
from decimal import Decimal
from django.core.exceptions import ValidationError
from users.models import User
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Point


class Provider(models.Model):
    """
    Provider model (veterinary clinic, grooming salon, etc.).
    
    Основные характеристики:
    - Название и описание учреждения
    - Контактная информация
    - Географические координаты
    - Рейтинг и статус активности
    
    Технические особенности:
    - Автоматическое геокодирование адреса
    - Поиск ближайших учреждений
    - Управление статусом активности
    - Оптимизированные индексы для поиска
    
    Примечание:
    При сохранении модели автоматически выполняется геокодирование адреса
    для получения координат через Google Maps API.
    """
    name = models.CharField(
        _('Name'),
        max_length=200,
        help_text=_('Name of the provider')
    )
    description = models.TextField(
        _('Description'),
        help_text=_('Description of the provider')
    )
    # Старое поле адреса (для обратной совместимости)
    address = models.CharField(
        _('Address'),
        max_length=200,
        blank=True,
        help_text=_('Legacy address field for backward compatibility')
    )
    
    # Новая структурированная модель адреса
    structured_address = models.ForeignKey(
        'geolocation.Address',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='providers',
        verbose_name=_('Structured Address'),
        help_text=_('Structured address with validation')
    )
    
    # Координаты (теперь получаются из структурированного адреса)
    point = gis_models.PointField(srid=4326, verbose_name=_('Point'), null=True, blank=True)
    
    phone_number = models.CharField(
        _('Phone Number'),
        max_length=20,
        help_text=_('Contact phone number')
    )
    email = models.EmailField(
        _('Email'),
        help_text=_('Contact email')
    )
    website = models.URLField(
        _('Website'),
        blank=True,
        help_text=_('Provider website')
    )
    logo = models.ImageField(
        _('Logo'),
        upload_to='providers/logos/%Y/%m/%d/',
        blank=True,
        null=True,
        help_text=_('Provider logo')
    )
    rating = models.FloatField(
        _('Rating'),
        default=0.0,
        help_text=_('Provider rating')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether the provider is currently active')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )
    
    # Добавляем связь с доступными уровнями категорий
    available_category_levels = models.ManyToManyField(
        'catalog.Service',
        related_name='available_providers',
        verbose_name=_('Available Category Levels'),
        help_text=_('Category levels available for this provider')
    )
    
    # Настройки блокировки
    exclude_from_blocking_checks = models.BooleanField(
        _('Exclude From Blocking Checks'),
        default=False,
        help_text=_('Whether this provider should be excluded from automatic blocking checks')
    )
    blocking_exclusion_reason = models.TextField(
        _('Blocking Exclusion Reason'),
        blank=True,
        help_text=_('Reason for excluding this provider from blocking checks')
    )

    class Meta:
        verbose_name = _('Provider')
        verbose_name_plural = _('Providers')
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['address']),
            models.Index(fields=['rating']),
            models.Index(fields=['is_active']),
            gis_models.Index(fields=['point'], name='idx_provider_point'),
            models.Index(fields=['exclude_from_blocking_checks']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление учреждения.
        
        Returns:
            str: Название учреждения
        """
        return self.name

    def save(self, *args, **kwargs):
        """
        Сохраняет модель и выполняет геокодирование адреса.
        
        Примечание:
        Приоритет отдается структурированному адресу. Если он указан и валидирован,
        координаты берутся из него. Иначе используется старое поле address.
        """
        # Если есть структурированный адрес и он валидирован, берем координаты из него
        if self.structured_address and self.structured_address.is_validated:
            if self.structured_address.point:
                self.point = self.structured_address.point
        # Иначе используем старое поле address для обратной совместимости
        elif not self.point and self.address:
            try:
                # Инициализация клиента Google Maps
                gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)
                
                # Геокодирование адреса
                geocode_result = gmaps.geocode(self.address)
                
                if geocode_result:
                    # Получение координат из результата
                    location = geocode_result[0]['geometry']['location']
                    self.point = Point(location['lng'], location['lat'], srid=4326)
            except Exception as e:
                # В случае ошибки сохраняем без координат
                print(f"Geocoding error: {e}")
        
        super().save(*args, **kwargs)

    def distance_to(self, lat, lon):
        """
        Вычисляет расстояние от учреждения до указанной точки.
        
        Параметры:
            lat (float): Широта целевой точки
            lon (float): Долгота целевой точки
            
        Returns:
            float: Расстояние в километрах или None, если координаты не указаны
        """
        if not self.point:
            return None
        
        target_point = Point(lon, lat, srid=4326)
        return self.point.distance(target_point) * 111.32  # Convert to km

    @classmethod
    def find_nearest(cls, lat, lon, radius=10, limit=10):
        """
        Находит ближайшие учреждения в указанном радиусе.
        
        Параметры:
            lat (float): Широта центра поиска
            lon (float): Долгота центра поиска
            radius (float): Радиус поиска в километрах
            limit (int): Максимальное количество результатов
            
        Returns:
            list: Список кортежей (provider, distance) с ближайшими учреждениями
        """
        from django.contrib.gis.geos import Point
        from django.contrib.gis.db.models.functions import Distance
        
        search_point = Point(lon, lat)
        
        # Используем PostGIS для поиска ближайших учреждений
        providers = cls.objects.filter(
            is_active=True,
            point__isnull=False
        ).filter(
            point__distance_lte=(search_point, radius * 1000)  # radius в метрах
        ).annotate(
            distance=Distance('point', search_point)
        ).order_by('distance')[:limit]
        
        # Возвращаем список кортежей (provider, distance)
        return [(provider, provider.distance.m) for provider in providers]

    def get_available_categories(self):
        """
        Получает все доступные категории для провайдера.
        """
        return self.available_category_levels.all()
    
    def get_available_services(self):
        """
        Получает все доступные услуги для провайдера.
        """
        return Service.objects.filter(
            category__in=self.get_available_categories()
        )


class Employee(models.Model):
    """
    Employee model (veterinarian, groomer, etc.).
    
    Основные характеристики:
    - Связь с пользовательским аккаунтом
    - Список учреждений, где работает
    - Должность и биография
    - Специализации и услуги
    
    Технические особенности:
    - Мягкое удаление через флаг is_active
    - Автоматическое отслеживание времени создания и обновления
    - Связь с пользователем через OneToOneField
    - Связь с учреждениями через ManyToManyField
    
    Примечание:
    При деактивации сотрудника все связанные записи должны быть обработаны
    через сигналы Django (см. signals.py).
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='employee_profile',
        help_text=_('User account of the employee')
    )
    providers = models.ManyToManyField(
        Provider,
        through='EmployeeProvider',
        verbose_name=_('Providers'),
        related_name='employees',
        help_text=_('Providers this employee works for')
    )
    position = models.CharField(
        _('Position'),
        max_length=100,
        help_text=_('Employee position')
    )
    bio = models.TextField(
        _('Bio'),
        blank=True,
        help_text=_('Employee biography')
    )
    photo = models.ImageField(
        _('Photo'),
        upload_to='employees/photos/%Y/%m/%d/',
        blank=True,
        null=True,
        help_text=_('Employee photo')
    )
    services = models.ManyToManyField(
        Service,
        verbose_name=_('Services'),
        help_text=_('Services this employee can provide')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether the employee is currently active')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Employee')
        verbose_name_plural = _('Employees')
        ordering = ['user__last_name', 'user__first_name']
        indexes = [
            models.Index(fields=['position']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление сотрудника.
        
        Returns:
            str: Полное имя сотрудника
        """
        return self.user.get_full_name()

    def can_view_pet_medical_history(self):
        """
        Проверяет, может ли сотрудник просматривать медицинскую историю питомца.
        
        Returns:
            bool: True, если сотрудник имеет право просматривать историю
        """
        return self.specializations.filter(
            permissions__contains={'view_medical_history': True}
        ).exists()

    def can_edit_pet_medical_history(self):
        """
        Проверяет, может ли сотрудник редактировать медицинскую историю питомца.
        
        Returns:
            bool: True, если сотрудник имеет право редактировать историю
        """
        return self.specializations.filter(
            permissions__contains={'edit_medical_history': True}
        ).exists()

    def can_perform_grooming(self):
        """
        Проверяет, может ли сотрудник выполнять груминг.
        
        Returns:
            bool: True, если сотрудник имеет право выполнять груминг
        """
        return self.specializations.filter(
            permissions__contains={'perform_grooming': True}
        ).exists()

    def can_schedule_appointments(self):
        """
        Проверяет, может ли сотрудник планировать встречи.
        
        Returns:
            bool: True, если сотрудник имеет право планировать встречи
        """
        return self.specializations.filter(
            permissions__contains={'schedule_appointments': True}
        ).exists()

    def has_confirmed_provider(self):
        """
        Проверяет, есть ли у сотрудника подтвержденное учреждение.
        
        Returns:
            bool: True, если у сотрудника есть подтвержденное учреждение
        """
        return self.employeeprovider_set.filter(
            is_confirmed=True,
            end_date__isnull=True
        ).exists()

    def get_active_providers(self):
        """
        Возвращает список активных учреждений сотрудника.
        
        Returns:
            QuerySet: Список активных учреждений
        """
        return self.providers.filter(
            employeeprovider_set__end_date__isnull=True
        )

    def deactivate(self, by_user):
        """
        Деактивирует сотрудника.
        
        Параметры:
            by_user (User): Пользователь, выполняющий деактивацию
            
        Примечание:
        При деактивации сотрудника все связанные записи должны быть обработаны
        через сигналы Django (см. signals.py).
        """
        if not by_user.is_system_admin():
            raise ValueError(_("Only system admin can deactivate employees"))
        
        self.is_active = False
        self.save()


class EmployeeJoinRequest(models.Model):
    """
    Employee join request model.
    
    Основные характеристики:
    - Связь с пользователем и учреждением
    - Должность и комментарий
    - Статус заявки
    - Временные метки
    
    Технические особенности:
    - Автоматическое отслеживание времени создания и обновления
    - Управление статусом заявки
    - Связь с пользователем и учреждением через ForeignKey
    
    Примечание:
    Заявка может быть в одном из трех состояний:
    - pending (ожидает рассмотрения)
    - approved (одобрена)
    - rejected (отклонена)
    """
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='join_requests',
        verbose_name=_('User')
    )
    provider = models.ForeignKey(
        'Provider',
        on_delete=models.CASCADE,
        related_name='join_requests',
        verbose_name=_('Provider')
    )
    position = models.CharField(
        _('Position'),
        max_length=255
    )
    comment = models.TextField(
        _('Comment'),
        blank=True
    )
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=[
            ('pending', _('Pending')),
            ('approved', _('Approved')),
            ('rejected', _('Rejected'))
        ],
        default='pending'
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Employee Join Request')
        verbose_name_plural = _('Employee Join Requests')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление заявки.
        
        Returns:
            str: Строковое представление заявки
        """
        return f"{self.user} - {self.provider} ({self.status})"


class EmployeeProvider(models.Model):
    """
    Employee-Provider relationship model.
    
    Основные характеристики:
    - Связь с сотрудником и учреждением
    - Период работы
    - Статус менеджера
    - Подтверждение сотрудника
    
    Технические особенности:
    - Уникальная связь по сотруднику, учреждению и дате начала
    - Автоматическое отслеживание времени создания и обновления
    - Управление подтверждением сотрудника
    
    Примечание:
    Эта модель используется для отслеживания истории работы сотрудника
    в различных учреждениях.
    """
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        verbose_name=_('Employee'),
        related_name='employeeprovider_set'
    )
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        verbose_name=_('Provider'),
        related_name='employeeprovider_set'
    )
    start_date = models.DateField(
        _('Start Date'),
        help_text=_('Date when employee started working at this provider')
    )
    end_date = models.DateField(
        _('End Date'),
        null=True,
        blank=True,
        help_text=_('Date when employee stopped working at this provider')
    )
    is_manager = models.BooleanField(
        _('Is Manager'),
        default=False,
        help_text=_('Whether this employee is a manager at this provider')
    )
    is_confirmed = models.BooleanField(
        _('Is Confirmed'),
        default=False,
        help_text=_('Confirmed by employee')
    )
    confirmation_requested_at = models.DateTimeField(
        _('Confirmation Requested At'),
        null=True,
        blank=True,
        help_text=_('When the confirmation was requested')
    )
    confirmed_at = models.DateTimeField(
        _('Confirmed At'),
        null=True,
        blank=True,
        help_text=_('When the confirmation was received')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Employee Provider')
        verbose_name_plural = _('Employee Providers')
        unique_together = ['employee', 'provider', 'start_date']
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['start_date']),
            models.Index(fields=['end_date']),
            models.Index(fields=['is_confirmed']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление связи.
        
        Returns:
            str: Строковое представление связи
        """
        return f"{self.employee} - {self.provider} ({self.start_date})"

    def is_currently_employed(self):
        """
        Проверяет, работает ли сотрудник в учреждении в настоящее время.
        
        Returns:
            bool: True, если сотрудник работает в учреждении
        """
        return self.end_date is None

    def request_confirmation(self):
        """
        Запрашивает подтверждение сотрудника.
        
        Примечание:
        Устанавливает время запроса подтверждения.
        """
        self.confirmation_requested_at = timezone.now()
        self.save()

    def confirm(self):
        """
        Подтверждает сотрудника.
        
        Примечание:
        Устанавливает время подтверждения и статус подтверждения.
        """
        self.is_confirmed = True
        self.confirmed_at = timezone.now()
        self.save()

    def can_work(self):
        """
        Проверяет, может ли сотрудник работать в учреждении.
        
        Returns:
            bool: True, если сотрудник может работать
        """
        return self.is_currently_employed() and self.is_confirmed


class Schedule(models.Model):
    """
    Employee schedule model.
    
    Основные характеристики:
    - Связь с сотрудником
    - День недели
    - Время начала и окончания работы
    - Перерыв
    
    Технические особенности:
    - Уникальная связь по сотруднику и дню недели
    - Валидация времени работы
    - Управление статусом рабочего дня
    
    Примечание:
    Расписание используется для определения доступности
    специалиста в конкретные дни недели.
    """
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        verbose_name=_('Employee'),
        related_name='schedules',
        help_text=_('Employee this schedule belongs to')
    )
    day_of_week = models.PositiveSmallIntegerField(
        _('Day Of Week'),
        choices=[
            (0, _('Monday')),
            (1, _('Tuesday')),
            (2, _('Wednesday')),
            (3, _('Thursday')),
            (4, _('Friday')),
            (5, _('Saturday')),
            (6, _('Sunday')),
        ],
        help_text=_('Day of the week')
    )
    start_time = models.TimeField(
        _('Start Time'),
        help_text=_('Start time of the working day')
    )
    end_time = models.TimeField(
        _('End Time'),
        help_text=_('End time of the working day')
    )
    break_start = models.TimeField(
        _('Break Start'),
        null=True,
        blank=True,
        help_text=_('Start time of the break')
    )
    break_end = models.TimeField(
        _('Break End'),
        null=True,
        blank=True,
        help_text=_('End time of the break')
    )
    is_working = models.BooleanField(
        _('Is Working'),
        default=True,
        help_text=_('Whether the employee works on this day')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Schedule')
        verbose_name_plural = _('Schedules')
        ordering = ['employee', 'day_of_week']
        unique_together = ['employee', 'day_of_week']
        indexes = [
            models.Index(fields=['day_of_week']),
            models.Index(fields=['is_working']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление расписания.
        
        Returns:
            str: Строковое представление расписания
        """
        return f"{self.employee} - {self.get_day_of_week_display()}"

    def clean(self):
        """
        Проверяет корректность времени работы.
        
        Raises:
            ValidationError: Если время работы некорректно
        """
        if self.start_time >= self.end_time:
            raise ValidationError(_("Start time must be before end time"))
        
        if self.break_start and self.break_end:
            if self.break_start >= self.break_end:
                raise ValidationError(_("Break start time must be before break end time"))
            if not (self.start_time <= self.break_start < self.break_end <= self.end_time):
                raise ValidationError(_("Break must be within working hours"))
        
        # Проверяем, что расписание сотрудника не выходит за рамки рабочего времени учреждения
        try:
            provider_schedule = ProviderSchedule.objects.get(
                provider__employees=self.employee,
                weekday=self.day_of_week
            )
            
            if not provider_schedule.is_closed:
                if provider_schedule.open_time and self.start_time < provider_schedule.open_time:
                    raise ValidationError(
                        _("Employee start time cannot be earlier than provider opening time")
                    )
                if provider_schedule.close_time and self.end_time > provider_schedule.close_time:
                    raise ValidationError(
                        _("Employee end time cannot be later than provider closing time")
                    )
        except ProviderSchedule.DoesNotExist:
            # Если расписание учреждения не настроено, пропускаем проверку
            pass

    def save(self, *args, **kwargs):
        """
        Сохраняет модель и проверяет корректность.
        
        Примечание:
        Перед сохранением выполняется проверка корректности времени работы.
        """
        self.clean()
        super().save(*args, **kwargs)


class ProviderService(models.Model):
    """
    Provider-Service relationship model.
    
    Основные характеристики:
    - Связь с учреждением и услугой
    - Цена услуги в учреждении
    - Статус активности
    
    Технические особенности:
    - Уникальная связь по учреждению и услуге
    - Автоматическое отслеживание времени создания и обновления
    - Управление статусом активности
    
    Примечание:
    Эта модель используется для управления ценами на услуги
    в конкретных учреждениях.
    """
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        verbose_name=_('Provider'),
        related_name='provider_services',
        help_text=_('Provider offering this service')
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        verbose_name=_('Service'),
        related_name='provider_services',
        help_text=_('Service being offered')
    )
    price = models.DecimalField(
        _('Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Price of the service at this provider')
    )
    duration_minutes = models.PositiveIntegerField(
        _('Duration In Minutes'),
        help_text=_('Duration of the service in minutes for this provider')
    )
    tech_break_minutes = models.PositiveIntegerField(
        _('Technical Break Minutes'),
        default=0,
        help_text=_('Technical break time in minutes after the service (for cleaning, preparation, etc.)')
    )
    base_price = models.DecimalField(
        _('Base Price'),
        max_digits=10,
        decimal_places=2,
        help_text=_('Base price for the service at this provider')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether this service is currently available')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Provider Service')
        verbose_name_plural = _('Provider Services')
        ordering = ['provider', 'service']
        unique_together = ['provider', 'service']
        indexes = [
            models.Index(fields=['provider', 'service']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление связи.
        
        Returns:
            str: Строковое представление связи
        """
        return f"{self.provider} - {self.service}"


class ProviderSchedule(models.Model):
    """
    Provider schedule model.
    
    Основные характеристики:
    - Связь с учреждением
    - День недели
    - Время открытия и закрытия
    - Статус выходного дня
    
    Технические особенности:
    - Уникальная связь по учреждению и дню недели
    - Управление статусом выходного дня
    - Автоматическое отслеживание времени создания и обновления
    
    Примечание:
    Расписание используется для определения часов работы
    учреждения в конкретные дни недели.
    """
    provider = models.ForeignKey(
        'Provider',
        on_delete=models.CASCADE,
        related_name='schedules'
    )
    weekday = models.IntegerField(
        choices=[
            (0, _('Monday')),
            (1, _('Tuesday')),
            (2, _('Wednesday')),
            (3, _('Thursday')),
            (4, _('Friday')),
            (5, _('Saturday')),
            (6, _('Sunday'))
        ],
        verbose_name=_('Day Of Week')
    )
    open_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name=_('Open Time')
    )
    close_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name=_('Close Time')
    )
    is_closed = models.BooleanField(
        _('Is Closed'),
        default=False,
        help_text=_('Whether the provider is closed on this day')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        unique_together = ('provider', 'weekday')
        verbose_name = _('Provider Schedule')
        verbose_name_plural = _('Provider Schedules')
        indexes = [
            models.Index(fields=['weekday']),
            models.Index(fields=['is_closed']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление расписания.
        
        Returns:
            str: Строковое представление расписания
        """
        return f"{self.provider} - {self.get_weekday_display()}"


class EmployeeWorkSlot(models.Model):
    """
    Employee work slot model.
    
    Основные характеристики:
    - Связь с сотрудником
    - Дата и время работы
    - Тип слота
    - Комментарий
    
    Технические особенности:
    - Различные типы слотов (работа, отпуск, больничный и т.д.)
    - Валидация времени работы
    - Управление доступностью
    
    Примечание:
    Эта модель используется для управления конкретными рабочими
    интервалами сотрудника в определенные даты.
    """
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='work_slots'
    )
    date = models.DateField(
        verbose_name=_('Date')
    )
    start_time = models.TimeField(
        verbose_name=_('Start Time')
    )
    end_time = models.TimeField(
        verbose_name=_('End Time')
    )
    slot_type = models.CharField(
        max_length=20,
        choices=[
            ('work', _('Work')),
            ('vacation', _('Vacation')),
            ('sick', _('Sick Leave')),
            ('dayoff', _('Day Off')),
            ('substitution', _('Substitution')),
        ],
        default='work',
        verbose_name=_('Slot Type')
    )
    comment = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Comment')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Employee Work Slot')
        verbose_name_plural = _('Employee Work Slots')
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['slot_type']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление слота.
        
        Returns:
            str: Строковое представление слота
        """
        return f"{self.employee} - {self.date} ({self.slot_type})"

    def clean(self):
        """
        Проверяет корректность времени работы.
        
        Raises:
            ValidationError: Если время работы некорректно
        """
        if self.start_time >= self.end_time:
            raise ValidationError(_("Start time must be before end time"))

    def save(self, *args, **kwargs):
        """
        Сохраняет модель и проверяет корректность.
        
        Примечание:
        Перед сохранением выполняется проверка корректности времени работы.
        """
        self.clean()
        super().save(*args, **kwargs)

    def is_available(self, start_time, end_time):
        """
        Проверяет, доступен ли слот в указанное время.
        
        Параметры:
            start_time (time): Время начала
            end_time (time): Время окончания
            
        Returns:
            bool: True, если слот доступен
        """
        if self.slot_type != 'work':
            return False
        
        return (
            self.start_time <= start_time and
            self.end_time >= end_time
        )


class SchedulePattern(models.Model):
    """
    Schedule pattern model.
    
    Основные характеристики:
    - Название и описание шаблона
    - Связь с учреждением
    - Дни недели в шаблоне
    
    Технические особенности:
    - Управление типовыми расписаниями
    - Автоматическое отслеживание времени создания и обновления
    - Связь с днями недели через ForeignKey
    
    Примечание:
    Шаблоны используются для быстрого создания типовых
    расписаний для сотрудников.
    """
    name = models.CharField(
        max_length=100,
        verbose_name=_('Name')
    )
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='schedule_patterns'
    )
    description = models.TextField(
        blank=True,
        verbose_name=_('Description')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Schedule Pattern')
        verbose_name_plural = _('Schedule Patterns')
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление шаблона.
        
        Returns:
            str: Строковое представление шаблона
        """
        return f"{self.name} ({self.provider})"


class PatternDay(models.Model):
    """
    Pattern day model.
    
    Основные характеристики:
    - Связь с шаблоном
    - День недели
    - Время начала и окончания работы
    - Статус выходного дня
    
    Технические особенности:
    - Уникальная связь по шаблону и дню недели
    - Управление статусом выходного дня
    - Автоматическое отслеживание времени создания и обновления
    
    Примечание:
    Эта модель используется для определения рабочих часов
    в конкретные дни недели в рамках шаблона.
    """
    pattern = models.ForeignKey(
        SchedulePattern,
        on_delete=models.CASCADE,
        related_name='days'
    )
    weekday = models.IntegerField(
        choices=[
            (0, _('Monday')),
            (1, _('Tuesday')),
            (2, _('Wednesday')),
            (3, _('Thursday')),
            (4, _('Friday')),
            (5, _('Saturday')),
            (6, _('Sunday'))
        ],
        verbose_name=_('Day Of Week')
    )
    start_time = models.TimeField(
        null=True,
        blank=True
    )
    end_time = models.TimeField(
        null=True,
        blank=True
    )
    is_day_off = models.BooleanField(
        _('Is Day Off'),
        default=False,
        help_text=_('Whether this is a day off')
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Pattern Day')
        verbose_name_plural = _('Pattern Days')
        unique_together = ('pattern', 'weekday')
        ordering = ['pattern', 'weekday']
        indexes = [
            models.Index(fields=['weekday']),
            models.Index(fields=['is_day_off']),
        ]

    def __str__(self):
        """
        Возвращает строковое представление дня.
        
        Returns:
            str: Строковое представление дня
        """
        return f"{self.pattern} - {self.get_weekday_display()}"


class ManagerTransferInvite(models.Model):
    """
    Модель приглашения на передачу полномочий менеджера учреждения.

    from_manager — сотрудник, инициирующий передачу прав
    to_employee — сотрудник, которому передают права
    provider — учреждение
    is_accepted — приглашение принято
    is_declined — приглашение отклонено
    created_at, accepted_at, declined_at — временные метки
    """
    from_manager = models.ForeignKey(
        'Employee', related_name='sent_manager_invites', on_delete=models.CASCADE,
        verbose_name=_('From manager')
    )
    to_employee = models.ForeignKey(
        'Employee', related_name='received_manager_invites', on_delete=models.CASCADE,
        verbose_name=_('To employee')
    )
    provider = models.ForeignKey('Provider', on_delete=models.CASCADE, verbose_name=_('Provider'))
    is_accepted = models.BooleanField(default=False, verbose_name=_('Accepted'))
    is_declined = models.BooleanField(default=False, verbose_name=_('Declined'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created at'))
    accepted_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Accepted at'))
    declined_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Declined at'))

    class Meta:
        verbose_name = _('Manager transfer invite')
        verbose_name_plural = _('Manager transfer invites')
        unique_together = ('to_employee', 'provider', 'is_accepted', 'is_declined')
