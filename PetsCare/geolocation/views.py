"""
Представления для модуля геолокации.

Содержит API представления для:
1. CRUD операций с адресами
2. Валидации адресов через Google Maps API
3. Автодополнения адресов
4. Геокодирования и обратного геокодирования
5. Кэширования результатов
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _

from .models import Address, AddressValidation, AddressCache
from .serializers import (
    AddressSerializer, AddressValidationSerializer, AddressCacheSerializer,
    AddressAutocompleteSerializer, AddressGeocodeSerializer, AddressReverseGeocodeSerializer,
    AddressBulkValidationSerializer
)
from .services import AddressValidationService, GoogleMapsService


class AddressViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing addresses.
    
    Supports:
    - CRUD operations with addresses
    - Automatic validation when creating/updating
    - Filtering by validation status
    - Searching by address components
    """
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Returns filtered queryset of addresses.
        """
        queryset = Address.objects.all()
        
        # Filter by validation status
        validation_status = self.request.query_params.get('validation_status')
        if validation_status:
            queryset = queryset.filter(validation_status=validation_status)
        
        # Filter by country
        country = self.request.query_params.get('country')
        if country:
            queryset = queryset.filter(country__icontains=country)
        
        # Filter by city
        locality = self.request.query_params.get('locality')
        if locality:
            queryset = queryset.filter(locality__icontains=locality)
        
        # Search by address
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                formatted_address__icontains=search
            ) | queryset.filter(
                route__icontains=search
            ) | queryset.filter(
                locality__icontains=search
            )
        
        return queryset.order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def validate(self, request, pk=None):
        """
        Force validation of an address.
        
        Args:
            request: HTTP request
            pk: ID of the address
            
        Returns:
            Response: Validation result
        """
        address = self.get_object()
        
        try:
            with transaction.atomic():
                validation_service = AddressValidationService()
                validation_result = validation_service.validate_address(address)
                
                # Update address with validation results
                if validation_result.is_valid:
                    address.formatted_address = validation_result.formatted_address
                    address.latitude = validation_result.latitude
                    address.longitude = validation_result.longitude
                    address.is_validated = True
                    address.validation_status = 'valid'
                else:
                    address.validation_status = 'invalid'
                
                address.save()
                
                return Response({
                    'success': True,
                    'is_valid': validation_result.is_valid,
                    'formatted_address': validation_result.formatted_address,
                    'latitude': validation_result.latitude,
                    'longitude': validation_result.longitude,
                    'confidence_score': validation_result.confidence_score
                })
                
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Statistics about addresses.
        
        Returns:
            Response: Address statistics
        """
        total_addresses = Address.objects.count()
        validated_addresses = Address.objects.filter(is_validated=True).count()
        invalid_addresses = Address.objects.filter(validation_status='invalid').count()
        pending_addresses = Address.objects.filter(validation_status='pending').count()
        
        return Response({
            'total_addresses': total_addresses,
            'validated_addresses': validated_addresses,
            'invalid_addresses': invalid_addresses,
            'pending_addresses': pending_addresses,
            'validation_rate': (validated_addresses / total_addresses * 100) if total_addresses > 0 else 0
        })


class AddressValidationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing address validation results.
    """
    queryset = AddressValidation.objects.all()
    serializer_class = AddressValidationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Returns filtered queryset of validation results.
        """
        queryset = AddressValidation.objects.all()
        
        # Filter by address
        address_id = self.request.query_params.get('address_id')
        if address_id:
            queryset = queryset.filter(address_id=address_id)
        
        # Filter by validation status
        is_valid = self.request.query_params.get('is_valid')
        if is_valid is not None:
            queryset = queryset.filter(is_valid=is_valid.lower() == 'true')
        
        return queryset.order_by('-created_at')


class AddressCacheViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing geocoding cache.
    """
    queryset = AddressCache.objects.all()
    serializer_class = AddressCacheSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Returns filtered queryset of cache.
        """
        queryset = AddressCache.objects.all()
        
        # Filter by query
        query = self.request.query_params.get('query')
        if query:
            queryset = queryset.filter(query_text__icontains=query)
        
        return queryset.order_by('-created_at')


class AddressAutocompleteView(APIView):
    """
    API for autocomplete addresses via Google Maps API.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def post(self, request):
        """
        Autocomplete address.
        
        Args:
            request: HTTP request with data for autocomplete
            
        Returns:
            Response: List of autocomplete options
        """
        serializer = AddressAutocompleteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        query = serializer.validated_data['query']
        session_token = serializer.validated_data.get('session_token')
        
        try:
            maps_service = GoogleMapsService()
            predictions = maps_service.get_place_autocomplete(query, session_token)

            return Response({
                'success': True,
                'predictions': predictions
            })

        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AddressGeocodeView(APIView):
    """
    API for geocoding an address.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Geocoding an address.
        
        Args:
            request: HTTP request with address for geocoding
            
        Returns:
            Response: Geocoding result
        """
        serializer = AddressGeocodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        address_text = serializer.validated_data['address']
        
        try:
            maps_service = GoogleMapsService()
            geocode_result = maps_service.geocode_address(address_text)
            
            if geocode_result:
                return Response({
                    'success': True,
                    'formatted_address': geocode_result.get('formatted_address'),
                    'latitude': geocode_result.get('geometry', {}).get('location', {}).get('lat'),
                    'longitude': geocode_result.get('geometry', {}).get('location', {}).get('lng'),
                    'place_id': geocode_result.get('place_id'),
                    'components': geocode_result.get('address_components', [])
                })
            else:
                return Response({
                    'success': False,
                    'error': 'Address not found'
                }, status=status.HTTP_404_NOT_FOUND)
                
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AddressReverseGeocodeView(APIView):
    """
    API for reverse geocoding coordinates.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Reverse geocoding coordinates.
        
        Args:
            request: HTTP request with coordinates
            
        Returns:
            Response: Reverse geocoding result
        """
        serializer = AddressReverseGeocodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        latitude = serializer.validated_data['latitude']
        longitude = serializer.validated_data['longitude']
        
        try:
            maps_service = GoogleMapsService()
            reverse_geocode_result = maps_service.reverse_geocode(latitude, longitude)
            
            if reverse_geocode_result:
                return Response({
                    'success': True,
                    'formatted_address': reverse_geocode_result.get('formatted_address'),
                    'place_id': reverse_geocode_result.get('place_id'),
                    'components': reverse_geocode_result.get('address_components', [])
                })
            else:
                return Response({
                    'success': False,
                    'error': 'Address for coordinates not found'
                }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AddressValidationBulkView(APIView):
    """
    API for mass address validation.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Mass address validation.
        
        Args:
            request: HTTP request with list of addresses
            
        Returns:
            Response: Validation results
        """
        address_ids = request.data.get('address_ids', [])
        
        if not address_ids:
            return Response({
                'error': 'No address IDs specified for validation'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                validation_service = AddressValidationService()
                results = []
                
                for address_id in address_ids:
                    try:
                        address = Address.objects.get(id=address_id)
                        validation_result = validation_service.validate_address(address)
                        
                        # Update address
                        if validation_result.is_valid:
                            address.formatted_address = validation_result.formatted_address
                            address.latitude = validation_result.latitude
                            address.longitude = validation_result.longitude
                            address.is_validated = True
                            address.validation_status = 'valid'
                        else:
                            address.validation_status = 'invalid'
                        
                        address.save()
                        
                        results.append({
                            'address_id': address_id,
                            'success': True,
                            'is_valid': validation_result.is_valid
                        })
                        
                    except Address.DoesNotExist:
                        results.append({
                            'address_id': address_id,
                            'success': False,
                            'error': 'Address not found'
                        })
                
                return Response({
                    'success': True,
                    'results': results
                })
                
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 