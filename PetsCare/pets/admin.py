from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import PetType, Breed, Pet, MedicalRecord, PetRecord, PetRecordFile, User, DocumentType
from custom_admin import custom_admin_site
from django import forms


class PetTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'description')
    search_fields = ('name',)


class BreedAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'pet_type', 'description')
    list_filter = ('pet_type',)
    search_fields = ('name', 'pet_type__name')


class MedicalRecordInline(admin.StackedInline):
    model = MedicalRecord
    extra = 0
    fields = ('date', 'title', 'description', 'attachments', 'next_visit')


class PetRecordInline(admin.StackedInline):
    model = PetRecord
    extra = 0
    fields = (
        'service_category', 'service', 'provider', 'employee',
        'date', 'next_date', 'description', 'results',
        'recommendations', 'notes', 'serial_number', 'files'
    )
    raw_id_fields = ('provider', 'employee', 'files')


class PetAdminForm(forms.ModelForm):
    class Meta:
        model = Pet
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Для существующего питомца показываем только текущих владельцев
            self.fields['owners'].queryset = self.instance.owners.all()
        else:
            # Для нового питомца поле пустое
            self.fields['owners'].queryset = User.objects.none()


class PetAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для модели питомца.
    """
    list_display = [
        'id', 'name', 'pet_type', 'breed',
        'birth_date', 'main_owner'
    ]
    list_filter = ['pet_type', 'birth_date']
    search_fields = ['name', 'breed', 'main_owner__username']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'pet_type', 'breed', 'birth_date')
        }),
        (_('Ownership'), {
            'fields': ('main_owner', 'owners')
        }),
        (_('Physical Characteristics'), {
            'fields': ('weight',)
        }),
        (_('Additional Information'), {
            'fields': ('description', 'special_needs', 'medical_conditions')
        }),
        (_('Photo'), {
            'fields': ('photo',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    form = PetAdminForm


class MedicalRecordAdmin(admin.ModelAdmin):
    list_display = ('title', 'pet', 'date', 'next_visit')
    list_filter = ('date', 'next_visit')
    search_fields = ('title', 'description', 'pet__name')
    date_hierarchy = 'date'


@admin.register(PetRecord)
class PetRecordAdmin(admin.ModelAdmin):
    list_display = ('pet', 'service', 'provider', 'employee', 'date', 'next_date')
    list_filter = ('date', 'next_date')
    search_fields = ('pet__name', 'service__name', 'description', 'results')
    raw_id_fields = ('pet', 'provider', 'employee', 'files')
    readonly_fields = ('created_at', 'updated_at')


class PetRecordFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name', 'description')
    date_hierarchy = 'created_at'


custom_admin_site.register(PetType, PetTypeAdmin)
custom_admin_site.register(Breed, BreedAdmin)
custom_admin_site.register(Pet, PetAdmin)
custom_admin_site.register(MedicalRecord, MedicalRecordAdmin)
custom_admin_site.register(PetRecordFile, PetRecordFileAdmin)
custom_admin_site.register(DocumentType)
