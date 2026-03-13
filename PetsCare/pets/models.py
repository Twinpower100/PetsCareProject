"""
Модели для модуля pets.

Этот модуль содержит модели для управления питомцами в системе PetsCare.

Основные компоненты:
1. PetType - типы питомцев (кошки, собаки и т.д.)
2. Breed - породы питомцев
3. Pet - информация о питомцах
4. PetHealthNote - внешние owner-facing заметки о здоровье питомца
5. VisitRecord - записи о визитах/процедурах/услугах
6. PetDocument - документы, прикрепленные к заметкам и визитам
7. PetAccess - доступ к карте питомца

Особенности реализации:
- Поддержка различных типов питомцев
- Управление медицинскими записями
- Система доступа к информации о питомцах
- Прикрепление файлов к записям
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from catalog.models import Service
from users.models import User
from datetime import date, timedelta
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone
import uuid
import os
import logging

from .document_type_catalog import (
    DOCUMENT_TYPE_NAME_CHOICES,
    get_document_type_definition_by_code,
    get_document_type_definition_by_name,
)

logger = logging.getLogger(__name__)


class PetType(models.Model):
    """
    Тип питомца (кошка, собака, и т.д.)
    
    Особенности:
    - Уникальный технический код (code)
    - Проверка уникальности и формата кода
    - Мультиязычное наименование
    """
    name = models.CharField(
        _('Name'),
        max_length=50,
        unique=True,
        help_text=_('Type of pet (e.g., cat, dog, etc.)')
    )
    name_en = models.CharField(
        _('Name (English)'),
        max_length=50,
        blank=True,
        help_text=_('Name in English')
    )
    name_ru = models.CharField(
        _('Name (Russian)'),
        max_length=50,
        blank=True,
        help_text=_('Name in Russian')
    )
    name_me = models.CharField(
        _('Name (Montenegrian)'),
        max_length=50,
        blank=True,
        help_text=_('Name in Montenegrian')
    )
    name_de = models.CharField(
        _('Name (German)'),
        max_length=50,
        blank=True,
        help_text=_('Name in German')
    )
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
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of the pet type')
    )

    class Meta:
        verbose_name = _('Pet Type')
        verbose_name_plural = _('Pet Types')
        ordering = ['name']

    def __str__(self):
        return self.get_localized_name()
    
    def get_localized_name(self, language_code=None):
        """
        Получает локализованное название типа животного.
        
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


class Breed(models.Model):
    """
    Порода питомца
    
    Особенности:
    - Уникальный технический код (code)
    - Проверка уникальности и формата кода
    - Мультиязычное наименование
    """
    pet_type = models.ForeignKey(
        PetType,
        on_delete=models.CASCADE,
        verbose_name=_('Pet Type'),
        related_name='breeds',
        help_text=_('Type of pet this breed belongs to')
    )
    name = models.CharField(
        _('Name'),
        max_length=100,
        help_text=_('Name of the breed')
    )
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
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of the breed')
    )

    class Meta:
        verbose_name = _('Breed')
        verbose_name_plural = _('Breeds')
        ordering = ['pet_type', 'name']
        unique_together = ['pet_type', 'name']

    def __str__(self):
        return f"{self.get_localized_name()} ({self.pet_type.get_localized_name()})"
    
    def get_localized_name(self, language_code=None):
        """
        Получает локализованное название породы.
        
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


# Коды размеров для весовых правил и цен по размерам (должны совпадать с SizeRule.size_code).
SIZE_CATEGORY_CHOICES = [
    ('S', 'S'),
    ('M', 'M'),
    ('L', 'L'),
    ('XL', 'XL'),
]
# Порядок размера для выбора «выше» при пересечении диапазонов: S < M < L < XL.
SIZE_CATEGORY_ORDER = {'S': 0, 'M': 1, 'L': 2, 'XL': 3}


class SizeRule(models.Model):
    """
    Глобальное правило: диапазон веса для размера (S/M/L/XL) по типу питомца.

    Используется для автоматического определения размерной категории питомца по весу
    и для привязки цен по размерам (LocationServicePrice / ServiceVariant).
    """
    pet_type = models.ForeignKey(
        PetType,
        on_delete=models.CASCADE,
        verbose_name=_('Pet Type'),
        related_name='size_rules',
        help_text=_('Pet type (e.g. dog, cat)')
    )
    size_code = models.CharField(
        _('Size Code'),
        max_length=10,
        choices=SIZE_CATEGORY_CHOICES,
        help_text=_('Size category: S, M, L, XL')
    )
    min_weight_kg = models.DecimalField(
        _('Min Weight (kg)'),
        max_digits=5,
        decimal_places=2,
        help_text=_('Minimum weight in kg (inclusive)')
    )
    max_weight_kg = models.DecimalField(
        _('Max Weight (kg)'),
        max_digits=5,
        decimal_places=2,
        help_text=_('Maximum weight in kg (inclusive)')
    )

    class Meta:
        verbose_name = _('Size Rule')
        verbose_name_plural = _('Size Rules')
        ordering = ['pet_type', 'min_weight_kg']
        unique_together = [['pet_type', 'size_code']]

    def __str__(self):
        return f"{self.pet_type.code} {self.size_code}: {self.min_weight_kg}-{self.max_weight_kg} kg"

    def clean(self):
        if self.min_weight_kg is not None and self.max_weight_kg is not None:
            if self.min_weight_kg > self.max_weight_kg:
                raise ValidationError(
                    _('Min weight must be less than or equal to max weight.')
                )


class ChronicCondition(models.Model):
    """
    Справочник хронических заболеваний питомцев.
    Влияет на протоколы провайдеров (фиксация, сушка, лакомства и т.д.).
    Категория задаётся choices без отдельной модели типов.
    """
    CATEGORY_ORTHOPAEDIC = 'orthopaedic'
    CATEGORY_CARDIO_RESPIRATORY = 'cardio_respiratory'
    CATEGORY_NEUROLOGICAL = 'neurological'
    CATEGORY_DERMATOLOGICAL_IMMUNE = 'dermatological_immune'
    CATEGORY_ENDOCRINE_SYSTEMIC = 'endocrine_systemic'

    CATEGORY_CHOICES = [
        (CATEGORY_ORTHOPAEDIC, _('Orthopaedic')),
        (CATEGORY_CARDIO_RESPIRATORY, _('Cardiological and respiratory')),
        (CATEGORY_NEUROLOGICAL, _('Neurological')),
        (CATEGORY_DERMATOLOGICAL_IMMUNE, _('Dermatological and immune')),
        (CATEGORY_ENDOCRINE_SYSTEMIC, _('Endocrine and systemic')),
    ]

    code = models.CharField(
        _('Code'),
        max_length=50,
        unique=True,
        help_text=_('Unique code for API and i18n (e.g. osteoarthritis, asthma)')
    )
    name = models.CharField(
        _('Name'),
        max_length=200,
        help_text=_('Default display name')
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
    name_de = models.CharField(
        _('Name (German)'),
        max_length=200,
        blank=True,
        help_text=_('Name in German')
    )
    name_me = models.CharField(
        _('Name (Montenegrin)'),
        max_length=200,
        blank=True,
        help_text=_('Name in Montenegrin')
    )
    category = models.CharField(
        _('Category'),
        max_length=30,
        choices=CATEGORY_CHOICES,
        help_text=_('Type of chronic condition')
    )
    order = models.PositiveSmallIntegerField(
        _('Order'),
        default=0,
        help_text=_('Display order within category')
    )

    class Meta:
        verbose_name = _('Chronic Condition')
        verbose_name_plural = _('Chronic Conditions')
        ordering = ['category', 'order', 'code']

    def get_localized_name(self, language_code=None):
        """Возвращает локализованное название по коду языка (en, ru, de, me)."""
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()
        if language_code:
            language_code = language_code.split('-')[0].lower()
        if language_code == 'en' and self.name_en:
            return self.name_en
        if language_code == 'ru' and self.name_ru:
            return self.name_ru
        if language_code == 'de' and self.name_de:
            return self.name_de
        if language_code == 'me' and self.name_me:
            return self.name_me
        return self.name

    def __str__(self):
        return f"{self.get_category_display()}: {self.name}"


class PhysicalFeature(models.Model):
    """
    Справочник физических особенностей питомцев (отсутствие конечностей, слепота и т.д.).
    Используется в medical_conditions.physical_features как список кодов.
    """
    code = models.CharField(
        _('Code'),
        max_length=50,
        unique=True,
        help_text=_('Unique code (e.g. featureAmputee, featureBlindness)')
    )
    name = models.CharField(
        _('Name'),
        max_length=100,
        help_text=_('Default display name')
    )
    name_en = models.CharField(
        _('Name (English)'),
        max_length=100,
        blank=True,
    )
    name_ru = models.CharField(
        _('Name (Russian)'),
        max_length=100,
        blank=True,
    )
    name_de = models.CharField(
        _('Name (German)'),
        max_length=100,
        blank=True,
    )
    name_me = models.CharField(
        _('Name (Montenegrin)'),
        max_length=100,
        blank=True,
    )
    order = models.PositiveSmallIntegerField(
        _('Order'),
        default=0,
    )

    class Meta:
        verbose_name = _('Physical Feature')
        verbose_name_plural = _('Physical Features')
        ordering = ['order', 'code']

    def get_localized_name(self, language_code=None):
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()
        if language_code:
            language_code = language_code.split('-')[0].lower()
        if language_code == 'en' and self.name_en:
            return self.name_en
        if language_code == 'ru' and self.name_ru:
            return self.name_ru
        if language_code == 'de' and self.name_de:
            return self.name_de
        if language_code == 'me' and self.name_me:
            return self.name_me
        return self.name

    def __str__(self):
        return self.name


class BehavioralTrait(models.Model):
    """
    Справочник поведенческих особенностей питомцев.
    Используется в Pet.behavioral_traits как список кодов (JSONField).
    """
    code = models.CharField(
        _('Code'),
        max_length=50,
        unique=True,
        help_text=_('Unique code (e.g. traitFlightRisk, traitWaterFear)')
    )
    name = models.CharField(
        _('Name'),
        max_length=100,
        help_text=_('Default display name')
    )
    name_en = models.CharField(
        _('Name (English)'),
        max_length=100,
        blank=True,
    )
    name_ru = models.CharField(
        _('Name (Russian)'),
        max_length=100,
        blank=True,
    )
    name_de = models.CharField(
        _('Name (German)'),
        max_length=100,
        blank=True,
    )
    name_me = models.CharField(
        _('Name (Montenegrin)'),
        max_length=100,
        blank=True,
    )
    order = models.PositiveSmallIntegerField(
        _('Order'),
        default=0,
    )

    class Meta:
        verbose_name = _('Behavioral Trait')
        verbose_name_plural = _('Behavioral Traits')
        ordering = ['order', 'code']

    def get_localized_name(self, language_code=None):
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()
        if language_code:
            language_code = language_code.split('-')[0].lower()
        if language_code == 'en' and self.name_en:
            return self.name_en
        if language_code == 'ru' and self.name_ru:
            return self.name_ru
        if language_code == 'de' and self.name_de:
            return self.name_de
        if language_code == 'me' and self.name_me:
            return self.name_me
        return self.name

    def __str__(self):
        return self.name


class Pet(models.Model):
    """
    Модель питомца.
    
    Особенности:
    - Связь с владельцем
    - Основная информация
    - Медицинские данные
    - Особенности ухода
    """
    GENDER_CHOICES = [
        ('M', _('Male')),
        ('F', _('Female')),
        ('U', _('Unknown')),
    ]

    NEUTERED_CHOICES = [
        ('Y', _('Yes')),
        ('N', _('No')),
        ('U', _('Unknown')),
    ]

    owners = models.ManyToManyField(
        User,
        through='PetOwner',
        related_name='pets',
        verbose_name=_('Owners'),
        help_text=_('All owners of the pet')
    )

    @property
    def main_owner(self):
        """Возвращает основного владельца питомца.

        Оптимизация: если petowner_set уже подгружен через
        prefetch_related, фильтруем в памяти; иначе — один SQL-запрос.
        """
        # Поддержка legacy-сценария, когда main_owner передают до первого save().
        if self.pk is None and hasattr(self, '_pending_main_owner'):
            return self._pending_main_owner
        # Пробуем использовать prefetched данные
        if 'petowner_set' in getattr(self, '_prefetched_objects_cache', {}):
            for po in self.petowner_set.all():
                if po.role == 'main':
                    return po.user
            return None
        # Fallback: запрос к БД
        po = self.petowner_set.filter(role='main').select_related('user').first()
        return po.user if po else None

    @main_owner.setter
    def main_owner(self, value):
        """Сохраняет main owner для старых create/update flows."""
        self._pending_main_owner = value

    @property
    def main_owner_id(self):
        """ID основного владельца (для обратной совместимости)."""
        if self.pk is None and hasattr(self, '_pending_main_owner'):
            return getattr(self._pending_main_owner, 'id', None)
        if 'petowner_set' in getattr(self, '_prefetched_objects_cache', {}):
            for po in self.petowner_set.all():
                if po.role == 'main':
                    return po.user_id
            return None
        po = self.petowner_set.filter(role='main').values_list('user_id', flat=True).first()
        return po
    name = models.CharField(
        _('Name'),
        max_length=100,
        help_text=_('Pet name')
    )
    pet_type = models.ForeignKey(
        PetType,
        on_delete=models.PROTECT,
        verbose_name=_('Pet Type'),
        related_name='pets',
        help_text=_('Type of pet')
    )
    breed = models.ForeignKey(
        Breed,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Breed'),
        related_name='pets',
        help_text=_('Pet breed')
    )
    birth_date = models.DateField(
        _('Birth Date'),
        null=True,
        blank=True,
        help_text=_('Pet birth date. Null = unknown (e.g. adopted without papers).')
    )
    weight = models.DecimalField(
        _('Weight'),
        max_digits=5,
        decimal_places=2,
        null=False,
        blank=False,
        help_text=_('Pet weight in kg (mandatory for size-based pricing)')
    )
    gender = models.CharField(
        _('Gender'),
        max_length=1,
        choices=GENDER_CHOICES,
        default='U',
        help_text=_('Gender of the pet (Male, Female, Unknown)')
    )
    is_neutered = models.CharField(
        _('Is Neutered'),
        max_length=1,
        choices=NEUTERED_CHOICES,
        default='U',
        help_text=_('Neutering status (Yes, No, Unknown)')
    )
    rabies_vaccination_expiry = models.DateField(
        _('Rabies vaccination expiry'),
        null=True,
        blank=True,
        help_text=_('Date when rabies vaccination expires (next revaccination). Null = unknown.')
    )
    core_vaccination_expiry = models.DateField(
        _('Core vaccination expiry'),
        null=True,
        blank=True,
        help_text=_('Date when core/complex vaccination expires. Null = unknown.')
    )
    identifier = models.CharField(
        _('Identifier'),
        max_length=50,
        null=True,
        blank=True,
        help_text=_('Microchip number (15 digits) or tattoo. Format depends on country.')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Additional information about the pet')
    )
    behavioral_traits = models.JSONField(
        _('Behavioral Traits'),
        default=list,
        blank=True,
        help_text=_('List of behavioral tags (e.g. flight_risk, water_fear)')
    )
    special_needs = models.JSONField(
        _('Special Needs'),
        default=dict,
        blank=True,
        null=True,
        help_text=_('Special care requirements')
    )
    medical_conditions = models.JSONField(
        _('Medical Conditions'),
        default=dict,
        blank=True,
        null=True,
        help_text=_('Medical conditions and history (allergies, etc.). Chronic conditions use chronic_conditions M2M.')
    )
    chronic_conditions = models.ManyToManyField(
        ChronicCondition,
        related_name='pets',
        verbose_name=_('Chronic conditions'),
        blank=True,
        help_text=_('Standardized chronic conditions from reference list')
    )
    photo = models.ImageField(
        _('Photo'),
        upload_to='pets/%Y/%m/%d/',
        null=True,
        blank=True,
        help_text=_('Pet photo')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether the pet is active')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )

    class Meta:
        verbose_name = _('Pet')
        verbose_name_plural = _('Pets')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.pet_type.name if self.pet_type else 'Unknown'})"

    def get_age(self):
        """Возвращает возраст питомца в годах."""
        if not self.birth_date:
            return None
        today = date.today()
        age = today.year - self.birth_date.year
        if today.month < self.birth_date.month or (
            today.month == self.birth_date.month and
            today.day < self.birth_date.day
        ):
            age -= 1
        return age

    def get_current_size_category(self):
        """
        Определяет размерную категорию (S/M/L/XL) по весу и глобальным правилам SizeRule.

        - Ищет правила для pet_type, в диапазон которых попадает self.weight.
        - Если вес попадает в несколько диапазонов (граница), возвращает больший размер.
        - Если вес выше всех max_weight_kg для типа, возвращает максимальный размер для типа.
        - Если правил для типа нет, возвращает None.

        Returns:
            str | None: Код размера (S, M, L, XL) или None.
        """
        weight_val = float(self.weight)
        rules = list(
            SizeRule.objects.filter(pet_type=self.pet_type).order_by('min_weight_kg')
        )
        if not rules:
            return None
        # Все подходящие по диапазону [min_weight_kg, max_weight_kg]
        matching = [
            r for r in rules
            if float(r.min_weight_kg) <= weight_val <= float(r.max_weight_kg)
        ]
        if matching:
            # Берём размер с большим порядком (если несколько — «выше»)
            return max(matching, key=lambda r: SIZE_CATEGORY_ORDER.get(r.size_code, -1)).size_code
        # Вес выше всех max — возвращаем максимальный размер для типа
        return max(rules, key=lambda r: SIZE_CATEGORY_ORDER.get(r.size_code, -1)).size_code

    def clean(self):
        # Валидация основного владельца перенесена в PetOwner
        # (проверка наличия ровно одного 'main' владельца)
        pass

    def save(self, *args, **kwargs):
        # Сохраняем объект
        super().save(*args, **kwargs)

        if hasattr(self, '_pending_main_owner') and self._pending_main_owner is not None:
            self._sync_main_owner_relation(self._pending_main_owner)

        # Ресайз фото до заданного max разрешения при необходимости
        if self.photo:
            self._resize_photo_if_needed()

    def _sync_main_owner_relation(self, owner):
        """Синхронизирует PetOwner после legacy-записи через Pet.main_owner."""
        existing_main = self.petowner_set.filter(role='main').first()
        if existing_main and existing_main.user_id == owner.id:
            return

        self.petowner_set.filter(role='main').exclude(user=owner).update(role='coowner')
        relation, created = PetOwner.objects.get_or_create(
            pet=self,
            user=owner,
            defaults={'role': 'main'},
        )
        if not created and relation.role != 'main':
            relation.role = 'main'
            relation.save(update_fields=['role'])

    def _resize_photo_if_needed(self):
        """Уменьшает фото до PET_PHOTO_MAX_WIDTH×PET_PHOTO_MAX_HEIGHT при необходимости."""
        from .constants import PET_PHOTO_MAX_WIDTH, PET_PHOTO_MAX_HEIGHT
        try:
            path = self.photo.path
        except (ValueError, NotImplementedError):
            return
        if not path or not os.path.isfile(path):
            return
        try:
            from PIL import Image
            with Image.open(path) as img:
                img.load()
                w, h = img.size
                if w <= PET_PHOTO_MAX_WIDTH and h <= PET_PHOTO_MAX_HEIGHT:
                    return
                ratio = min(
                    PET_PHOTO_MAX_WIDTH / w,
                    PET_PHOTO_MAX_HEIGHT / h,
                    1.0
                )
                new_w = max(1, int(w * ratio))
                new_h = max(1, int(h * ratio))
                resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                resized.save(path, format=img.format or 'JPEG', quality=88, optimize=True)
        except Exception as e:
            logger.warning('Pet photo resize failed for pk=%s: %s', self.pk, e)


class PetOwner(models.Model):
    """
    Явная through-модель для связи Pet ↔ User.

    Роли:
    - 'main'     — основной владелец (ровно один на питомца)
    - 'coowner'  — совладелец (может быть несколько)

    Ограничения:
    - UniqueConstraint на (pet, user) — один пользователь не может
      быть дважды привязан к одному питомцу.
    - Бизнес-правило: у каждого питомца ровно один PetOwner с role='main'.
    """
    ROLE_CHOICES = [
        ('main', _('Main Owner')),
        ('coowner', _('Co-owner')),
    ]

    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        verbose_name=_('Pet'),
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_('Owner'),
    )
    role = models.CharField(
        _('Role'),
        max_length=10,
        choices=ROLE_CHOICES,
        default='coowner',
        help_text=_('Owner role: main or co-owner'),
    )
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True,
    )

    class Meta:
        verbose_name = _('Pet Owner')
        verbose_name_plural = _('Pet Owners')
        constraints = [
            models.UniqueConstraint(
                fields=['pet', 'user'],
                name='unique_pet_owner_rel',
            ),
        ]
        indexes = [
            models.Index(fields=['pet', 'role']),
        ]

    def __str__(self):
        return f"{self.user} → {self.pet.name} ({self.get_role_display()})"

    def clean(self):
        """Проверяет, что не создаётся второй main-владелец."""
        super().clean()
        if self.role == 'main':
            qs = PetOwner.objects.filter(pet=self.pet, role='main')
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    _('This pet already has a main owner. '
                      'Change the existing main owner\'s role first.')
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class PetHealthNote(models.Model):
    """
    Внешняя клиническая заметка владельца по питомцу.

    Явно не является протоколом визита провайдера. Файлы хранятся в PetDocument,
    который может опционально ссылаться на заметку.
    """
    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        verbose_name=_('Pet'),
        related_name='health_notes',
        help_text=_('Pet to which this note belongs')
    )
    date = models.DateField(
        _('Date'),
        help_text=_('Date of the note')
    )
    title = models.CharField(
        _('Title'),
        max_length=200,
        help_text=_('Short title of the note')
    )
    description = models.TextField(
        _('Description'),
        help_text=_('Description of the note')
    )
    next_visit = models.DateField(
        _('Next Visit'),
        null=True,
        blank=True,
        help_text=_('Date of the next recommended visit')
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
        db_table = 'pets_medicalrecord'
        verbose_name = _('Pet Health Note')
        verbose_name_plural = _('Pet Health Notes')
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.pet.name} - {self.title} ({self.date})"

    def get_localized_title(self, language_code=None):
        return self.title

    def get_localized_description(self, language_code=None):
        return self.description


class VisitRecord(models.Model):
    """
    Канонический протокол визита/приёма питомца.

    Особенности:
    - Связь с питомцем и услугой
    - Отслеживание исполнителя и учреждения
    - Хранение результатов и документов
    - Планирование следующей процедуры
    """
    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        verbose_name=_('Pet'),
        related_name='records'
    )
    # ВРЕМЕННО: оставляем для обратной совместимости, будет удалено после миграции данных
    provider = models.ForeignKey(
        'providers.Provider',
        on_delete=models.PROTECT,
        verbose_name=_('Provider (Legacy)'),
        related_name='visit_records',
        null=True,
        blank=True,
        help_text=_('Legacy field - use provider_location instead')
    )
    provider_location = models.ForeignKey(
        'providers.ProviderLocation',
        on_delete=models.PROTECT,
        verbose_name=_('Provider Location'),
        related_name='visit_records',
        null=True,
        blank=True,
        help_text=_('Location where the service was provided')
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        verbose_name=_('Service'),
        related_name='visit_records'
    )
    employee = models.ForeignKey(
        'providers.Employee',
        on_delete=models.PROTECT,
        verbose_name=_('Employee'),
        related_name='visit_records',
        null=True,
        blank=True,
        help_text=_('Employee who performed the procedure; empty when record is added by owner')
    )
    date = models.DateTimeField(
        _('Date'),
        help_text=_('Date and time when the procedure was performed')
    )
    next_date = models.DateField(
        _('Next Date'),
        null=True,
        blank=True,
        help_text=_('Date when the next procedure should be performed')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of what was done')
    )
    results = models.TextField(
        _('Results'),
        blank=True,
        help_text=_('Results of the procedure')
    )
    recommendations = models.TextField(
        _('Recommendations'),
        blank=True,
        help_text=_('Recommendations for the pet owner')
    )
    notes = models.TextField(
        _('Notes'),
        blank=True,
        help_text=_('Internal notes')
    )
    diagnosis = models.TextField(
        _('Diagnosis'),
        blank=True,
        null=True,
        help_text=_('Diagnosis (optional, can be empty for vaccinations)')
    )
    anamnesis = models.TextField(
        _('Anamnesis'),
        blank=True,
        null=True,
        help_text=_('Anamnesis / medical history note (optional)')
    )
    serial_number = models.CharField(
        _('Serial Number'),
        max_length=100,
        blank=True,
        help_text=_('Serial number (for vaccinations, medications, etc.)')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('Created By'),
        related_name='created_records'
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
        db_table = 'pets_petrecord'
        verbose_name = _('Visit Record')
        verbose_name_plural = _('Visit Records')
        ordering = ['-date']

    def __str__(self):
        return f"{self.pet.name} - {self.service.name} ({self.date})"

    def clean(self):
        """
        Валидация записи питомца.
        """
        super().clean()
        
        # Проверяем совместимость услуги с типом животного
        if self.service and self.pet and self.pet.pet_type:
            if not self.service.is_available_for_pet_type(self.pet.pet_type):
                raise ValidationError(
                    _('Service "%(service)s" is not available for pet type "%(pet_type)s".')
                    % {'service': self.service.name, 'pet_type': self.pet.pet_type.name}
                )
    
    def save(self, *args, **kwargs):
        # Валидируем перед сохранением
        self.full_clean()
        
        # Если это новая запись и услуга периодическая, устанавливаем дату следующей процедуры
        if not self.pk and self.service.is_periodic and self.service.period_days is not None:
            self.next_date = self.date + timedelta(days=self.service.period_days)
        super().save(*args, **kwargs)


class VisitRecordAddendum(models.Model):
    """
    Дополнение только для добавления (append-only) — клиническое обновление после визита
    для существующего протокола визита.

    Обеспечивает явность и аудируемость послефактумных обновлений вместо перегрузки
    PetHealthNote или тихой перезаписи исходного протокола визита.
    """
    visit_record = models.ForeignKey(
        'VisitRecord',
        on_delete=models.CASCADE,
        related_name='addenda',
        verbose_name=_('Visit Record'),
        help_text=_('Visit protocol to which this addendum belongs')
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='visit_record_addenda',
        verbose_name=_('Author'),
        help_text=_('User who created the addendum')
    )
    content = models.TextField(
        _('Content'),
        help_text=_('Clinical addendum text')
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
        verbose_name = _('Visit Record Addendum')
        verbose_name_plural = _('Visit Record Addenda')
        ordering = ['created_at']

    def __str__(self):
        return f"Addendum #{self.pk or 'new'} for visit #{self.visit_record_id}"

    def clean(self):
        super().clean()
        if not (self.content or '').strip():
            raise ValidationError(_('Addendum content cannot be empty'))

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class PetDocument(models.Model):
    """
    Универсальная модель файла питомца
    
    Расширенная версия для поддержки системы документов с:
    - Типом документа
    - Метаданными (даты выдачи/истечения, номер, орган выдачи)
    - Аудитом (кто загрузил, дата загрузки)
    - Связями с записями
    """
    # Основные поля
    file = models.FileField(
        _('File'),
        upload_to='pets/documents/%Y/%m/%d/',
        help_text=_('Document file')
    )
    name = models.CharField(
        _('Name'),
        max_length=255,
        help_text=_('Document name')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Document description')
    )
    
    # Связи
    pet = models.ForeignKey(
        'Pet',
        on_delete=models.CASCADE,
        verbose_name=_('Pet'),
        related_name='documents',
        help_text=_('Pet to which the document belongs')
    )
    document_type = models.ForeignKey(
        'DocumentType',
        on_delete=models.PROTECT,
        verbose_name=_('Document Type'),
        related_name='documents',
        null=True,
        blank=True,
        help_text=_('Type of the document')
    )
    health_note = models.ForeignKey(
        'PetHealthNote',
        on_delete=models.CASCADE,
        verbose_name=_('Health Note'),
        related_name='documents',
        null=True,
        blank=True,
        help_text=_('Health note to which the document is attached')
    )
    visit_record = models.ForeignKey(
        'VisitRecord',
        on_delete=models.CASCADE,
        verbose_name=_('Visit Record'),
        related_name='documents',
        null=True,
        blank=True,
        help_text=_('Visit record to which the document is attached')
    )
    
    # Метаданные документа
    issue_date = models.DateField(
        _('Issue Date'),
        null=True,
        blank=True,
        help_text=_('Document issue date')
    )
    expiry_date = models.DateField(
        _('Expiry Date'),
        null=True,
        blank=True,
        help_text=_('Document expiry date')
    )
    document_number = models.CharField(
        _('Document Number'),
        max_length=100,
        blank=True,
        help_text=_('Document number')
    )
    issuing_authority = models.CharField(
        _('Issuing Authority'),
        max_length=200,
        blank=True,
        help_text=_('Issuing authority')
    )
    
    # Аудит
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('Uploaded By'),
        related_name='uploaded_documents',
        help_text=_('User who uploaded the document')
    )
    uploaded_at = models.DateTimeField(
        _('Uploaded At'),
        auto_now_add=True,
        help_text=_('Upload date and time')
    )
    
    # Системные поля
    created_at = models.DateTimeField(
        _('Created At'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated At'),
        auto_now=True
    )

    class Meta:
        db_table = 'pets_petrecordfile'
        verbose_name = _('Pet Document')
        verbose_name_plural = _('Pet Documents')
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.name} - {self.pet.name}"

    def clean(self):
        """Валидация модели"""
        super().clean()
        
        # Проверяем, что документ привязан к питомцу
        if not self.pet:
            raise ValidationError(_('Document must be attached to a pet'))
        
        # Проверяем, что документ привязан только к одной записи
        record_count = sum([
            1 if self.health_note else 0,
            1 if self.visit_record else 0
        ])
        if record_count > 1:
            raise ValidationError(_('Document can only be attached to one record'))
        
        # Проверяем требования типа документа
        if self.document_type:
            if self.document_type.requires_issue_date and not self.issue_date:
                raise ValidationError(_('Issue date is required for this document type'))
            
            if self.document_type.requires_expiry_date and not self.expiry_date:
                raise ValidationError(_('Expiry date is required for this document type'))
            
            if self.document_type.requires_issuing_authority and not self.issuing_authority:
                raise ValidationError(_('Issuing authority is required for this document type'))
            
            if self.document_type.requires_document_number and not self.document_number:
                raise ValidationError(_('Document number is required for this document type'))
        
        # Проверяем даты
        if self.issue_date and self.expiry_date and self.issue_date > self.expiry_date:
            raise ValidationError(_('Issue date cannot be after expiry date'))

    @property
    def is_expired(self):
        """Проверяет, истек ли срок действия документа"""
        if self.expiry_date:
            return self.expiry_date < date.today()
        return False

    @property
    def days_until_expiry(self):
        """Возвращает количество дней до истечения документа"""
        if self.expiry_date:
            delta = self.expiry_date - date.today()
            return delta.days
        return None

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class PetAccess(models.Model):
    """
    Доступ к карте питомца
    """
    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        verbose_name=_('Pet'),
        related_name='accesses'
    )
    granted_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_('Granted To'),
        related_name='pet_accesses'
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_('Granted By'),
        related_name='granted_pet_accesses'
    )
    token = models.UUIDField(
        _('Token'),
        unique=True
    )
    expires_at = models.DateTimeField(
        _('Expires At')
    )
    permissions = models.JSONField(
        _('Permissions'),
        default=dict
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
        verbose_name = _('Pet Access')
        verbose_name_plural = _('Pet Accesses')
        ordering = ['-created_at']
        unique_together = ['pet', 'granted_to']

    def __str__(self):
        return f"{self.pet.name} - {self.granted_to}"

    @property
    def can_read(self):
        """
        Возвращает True, если у пользователя есть право на чтение карты питомца.
        """
        return self.permissions.get('read', False)

    @property
    def can_book(self):
        """
        Возвращает True, если у пользователя есть право на бронирование услуг для питомца.
        """
        return self.permissions.get('book', False)

    @property
    def can_write(self):
        """
        Возвращает True, если у пользователя есть право на редактирование карты питомца.
        """
        return self.permissions.get('write', False)


class DocumentType(models.Model):
    """
    Тип документа питомца из согласованного фиксированного каталога.

    Особенности:
    - Наименование выбирается только из утвержденного списка
    - Технический код и локализованные названия синхронизируются автоматически
    - Требования к метаданным определяются каталогом, а не ручным вводом
    """
    name = models.CharField(
        _('Name'),
        max_length=100,
        choices=DOCUMENT_TYPE_NAME_CHOICES,
        help_text=_('Select one of the approved document types.')
    )
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
    code = models.CharField(
        _('Code'),
        max_length=50,
        unique=True,
        validators=[RegexValidator(
            regex=r'^[a-zA-Z0-9_]+$',
            message=_('Code must contain only Latin letters, numbers and underscores.')
        )],
        help_text=_('Canonical technical code synchronized from the approved document catalog.')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Canonical description synchronized from the approved document catalog.')
    )
    requires_issue_date = models.BooleanField(
        _('Requires Issue Date'),
        default=False,
        help_text=_('Whether issue date is required')
    )
    requires_expiry_date = models.BooleanField(
        _('Requires Expiry Date'),
        default=False,
        help_text=_('Whether expiry date is required')
    )
    requires_issuing_authority = models.BooleanField(
        _('Requires Issuing Authority'),
        default=False,
        help_text=_('Whether issuing authority is required')
    )
    requires_document_number = models.BooleanField(
        _('Requires Document Number'),
        default=False,
        help_text=_('Whether document number is required')
    )
    is_active = models.BooleanField(
        _('Is Active'),
        default=True,
        help_text=_('Whether the document type is active')
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
        verbose_name = _('Document Type')
        verbose_name_plural = _('Document Types')
        ordering = ['name']

    def __str__(self):
        return self.get_localized_name()
    
    def get_localized_name(self, language_code=None):
        """
        Получает локализованное название типа документа.
        
        Args:
            language_code: Код языка (en, ru, me, de). Если None, используется текущий язык.
            
        Returns:
            str: Локализованное название
        """
        if language_code is None:
            from django.utils import translation
            language_code = translation.get_language()

        if language_code == 'cnr':
            language_code = 'me'

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

    def _resolve_catalog_definition(self):
        """
        Возвращает описание согласованного типа по имени или коду.
        """
        if self.name:
            definition = get_document_type_definition_by_name(self.name)
            if definition is not None:
                return definition

        if self.code:
            definition = get_document_type_definition_by_code(self.code)
            if definition is not None:
                return definition

        return None

    def _sync_catalog_fields(self, definition=None):
        """
        Синхронизирует поля модели из единого каталога типов документов.
        """
        definition = definition or self._resolve_catalog_definition()
        if definition is None:
            return None

        self.name = definition.name
        self.code = definition.code
        self.name_en = definition.name_en
        self.name_ru = definition.name_ru
        self.name_me = definition.name_me
        self.name_de = definition.name_de
        self.description = definition.description
        self.requires_issue_date = definition.requires_issue_date
        self.requires_expiry_date = definition.requires_expiry_date
        self.requires_issuing_authority = definition.requires_issuing_authority
        self.requires_document_number = definition.requires_document_number
        return definition

    def clean(self):
        """Валидация модели"""
        super().clean()
        definition = self._resolve_catalog_definition()
        if definition is None:
            raise ValidationError({
                'name': _('Document type name must be selected from the approved catalog')
            })
        self._sync_catalog_fields(definition)
        if self.requires_expiry_date and not self.requires_issue_date:
            raise ValidationError(_('Issue date is required if expiry date is required'))

    def save(self, *args, **kwargs):
        """
        Сохраняет модель только после синхронизации с каталогом типов документов.
        """
        self._sync_catalog_fields()
        self.full_clean()
        super().save(*args, **kwargs)


class PetOwnerIncapacity(models.Model):
    """
    Модель для отслеживания недееспособности владельцев питомцев.
    
    Особенности:
    - Отслеживание статуса недееспособности
    - История изменений статуса
    - Привязка к питомцам и владельцам
    - Автоматические действия
    """
    STATUS_CHOICES = [
        ('pending_confirmation', _('Pending Confirmation')),
        ('confirmed_incapacity', _('Confirmed Incapacity')),
        ('pet_lost', _('Pet Lost/Deceased')),
        ('resolved', _('Resolved')),
        ('auto_deleted', _('Auto Deleted')),
        ('coowner_assigned', _('Co-owner Assigned as Main')),
    ]
    
    FLOW_CHOICES = [
        ('automatic_detection', _('Automatic Detection')),
        ('coowner_report_pet_lost', _('Co-owner Report: Pet Lost')),
        ('coowner_report_owner_incapacity', _('Co-owner Report: Owner Incapacity')),
    ]
    
    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        verbose_name=_('Pet'),
        related_name='incapacity_records'
    )
    main_owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_('Main Owner'),
        related_name='incapacity_records_as_main'
    )
    reported_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_('Reported By'),
        related_name='incapacity_reports',
        help_text=_('User who reported the incapacity')
    )
    
    status = models.CharField(
        _('Status'),
        max_length=30,
        choices=STATUS_CHOICES,
        default='pending_confirmation'
    )
    
    flow_type = models.CharField(
        _('Flow Type'),
        max_length=35,
        choices=FLOW_CHOICES,
        help_text=_('Type of incapacity handling flow')
    )
    
    # Детали недееспособности
    incapacity_reason = models.TextField(
        _('Incapacity Reason'),
        blank=True,
        help_text=_('Reason for incapacity (if reported by co-owner)')
    )
    
    # Даты и сроки
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    confirmation_deadline = models.DateTimeField(
        _('Confirmation Deadline'),
        help_text=_('Deadline for pet status confirmation')
    )
    resolved_at = models.DateTimeField(
        _('Resolved At'),
        null=True,
        blank=True
    )
    
    # Автоматические действия
    auto_action_taken = models.CharField(
        _('Auto Action Taken'),
        max_length=50,
        blank=True,
        help_text=_('Automatic action that was taken')
    )
    new_main_owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('New Main Owner'),
        related_name='incapacity_records_as_new_main',
        help_text=_('New main owner assigned automatically')
    )
    
    # Уведомления
    notifications_sent = models.JSONField(
        _('Notifications Sent'),
        default=list,
        help_text=_('List of notification IDs sent to owners')
    )
    
    # Метаданные
    notes = models.TextField(
        _('Notes'),
        blank=True,
        help_text=_('Additional notes about this incapacity case')
    )
    
    class Meta:
        verbose_name = _('Pet Owner Incapacity')
        verbose_name_plural = _('Pet Owner Incapacities')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['flow_type']),
            models.Index(fields=['confirmation_deadline']),
            models.Index(fields=['pet', 'main_owner']),
        ]
    
    def __str__(self):
        return f"Incapacity case for {self.pet.name} (Owner: {self.main_owner}) - {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        """Автоматически устанавливаем дедлайн подтверждения при создании"""
        if not self.pk and not self.confirmation_deadline:
            from billing.models import BlockingSystemSettings
            settings = BlockingSystemSettings.get_settings()
            deadline_days = settings.get_pet_confirmation_deadline_days()
            self.confirmation_deadline = timezone.now() + timedelta(days=deadline_days)
        super().save(*args, **kwargs)

    def is_deadline_passed(self):
        """Проверяет, истек ли дедлайн подтверждения"""
        return timezone.now() > self.confirmation_deadline
    
    def can_take_auto_action(self):
        """Проверяет, можно ли выполнить автоматическое действие"""
        return (self.status == 'pending_confirmation' and 
                self.is_deadline_passed())
    
    def take_auto_action(self):
        """Выполняет автоматическое действие на основе настроек"""
        from billing.models import BlockingSystemSettings
        settings = BlockingSystemSettings.get_settings()
        
        if not self.can_take_auto_action():
            return False
        
        try:
            if settings.should_auto_delete_unconfirmed_pets():
                # Удаляем питомца
                self.status = 'auto_deleted'
                self.auto_action_taken = 'pet_deleted'
                self.resolved_at = timezone.now()
                self.save()
                
                # Удаляем питомца
                self.pet.delete()
                return True
                
            elif settings.should_auto_assign_coowner_as_main():
                # Назначаем совладельца основным через PetOwner
                from pets.models import PetOwner
                coowners = self.pet.owners.exclude(id=self.main_owner.id)
                if coowners.exists():
                    new_main = self._select_coowner_by_priority(coowners, settings)
                    if new_main:
                        # Снимаем роль main у текущего главного
                        PetOwner.objects.filter(
                            pet=self.pet, role='main'
                        ).update(role='coowner')
                        # Назначаем нового main
                        PetOwner.objects.filter(
                            pet=self.pet, user=new_main
                        ).update(role='main')
                        
                        self.status = 'coowner_assigned'
                        self.auto_action_taken = 'coowner_assigned'
                        self.new_main_owner = new_main
                        self.resolved_at = timezone.now()
                        self.save()
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error taking auto action for incapacity case {self.id}: {str(e)}")
            return False
    
    def _select_coowner_by_priority(self, coowners, settings):
        """Выбирает совладельца по приоритету"""
        priority = settings.get_coowner_assignment_priority()
        
        if priority == 'oldest':
            return coowners.order_by('date_joined').first()
        elif priority == 'newest':
            return coowners.order_by('-date_joined').first()
        elif priority == 'random':
            return coowners.order_by('?').first()
        
        return coowners.first()


class PetIncapacityNotification(models.Model):
    """
    Модель для отслеживания уведомлений о недееспособности владельцев.
    
    Особенности:
    - Отслеживание статуса отправки
    - Различные типы уведомлений
    - История уведомлений
    """
    NOTIFICATION_TYPES = [
        ('confirmation_request', _('Confirmation Request')),
        ('deadline_warning', _('Deadline Warning')),
        ('auto_action_notification', _('Auto Action Notification')),
        ('resolution_notification', _('Resolution Notification')),
    ]
    
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('sent', _('Sent')),
        ('failed', _('Failed')),
    ]
    
    incapacity_record = models.ForeignKey(
        PetOwnerIncapacity,
        on_delete=models.CASCADE,
        verbose_name=_('Incapacity Record'),
        related_name='notifications'
    )
    
    notification_type = models.CharField(
        _('Notification Type'),
        max_length=30,
        choices=NOTIFICATION_TYPES
    )
    
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Получатели уведомления
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_('Recipient'),
        related_name='incapacity_notifications_received'
    )
    
    # Содержание уведомления
    subject = models.CharField(
        _('Subject'),
        max_length=200
    )
    message = models.TextField(_('Message'))
    
    # Время отправки
    sent_at = models.DateTimeField(
        _('Sent At'),
        null=True,
        blank=True
    )
    
    # Ошибки при отправке
    error_message = models.TextField(
        _('Error Message'),
        blank=True
    )
    
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('Pet Incapacity Notification')
        verbose_name_plural = _('Pet Incapacity Notifications')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['recipient']),
        ]
    
    def __str__(self):
        return f"{self.get_notification_type_display()} to {self.recipient} - {self.get_status_display()}"
    
    def mark_as_sent(self):
        """Отмечает уведомление как отправленное"""
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.save()
    
    def mark_as_failed(self, error_message=''):
        """Отмечает уведомление как неудачное"""
        self.status = 'failed'
        self.error_message = error_message
        self.save()
