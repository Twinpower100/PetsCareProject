from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import PetType, Breed, SizeRule, Pet, MedicalRecord, PetRecord, PetRecordFile, User, DocumentType
from custom_admin import custom_admin_site
from django import forms
import json


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


class MedicalRecordInline(admin.StackedInline):
    model = MedicalRecord
    extra = 0
    fields = ('date', 'title', 'description', 'attachments', 'next_visit')


class PetRecordInline(admin.StackedInline):
    model = PetRecord
    extra = 0
    fields = (
        'service', 'provider_location', 'employee',
        'date', 'next_date', 'description', 'results',
        'recommendations', 'notes', 'serial_number', 'files'
    )
    raw_id_fields = ('provider_location', 'employee', 'files')


class PetAdminForm(forms.ModelForm):
    class Meta:
        model = Pet
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Настраиваем queryset для всех активных пользователей
        active_users = User.objects.filter(is_active=True).order_by('email')
        
        if self.instance and self.instance.pk:
            # Для существующего питомца показываем всех активных пользователей
            # чтобы можно было добавить новых владельцев
            self.fields['owners'].queryset = active_users
        else:
            # Для нового питомца показываем всех активных пользователей
            self.fields['owners'].queryset = active_users
        
        # Настраиваем отображение пользователей для основного владельца
        self.fields['main_owner'].queryset = active_users
        
        # Поле owners обязательно для заполнения
        self.fields['owners'].required = True
        
        # Настраиваем JSON поля как опциональные
        self.fields['special_needs'].required = False
        self.fields['medical_conditions'].required = False
        
        # Настраиваем виджеты для JSON полей
        self.fields['special_needs'].widget = forms.Textarea(attrs={
            'rows': 4,
            'cols': 80,
            'placeholder': '{"diet": "Специальная диета", "medications": ["Витамины"]}'
        })
        self.fields['medical_conditions'].widget = forms.Textarea(attrs={
            'rows': 4,
            'cols': 80,
            'placeholder': '{"chronic_conditions": ["Диабет"], "allergies": ["Курица"]}'
        })
    
    def clean(self):
        cleaned_data = super().clean()
        main_owner = cleaned_data.get('main_owner')
        owners = cleaned_data.get('owners')
        
        # Проверяем, что есть хотя бы один владелец
        if not owners:
            raise forms.ValidationError({'owners': _('There must be at least one owner.')})
        
        # Проверяем, что основной владелец входит в список владельцев
        if main_owner and main_owner not in owners:
            raise forms.ValidationError({
                'main_owner': _('Main owner must be in owners list.'),
                'owners': _('Please select the main owner in the owners list.')
            })
        
        # Валидируем JSON поля
        special_needs = cleaned_data.get('special_needs')
        medical_conditions = cleaned_data.get('medical_conditions')
        
        if special_needs:
            try:
                if isinstance(special_needs, str):
                    json.loads(special_needs)
            except json.JSONDecodeError:
                raise forms.ValidationError({
                    'special_needs': _('Invalid JSON format for special needs.')
                })
        
        if medical_conditions:
            try:
                if isinstance(medical_conditions, str):
                    json.loads(medical_conditions)
            except json.JSONDecodeError:
                raise forms.ValidationError({
                    'medical_conditions': _('Invalid JSON format for medical conditions.')
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        """Переопределяем save для правильной обработки ManyToMany полей"""
        instance = super().save(commit=False)
        
        # Сохраняем ManyToMany данные
        owners_data = self.cleaned_data.get('owners', [])
        
        if commit:
            # Сохраняем объект
            instance.save()
            
            # Устанавливаем ManyToMany связи
            instance.owners.set(owners_data)
        else:
            # Если не commit, сохраняем данные для последующего использования
            instance._owners_data = owners_data
        
        return instance


class PetAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для модели питомца.
    """
    list_display = [
        'id', 'name', 'pet_type', 'breed',
        'birth_date', 'main_owner', 'is_active'
    ]
    list_filter = ['pet_type', 'birth_date', 'is_active']
    search_fields = ['name', 'breed', 'main_owner__email']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'pet_type', 'breed', 'birth_date', 'is_active')
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
    
    def save_model(self, request, obj, form, change):
        """Переопределяем save_model для правильной обработки ManyToMany полей"""
        # Сохраняем объект
        obj.save()
        
        # Устанавливаем ManyToMany связи
        if 'owners' in form.cleaned_data:
            obj.owners.set(form.cleaned_data['owners'])


class MedicalRecordAdmin(admin.ModelAdmin):
    list_display = ('title', 'pet', 'date', 'next_visit')
    list_filter = ('date', 'next_visit')
    search_fields = ('title', 'description', 'pet__name')
    date_hierarchy = 'date'


@admin.register(PetRecord)
class PetRecordAdmin(admin.ModelAdmin):
    list_display = ('pet', 'service', 'provider_location', 'get_provider', 'employee', 'date', 'next_date')
    list_filter = ('date', 'next_date', 'provider_location')
    search_fields = ('pet__name', 'service__name', 'provider_location__name', 'provider_location__provider__name', 'description', 'results')
    raw_id_fields = ('pet', 'provider_location', 'employee', 'files')
    readonly_fields = ('created_at', 'updated_at', 'get_provider')
    
    def get_provider(self, obj):
        """Отображает название организации провайдера."""
        if obj.provider_location:
            return obj.provider_location.provider.name
        elif obj.provider:
            return obj.provider.name
        return '-'
    get_provider.short_description = _('Provider Organization')


class PetRecordFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name', 'description')
    date_hierarchy = 'created_at'


custom_admin_site.register(PetType, PetTypeAdmin)
custom_admin_site.register(Breed, BreedAdmin)
custom_admin_site.register(SizeRule, SizeRuleAdmin)
custom_admin_site.register(Pet, PetAdmin)
custom_admin_site.register(MedicalRecord, MedicalRecordAdmin)
custom_admin_site.register(PetRecordFile, PetRecordFileAdmin)
custom_admin_site.register(DocumentType)
