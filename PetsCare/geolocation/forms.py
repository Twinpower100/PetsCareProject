"""
Forms for the geolocation module.

Contains forms for:
1. Creating and editing addresses
2. Address validation
3. Address search
"""

from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Address, AddressValidation
from .services import AddressValidationService


class AddressForm(forms.ModelForm):
    """
    Форма для создания и редактирования адресов.
    
    Особенности:
    - Автоматическая валидация через Google Maps API
    - Поддержка автодополнения
    - Валидация обязательных полей
    """
    
    # Additional fields for convenience
    full_address = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Enter full address for auto-fill')
        }),
        help_text=_('Enter full address for automatic field filling')
    )
    
    auto_validate = forms.BooleanField(
        required=False,
        initial=True,
        help_text=_('Automatically validate address through Google Maps API')
    )
    
    class Meta:
        model = Address
        fields = [
            'house_number', 'street', 'city', 'region',
            'district', 'country', 'postal_code'
        ]
        widgets = {
            'house_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('House number')
            }),
            'street': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Street')
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('City')
            }),
            'region': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Region/State')
            }),
            'district': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('District')
            }),
            'country': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Country')
            }),
            'postal_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Postal code')
            }),
        }
    
    def clean(self):
        """
        Validates the form and performs geocoding if necessary.
        
        Returns:
            dict: Cleaned data
            
        Raises:
            forms.ValidationError: If validation fails
        """
        cleaned_data = super().clean()
        
        # Check if at least one address component is specified
        required_fields = ['house_number', 'street', 'city', 'country']
        if not any(cleaned_data.get(field) for field in required_fields):
            if not cleaned_data.get('full_address'):
                raise forms.ValidationError(
                    _("At least one address component or full address must be specified")
                )
        
        # If a full address is specified, try to parse it
        full_address = cleaned_data.get('full_address')
        if full_address:
            try:
                validation_service = AddressValidationService()
                # Create a temporary address for geocoding
                temp_address = Address(
                    house_number=cleaned_data.get('house_number', ''),
                    street=cleaned_data.get('street', ''),
                    city=cleaned_data.get('city', ''),
                    region=cleaned_data.get('region', ''),
                    district=cleaned_data.get('district', ''),
                    country=cleaned_data.get('country', ''),
                    postal_code=cleaned_data.get('postal_code', '')
                )
                
                # Perform geocoding
                is_valid = validation_service.validate_address(temp_address)
                
                if is_valid:
                    cleaned_data['formatted_address'] = temp_address.formatted_address
                    cleaned_data['latitude'] = temp_address.latitude
                    cleaned_data['longitude'] = temp_address.longitude
                    cleaned_data['is_valid'] = True
                    cleaned_data['is_geocoded'] = bool(temp_address.point)
                    cleaned_data['is_validated'] = True
                    cleaned_data['validation_status'] = 'valid'
                else:
                    cleaned_data['is_valid'] = False
                    cleaned_data['is_validated'] = True
                    cleaned_data['validation_status'] = 'invalid'
                    
            except Exception as e:
                raise forms.ValidationError(
                    _("Error during address geocoding: %(error)s") % {'error': str(e)}
                )
        
        return cleaned_data
    
    def save(self, commit=True):
        """
        Saves the address with validation.
        
        Args:
            commit (bool): Save to database
            
        Returns:
            Address: Saved address
        """
        instance = super().save(commit=False)
        
        # If automatic validation is enabled and the address is not validated
        if self.cleaned_data.get('auto_validate') and not instance.is_validated:
            try:
                validation_service = AddressValidationService()
                validation_service.validate_address(instance)
                    
            except Exception:
                # If validation fails, save without validation
                instance.validation_status = 'pending'
        
        if commit:
            instance.save()
        
        return instance


class AddressSearchForm(forms.Form):
    """
    Form for searching addresses.
    """
    
    search_query = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by address, city, country...'
        }),
        help_text=_('Enter text to search for addresses')
    )
    
    validation_status = forms.ChoiceField(
        choices=[
            ('', 'All statuses'),
            ('pending', 'Waiting for validation'),
            ('valid', 'Valid'),
            ('invalid', 'Invalid')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text=_('Filter by validation status')
    )
    
    country = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Country'
        }),
        help_text=_('Filter by country')
    )
    
    locality = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'City'
        }),
        help_text=_('Filter by city')
    )


class AddressValidationForm(forms.Form):
    """
    Form for forced address validation.
    """
    
    address_id = forms.IntegerField(
        widget=forms.HiddenInput(),
        help_text=_('ID of address to validate')
    )
    
    force_validation = forms.BooleanField(
        required=False,
        initial=True,
        help_text=_('Forcefully revalidate address')
    )
    
    def clean_address_id(self):
        """
        Checks the existence of the address.
        
        Returns:
            int: Address ID
            
        Raises:
            forms.ValidationError: If address not found
        """
        address_id = self.cleaned_data['address_id']
        try:
            Address.objects.get(id=address_id)
        except Address.DoesNotExist:
            raise forms.ValidationError(_("Address with specified ID not found"))
        return address_id


class AddressBulkValidationForm(forms.Form):
    """
    Form for mass address validation.
    """
    
    address_ids = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'Enter address IDs separated by comma or new line'
        }),
        help_text=_('IDs of addresses for mass validation (separated by comma or new line)')
    )
    
    def clean_address_ids(self):
        """
        Cleans and validates a list of address IDs.
        
        Returns:
            list: List of address IDs
            
        Raises:
            forms.ValidationError: If validation fails
        """
        address_ids_text = self.cleaned_data['address_ids']
        
        # Parse address IDs
        address_ids = []
        for line in address_ids_text.split('\n'):
            for item in line.split(','):
                item = item.strip()
                if item:
                    try:
                        address_id = int(item)
                        address_ids.append(address_id)
                    except ValueError:
                        raise forms.ValidationError(
                            _("Invalid address ID: %(id)s") % {'id': item}
                        )
        
        if not address_ids:
            raise forms.ValidationError(_("No address IDs specified for validation"))
        
        # Check the existence of addresses
        existing_ids = set(Address.objects.filter(id__in=address_ids).values_list('id', flat=True))
        missing_ids = set(address_ids) - existing_ids
        
        if missing_ids:
            raise forms.ValidationError(
                _("The following addresses not found: %(ids)s") % {'ids': ', '.join(map(str, missing_ids))}
            )
        
        return address_ids 