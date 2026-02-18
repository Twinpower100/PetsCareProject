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
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
import logging

from .models import Address, AddressValidation, AddressCache
from .serializers import (
    AddressSerializer, AddressValidationSerializer, AddressCacheSerializer,
    AddressAutocompleteSerializer, PlaceDetailsSerializer,
    AddressGeocodeSerializer, AddressReverseGeocodeSerializer
)
from .services import AddressValidationService, GoogleMapsService

logger = logging.getLogger(__name__)


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
            queryset = queryset.filter(city__icontains=locality)
        
        # Search by address
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(formatted_address__icontains=search) |
                Q(street__icontains=search) |
                Q(house_number__icontains=search) |
                Q(building__icontains=search) |
                Q(city__icontains=search) |
                Q(district__icontains=search) |
                Q(region__icontains=search) |
                Q(country__icontains=search)
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
                is_valid = validation_service.validate_address(address)  # bool; service already saves address
                address.refresh_from_db()
                
                return Response({
                    'success': True,
                    'is_valid': is_valid,
                    'formatted_address': address.formatted_address or '',
                    'latitude': float(address.latitude) if address.latitude is not None else None,
                    'longitude': float(address.longitude) if address.longitude is not None else None,
                    'validation_status': address.validation_status,
                })
                
        except Exception as e:
            logger.exception("Address validation failed: %s", e)
            return Response({
                'success': False,
                'error': _('Unexpected error')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Statistics about addresses.
        
        Returns:
            Response: Address statistics
        """
        total_addresses = Address.objects.count()
        validated_addresses = Address.objects.exclude(validation_status='pending').count()
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
        
        try:
            maps_service = GoogleMapsService()
            predictions = maps_service.autocomplete_address(query)

            return Response({
                'success': True,
                'predictions': predictions
            })

        except Exception as e:
            logger.exception("Address autocomplete failed: %s", e)
            return Response({
                'success': False,
                'error': _('Unexpected error')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PlaceDetailsView(APIView):
    """
    API Place Details по place_id: полный адрес (с номером дома), координаты, компоненты.
    Вызывается после выбора подсказки автодополнения.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PlaceDetailsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        place_id = serializer.validated_data['place_id']
        try:
            maps_service = GoogleMapsService()
            details = maps_service.get_place_details(place_id)
            if not details:
                return Response({'success': False, 'error': _('Place not found')}, status=status.HTTP_404_NOT_FOUND)
            return Response({'success': True, **details})
        except ValueError as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.exception("Place details failed: %s", e)
            return Response({'success': False, 'error': _('Unexpected error')}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
        
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            maps_service = GoogleMapsService()
            
            # Просто используем Google Maps API напрямую - он умеет обрабатывать адреса в разных форматах
            geocode_result = maps_service.geocode_address(address_text.strip())
            
            if geocode_result:
                # Извлекаем координаты из структуры, возвращаемой _parse_geocoding_result
                coordinates = geocode_result.get('coordinates', {})
                return Response({
                    'success': True,
                    'formatted_address': geocode_result.get('formatted_address'),
                    'latitude': float(coordinates.get('latitude')) if coordinates.get('latitude') else None,
                    'longitude': float(coordinates.get('longitude')) if coordinates.get('longitude') else None,
                    'place_id': geocode_result.get('place_id'),
                    'components': geocode_result.get('address_components', [])
                })
            else:
                return Response({
                    'success': False,
                    'error': 'Address not found'
                }, status=status.HTTP_404_NOT_FOUND)
                
        except ValueError as e:
            # Ошибка с API ключом Google Maps
            error_msg = str(e)
            logger.error(f"Google Maps API key error: {error_msg}")
            return Response({
                'success': False,
                'error': 'Google Maps API configuration error. Please contact administrator.',
                'details': error_msg if 'REQUEST_DENIED' in error_msg or 'invalid' in error_msg.lower() else None
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.exception("Unexpected error in geocoding: %s", e)
            return Response({
                'success': False,
                'error': _('Unexpected error')
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
            logger.exception("Reverse geocoding failed: %s", e)
            return Response({
                'success': False,
                'error': _('Unexpected error')
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
                        is_valid = validation_service.validate_address(address)  # bool; service already saves
                        address.refresh_from_db()
                        results.append({
                            'address_id': address_id,
                            'success': True,
                            'is_valid': is_valid,
                            'validation_status': address.validation_status,
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
            logger.exception("Bulk address validation failed: %s", e)
            return Response({
                'success': False,
                'error': _('Unexpected error')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class HolidaysAPIView(APIView):
    """
    API нерабочих дней по стране и году: государственные праздники + наблюдаемые даты (переносы).
    Используется при настройке графика работы локации (закрыто в праздники).
    Источник: библиотека holidays (country_holidays) с observed=True — для стран вроде РФ
    включаются дни, когда праздник переносится (напр. с воскресенья на понедельник).
    Это не полный производственный календарь РФ (все переносы могут отличаться от приказа Минтруда).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        country = request.query_params.get('country', '').upper()[:2]
        year_str = request.query_params.get('year', '')
        lang = (request.query_params.get('lang') or 'en').strip().lower()[:5]
        # Язык для названий праздников: en, de, ru, sr (и т.д.) — как поддерживает библиотека holidays
        if not lang or len(lang) < 2:
            lang = 'en'
        if not country or not year_str:
            return Response(
                {'error': _('Query parameters "country" (ISO 3166-1 alpha-2) and "year" are required.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            year = int(year_str)
        except ValueError:
            return Response(
                {'error': _('Parameter "year" must be an integer.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        if year < 2000 or year > 2100:
            return Response(
                {'error': _('Year must be between 2000 and 2100.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            import holidays as holidays_lib
            # observed=True: включать даты, когда праздник отмечается (перенос с выходного на рабочий день)
            # language: язык названий праздников (en, de, ru, sr и т.д.); при ошибке — откат на en
            try:
                country_holidays = holidays_lib.country_holidays(
                    country, years=year, observed=True, language=lang
                )
            except (ValueError, TypeError):
                country_holidays = holidays_lib.country_holidays(
                    country, years=year, observed=True, language='en'
                )
            items = [
                {'date': d.isoformat(), 'name': name or ''}
                for d, name in sorted(country_holidays.items())
            ]
            return Response({'country': country, 'year': year, 'holidays': items})
        except NotImplementedError:
            return Response(
                {'error': _('Holidays for this country are not supported.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.exception("Holidays API failed: %s", e)
            return Response(
                {'error': _('Unexpected error')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )