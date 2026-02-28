from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from .models import Vacation, SickLeave
from .serializers import VacationSerializer, SickLeaveSerializer
from providers.models import Employee, ProviderLocation, EmployeeLocationRole, Schedule
from booking.reassignment_service import BookingReassignmentService
from datetime import datetime
from django.db.models import Q

class AbsenceCreateAPIView(APIView):
    """
    Base view for creating absences (Vacation/SickLeave) with booking conflict handling.
    """
    permission_classes = [permissions.IsAuthenticated]
    model_class = None
    serializer_class = None

    def post(self, request, employee_id):
        employee = get_object_or_404(Employee, pk=employee_id)
        
        # Check permissions: system admin or provider admin/manager
        # (Assuming standard permission check similar to employee deactivation)
        # Simplified for now:
        if not (request.user.is_system_admin() or request.user.is_provider_admin()):
             return Response({'error': _('Permission denied')}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        start_date = serializer.validated_data.get('start_date')
        end_date = serializer.validated_data.get('end_date')
        target_location = serializer.validated_data.get('provider_location')

        # Check for overlapping absences
        overlap_query = Q(employee=employee)
        
        # Location consistency: local absence conflicts with global or same-location ones.
        # Global absence conflicts with everything.
        if target_location:
            overlap_query &= Q(Q(provider_location=target_location) | Q(provider_location__isnull=True))
        
        # Date overlap logic
        if end_date:
            overlap_query &= Q(start_date__lte=end_date) & Q(Q(end_date__isnull=True) | Q(end_date__gte=start_date))
        else:
            overlap_query &= Q(Q(end_date__isnull=True) | Q(end_date__gte=start_date))

        if Vacation.objects.filter(overlap_query).exists() or SickLeave.objects.filter(overlap_query).exists():
             return Response({
                 'error': 'overlapping_absence',
                 'detail': _('Employee already has an absence (vacation or sick leave) scheduled for this period/location.')
             }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check conflicts
        if target_location:
            relevant_locations = [target_location]
        else:
            relevant_locations = employee.locations.all()

        all_future_bookings = []
        for loc in relevant_locations:
            bookings = BookingReassignmentService.get_future_bookings(
                employee_id=employee_id,
                location_id=loc.id,
                start_date=timezone.make_aware(datetime.combine(start_date, timezone.now().time())),
                end_date=timezone.make_aware(datetime.combine(end_date, timezone.now().time())) if end_date else None
            )
            all_future_bookings.extend(list(bookings))

        # Поддержка resolution / resolution_action и cancel_reason / cancellation_reason (как в deactivate)
        resolution_action = request.data.get('resolution_action') or request.data.get('resolution')
        cancellation_reason = request.data.get('cancellation_reason') or request.data.get('cancel_reason', '') or str(_("Specialist is absent"))
        future_count = len(all_future_bookings)

        if all_future_bookings and not resolution_action:
            bookings_payload = BookingReassignmentService.serialize_bookings_for_response(all_future_bookings)
            return Response({
                'error': 'has_future_bookings',
                'future_bookings_count': future_count,
                'message': _(
                    'Employee has future bookings during this period. '
                    'Please choose an action: cancel them or reassign to another specialist.'
                ),
                'bookings': bookings_payload,
                'conflict_type': 'future_bookings',
                'bookings_count': future_count,
            }, status=status.HTTP_409_CONFLICT)

        # Process resolution
        if all_future_bookings and resolution_action:
            if resolution_action == 'granular':
                granular_resolutions = request.data.get('granular_resolutions', [])
                result = BookingReassignmentService.process_granular_resolutions(
                    granular_resolutions, request.user
                )
            elif resolution_action == 'cancel':
                result = BookingReassignmentService.cancel_bookings(
                    bookings=all_future_bookings,
                    cancelled_by=request.user,
                    reason=cancellation_reason
                )
                BookingReassignmentService.send_cancellation_notifications(
                    result['cancelled_bookings'],
                    reason=cancellation_reason
                )
            elif resolution_action == 'reassign':
                target_employee_id = request.data.get('target_employee_id')
                if not target_employee_id:
                    return Response({'error': _('Target employee is required for reassignment')}, status=status.HTTP_400_BAD_REQUEST)
                
                target_employee = get_object_or_404(Employee, pk=target_employee_id)
                try:
                    result = BookingReassignmentService.reassign_bookings(
                        bookings=all_future_bookings,
                        target_employee=target_employee,
                        reassigned_by=request.user
                    )
                    BookingReassignmentService.send_reassignment_notifications(
                        result['reassigned_bookings'],
                        target_employee
                    )
                except Exception as e:
                    return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Create the absence
        absence = serializer.save()
        
        # Auto-approve if created by admin
        if request.user.is_system_admin() or request.user.is_provider_admin():
            if isinstance(absence, Vacation):
                absence.is_approved = True
                absence.approved_by = request.user
                absence.approved_at = timezone.now()
            elif isinstance(absence, SickLeave):
                absence.is_confirmed = True
                absence.confirmed_by = request.user
                absence.confirmed_at = timezone.now()
            absence.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)

class VacationCreateAPIView(AbsenceCreateAPIView):
    model_class = Vacation
    serializer_class = VacationSerializer

class SickLeaveCreateAPIView(AbsenceCreateAPIView):
    model_class = SickLeave
    serializer_class = SickLeaveSerializer

class VacationDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Vacation.objects.all()
    serializer_class = VacationSerializer
    permission_classes = [permissions.IsAuthenticated]

class SickLeaveDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = SickLeave.objects.all()
    serializer_class = SickLeaveSerializer
    permission_classes = [permissions.IsAuthenticated]

class LocationAggregatedScheduleAPIView(APIView):
    """
    Returns aggregated schedule for a location within a date range.
    Includes work shifts and absences.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, location_id):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        
        if not start_date_str or not end_date_str:
             return Response({'error': _('start_date and end_date are required (YYYY-MM-DD)')}, status=400)
             
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': _('Invalid date format')}, status=400)

        location = get_object_or_404(ProviderLocation, pk=location_id)
        
        # Get employees for this location
        from providers.models import EmployeeProvider, EmployeeLocationRole
        
        provider = location.provider
        
        # Get employee IDs assigned to this location from EmployeeProvider
        # (matching the logic in LocationStaffListAPIView)
        employees = Employee.objects.filter(
            locations=location,
            employeeprovider_set__provider=provider,
            employeeprovider_set__end_date__isnull=True,
        ).select_related('user').distinct()
        
        result = []
        for employee in employees:
            emp_data = {
                'id': employee.id,
                'full_name': employee.user.get_full_name(),
                'items': []
            }
            
            # Get absences
            absences_query = Q(employee=employee) & Q(Q(provider_location=location) | Q(provider_location__isnull=True))
            
            vacations = Vacation.objects.filter(
                absences_query,
                start_date__lte=end_date,
                end_date__gte=start_date
            )
            for v in vacations:
                emp_data['items'].append({
                    'id': v.id,
                    'type': 'vacation',
                    'start_date': v.start_date.isoformat(),
                    'end_date': v.end_date.isoformat(),
                    'vacation_type': v.vacation_type,
                    'is_approved': v.is_approved
                })
                
            sick_leaves = SickLeave.objects.filter(
                absences_query,
                start_date__lte=end_date
            ).filter(Q(end_date__isnull=True) | Q(end_date__gte=start_date))
            for s in sick_leaves:
                emp_data['items'].append({
                    'id': s.id,
                    'type': 'sick_leave',
                    'start_date': s.start_date.isoformat(),
                    'end_date': s.end_date.isoformat() if s.end_date else None,
                    'sick_leave_type': s.sick_leave_type,
                    'is_confirmed': s.is_confirmed
                })
                
            # Get recurring schedule
            schedules = Schedule.objects.filter(
                employee=employee,
                provider_location=location,
                is_working=True
            )
            for sch in schedules:
                 emp_data['items'].append({
                     'type': 'schedule',
                     'day_of_week': sch.day_of_week,
                     'start_time': sch.start_time.isoformat() if sch.start_time else None,
                     'end_time': sch.end_time.isoformat() if sch.end_time else None,
                     'break_start': sch.break_start.isoformat() if sch.break_start else None,
                     'break_end': sch.break_end.isoformat() if sch.break_end else None
                 })
            
            result.append(emp_data)
            
        return Response(result)
