from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import PetType, Breed, SizeRule, Pet, PetHealthNote, VisitRecord, PetDocument, User, DocumentType, ChronicCondition, PhysicalFeature, BehavioralTrait, PetOwner, VisitRecordAddendum
from custom_admin import custom_admin_site
from django import forms
import json

from .document_type_catalog import get_document_type_order_expression


class PetTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'description')
    search_fields = ('name',)


class BreedAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'pet_type', 'description')
    list_filter = ('pet_type',)
    search_fields = ('name', 'pet_type__name')


class SizeRuleAdmin(admin.ModelAdmin):
    """Правила весовых диапазонов по типу питомца (S/M/L/XL) для ценообразования."""
    list_display = ('pet_type', 'size_code', 'min_weight_kg', 'max_weight_kg')
    list_filter = ('pet_type', 'size_code')
    search_fields = ('pet_type__code', 'pet_type__name')
    ordering = ('pet_type', 'min_weight_kg')


class ChronicConditionAdmin(admin.ModelAdmin):
    """Справочник хронических заболеваний для карточки питомца."""
    list_display = ('code', 'name', 'name_ru', 'name_en', 'category', 'order')
    list_filter = ('category',)
    search_fields = ('code', 'name', 'name_ru', 'name_en')
    ordering = ('category', 'order', 'code')


class PhysicalFeatureAdmin(admin.ModelAdmin):
    """Справочник физических особенностей (отсутствие конечностей, слепота и т.д.)."""
    list_display = ('code', 'name', 'name_ru', 'name_en', 'order')
    search_fields = ('code', 'name')
    ordering = ('order', 'code')


class BehavioralTraitAdmin(admin.ModelAdmin):
    """Справочник поведенческих особенностей."""
    list_display = ('code', 'name', 'name_ru', 'name_en', 'order')
    search_fields = ('code', 'name')
    ordering = ('order', 'code')


class PetHealthNoteInline(admin.StackedInline):
    model = PetHealthNote
    extra = 0
    fields = ('date', 'title', 'description', 'next_visit')


class VisitRecordInline(admin.StackedInline):
    model = VisitRecord
    extra = 0
    fields = (
        'service', 'provider_location', 'employee',
        'date', 'next_date', 'description', 'results',
        'recommendations', 'notes', 'serial_number'
    )
    raw_id_fields = ('provider_location', 'employee')



class PetOwnerInline(admin.TabularInline):
    """Inline для управления владельцами питомца (через PetOwner)."""
    model = PetOwner
    extra = 1
    fields = ('user', 'role', 'created_at')
    readonly_fields = ('created_at',)
    raw_id_fields = ('user',)
    verbose_name = _('Owner')
    verbose_name_plural = _('Owners')


class PetAdminForm(forms.ModelForm):
    class Meta:
        model = Pet
        exclude = ('owners',)  # owners управляется через PetOwnerInline

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Настраиваем JSON поля как опциональные
        if 'special_needs' in self.fields:
            self.fields['special_needs'].required = False
            self.fields['special_needs'].widget = forms.Textarea(attrs={
                'rows': 4, 'cols': 80,
                'placeholder': '{"diet": "Специальная диета", "medications": ["Витамины"]}'
            })
        if 'medical_conditions' in self.fields:
            self.fields['medical_conditions'].required = False
            self.fields['medical_conditions'].widget = forms.Textarea(attrs={
                'rows': 4, 'cols': 80,
                'placeholder': '{"chronic_conditions": ["Диабет"], "allergies": ["Курица"]}'
            })
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Валидируем JSON поля
        for field_name in ('special_needs', 'medical_conditions'):
            value = cleaned_data.get(field_name)
            if value:
                try:
                    if isinstance(value, str):
                        json.loads(value)
                except json.JSONDecodeError:
                    raise forms.ValidationError({
                        field_name: _('Invalid JSON format.')
                    })
        
        return cleaned_data


class PetAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для модели питомца.
    Владельцы управляются через PetOwnerInline.
    """
    list_display = [
        'id', 'name', 'pet_type', 'breed',
        'birth_date', 'get_main_owner', 'is_active'
    ]
    list_filter = ['pet_type', 'birth_date', 'is_active']
    search_fields = ['name', 'breed__name', 'petowner__user__email']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [PetOwnerInline, PetHealthNoteInline, VisitRecordInline]
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'pet_type', 'breed', 'birth_date', 'is_active')
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

    @admin.display(description=_('Main Owner'))
    def get_main_owner(self, obj):
        mo = obj.main_owner
        return mo.email if mo else '-'


class PetHealthNoteAdmin(admin.ModelAdmin):
    list_display = ('title', 'pet', 'date', 'next_visit')
    list_filter = ('date', 'next_visit')
    search_fields = ('title', 'description', 'pet__name')
    date_hierarchy = 'date'


@admin.register(VisitRecord)
class VisitRecordAdmin(admin.ModelAdmin):
    list_display = ('pet', 'service', 'provider_location', 'get_provider', 'employee', 'date', 'next_date')
    list_filter = ('date', 'next_date', 'provider_location')
    search_fields = ('pet__name', 'service__name', 'provider_location__name', 'provider_location__provider__name', 'description', 'results')
    raw_id_fields = ('pet', 'provider_location', 'employee')
    readonly_fields = ('created_at', 'updated_at', 'get_provider')
    
    def get_provider(self, obj):
        """Отображает название организации провайдера."""
        if obj.provider_location:
            return obj.provider_location.provider.name
        elif obj.provider:
            return obj.provider.name
        return '-'
    get_provider.short_description = _('Provider Organization')


class PetDocumentAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name', 'description')
    date_hierarchy = 'created_at'


class DocumentTypeAdmin(admin.ModelAdmin):
    """Админка фиксированного каталога типов документов питомца."""

    list_display = (
        'name',
        'code',
        'requires_issue_date',
        'requires_expiry_date',
        'requires_issuing_authority',
        'requires_document_number',
        'is_active',
    )
    list_editable = ('is_active',)
    readonly_fields = (
        'code',
        'description',
        'name_en',
        'name_ru',
        'name_me',
        'name_de',
        'requires_issue_date',
        'requires_expiry_date',
        'requires_issuing_authority',
        'requires_document_number',
        'created_at',
        'updated_at',
    )
    search_fields = ('name', 'code')

    def get_queryset(self, request):
        """Возвращает каталог в согласованном бизнес-порядке."""
        return super().get_queryset(request).order_by(
            get_document_type_order_expression(),
            'id',
        )


class VisitRecordAddendumAdmin(admin.ModelAdmin):
    list_display = ('id', 'visit_record', 'author', 'created_at')
    search_fields = ('content', 'author__email', 'visit_record__pet__name')
    raw_id_fields = ('visit_record', 'author')
    readonly_fields = ('created_at', 'updated_at')



custom_admin_site.register(PetType, PetTypeAdmin)
custom_admin_site.register(Breed, BreedAdmin)
custom_admin_site.register(SizeRule, SizeRuleAdmin)
custom_admin_site.register(ChronicCondition, ChronicConditionAdmin)
custom_admin_site.register(PhysicalFeature, PhysicalFeatureAdmin)
custom_admin_site.register(BehavioralTrait, BehavioralTraitAdmin)
custom_admin_site.register(Pet, PetAdmin)
custom_admin_site.register(PetOwner)
custom_admin_site.register(PetHealthNote, PetHealthNoteAdmin)
custom_admin_site.register(VisitRecord, VisitRecordAdmin)
custom_admin_site.register(PetDocument, PetDocumentAdmin)
custom_admin_site.register(DocumentType, DocumentTypeAdmin)
custom_admin_site.register(VisitRecordAddendum, VisitRecordAddendumAdmin)
