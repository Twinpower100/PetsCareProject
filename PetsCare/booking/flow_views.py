from datetime import datetime

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.models import ProviderBlocking
from catalog.models import Service
from pets.models import Pet
from providers.models import Employee, ProviderLocation, ProviderLocationService
from users.models import User
from users.email_verification_permissions import IsVerifiedForOwnerWriteActions

from .location_search import LocationSearchPayload, filter_locations_by_payload
from .routing import RoutingUnavailableError
from .services import BookingAvailabilityService, BookingDomainError, BookingTransactionService


def _get_request_language_code(request):
    """Возвращает поддерживаемый код языка из query/header/LocaleMiddleware."""
    language_code = (request.query_params.get('lang') or '').strip()
    if not language_code:
        language_code = getattr(request, 'LANGUAGE_CODE', '') or ''
    if not language_code:
        raw_header = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        language_code = raw_header.split(',')[0].split(';')[0].strip()

    language_code = (language_code or 'en').split('-')[0].lower()
    if language_code == 'cnr':
        language_code = 'me'
    return language_code if language_code in {'en', 'ru', 'me', 'de'} else 'en'


def _parse_iso_datetime(value: str):
    """Парсит ISO datetime и приводит его к aware-формату."""
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None

    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _get_matching_location_services_queryset(
    *,
    pet,
    service_query: str,
    category_id: str | None,
):
    """Строит queryset услуг локации под pet/service filters."""
    service_name_filter = None
    category_filter = None

    if service_query:
        service_name_filter = (
            Q(service__name__icontains=service_query) |
            Q(service__name_en__icontains=service_query) |
            Q(service__name_ru__icontains=service_query) |
            Q(service__name_me__icontains=service_query) |
            Q(service__name_de__icontains=service_query) |
            Q(service__parent__name__icontains=service_query) |
            Q(service__parent__name_en__icontains=service_query) |
            Q(service__parent__name_ru__icontains=service_query) |
            Q(service__parent__name_me__icontains=service_query) |
            Q(service__parent__name_de__icontains=service_query) |
            Q(service__parent__parent__name__icontains=service_query) |
            Q(service__parent__parent__name_en__icontains=service_query) |
            Q(service__parent__parent__name_ru__icontains=service_query) |
            Q(service__parent__parent__name_me__icontains=service_query) |
            Q(service__parent__parent__name_de__icontains=service_query)
        )

    if category_id:
        try:
            category_value = int(category_id)
            category_filter = (
                Q(service_id=category_value) |
                Q(service__parent_id=category_value) |
                Q(service__parent__parent_id=category_value)
            )
        except ValueError:
            category_filter = None

    pet_size = pet.get_current_size_category()
    queryset = ProviderLocationService.objects.filter(
        pet_type=pet.pet_type,
        is_active=True,
    ).select_related('service')
    if pet_size:
        queryset = queryset.filter(size_code=pet_size)
    if service_name_filter is not None:
        queryset = queryset.filter(service_name_filter)
    if category_filter is not None:
        queryset = queryset.filter(category_filter)
    return queryset


class ProviderSearchAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pet_id = request.query_params.get('pet_id')
        legacy_query = (request.query_params.get('q') or '').strip()
        service_query = (request.query_params.get('service_query') or '').strip()
        location_query = (request.query_params.get('location_query') or '').strip()
        location_label = (request.query_params.get('location_label') or '').strip()
        location_place_id = (request.query_params.get('location_place_id') or '').strip()
        location_city = (request.query_params.get('location_city') or '').strip()
        location_country = (request.query_params.get('location_country') or '').strip()
        location_source = (request.query_params.get('location_source') or '').strip()
        date_str = request.query_params.get('date')
        category_id = request.query_params.get('category_id')
        lat = request.query_params.get('location_lat') or request.query_params.get('lat')
        lon = request.query_params.get('location_lon') or request.query_params.get('lon')

        if not pet_id:
            return Response({'error': _('pet_id is required')}, status=status.HTTP_400_BAD_REQUEST)

        try:
            pet = Pet.objects.get(id=pet_id, owners=request.user)
        except Pet.DoesNotExist:
            return Response({'error': _('Pet not found')}, status=status.HTTP_404_NOT_FOUND)

        if legacy_query:
            if not service_query:
                service_query = legacy_query
            if not location_query:
                location_query = legacy_query

        matching_services = _get_matching_location_services_queryset(
            pet=pet,
            service_query=service_query,
            category_id=category_id,
        )
        active_search_blockings = ProviderBlocking.objects.filter(
            provider_id=OuterRef('provider_id'),
            status='active',
            blocking_level__gte=2,
        )

        locations = ProviderLocation.objects.filter(is_active=True).select_related(
            'provider__invoice_currency',
            'structured_address',
        ).annotate(
            has_matching_service=Exists(
                matching_services.filter(location_id=OuterRef('pk'))
            ),
            provider_has_search_blocking=Exists(active_search_blockings),
        ).filter(
            has_matching_service=True,
            provider_has_search_blocking=False,
        ).distinct()

        try:
            search_lat = float(lat) if lat not in (None, '') else None
            search_lon = float(lon) if lon not in (None, '') else None
        except (TypeError, ValueError):
            search_lat = None
            search_lon = None

        location_payload = LocationSearchPayload(
            raw_query=location_query,
            label=location_label,
            place_id=location_place_id,
            city=location_city,
            country=location_country,
            source=location_source,
            lat=search_lat,
            lon=search_lon,
        )

        if search_lat is not None and search_lon is not None:
            try:
                user_point = Point(search_lon, search_lat, srid=4326)
                locations = locations.annotate(
                    distance=Distance('structured_address__point', user_point)
                ).order_by('distance')
            except ValueError:
                pass

        locations = list(locations)
        if location_payload.has_text:
            locations = filter_locations_by_payload(locations, location_payload)

        target_date = None
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({'error': _('Invalid date format')}, status=status.HTTP_400_BAD_REQUEST)

        language_code = _get_request_language_code(request)
        results = []

        try:
            for location in locations[:50]:
                services_qs = matching_services.filter(location=location)
                seen_service_ids = set()
                services_data = []
                for location_service in services_qs:
                    if location_service.service_id in seen_service_ids:
                        continue
                    if target_date is not None and not BookingAvailabilityService.location_has_real_availability(
                        provider_location=location,
                        service=location_service.service,
                        pet=pet,
                        requester=request.user,
                        target_date=target_date,
                    ):
                        continue
                    seen_service_ids.add(location_service.service_id)
                    services_data.append(
                        {
                            'id': location_service.service.id,
                            'name': location_service.service.get_localized_name(language_code),
                            'price': location_service.price,
                            'duration_minutes': location_service.duration_minutes,
                        }
                    )

                if target_date is not None and not services_data:
                    continue

                dist_value = getattr(location, 'distance', None)
                dist_m = dist_value.m if dist_value else None

                latitude = None
                longitude = None
                if location.structured_address and location.structured_address.point:
                    longitude = location.structured_address.point.x
                    latitude = location.structured_address.point.y

                results.append(
                    {
                        'id': location.id,
                        'name': location.name,
                        'provider_name': location.provider.name,
                        'address': location.structured_address.formatted_address if location.structured_address else '',
                        'distance_meters': dist_m,
                        'lat': float(latitude) if latitude is not None else None,
                        'lon': float(longitude) if longitude is not None else None,
                        'services': services_data,
                        'rating': getattr(location.provider, 'rating', 5.0),
                        'currency_code': location.provider.invoice_currency.code if getattr(location.provider, 'invoice_currency', None) else None,
                    }
                )
        except RoutingUnavailableError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(results)


class LocationSlotsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, location_id):
        service_id = request.query_params.get('service_id')
        pet_id = request.query_params.get('pet_id')
        date_start_str = request.query_params.get('date_start')
        date_end_str = request.query_params.get('date_end')

        if not all([service_id, pet_id, date_start_str, date_end_str]):
            return Response(
                {'error': _('service_id, pet_id, date_start and date_end are required')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            pet = Pet.objects.get(id=pet_id, owners=request.user)
            location = ProviderLocation.objects.get(id=location_id, is_active=True)
            service = Service.objects.get(id=service_id)
        except (Pet.DoesNotExist, ProviderLocation.DoesNotExist, Service.DoesNotExist):
            return Response({'error': _('Object not found')}, status=status.HTTP_404_NOT_FOUND)

        try:
            date_start = datetime.strptime(date_start_str, '%Y-%m-%d').date()
            date_end = datetime.strptime(date_end_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': _('Invalid date format')}, status=status.HTTP_400_BAD_REQUEST)

        try:
            grouped_slots = BookingAvailabilityService.get_available_slots(
                provider_location=location,
                service=service,
                pet=pet,
                requester=request.user,
                date_start=date_start,
                date_end=date_end,
            )
        except RoutingUnavailableError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({'slots_by_date': grouped_slots})


class BookingDraftValidationAPIView(APIView):
    permission_classes = [IsAuthenticated, IsVerifiedForOwnerWriteActions]

    def post(self, request):
        location_id = request.data.get('provider_location_id')
        service_id = request.data.get('service_id')
        pet_id = request.data.get('pet_id')
        start_time_str = request.data.get('start_time')
        employee_id = request.data.get('employee_id')
        escort_owner_id = request.data.get('escort_owner_id')

        if not all([location_id, service_id, pet_id, start_time_str]):
            return Response({'error': _('Missing required fields')}, status=status.HTTP_400_BAD_REQUEST)

        start_time = _parse_iso_datetime(start_time_str)
        if start_time is None:
            return Response({'error': _('Invalid date format')}, status=status.HTTP_400_BAD_REQUEST)

        try:
            pet = Pet.objects.get(id=pet_id, owners=request.user)
            location = ProviderLocation.objects.get(id=location_id, is_active=True)
            service = Service.objects.get(id=service_id)
        except (Pet.DoesNotExist, ProviderLocation.DoesNotExist, Service.DoesNotExist):
            return Response({'error': _('Related object not found')}, status=status.HTTP_404_NOT_FOUND)

        employee = None
        if employee_id:
            try:
                employee = Employee.objects.get(id=employee_id)
            except Employee.DoesNotExist:
                return Response({'error': _('Employee not found')}, status=status.HTTP_404_NOT_FOUND)

        escort_owner = None
        if escort_owner_id:
            try:
                escort_owner = User.objects.get(id=escort_owner_id)
            except User.DoesNotExist:
                return Response({'error': _('Escort owner not found')}, status=status.HTTP_404_NOT_FOUND)

        try:
            validation_result = BookingAvailabilityService.validate_booking_request(
                requester=request.user,
                pet=pet,
                provider_location=location,
                service=service,
                start_time=start_time,
                employee=employee,
                escort_owner=escort_owner,
            )
        except BookingDomainError as exc:
            return Response(exc.to_dict(), status=exc.status_code)
        except RoutingUnavailableError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        possible_escort_owners = []
        if validation_result.possible_escort_owner_ids:
            owners_qs = User.objects.filter(id__in=validation_result.possible_escort_owner_ids)
            possible_escort_owners = [
                {'id': u.id, 'first_name': u.first_name, 'last_name': u.last_name}
                for u in owners_qs
            ]

        payload = {
            'is_bookable': validation_result.is_bookable,
            'requires_escort_assignment': validation_result.requires_escort_assignment,
            'possible_escort_owners': possible_escort_owners,
            'possible_escort_owner_ids': validation_result.possible_escort_owner_ids,
            'conflicting_bookings': validation_result.conflicting_bookings,
            'employee_id': validation_result.employee.id if validation_result.employee else employee_id,
            'start_time': validation_result.start_time.isoformat(),
            'end_time': validation_result.end_time.isoformat(),
            'occupied_duration_minutes': validation_result.occupied_duration_minutes,
            'price': str(validation_result.price),
            'has_duplicate_warning': validation_result.has_duplicate_warning,
            'duplicate_booking_warning': validation_result.duplicate_booking_warning,
        }
        if not validation_result.is_bookable:
            payload['code'] = validation_result.failure_code
            payload['message'] = str(validation_result.failure_message)
        return Response(payload)


class CreateAppointmentAPIView(APIView):
    permission_classes = [IsAuthenticated, IsVerifiedForOwnerWriteActions]

    def post(self, request):
        location_id = request.data.get('provider_location_id')
        service_id = request.data.get('service_id')
        pet_id = request.data.get('pet_id')
        start_time_str = request.data.get('start_time')
        employee_id = request.data.get('employee_id')
        escort_owner_id = request.data.get('escort_owner_id')
        notes = request.data.get('notes', '')

        if not all([location_id, service_id, pet_id, start_time_str, employee_id]):
            return Response({'error': _('Missing required fields')}, status=status.HTTP_400_BAD_REQUEST)

        start_time = _parse_iso_datetime(start_time_str)
        if start_time is None:
            return Response({'error': _('Invalid date format')}, status=status.HTTP_400_BAD_REQUEST)

        try:
            pet = Pet.objects.get(id=pet_id, owners=request.user)
            location = ProviderLocation.objects.get(id=location_id, is_active=True)
            employee = Employee.objects.get(id=employee_id)
            service = Service.objects.get(id=service_id)
        except (Pet.DoesNotExist, ProviderLocation.DoesNotExist, Employee.DoesNotExist, Service.DoesNotExist):
            return Response({'error': _('Related object not found')}, status=status.HTTP_404_NOT_FOUND)

        escort_owner = None
        if escort_owner_id:
            try:
                escort_owner = pet.owners.get(id=escort_owner_id)
            except User.DoesNotExist:
                return Response({'error': _('Escort owner must be one of the pet owners')}, status=status.HTTP_400_BAD_REQUEST)

        try:
            booking = BookingTransactionService.create_booking(
                user=request.user,
                pet=pet,
                provider=location.provider,
                employee=employee,
                service=service,
                start_time=start_time,
                provider_location=location,
                escort_owner=escort_owner,
                notes=notes,
            )
        except BookingDomainError as exc:
            return Response(exc.to_dict(), status=exc.status_code)
        except RoutingUnavailableError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(
            {
                'success': True,
                'booking_id': booking.id,
                'code': booking.code,
                'price': booking.price,
                'start_time': booking.start_time.isoformat(),
                'end_time': booking.end_time.isoformat(),
                'escort_owner_id': booking.escort_owner_id,
                'occupied_duration_minutes': booking.occupied_duration_minutes,
            },
            status=status.HTTP_201_CREATED,
        )
