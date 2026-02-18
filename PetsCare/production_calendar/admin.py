"""
Админка глобального производственного календаря.

При сохранении записи из админки автоматически выставляется is_manually_corrected=True.
list_editable для быстрого массового изменения day_type и is_manually_corrected.
Регистрация в custom_admin выполняется в custom_admin.admin.register_admin_models().
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import ProductionCalendar


class YearListFilter(admin.SimpleListFilter):
    """Фильтр по году (вычисляется из date)."""
    title = _('Year')
    parameter_name = 'year'

    def lookups(self, request, model_admin):
        from django.db.models.functions import ExtractYear
        from django.db.models import IntegerField
        qs = model_admin.get_queryset(request)
        years = qs.annotate(
            y=ExtractYear('date', output_field=IntegerField())
        ).values_list('y', flat=True).distinct().order_by('-y')[:25]
        return [(y, str(y)) for y in years]

    def queryset(self, request, queryset):
        if self.value():
            from django.db.models.functions import ExtractYear
            return queryset.filter(date__year=self.value())
        return queryset


class ProductionCalendarAdmin(admin.ModelAdmin):
    list_display = [
        'date',
        'country',
        'day_type',
        'description',
        'is_transfer',
        'is_manually_corrected',
        'year_from_date',
    ]
    list_editable = ['day_type', 'is_manually_corrected']
    list_filter = [
        'country',
        'day_type',
        'is_manually_corrected',
        YearListFilter,
        ('date', admin.DateFieldListFilter),
    ]
    search_fields = ['description']
    date_hierarchy = 'date'
    ordering = ['-date', 'country']

    def year_from_date(self, obj):
        return obj.date.year if obj.date else None

    year_from_date.short_description = _('Year')
    year_from_date.admin_order_field = 'date'

    def save_model(self, request, obj, form, change):
        """При любом сохранении из админки помечаем запись как вручную исправленную."""
        obj.is_manually_corrected = True
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        """При сохранении через list_editable выставляем is_manually_corrected изменённым записям."""
        instances = formset.save(commit=False)
        for instance in instances:
            instance.is_manually_corrected = True
            instance.save()
        formset.save_m2m()


# Регистрация выполняется в custom_admin.admin.register_admin_models(), чтобы гарантировать появление в админке
