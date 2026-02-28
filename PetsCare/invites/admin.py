"""
Django Admin для единой модели Invite.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from custom_admin import custom_admin_site
from .models import Invite


class InviteAdmin(admin.ModelAdmin):
    """Единый админ для всех типов инвайтов."""

    list_display = [
        'id',
        'invite_type',
        'email',
        'status',
        'provider_display',
        'location_display',
        'pet_display',
        'expires_at',
        'created_at',
    ]
    list_filter = ['invite_type', 'status', 'created_at']
    search_fields = ['email', 'provider__name', 'provider_location__name', 'token']
    readonly_fields = ['token', 'created_at', 'accepted_at', 'declined_at']

    def provider_display(self, obj):
        return obj.provider.name if obj.provider else '—'

    provider_display.short_description = _('Provider')

    def location_display(self, obj):
        return obj.provider_location.name if obj.provider_location else '—'

    location_display.short_description = _('Location')

    def pet_display(self, obj):
        return obj.pet.name if obj.pet else '—'

    pet_display.short_description = _('Pet')


custom_admin_site.register(Invite, InviteAdmin)
