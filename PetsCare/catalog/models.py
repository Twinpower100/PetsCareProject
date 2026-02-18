"""
Catalog models for the application.

Этот модуль содержит модели для:
1. Услуг
2. Управления периодичностью и напоминаниями
"""

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator


class Service(models.Model):
    """
    Модель услуги/категории.
    
    Используется для создания иерархической структуры услуг.
    Если parent=None, то это категория верхнего уровня.
    Если parent указан, то это либо подкатегория, либо услуга.
    """
    code = models.CharField(
        _('Code'),
        max_length=50,
        unique=True,
        validators=[RegexValidator(
            regex=r'^[a-zA-Z0-9_]+$',
            message=_('Code must contain only Latin letters, numbers and underscores.')
        )],
        help_text=_('Unique technical code (Latin letters, numbers, underscores). Used for integrations and business logic.')
    )
    name = models.CharField(
        _('Name'),
        max_length=200,
        help_text=_('Name of the service or category')
    )
    name_en = models.CharField(
        _('Name (English)'),
        max_length=200,
        blank=True,
        help_text=_('Name in English')
    )
    name_ru = models.CharField(
        _('Name (Russian)'),
        max_length=200,
        blank=True,
        help_text=_('Name in Russian')
    )
    name_me = models.CharField(
        _('Name (Montenegrian)'),
        max_length=200,
        blank=True,
        help_text=_('Name in Montenegrian')
    )
    name_de = models.CharField(
        _('Name (German)'),
        max_length=200,
        blank=True,
        help_text=_('Name in German')
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name=_('Parent'),
        help_text=_('Parent service or category in the hierarchy')
    )
    level = models.PositiveIntegerField(
        _('Level'),
        default=0,
        help_text=_('Level in the hierarchy')
    )
    hierarchy_order = models.CharField(
        _('Hierarchy Order'),
        max_length=100,
        blank=True,
        help_text=_('Hierarchical order for sorting (e.g., 1, 1_1, 1_2, 2_1)')
    )
    version = models.PositiveIntegerField(
        _('Version'),
        default=1,
        help_text=_('Version for optimistic locking')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of the service or category')
    )
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
    icon = models.CharField(
        _('Icon'),
        max_length=50,
        blank=True,
        help_text=_('Icon class or identifier')
    )
    
    # Поля для услуг (заполняются только для конечных услуг)
    is_mandatory = models.BooleanField(
        _('Is Mandatory'),
        default=False,
        help_text=_('Whether this service is mandatory for pets')
    )
    is_periodic = models.BooleanField(
        _('Is Periodic'),
        default=False,
        help_text=_('Whether this service needs to be repeated periodically')
    )
    period_days = models.PositiveIntegerField(
        _('Period In Days'),
        null=True,
        blank=True,
        help_text=_('Number of days between periodic procedures')
    )
    send_reminders = models.BooleanField(
        _('Send Reminders'),
        default=False,
        help_text=_('Whether to send reminders for this service')
    )
    reminder_days_before = models.PositiveIntegerField(
        _('Reminder Days Before'),
        null=True,
        blank=True,
        help_text=_('Days before the procedure to send a reminder')
    )
    
    requires_license = models.BooleanField(
        _('Requires License'),
        default=False,
        help_text=_('Whether this service requires special licensing or certification')
    )

    # Признак «оказывается клиенту». False для технических услуг (клинер, санитар и т.п.) —
    # они не бронируются клиентами, используются только для расписания персонала.
    is_client_facing = models.BooleanField(
        _('Is client facing'),
        default=True,
        help_text=_('If False, this is a technical/internal service (e.g. cleaning) not bookable by clients.')
    )
    
    # Связь с типами животных
    allowed_pet_types = models.ManyToManyField(
        'pets.PetType',
        blank=True,
        verbose_name=_('Allowed Pet Types'),
        help_text=_('Pet types this service is available for. If empty, available for all types.')
    )
    
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether the service or category is currently active')
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
        verbose_name = _('Service')
        verbose_name_plural = _('Services')
        ordering = ['hierarchy_order', 'name']
        indexes = [
            models.Index(fields=['parent', 'level']),
            models.Index(fields=['level']),
            models.Index(fields=['hierarchy_order']),
        ]

    def __str__(self):
        return self.get_localized_name()
    
    def get_localized_name(self, language_code=None):
        """
        Получает локализованное название услуги.
        
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
        Получает локализованное описание услуги.
        
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

    def calculate_hierarchy_order(self):
        """
        Вычисляет иерархический порядок для сортировки.
        
        Returns:
            str: Строка с иерархическим порядком (например, "1", "1_1", "1_2", "2_1")
        """
        if not self.parent:
            # Для корневых элементов - просто порядковый номер
            siblings = Service.objects.filter(parent=None).order_by('id')
            for i, sibling in enumerate(siblings, 1):
                if sibling.id == self.id:
                    return str(i)
            return "1"
        else:
            # Для дочерних элементов - порядок родителя + порядковый номер среди братьев
            parent_order = self.parent.hierarchy_order or self.parent.calculate_hierarchy_order()
            siblings = Service.objects.filter(parent=self.parent).order_by('id')
            for i, sibling in enumerate(siblings, 1):
                if sibling.id == self.id:
                    return f"{parent_order}_{i}"
            return f"{parent_order}_1"

    @transaction.atomic
    def save(self, *args, **kwargs):
        """
        Переопределение метода сохранения для автоматического расчета уровня и иерархического порядка.
        Защищено от гонки транзакций с оптимистичным блокированием.
        """
        from django.core.exceptions import ValidationError
        
        # Блокируем запись для редактирования
        if self.pk:
            try:
                # Получаем текущую версию с блокировкой
                current = Service.objects.select_for_update().get(pk=self.pk)
                if current.version != self.version:
                    raise ValidationError(_('Record was modified by another user. Please refresh and try again.'))
                self.version = current.version + 1
            except Service.DoesNotExist:
                raise ValidationError(_('Record was deleted by another user.'))
        else:
            # Для новых записей версия = 1
            self.version = 1
        
        # Вычисляем уровень
        if self.parent:
            self.level = self.parent.level + 1
        else:
            self.level = 0
        
        # Вычисляем иерархический порядок
        self.hierarchy_order = self.calculate_hierarchy_order()
        
        super().save(*args, **kwargs)

    def get_ancestors(self):
        """
        Получает всех предков.
        
        Returns:
            QuerySet: QuerySet с предками
        """
        ancestors = []
        current = self
        while current.parent:
            current = current.parent
            ancestors.append(current)
        return ancestors

    def get_descendants(self):
        """
        Получает всех потомков.
        
        Returns:
            QuerySet: QuerySet с потомками
        """
        return Service.objects.filter(parent=self)

    def get_full_path(self):
        """
        Получает полный путь.
        
        Returns:
            str: Полный путь
        """
        path = [self.name]
        current = self
        while current.parent:
            current = current.parent
            path.append(current.name)
        return ' > '.join(reversed(path))

    def get_next_date(self, from_date):
        """
        Рассчитывает дату следующей процедуры.
        
        Args:
            from_date: Дата, от которой считать следующую процедуру
            
        Returns:
            date: Дата следующей процедуры или None, если процедура не периодическая
        """
        if self.is_periodic and self.period_days:
            from datetime import timedelta
            return from_date + timedelta(days=self.period_days)
        return None

    @property
    def is_category(self):
        """
        Проверяет, является ли запись категорией.
        
        Returns:
            bool: True если это категория (нет потомков)
        """
        return not self.children.exists()

    @property
    def is_service(self):
        """
        Проверяет, является ли запись услугой.
        
        Returns:
            bool: True если это услуга (есть потомки)
        """
        return self.children.exists()
    
    def is_available_for_pet_type(self, pet_type):
        """
        Проверяет, доступна ли услуга для данного типа животного.
        
        Args:
            pet_type: PetType объект или ID типа животного
            
        Returns:
            bool: True если услуга доступна для данного типа животного
        """
        if not self.allowed_pet_types.exists():
            # Если не указаны ограничения, услуга доступна для всех типов
            return True
        
        if hasattr(pet_type, 'id'):
            pet_type_id = pet_type.id
        else:
            pet_type_id = pet_type
            
        return self.allowed_pet_types.filter(id=pet_type_id).exists()
    
    def get_periodic_info_for_pet_type(self, pet_type):
        """
        Получает информацию о периодичности услуги для конкретного типа животного.
        
        Args:
            pet_type: PetType объект или ID типа животного
            
        Returns:
            dict: Словарь с информацией о периодичности
        """
        if not self.is_available_for_pet_type(pet_type):
            return {
                'is_available': False,
                'is_periodic': False,
                'period_days': None,
                'send_reminders': False,
                'reminder_days_before': None
            }
        
        return {
            'is_available': True,
            'is_periodic': self.is_periodic,
            'period_days': self.period_days,
            'send_reminders': self.send_reminders,
            'reminder_days_before': self.reminder_days_before
        }

