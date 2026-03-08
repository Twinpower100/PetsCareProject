from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Q, F, Min, Prefetch, Exists, OuterRef
from django.utils.translation import gettext_lazy as _
from datetime import datetime, timedelta
from django.utils import timezone

from pets.models import Pet
from providers.models import ProviderLocation, ProviderLocationService, Employee, Schedule
from catalog.models import Service
from .models import Booking, BookingStatus
from .location_search import LocationSearchPayload, filter_locations_by_payload

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
        lat = request.query_params.get('location_lat') or request.query_params.get('lat')
        lon = request.query_params.get('location_lon') or request.query_params.get('lon')
        date_str = request.query_params.get('date')
        category_id = request.query_params.get('category_id')
        
        if not pet_id:
            return Response({'error': _("pet_id is required")}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            pet = Pet.objects.get(id=pet_id, owners=request.user)
        except Pet.DoesNotExist:
            return Response({'error': _("Pet not found")}, status=status.HTTP_404_NOT_FOUND)

        # Backward compatibility for older frontend calls that still send a single mixed `q`.
        if legacy_query:
            if not service_query:
                service_query = legacy_query
            if not location_query:
                location_query = legacy_query

        pet_size = pet.get_current_size_category()

        # Base query for ProviderLocation (currency from provider's invoice_currency / price list)
        locations = ProviderLocation.objects.filter(is_active=True).select_related(
            'provider__invoice_currency', 'structured_address'
        )

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
                cat_id = int(category_id)
                category_filter = (
                    Q(service_id=cat_id) |
                    Q(service__parent_id=cat_id) |
                    Q(service__parent__parent_id=cat_id)
                )
            except ValueError:
                category_filter = None

        matching_location_services = ProviderLocationService.objects.filter(
            location_id=OuterRef('pk'),
            pet_type=pet.pet_type,
            is_active=True
        )

        if pet_size:
            matching_location_services = matching_location_services.filter(size_code=pet_size)

        if service_name_filter is not None:
            matching_location_services = matching_location_services.filter(service_name_filter)

        if category_filter is not None:
            matching_location_services = matching_location_services.filter(category_filter)

        locations = locations.annotate(
            has_matching_service=Exists(matching_location_services)
        ).filter(has_matching_service=True).distinct()

        try:
            search_lat = float(lat) if lat not in (None, '') else None
        except (TypeError, ValueError):
            search_lat = None

        try:
            search_lon = float(lon) if lon not in (None, '') else None
        except (TypeError, ValueError):
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

        # Geolocation Distance
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

        # Optional: filter by rough time (date) — exclude locations with no slots on that date.
        # If that would return 0 locations, skip the filter so we still show results (user can pick another date).
        if date_str:
            try:
                filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                day_of_week = filter_date.weekday()
                loc_ids_with_schedule = set(
                    Schedule.objects.filter(
                        provider_location__in=locations,
                        day_of_week=day_of_week,
                        is_working=True
                    ).values_list('provider_location_id', flat=True).distinct()
                )
                locations_filtered = [loc for loc in locations if loc.id in loc_ids_with_schedule]
                locations = locations_filtered if locations_filtered else locations
            except ValueError:
                pass

        # Formatting response
        language_code = (getattr(request, 'LANGUAGE_CODE', '') or 'en').split('-')[0]
        results = []
        for loc in locations[:50]:  # limit to 50
            # Get services available for this pet at this location (one row per service, by pet size if available)
            services_qs = ProviderLocationService.objects.filter(
                location=loc,
                pet_type=pet.pet_type,
                is_active=True
            ).select_related('service')
            if pet_size:
                services_qs = services_qs.filter(size_code=pet_size)
            if service_name_filter is not None:
                services_qs = services_qs.filter(service_name_filter)
            if category_filter is not None:
                services_qs = services_qs.filter(category_filter)
            # Deduplicate by service id (take first by size)
            seen_service_ids = set()
            services_data = []
            for ls in services_qs:
                if ls.service_id not in seen_service_ids:
                    seen_service_ids.add(ls.service_id)
                    services_data.append({
                        'id': ls.service.id,
                        'name': ls.service.get_localized_name(language_code),
                        'price': ls.price,
                        'duration_minutes': ls.duration_minutes,
                    })

            dist_value = getattr(loc, 'distance', None)
            dist_m = dist_value.m if dist_value else None

            # Coordinates for map (Point is lon, lat)
            lat, lon = None, None
            if loc.structured_address and loc.structured_address.point:
                lon, lat = loc.structured_address.point.x, loc.structured_address.point.y

            results.append({
                'id': loc.id,
                'name': loc.name,
                'provider_name': loc.provider.name,
                'address': loc.structured_address.formatted_address if loc.structured_address else '',
                'distance_meters': dist_m,
                'lat': float(lat) if lat is not None else None,
                'lon': float(lon) if lon is not None else None,
                'services': services_data,
                'rating': getattr(loc.provider, 'rating', 5.0),
                'currency_code': loc.provider.invoice_currency.code if getattr(loc.provider, 'invoice_currency', None) else None,
            })

        return Response(results)


class LocationSlotsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, location_id):
        service_id = request.query_params.get('service_id')
        pet_id = request.query_params.get('pet_id')
        date_start_str = request.query_params.get('date_start')
        date_end_str = request.query_params.get('date_end')

        if not all([service_id, pet_id, date_start_str, date_end_str]):
            return Response({'error': _("service_id, pet_id, date_start, date_end are required")}, status=status.HTTP_400_BAD_REQUEST)

        try:
            pet = Pet.objects.get(id=pet_id, owners=request.user)
            location = ProviderLocation.objects.get(id=location_id, is_active=True)
        except (Pet.DoesNotExist, ProviderLocation.DoesNotExist):
            return Response({'error': _("Object not found or service not available for this pet at this location")}, status=status.HTTP_404_NOT_FOUND)

        size_code = pet.get_current_size_category()
        loc_service_qs = ProviderLocationService.objects.filter(
            location=location,
            service_id=service_id,
            pet_type=pet.pet_type,
            is_active=True
        )
        if size_code:
            loc_service_qs = loc_service_qs.filter(size_code=size_code)
        loc_service = loc_service_qs.first()
        if not loc_service:
            return Response({'error': _("Service not available for this pet at this location (check pet type and size)")}, status=status.HTTP_404_NOT_FOUND)

        try:
            date_start = datetime.strptime(date_start_str, '%Y-%m-%d').date()
            date_end = datetime.strptime(date_end_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': _("Invalid date format")}, status=status.HTTP_400_BAD_REQUEST)

        total_duration = loc_service.duration_minutes + loc_service.tech_break_minutes

        # Basic slot generation logic (could be improved to use EmployeeAutoBookingService fully)
        # 1. Find employees working at this location for this service
        # In this simplistic version, we just find Schedules at this location

        employees = Employee.objects.filter(
            schedules__provider_location=location,
            schedules__is_working=True
        ).distinct()

        grouped_slots = {}
        current_date = date_start
        while current_date <= date_end:
            date_str = current_date.isoformat()
            grouped_slots[date_str] = []
            
            day_of_week = current_date.weekday()

            for emp in employees:
                schedules = Schedule.objects.filter(
                    employee=emp, day_of_week=day_of_week, provider_location=location, is_working=True
                )
                for sched in schedules:
                    work_start = timezone.make_aware(datetime.combine(current_date, sched.start_time))
                    work_end = timezone.make_aware(datetime.combine(current_date, sched.end_time))
                    
                    # Get bookings for this employee on this day
                    bookings = Booking.objects.filter(
                        employee=emp,
                        start_time__date=current_date,
                        status__name__in=['active', 'pending_confirmation']
                    ).order_by('start_time')

                    # Generate slots
                    current_time = work_start
                    while current_time + timedelta(minutes=total_duration) <= work_end:
                        slot_end = current_time + timedelta(minutes=loc_service.duration_minutes)
                        slot_full_end = current_time + timedelta(minutes=total_duration)
                        
                        # Check conflicts
                        conflict = False
                        for b in bookings:
                            if (current_time < b.end_time and slot_full_end > b.start_time):
                                conflict = True
                                current_time = b.end_time # jump past booking
                                break
                        
                        if not conflict:
                            if current_time >= timezone.now():
                                grouped_slots[date_str].append({
                                    'start_time': current_time.isoformat(),
                                    'end_time': slot_end.isoformat(),
                                    'employee_id': emp.id
                                })
                            current_time += timedelta(minutes=30)  # Step by 30 mins
                        
            current_date += timedelta(days=1)

        # Sort slots within each day by start_time
        for date_str in grouped_slots:
            grouped_slots[date_str].sort(key=lambda s: s['start_time'])

        return Response({'slots_by_date': grouped_slots})


class CreateAppointmentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        location_id = request.data.get('provider_location_id')
        service_id = request.data.get('service_id')
        pet_id = request.data.get('pet_id')
        start_time_str = request.data.get('start_time')
        employee_id = request.data.get('employee_id') # from the slot

        if not all([location_id, service_id, pet_id, start_time_str, employee_id]):
            return Response({'error': _("Missing required fields")}, status=status.HTTP_400_BAD_REQUEST)

        try:
            pet = Pet.objects.get(id=pet_id, owners=request.user)
            location = ProviderLocation.objects.get(id=location_id)
            employee = Employee.objects.get(id=employee_id)
            start_time = timezone.datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        except (Pet.DoesNotExist, ProviderLocation.DoesNotExist, Employee.DoesNotExist):
            return Response({'error': _("Related object not found")}, status=status.HTTP_404_NOT_FOUND)
        except ValueError:
            return Response({'error': _("Invalid date format")}, status=status.HTTP_400_BAD_REQUEST)

        size_code = pet.get_current_size_category()
        loc_service_qs = ProviderLocationService.objects.filter(
            location=location,
            service_id=service_id,
            pet_type=pet.pet_type,
            is_active=True
        )
        if size_code:
            loc_service_qs = loc_service_qs.filter(size_code=size_code)
        loc_service = loc_service_qs.first()
        if not loc_service:
            return Response({'error': _("Service not available for this pet at this location")}, status=status.HTTP_404_NOT_FOUND)

        if start_time < timezone.now():
            return Response({'error': _("Cannot book in the past")}, status=status.HTTP_400_BAD_REQUEST)

        end_time = start_time + timedelta(minutes=loc_service.duration_minutes)
        full_end_time = end_time + timedelta(minutes=loc_service.tech_break_minutes)

        # Check availability again to avoid race conditions
        conflicts = Booking.objects.filter(
            employee=employee,
            start_time__lt=full_end_time,
            end_time__gt=start_time,
            status__name__in=['active', 'pending_confirmation']
        )
        if conflicts.exists():
            return Response({'error': _("Slot is already booked")}, status=status.HTTP_409_CONFLICT)

        # Create
        status_obj, _ = BookingStatus.objects.get_or_create(name='active')
        import random, string
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

        booking = Booking.objects.create(
            user=request.user,
            pet=pet,
            provider=location.provider,
            provider_location=location,
            employee=employee,
            service=loc_service.service,
            status=status_obj,
            start_time=start_time,
            end_time=end_time,
            price=loc_service.price,
            code=code
        )

        return Response({
            'success': True,
            'booking_id': booking.id,
            'code': booking.code,
            'price': booking.price,
            'start_time': booking.start_time
        }, status=status.HTTP_201_CREATED)
