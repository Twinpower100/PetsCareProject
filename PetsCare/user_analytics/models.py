from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
from datetime import timedelta

User = get_user_model()

class UserGrowth(models.Model):
    """Модель для отслеживания роста пользователей"""
    
    PERIOD_CHOICES = [
        ('daily', _('Daily')),
        ('weekly', _('Weekly')),
        ('monthly', _('Monthly')),
    ]
    
    period_type = models.CharField(max_length=10, choices=PERIOD_CHOICES, verbose_name=_("Period Type"))
    period_start = models.DateField(verbose_name=_("Period Start"))
    period_end = models.DateField(verbose_name=_("Period End"))
    
    # Метрики роста
    new_registrations = models.PositiveIntegerField(default=0, verbose_name=_("New Registrations"))
    total_users = models.PositiveIntegerField(default=0, verbose_name=_("Total Users"))
    growth_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name=_("Growth Rate (%)"))
    
    # Детализация по типам пользователей
    new_owners = models.PositiveIntegerField(default=0, verbose_name=_("New Owners"))
    new_sitters = models.PositiveIntegerField(default=0, verbose_name=_("New Sitters"))
    new_providers = models.PositiveIntegerField(default=0, verbose_name=_("New Providers"))
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))
    
    class Meta:
        verbose_name = _("User Growth")
        verbose_name_plural = _("User Growth")
        unique_together = ['period_type', 'period_start']
        ordering = ['-period_start']
    
    def __str__(self):
        return f"Growth {self.get_period_type_display()} {self.period_start} - {self.period_end}"


class UserActivity(models.Model):
    """Модель для отслеживания активности пользователей"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("User"))
    date = models.DateField(default=timezone.now, verbose_name=_("Date"))
    
    # Метрики активности
    login_count = models.PositiveIntegerField(default=0, verbose_name=_("Login Count"))
    session_duration = models.PositiveIntegerField(default=0, verbose_name=_("Session Duration (sec)"))
    page_views = models.PositiveIntegerField(default=0, verbose_name=_("Page Views"))
    actions_count = models.PositiveIntegerField(default=0, verbose_name=_("Actions Count"))
    
    # Детализация действий
    searches_count = models.PositiveIntegerField(default=0, verbose_name=_("Searches Count"))
    bookings_count = models.PositiveIntegerField(default=0, verbose_name=_("Bookings Count"))
    reviews_count = models.PositiveIntegerField(default=0, verbose_name=_("Reviews Count"))
    messages_count = models.PositiveIntegerField(default=0, verbose_name=_("Messages Count"))
    
    # Время активности
    first_activity = models.DateTimeField(null=True, blank=True, verbose_name=_("First Activity"))
    last_activity = models.DateTimeField(null=True, blank=True, verbose_name=_("Last Activity"))
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))
    
    class Meta:
        verbose_name = _("User Activity")
        verbose_name_plural = _("User Activities")
        unique_together = ['user', 'date']
        ordering = ['-date', '-last_activity']
    
    def __str__(self):
        return f"Activity {self.user} {self.date}"


class UserConversion(models.Model):
    """Модель для отслеживания конверсии пользователей"""
    
    STAGE_CHOICES = [
        ('registration', _('Registration')),
        ('profile_completion', _('Profile Completion')),
        ('first_search', _('First Search')),
        ('first_view', _('First View')),
        ('first_booking', _('First Booking')),
        ('first_payment', _('First Payment')),
        ('repeat_booking', _('Repeat Booking')),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("User"))
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, verbose_name=_("Conversion Stage"))
    achieved_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Achieved At"))
    
    # Дополнительные данные
    time_to_achieve = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Time to Achieve (hours)"))
    source = models.CharField(max_length=50, blank=True, verbose_name=_("Source"))
    
    class Meta:
        verbose_name = _("User Conversion")
        verbose_name_plural = _("User Conversions")
        unique_together = ['user', 'stage']
        ordering = ['-achieved_at']
    
    def __str__(self):
        return f"{self.user} - {self.get_stage_display()}"


class UserMetrics(models.Model):
    """Агрегированные метрики пользователей"""
    
    PERIOD_CHOICES = [
        ('daily', _('Daily')),
        ('weekly', _('Weekly')),
        ('monthly', _('Monthly')),
    ]
    
    period_type = models.CharField(max_length=10, choices=PERIOD_CHOICES, verbose_name=_("Period Type"))
    period_start = models.DateField(verbose_name=_("Period Start"))
    period_end = models.DateField(verbose_name=_("Period End"))
    
    # Общие метрики
    total_users = models.PositiveIntegerField(default=0, verbose_name=_("Total Users"))
    active_users = models.PositiveIntegerField(default=0, verbose_name=_("Active Users"))
    new_users = models.PositiveIntegerField(default=0, verbose_name=_("New Users"))
    churned_users = models.PositiveIntegerField(default=0, verbose_name=_("Churned Users"))
    
    # Метрики активности
    avg_session_duration = models.PositiveIntegerField(default=0, verbose_name=_("Average Session Duration (sec)"))
    avg_page_views = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name=_("Average Page Views"))
    retention_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name=_("Retention Rate (%)"))
    
    # Метрики конверсии
    conversion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name=_("Conversion Rate (%)"))
    booking_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name=_("Booking Rate (%)"))
    payment_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name=_("Payment Rate (%)"))
    
    # Детализация по типам
    owners_count = models.PositiveIntegerField(default=0, verbose_name=_("Owners Count"))
    sitters_count = models.PositiveIntegerField(default=0, verbose_name=_("Sitters Count"))
    providers_count = models.PositiveIntegerField(default=0, verbose_name=_("Providers Count"))
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))
    
    class Meta:
        verbose_name = _("User Metrics")
        verbose_name_plural = _("User Metrics")
        unique_together = ['period_type', 'period_start']
        ordering = ['-period_start']
    
    def __str__(self):
        return f"Metrics {self.get_period_type_display()} {self.period_start} - {self.period_end}"
    
    @property
    def churn_rate(self):
        """Коэффициент оттока"""
        if self.total_users > 0:
            return round((self.churned_users / self.total_users) * 100, 2)
        return 0
