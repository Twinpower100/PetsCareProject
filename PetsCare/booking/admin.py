from django.contrib import admin
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .models import (
    AbuseRule,
    Booking,
    BookingAutoCompleteSettings,
    BookingCancellation,
    BookingCancellationReason,
    BookingNote,
    BookingPayment,
    BookingReview,
    BookingStatus,
    BookingServiceIssue,
)
from .manual_v2_models import ManualBooking, ManualVisitProtocol, ProviderClientLead
from .constants import (
    CANCELLED_BY_PROVIDER,
    CANCELLATION_REASON_CLIENT_NO_SHOW,
)
from custom_admin import custom_admin_site


class EscortAssignmentFilter(admin.SimpleListFilter):
    """Фильтр по типу escort assignment."""

    title = _('Escort Assignment')
    parameter_name = 'escort_assignment'

    def lookups(self, request, model_admin):
        return (
            ('creator', _('Escort equals creator')),
            ('other', _('Escort differs from creator')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'creator':
            return queryset.filter(user_id=models.F('escort_owner_id'))
        if self.value() == 'other':
            return queryset.exclude(user_id=models.F('escort_owner_id'))
        return queryset


class BookingNoteInline(admin.TabularInline):
    model = BookingNote
    extra = 0
    fields = ('text', 'created_by', 'created_at')
    readonly_fields = ('created_by', 'created_at')


class BookingCancellationInline(admin.TabularInline):
    model = BookingCancellation
    extra = 0
    fields = ('cancelled_by', 'cancelled_by_side', 'reason_code', 'client_attendance', 'reason', 'is_abuse', 'abuse_rule', 'created_at')
    readonly_fields = ('cancelled_by', 'cancelled_by_side', 'reason_code', 'client_attendance', 'is_abuse', 'abuse_rule', 'created_at')


class AbuseRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'period', 'max_cancellations', 'is_active')
    list_filter = ('is_active', 'period')
    search_fields = ('name', 'description')
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'is_active')
        }),
        (_('Rule Settings'), {
            'fields': ('period', 'max_cancellations')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')


class BookingStatusAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для модели статуса бронирования.
    """
    list_display = ['name', 'description']
    search_fields = ['name', 'description']
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'description')
        }),
    )


class BookingCancellationReasonAdmin(admin.ModelAdmin):
    list_display = ('code', 'label', 'scope', 'is_active', 'sort_order')
    list_filter = ('scope', 'is_active')
    search_fields = ('code', 'label', 'description')


class BookingAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для модели бронирования.
    """
    list_display = [
        'id', 'code', 'user', 'escort_owner', 'pet', 'get_pet_owners',
        'provider_location', 'get_provider', 'employee', 'service', 'status',
        'start_time', 'end_time', 'occupied_duration_minutes', 'price',
        'created_at', 'completed_at', 'cancelled_at'
    ]
    list_filter = [
        'status', 'provider_location', 'provider_location__provider', 'escort_owner',
        EscortAssignmentFilter, 'employee', 'service', 'start_time', 'end_time',
        'created_at', 'updated_at', 'completed_at', 'cancelled_at'
    ]
    search_fields = [
        'code', 'user__username', 'user__email', 'escort_owner__username',
        'escort_owner__email', 'pet__name', 'provider_location__name',
        'provider_location__provider__name', 'employee__user__username',
        'employee__user__email', 'service__name', 'pet__owners__username',
        'pet__owners__email'
    ]
    readonly_fields = [
        'code', 'occupied_duration_minutes', 'created_at', 'updated_at',
        'completed_at', 'completed_by_actor', 'completed_by_user', 'completion_reason_code',
        'cancelled_at', 'cancelled_by', 'cancelled_by_user', 'cancellation_reason',
        'cancellation_reason_text', 'client_attendance', 'get_provider', 'get_pet_owners'
    ]
    list_select_related = [
        'user', 'escort_owner', 'pet', 'provider_location',
        'provider_location__provider', 'employee', 'employee__user', 'service', 'status'
    ]
    autocomplete_fields = ['user', 'escort_owner', 'pet', 'provider_location', 'employee', 'service', 'status']
    date_hierarchy = 'created_at'
    inlines = [BookingNoteInline, BookingCancellationInline]
    
    actions = ['complete_bookings', 'cancel_bookings', 'mark_no_show']

    def get_queryset(self, request):
        """Подгружает связанные сущности для list/detail без N+1."""
        return super().get_queryset(request).prefetch_related('pet__owners')
    
    def complete_bookings(self, request, queryset):
        """Завершить выбранные бронирования"""
        from .services import BookingCompletionService
        
        completed_count = 0
        for booking in queryset:
            if booking.can_be_completed:
                try:
                    BookingCompletionService.complete_booking(booking, request.user, 'completed')
                    completed_count += 1
                except Exception as e:
                    self.message_user(request, _("Error completing booking {}: {}").format(booking.id, e), level='ERROR')
        
        self.message_user(request, _("Completed {} bookings").format(completed_count))
    
    complete_bookings.short_description = _("Complete selected bookings")
    
    def cancel_bookings(self, request, queryset):
        """Отменить выбранные бронирования"""
        from .services import BookingCompletionService
        
        cancelled_count = 0
        for booking in queryset:
            if booking.can_be_cancelled:
                try:
                    reason = _("Cancelled by administrator {}").format(request.user.username)
                    BookingCompletionService.cancel_booking(booking, request.user, reason)
                    cancelled_count += 1
                except Exception as e:
                    self.message_user(request, _("Error cancelling booking {}: {}").format(booking.id, e), level='ERROR')
        
        self.message_user(request, _("Cancelled {} bookings").format(cancelled_count))
    
    cancel_bookings.short_description = _("Cancel selected bookings")
    
    def mark_no_show(self, request, queryset):
        """Отметить как 'не явился'"""
        from .services import BookingCompletionService
        
        marked_count = 0
        for booking in queryset:
            if booking.can_be_completed:
                try:
                    no_show_reason = BookingCancellationReason.objects.filter(
                        code=CANCELLATION_REASON_CLIENT_NO_SHOW,
                        is_active=True,
                    ).first()
                    if no_show_reason is None:
                        raise ValidationError(_("No-show reason is not configured"))
                    booking.cancel_booking(
                        cancelled_by=CANCELLED_BY_PROVIDER,
                        cancelled_by_user=request.user,
                        cancellation_reason=no_show_reason,
                        cancellation_reason_text=_("Marked as no-show by administrator"),
                        client_attendance='no_show',
                    )
                    marked_count += 1
                except Exception as e:
                    self.message_user(request, _("Error marking booking {}: {}").format(booking.id, e), level='ERROR')
        
        self.message_user(request, _("Marked as 'no show' {} bookings").format(marked_count))
    
    mark_no_show.short_description = _("Mark as 'no show'")
    
    def get_provider(self, obj):
        """Отображает название организации провайдера."""
        if obj.provider_location:
            return obj.provider_location.provider.name
        elif obj.provider:
            return obj.provider.name
        return '-'
    get_provider.short_description = _('Provider Organization')

    def get_pet_owners(self, obj):
        """Показывает owners/coowners питомца для проверки escort assignment."""
        return ', '.join(obj.pet.owners.values_list('email', flat=True))
    get_pet_owners.short_description = _('Pet Owners')
    
    fieldsets = (
        (None, {
            'fields': ('user', 'escort_owner', 'pet', 'get_pet_owners', 'provider_location', 'employee', 'service')
        }),
        (_('Time'), {
            'fields': ('start_time', 'end_time', 'occupied_duration_minutes')
        }),
        (_('Status'), {
            'fields': ('status', 'price', 'notes', 'code')
        }),
        (_('Completion Metadata'), {
            'fields': ('completed_at', 'completed_by_actor', 'completed_by_user', 'completion_reason_code')
        }),
        (_('Cancellation Metadata'), {
            'fields': (
                'cancelled_at',
                'cancelled_by',
                'cancelled_by_user',
                'cancellation_reason',
                'cancellation_reason_text',
                'client_attendance',
            )
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def save_model(self, request, obj, form, change):
        """
        Сохраняет модель бронирования с транзакционной защитой.
        """
        from .services import BookingDomainError, BookingTransactionService
        
        try:
            if change:
                saved_booking = BookingTransactionService.update_booking(
                    booking_id=obj.id,
                    new_start_time=obj.start_time,
                    new_employee=obj.employee,
                    new_service=obj.service,
                    new_price=obj.price,
                    new_notes=obj.notes,
                    new_escort_owner=obj.escort_owner,
                )
                obj.pk = saved_booking.pk
                self.log_change(request, saved_booking, _('Booking updated via booking transaction service'))
            else:
                provider = obj.provider
                if not provider and obj.provider_location:
                    provider = obj.provider_location.provider
                
                saved_booking = BookingTransactionService.create_booking(
                    user=obj.user,
                    pet=obj.pet,
                    provider=provider,
                    employee=obj.employee,
                    service=obj.service,
                    start_time=obj.start_time,
                    price=obj.price,
                    notes=obj.notes,
                    provider_location=obj.provider_location,
                    escort_owner=obj.escort_owner,
                )
                obj.pk = saved_booking.pk
                self.log_addition(request, saved_booking, _('Booking created via booking transaction service'))
        except BookingDomainError as e:
            from django.contrib import messages
            messages.error(request, str(e.message))
            return
        except ValidationError as e:
            from django.contrib import messages
            messages.error(request, str(e))
            return
        except Exception as e:
            from django.contrib import messages
            messages.error(request, _("Error saving booking: {}").format(str(e)))
            return


class BookingNoteAdmin(admin.ModelAdmin):
    list_display = ('booking', 'created_by', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('text', 'booking__pet__name')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_by', 'created_at')


class BookingCancellationAdmin(admin.ModelAdmin):
    list_display = ('booking', 'cancelled_by', 'cancelled_by_side', 'reason_code', 'is_abuse', 'abuse_rule', 'created_at')
    list_filter = ('cancelled_by_side', 'reason_code', 'is_abuse', 'abuse_rule', 'created_at')
    search_fields = ('reason', 'booking__pet__name', 'cancelled_by__username', 'reason_code__code', 'reason_code__label')
    fieldsets = (
        (None, {
            'fields': ('booking', 'cancelled_by', 'cancelled_by_side', 'reason_code', 'client_attendance', 'reason')
        }),
        (_('Abuse'), {
            'fields': ('is_abuse', 'abuse_rule')
        })
    )
    readonly_fields = ('booking', 'cancelled_by', 'cancelled_by_side', 'reason_code', 'client_attendance', 'is_abuse', 'abuse_rule', 'created_at')

    def has_add_permission(self, request):
        return False  # Отмены создаются только через API


class BookingPaymentAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для модели платежа.
    """
    list_display = [
        'id', 'booking', 'amount', 'payment_method',
        'transaction_id', 'created_at'
    ]
    list_filter = ['payment_method', 'created_at']
    search_fields = ['booking__id', 'transaction_id']
    readonly_fields = ['created_at']
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('booking', 'amount', 'payment_method')
        }),
        (_('Transaction Details'), {
            'fields': ('transaction_id',)
        }),
        (_('Metadata'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )


class BookingReviewAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для модели отзыва.
    """
    list_display = [
        'id', 'booking', 'rating', 'comment',
        'created_at'
    ]
    list_filter = ['rating', 'created_at']
    search_fields = ['booking__id', 'comment']
    readonly_fields = ['created_at']
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('booking', 'rating', 'comment')
        }),
        (_('Metadata'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )


@admin.register(BookingAutoCompleteSettings)
class BookingAutoCompleteSettingsAdmin(admin.ModelAdmin):
    """Админка для настроек автоматического завершения бронирований"""
    
    list_display = [
        'auto_complete_enabled',
        'auto_complete_days',
        'service_periodicity_hours',
        'service_start_time',
        'manual_booking_emergency_window_hours',
        'updated_at'
    ]
    
    list_editable = [
        'auto_complete_days',
        'service_periodicity_hours',
        'service_start_time',
        'manual_booking_emergency_window_hours',
    ]
    
    list_display_links = ['auto_complete_enabled']
    
    fieldsets = (
        (_('Main Settings'), {
            'fields': (
                'auto_complete_enabled',
                'auto_complete_days',
            )
        }),
        (_('Service Settings'), {
            'fields': (
                'service_periodicity_hours',
                'service_start_time',
                'manual_booking_emergency_window_hours',
            )
        }),
        (_('System Information'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    def has_add_permission(self, request):
        """Разрешить создание только одной записи настроек"""
        return not BookingAutoCompleteSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        """Запретить удаление настроек"""
        return False
    
    def get_queryset(self, request):
        """Всегда показывать только одну запись настроек"""
        return BookingAutoCompleteSettings.objects.filter(id=1)
    
    def save_model(self, request, obj, form, change):
        """Сохранить модель с ID=1"""
        obj.id = 1
        super().save_model(request, obj, form, change)


custom_admin_site.register(AbuseRule, AbuseRuleAdmin)
custom_admin_site.register(BookingStatus, BookingStatusAdmin)
custom_admin_site.register(BookingCancellationReason, BookingCancellationReasonAdmin)
custom_admin_site.register(Booking, BookingAdmin)
custom_admin_site.register(BookingNote, BookingNoteAdmin)
custom_admin_site.register(BookingCancellation, BookingCancellationAdmin)
custom_admin_site.register(BookingPayment, BookingPaymentAdmin)
custom_admin_site.register(BookingReview, BookingReviewAdmin)
custom_admin_site.register(BookingAutoCompleteSettings, BookingAutoCompleteSettingsAdmin)


@admin.register(BookingServiceIssue)
class BookingServiceIssueAdmin(admin.ModelAdmin):
    list_display = ('id', 'booking', 'issue_type', 'reported_by_side', 'status', 'resolution_outcome', 'created_at')
    list_filter = ('status', 'issue_type', 'reported_by_side', 'resolution_outcome', 'resolved_by_actor')
    search_fields = ('booking__code', 'description', 'resolution_note')
    readonly_fields = ('created_at', 'updated_at', 'resolved_at')
    raw_id_fields = ('booking', 'reported_by_user', 'resolved_by_user')

custom_admin_site.register(BookingServiceIssue, BookingServiceIssueAdmin)


@admin.register(ProviderClientLead)
class ProviderClientLeadAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'provider',
        'provider_location',
        'last_name',
        'first_name',
        'phone_number',
        'email',
        'invitation_status',
        'updated_at',
    )
    list_filter = ('provider', 'provider_location', 'source', 'invitation_status')
    search_fields = ('first_name', 'last_name', 'phone_number', 'normalized_phone_number', 'email')
    readonly_fields = ('normalized_phone_number', 'created_at', 'updated_at', 'version')
    raw_id_fields = ('provider', 'provider_location')


@admin.register(ManualBooking)
class ManualBookingAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'code',
        'provider',
        'provider_location',
        'service',
        'employee',
        'owner_last_name',
        'owner_first_name',
        'owner_phone_number',
        'pet_name',
        'size_code',
        'is_emergency',
        'status',
        'start_time',
        'updated_at',
    )
    list_filter = ('provider', 'provider_location', 'status', 'is_emergency', 'service', 'pet_type', 'size_code')
    search_fields = ('code', 'owner_first_name', 'owner_last_name', 'owner_phone_number', 'owner_email', 'pet_name')
    readonly_fields = (
        'code',
        'created_at',
        'updated_at',
        'completed_at',
        'cancelled_at',
        'version',
    )
    raw_id_fields = (
        'provider',
        'provider_location',
        'lead',
        'employee',
        'service',
        'pet_type',
        'breed',
        'created_by',
        'updated_by',
        'completed_by_user',
        'cancelled_by_user',
        'cancellation_reason',
    )


@admin.register(ManualVisitProtocol)
class ManualVisitProtocolAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'manual_booking',
        'protocol_family',
        'service',
        'employee',
        'date',
        'next_date',
        'updated_at',
    )
    list_filter = ('protocol_family', 'provider_location', 'service')
    search_fields = ('manual_booking__code', 'manual_booking__pet_name', 'manual_booking__owner_phone_number')
    readonly_fields = ('created_at', 'updated_at', 'version')
    raw_id_fields = (
        'manual_booking',
        'provider_location',
        'service',
        'employee',
        'created_by',
        'updated_by',
    )


custom_admin_site.register(ProviderClientLead, ProviderClientLeadAdmin)
custom_admin_site.register(ManualBooking, ManualBookingAdmin)
custom_admin_site.register(ManualVisitProtocol, ManualVisitProtocolAdmin)

