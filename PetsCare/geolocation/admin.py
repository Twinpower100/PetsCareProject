from django.contrib import admin
from django.contrib.admin.utils import flatten_fieldsets
from custom_admin import custom_admin_site
from django.utils.translation import gettext_lazy as _
from .models import Address, AddressValidation, AddressCache


@admin.register(Address, site=custom_admin_site)
class AddressAdmin(admin.ModelAdmin):
    """Админ-панель для управления структурированными адресами"""
    list_display = (
        'id', 'street', 'house_number', 'city', 'country',
        'validation_status', 'is_geocoded', 'created_at'
    )
    list_filter = (
        'validation_status', 'geocoding_accuracy', 'country', 'city', 
        'created_at', 'validated_at'
    )
    search_fields = (
        'street', 'house_number', 'city', 'country', 'region', 
        'formatted_address', 'postal_code'
    )
    readonly_fields = (
        'created_at', 'updated_at', 'validated_at', 'coordinates',
        'is_geocoded'
    )
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('country', 'region', 'city', 'district')
        }),
        (_('Street and House'), {
            'fields': ('street', 'house_number', 'building', 'apartment')
        }),
        (_('Additional'), {
            'fields': ('postal_code', 'formatted_address')
        }),
        (_('Geocoding'), {
            'fields': ('latitude', 'longitude', 'geocoding_accuracy')
        }),
        (_('Status'), {
            'fields': ('validation_status', 'is_geocoded')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at', 'validated_at'),
            'classes': ('collapse',)
        }),
    )
    # В целевой картине адреса создаются из фронта и админки провайдеров;
    # ручная валидация и сброс в pending не предусмотрены.
    actions = []

    def get_readonly_fields(self, request, obj=None):
        """В режиме просмотра (нет права change или ?_view=1 из кнопки «Просмотреть») все поля только для чтения."""
        if not self.has_change_permission(request, obj) or request.GET.get('_view'):
            # Не вызываем get_form() — возможна рекурсия при построении формы
            editable = list(flatten_fieldsets(self.fieldsets))
            extra = [f for f in self.readonly_fields if f not in editable]
            return editable + extra
        return self.readonly_fields

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """При ?_view=1 скрываем кнопки Сохранить и Удалить (режим только просмотр)."""
        if request.GET.get('_view'):
            extra_context = dict(extra_context or {})
            extra_context.update({
                'show_save': False,
                'show_save_and_add_another': False,
                'show_save_and_continue': False,
                'show_delete': False,
            })
        return super().change_view(request, object_id, form_url, extra_context)

@admin.register(AddressValidation, site=custom_admin_site)
class AddressValidationAdmin(admin.ModelAdmin):
    """Админ-панель для просмотра результатов валидации адресов"""
    list_display = (
        'address', 'is_valid', 'confidence_score', 'api_provider', 
        'processing_time', 'created_at'
    )
    list_filter = (
        'is_valid', 'api_provider', 'created_at'
    )
    search_fields = (
        'address__street', 'address__city', 'address__country'
    )
    readonly_fields = (
        'address', 'created_at', 'processing_time', 'api_provider',
        'validation_errors', 'suggestions', 'api_response'
    )
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('address', 'is_valid', 'confidence_score')
        }),
        (_('Validation Details'), {
            'fields': ('validation_errors', 'suggestions')
        }),
        (_('API Information'), {
            'fields': ('api_provider', 'api_response'),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'processing_time'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        """Запрещаем ручное создание записей валидации"""
        return False

    def has_change_permission(self, request, obj=None):
        """Запрещаем редактирование записей валидации"""
        return False


@admin.register(AddressCache, site=custom_admin_site)
class AddressCacheAdmin(admin.ModelAdmin):
    """Админ-панель для управления кэшем адресов"""
    list_display = (
        'cache_key', 'api_provider', 'hit_count', 'created_at', 
        'expires_at', 'is_expired'
    )
    list_filter = (
        'api_provider', 'created_at', 'expires_at'
    )
    search_fields = ('cache_key',)
    readonly_fields = (
        'cache_key', 'api_provider', 'created_at', 'hit_count', 
        'is_expired', 'address_data'
    )
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('cache_key', 'api_provider', 'hit_count')
        }),
        (_('Lifetime'), {
            'fields': ('created_at', 'expires_at', 'is_expired')
        }),
        (_('Cache Data'), {
            'fields': ('address_data',),
            'classes': ('collapse',)
        }),
    )
    actions = ['clear_expired_cache', 'clear_all_cache']

    def clear_expired_cache(self, request, queryset):
        """Действие для очистки истекшего кэша"""
        from django.utils import timezone
        expired_count = queryset.filter(expires_at__lt=timezone.now()).delete()[0]
        self.message_user(
            request, 
            _("Deleted %(count)d expired cache entries") % {'count': expired_count}
        )
    clear_expired_cache.short_description = _("Clear expired cache")

    def clear_all_cache(self, request, queryset):
        """Действие для очистки всего кэша"""
        deleted_count = queryset.delete()[0]
        self.message_user(
            request, 
            _("Deleted %(count)d cache entries") % {'count': deleted_count}
        )
    clear_all_cache.short_description = _("Clear all cache")

    def has_add_permission(self, request):
        """Запрещаем ручное создание записей кэша"""
        return False

    def has_change_permission(self, request, obj=None):
        """Запрещаем редактирование записей кэша"""
        return False 