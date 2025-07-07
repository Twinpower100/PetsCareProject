"""
Модели для модуля передержки питомцев.

Этот модуль содержит модели для:
1. Профиля передержки
2. Настроек передержки
3. Отзывов и рейтингов
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from users.models import User
from django.core.exceptions import ValidationError


class SitterProfile(models.Model):
    """
    Профиль передержки питомцев.
    
    Основные характеристики:
    - Связь с пользователем
    - Настройки передержки
    - Статистика и рейтинг
    
    Технические особенности:
    - Мягкое удаление через флаг is_active
    - Автоматическое отслеживание времени создания и обновления
    - Связь с пользователем через OneToOneField
    - Оптимизированные индексы для поиска
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='sitter',
        verbose_name=_('User')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Description of pet sitting services')
    )
    experience_years = models.PositiveIntegerField(
        _('Experience Years'),
        default=0,
        help_text=_('Years of experience in pet sitting')
    )
    pet_types = models.JSONField(
        _('Pet Types'),
        default=list,
        help_text=_('Types of pets the sitter can take care of')
    )
    max_pets = models.PositiveIntegerField(
        _('Max Pets'),
        default=1,
        help_text=_('Maximum number of pets that can be taken care of at once')
    )
    available_from = models.DateField(
        _('Available From'),
        null=True,
        blank=True,
        help_text=_('Date from which the sitter is available')
    )
    available_to = models.DateField(
        _('Available To'),
        null=True,
        blank=True,
        help_text=_('Date until which the sitter is available')
    )
    max_distance_km = models.PositiveIntegerField(
        _('Max Distance Km'),
        default=5,
        help_text=_('Maximum distance for pet sitting services')
    )
    
    compensation_type = models.CharField(
        _('Compensation Type'),
        max_length=20,
        choices=[
            ('paid', _('Paid')),
            ('unpaid', _('Unpaid'))
        ],
        default='paid',
        help_text=_('Type of compensation for services')
    )
    hourly_rate = models.DecimalField(
        _('Hourly Rate'),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Hourly rate for paid services')
    )
    is_verified = models.BooleanField(
        _('Is Verified'),
        default=False,
        help_text=_('Whether the sitter is verified by the platform')
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
        verbose_name = _('Sitter Profile')
        verbose_name_plural = _('Sitter Profiles')
        ordering = ['-created_at']

    def __str__(self):
        """
        Возвращает строковое представление профиля передержки.
        
        Returns:
            str: Полное имя пользователя
        """
        return f"Sitter Profile for {self.user.get_full_name()}"

    def update_rating(self, new_rating):
        """
        Обновляет рейтинг передержки.
        
        Args:
            new_rating (float): Новый рейтинг для добавления
            
        Примечание:
            Рейтинг рассчитывается как среднее арифметическое всех оценок
        """
        self.user.sitter_rating = (
            (self.user.sitter_rating * self.user.sitter_reviews_count + new_rating) /
            (self.user.sitter_reviews_count + 1)
        )
        self.user.sitter_reviews_count += 1
        self.user.save()

    def delete(self, *args, **kwargs):
        """
        Переопределяет удаление профиля ситтера.
        Запрещает удаление, если есть активные отклики или истории передержек.
        """
        if self.has_active_responses_or_history():
            raise ValidationError(_('Cannot delete sitter profile with active responses or pet sitting history.'))
        super().delete(*args, **kwargs)


class PetSittingAd(models.Model):
    """
    Модель объявления о передержке питомца.
    Связывает питомца, владельца, даты, описание, статус, локацию, компенсацию.
    Используется для публикации запросов на передержку.
    """
    pet = models.ForeignKey('pets.Pet', on_delete=models.CASCADE, related_name='sitting_ads', verbose_name=_('Pet'))
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='sitting_ads', verbose_name=_('Owner'))
    start_date = models.DateField(_('Start Date'))
    end_date = models.DateField(_('End Date'))
    description = models.TextField(_('Description'), blank=True)
    status = models.CharField(_('Status'), max_length=20, choices=[('active', _('Active')), ('closed', _('Closed'))], default='active')
    
    # Старое поле локации (для обратной совместимости)
    location = models.CharField(_('Location'), max_length=255, blank=True)
    
    # Новая структурированная модель адреса
    structured_address = models.ForeignKey(
        'geolocation.Address',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sitting_ads',
        verbose_name=_('Structured Address'),
        help_text=_('Structured address for pet sitting location')
    )
    
    max_distance_km = models.PositiveIntegerField(_('Max Distance (km)'), default=5)
    compensation_type = models.CharField(_('Compensation Type'), max_length=20, choices=[('paid', _('Paid')), ('unpaid', _('Unpaid'))], default='paid')
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Pet Sitting Ad')
        verbose_name_plural = _('Pet Sitting Ads')
        ordering = ['-created_at']

    def __str__(self):
        """
        Возвращает строковое представление объявления о передержке.
        """
        return f"Ad for {self.pet} by {self.owner} ({self.start_date}-{self.end_date})"


class PetSittingResponse(models.Model):
    """
    Модель отклика на объявление о передержке.
    Связывает объявление, ситтера, сообщение, статус отклика.
    Используется для откликов ситтеров на объявления владельцев.
    """
    ad = models.ForeignKey(PetSittingAd, on_delete=models.CASCADE, related_name='responses', verbose_name=_('Ad'))
    sitter = models.ForeignKey('sitters.SitterProfile', on_delete=models.CASCADE, related_name='responses', verbose_name=_('Sitter'))
    message = models.TextField(_('Message'), blank=True)
    status = models.CharField(_('Status'), max_length=20, choices=[('pending', _('Pending')), ('accepted', _('Accepted')), ('rejected', _('Rejected'))], default='pending')
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Pet Sitting Response')
        verbose_name_plural = _('Pet Sitting Responses')
        ordering = ['-created_at']

    def __str__(self):
        """
        Возвращает строковое представление отклика на объявление.
        """
        return f"Response by {self.sitter} to {self.ad} ({self.status})"


class PetSitting(models.Model):
    """
    Модель передержки (факт оказания услуги).
    Связывает объявление, отклик, ситтера, питомца, содержит статусы и отметки передачи/возврата.
    Используется для управления процессом передержки и отзывами.
    """
    ad = models.ForeignKey(PetSittingAd, on_delete=models.CASCADE, related_name='sittings', verbose_name=_('Ad'))
    response = models.ForeignKey('sitters.PetSittingResponse', on_delete=models.CASCADE, related_name='sittings', verbose_name=_('Response'))
    sitter = models.ForeignKey(SitterProfile, on_delete=models.CASCADE, related_name='sittings', verbose_name=_('Sitter'))
    pet = models.ForeignKey('pets.Pet', on_delete=models.CASCADE, related_name='sittings', verbose_name=_('Pet'))
    start_date = models.DateField(_('Start Date'))
    end_date = models.DateField(_('End Date'))
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=[
            ('waiting_start', _('Waiting Start')),
            ('active', _('Active')),
            ('waiting_end', _('Waiting End')),
            ('completed', _('Completed')),
            ('cancelled', _('Cancelled'))
        ],
        default='waiting_start'
    )
    owner_confirmed_start = models.BooleanField(_('Owner Confirmed Start'), default=False)
    sitter_confirmed_start = models.BooleanField(_('Sitter Confirmed Start'), default=False)
    owner_confirmed_end = models.BooleanField(_('Owner Confirmed End'), default=False)
    sitter_confirmed_end = models.BooleanField(_('Sitter Confirmed End'), default=False)
    review_left = models.BooleanField(_('Review Left'), default=False)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        verbose_name = _('Pet Sitting')
        verbose_name_plural = _('Pet Sittings')
        ordering = ['-start_date']

    def __str__(self):
        """
        Возвращает строковое представление передержки.
        """
        return f"PetSitting: {self.pet} with {self.sitter} ({self.start_date}-{self.end_date})"


class Review(models.Model):
    """
    Модель отзыва о передержке.
    Связывает историю передержки, автора, рейтинг, текст отзыва.
    Используется для формирования рейтинга ситтера и обратной связи.
    """
    history = models.ForeignKey(PetSitting, on_delete=models.CASCADE, related_name='reviews', verbose_name=_('History'))
    author = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='sitting_reviews', verbose_name=_('Author'))
    rating = models.PositiveSmallIntegerField(_('Rating'), choices=[(i, str(i)) for i in range(1, 6)])
    text = models.TextField(_('Text'), blank=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        verbose_name = _('Review')
        verbose_name_plural = _('Reviews')
        ordering = ['-created_at']

    def __str__(self):
        """
        Возвращает строковое представление отзыва.
        """
        return f"Review by {self.author} for {self.history} ({self.rating})" 