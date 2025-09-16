from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .models import BookingStatus, Booking, BookingNote, BookingCancellation, AbuseRule, BookingPayment, BookingReview, BookingAutoCompleteSettings
from custom_admin import custom_admin_site


class BookingNoteInline(admin.TabularInline):
    model = BookingNote
    extra = 0
    fields = ('text', 'created_by', 'created_at')
    readonly_fields = ('created_by', 'created_at')


class BookingCancellationInline(admin.TabularInline):
    model = BookingCancellation
    extra = 0
    fields = ('cancelled_by', 'reason', 'is_abuse', 'abuse_rule', 'created_at')
    readonly_fields = ('cancelled_by', 'is_abuse', 'abuse_rule', 'created_at')


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


class BookingAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для модели бронирования.
    """
    list_display = [
        'id', 'user', 'pet', 'provider', 'employee',
        'service', 'status', 'start_time', 'end_time',
        'price', 'created_at', 'completed_at', 'cancelled_at'
    ]
    list_filter = [
        'status', 'start_time', 'end_time',
        'created_at', 'updated_at', 'completed_at', 'cancelled_at'
    ]
    search_fields = [
        'user__username', 'pet__name', 'provider__name',
        'employee__user__username', 'service__name'
    ]
    readonly_fields = [
        'created_at', 'updated_at', 'completed_at', 'cancelled_at',
        'completed_by', 'cancelled_by', 'cancellation_reason'
    ]
    date_hierarchy = 'created_at'
    inlines = [BookingNoteInline, BookingCancellationInline]
    
    actions = ['complete_bookings', 'cancel_bookings', 'mark_no_show']
    
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
                    BookingCompletionService.complete_booking(booking, request.user, 'no_show')
                    marked_count += 1
                except Exception as e:
                    self.message_user(request, _("Error marking booking {}: {}").format(booking.id, e), level='ERROR')
        
        self.message_user(request, _("Marked as 'no show' {} bookings").format(marked_count))
    
    mark_no_show.short_description = _("Mark as 'no show'")
    fieldsets = (
        (None, {
            'fields': ('pet', 'provider_service', 'employee')
        }),
        (_('Time'), {
            'fields': ('start_time', 'end_time')
        }),
        (_('Status'), {
            'fields': ('status', 'price', 'description')
        }),
        (_('Metadata'), {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def save_model(self, request, obj, form, change):
        """
        Сохраняет модель бронирования с транзакционной защитой.
        """
        from .services import BookingTransactionService
        
        try:
            if change:
                # Обновление существующего бронирования
                BookingTransactionService.update_booking(
                    booking_id=obj.id,
                    new_start_time=obj.start_time,
                    new_end_time=obj.end_time,
                    new_employee=obj.employee,
                    new_service=obj.service,
                    new_price=obj.price,
                    new_notes=obj.notes
                )
            else:
                # Создание нового бронирования
                BookingTransactionService.create_booking(
                    user=obj.user,
                    pet=obj.pet,
                    provider=obj.provider,
                    employee=obj.employee,
                    service=obj.service,
                    start_time=obj.start_time,
                    end_time=obj.end_time,
                    price=obj.price,
                    notes=obj.notes
                )
        except ValidationError as e:
            from django.contrib import messages
            messages.error(request, str(e))
            return
        except Exception as e:
            from django.contrib import messages
            messages.error(request, _("Error saving booking: {}").format(str(e)))
            return
        
        super().save_model(request, obj, form, change)


class BookingNoteAdmin(admin.ModelAdmin):
    list_display = ('booking', 'created_by', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('text', 'booking__pet__name')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_by', 'created_at')


class BookingCancellationAdmin(admin.ModelAdmin):
    list_display = ('booking', 'cancelled_by', 'is_abuse', 'abuse_rule', 'created_at')
    list_filter = ('is_abuse', 'abuse_rule', 'created_at')
    search_fields = ('reason', 'booking__pet__name', 'cancelled_by__username')
    fieldsets = (
        (None, {
            'fields': ('booking', 'cancelled_by', 'reason')
        }),
        (_('Abuse'), {
            'fields': ('is_abuse', 'abuse_rule')
        })
    )
    readonly_fields = ('booking', 'cancelled_by', 'is_abuse', 'abuse_rule', 'created_at')

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
        'auto_complete_status',
        'service_periodicity_hours',
        'service_start_time',
        'updated_at'
    ]
    
    list_editable = [
        'auto_complete_days',
        'auto_complete_status',
        'service_periodicity_hours',
        'service_start_time'
    ]
    
    list_display_links = ['auto_complete_enabled']
    
    fieldsets = (
        (_('Main Settings'), {
            'fields': (
                'auto_complete_enabled',
                'auto_complete_days',
                'auto_complete_status',
            )
        }),
        (_('Service Settings'), {
            'fields': (
                'service_periodicity_hours',
                'service_start_time',
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
custom_admin_site.register(Booking, BookingAdmin)
custom_admin_site.register(BookingNote, BookingNoteAdmin)
custom_admin_site.register(BookingCancellation, BookingCancellationAdmin)
custom_admin_site.register(BookingPayment, BookingPaymentAdmin)
custom_admin_site.register(BookingReview, BookingReviewAdmin)
