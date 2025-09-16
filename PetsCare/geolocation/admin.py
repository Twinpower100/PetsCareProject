from django.contrib import admin
from custom_admin import custom_admin_site
from django.utils.translation import gettext_lazy as _
from .models import Location, SearchRadius, LocationHistory, Address, AddressValidation, AddressCache

@admin.register(Location, site=custom_admin_site)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('user', 'address', 'city', 'country', 'postal_code', 'created_at')
    search_fields = ('user__email', 'address', 'city', 'country', 'postal_code')
    list_filter = ('created_at', 'country', 'city')
    readonly_fields = ('created_at',)

@admin.register(SearchRadius, site=custom_admin_site)
class SearchRadiusAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'radius', 'is_active')
    search_fields = ('user__email', 'name')
    list_filter = ('is_active', 'radius')

@admin.register(LocationHistory, site=custom_admin_site)
class LocationHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'address', 'city', 'country', 'postal_code', 'created_at')
    search_fields = ('user__email', 'address', 'city', 'country', 'postal_code')
    list_filter = ('created_at', 'country', 'city')
    readonly_fields = ('created_at',)

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
        'is_valid', 'is_geocoded'
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
            'fields': ('validation_status', 'is_valid', 'is_geocoded')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at', 'validated_at'),
            'classes': ('collapse',)
        }),
    )
    actions = ['validate_addresses', 'clear_validation_status']

    def validate_addresses(self, request, queryset):
        """Действие для валидации выбранных адресов"""
        from .services import AddressValidationService
        
        validated_count = 0
        for address in queryset:
            try:
                service = AddressValidationService()
                result = service.validate_address(address)
                if result:
                    validated_count += 1
            except Exception as e:
                self.message_user(
                    request, 
                    _("Address validation error %(address_id)s: %(error)s") % {
                        'address_id': address.id,
                        'error': str(e)
                    }, 
                    level='ERROR'
                )
        
        self.message_user(
            request, 
            _("Validated %(validated)d out of %(total)d addresses") % {
                'validated': validated_count,
                'total': queryset.count()
            }
        )
    validate_addresses.short_description = _("Validate selected addresses")

    def clear_validation_status(self, request, queryset):
        """Действие для сброса статуса валидации"""
        updated = queryset.update(
            validation_status='pending',
            validated_at=None,
            geocoding_accuracy=''
        )
        self.message_user(
            request, 
            _("Validation status cleared for %(count)d addresses") % {'count': updated}
        )
    clear_validation_status.short_description = _("Clear validation status")


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