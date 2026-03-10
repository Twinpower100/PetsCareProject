"""
Universal Booking Reassignment / Cancellation Service.

This service handles mass cancellation or reassignment of bookings.
It is designed to be reusable across multiple business scenarios:
- Employee deactivation (offboarding)
- Vacation creation
- Sick leave creation
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class BookingReassignmentService:
    """
    Universal service for mass booking cancellation or reassignment.

    Supports two operations:
    - cancel: Move bookings to 'cancelled_by_provider' status
    - reassign: Change the employee on bookings to a target employee
    """

    @staticmethod
    def get_future_bookings(
        employee_id: int,
        location_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ):
        """
        Get future active bookings for an employee at a location.

        Args:
            employee_id: ID of the employee
            location_id: ID of the location
            start_date: Start date filter (defaults to now)
            end_date: End date filter (optional, for vacations/sick leave)

        Returns:
            QuerySet of Booking objects
        """
        from booking.models import Booking, BookingStatus

        now = start_date or timezone.now()

        # Get active/pending status objects
        active_statuses = BookingStatus.objects.filter(
            name__in=['active', 'pending_confirmation']
        )

        qs = Booking.objects.filter(
            employee_id=employee_id,
            provider_location_id=location_id,
            status__in=active_statuses,
            start_time__gt=now,
        )
        if end_date:
            qs = qs.filter(start_time__lt=end_date)
        return qs.select_related(
            'user', 'pet', 'employee', 'employee__user', 'service',
            'provider_location', 'status'
        ).order_by('start_time')

    @staticmethod
    def serialize_bookings_for_response(bookings) -> list:
        """
        Serialize bookings to a list of dicts for API response.
        """
        result = []
        for b in bookings:
            result.append({
                'id': b.id,
                'code': b.code,
                'service_name': b.service.name if b.service else '',
                'client_name': b.user.get_full_name() if b.user else '',
                'client_email': b.user.email if b.user else '',
                'pet_name': b.pet.name if b.pet else '',
                'start_time': b.start_time.isoformat() if b.start_time else None,
                'end_time': b.end_time.isoformat() if b.end_time else None,
                'price': str(b.price) if b.price else '0',
                'status': b.status.name if b.status else '',
            })
        return result

    @staticmethod
    @transaction.atomic
    def cancel_bookings(
        bookings,
        cancelled_by,
        reason: str = '',
    ) -> Dict[str, Any]:
        """
        Cancel a set of bookings (mark as cancelled_by_provider).

        Args:
            bookings: QuerySet or list of Booking objects
            cancelled_by: User performing the cancellation
            reason: Cancellation reason

        Returns:
            dict with 'cancelled_count' and 'cancelled_booking_ids'
        """
        from booking.models import BookingStatus, BookingCancellation

        cancelled_status = BookingStatus.objects.get(name='cancelled_by_provider')

        cancelled_ids = []
        cancelled_bookings = []
        now = timezone.now()

        for booking in bookings:
            if booking.status.name in ('cancelled_by_client', 'cancelled_by_provider'):
                continue
            if booking.completed_at:
                continue

            booking.status = cancelled_status
            booking.cancelled_by = cancelled_by
            booking.cancelled_at = now
            booking.cancellation_reason = reason or str(
                _("Specialist is no longer available at this location")
            )
            booking.save(update_fields=[
                'status', 'cancelled_by', 'cancelled_at',
                'cancellation_reason', 'updated_at'
            ])

            # Create cancellation record
            BookingCancellation.objects.create(
                booking=booking,
                cancelled_by=cancelled_by,
                reason=reason or str(
                    _("Specialist is no longer available at this location")
                ),
            )

            cancelled_ids.append(booking.id)
            cancelled_bookings.append(booking)

        logger.info(
            "Cancelled %d bookings by user %s. Reason: %s",
            len(cancelled_ids), cancelled_by, reason
        )

        return {
            'cancelled_count': len(cancelled_ids),
            'cancelled_booking_ids': cancelled_ids,
            'cancelled_bookings': cancelled_bookings,
        }

    @staticmethod
    @transaction.atomic
    def reassign_bookings(
        bookings,
        target_employee,
        reassigned_by,
    ) -> Dict[str, Any]:
        """
        Reassign bookings to a different employee.

        Checks:
        - Target employee is active and linked to the same location
        - Target employee can provide the required services
        - No time conflicts with existing bookings of the target employee

        Args:
            bookings: QuerySet or list of Booking objects
            target_employee: Employee to reassign bookings to
            reassigned_by: User performing the reassignment

        Returns:
            dict with 'reassigned_count', 'reassigned_booking_ids', 'conflicts'

        Raises:
            ValidationError: If target employee is not available or has conflicts
        """
        from booking.models import Booking
        from providers.models import EmployeeLocationService

        reassigned_ids = []
        reassigned_bookings = []
        conflicts = []

        # Group bookings by location to validate once per location
        location_ids = set()
        for b in bookings:
            if b.provider_location_id:
                location_ids.add(b.provider_location_id)

        # Validate target employee is linked to these locations
        for loc_id in location_ids:
            if not target_employee.locations.filter(pk=loc_id).exists():
                raise ValidationError(
                    _("Target employee is not assigned to location #%d") % loc_id
                )

        for booking in bookings:
            if booking.status.name in ('cancelled_by_client', 'cancelled_by_provider'):
                continue
            if booking.completed_at:
                continue

            # Check that target employee can provide the service at this location
            if booking.provider_location_id:
                can_provide = EmployeeLocationService.objects.filter(
                    employee=target_employee,
                    provider_location_id=booking.provider_location_id,
                    service=booking.service,
                ).exists()
                if not can_provide:
                    conflicts.append({
                        'booking_id': booking.id,
                        'reason': str(_(
                            "Target employee does not provide service '%s' at this location"
                        ) % (booking.service.name if booking.service else '')),
                    })
                    continue

            # Check for time conflicts
            conflicting = Booking.objects.filter(
                employee=target_employee,
                start_time__lt=booking.end_time,
                end_time__gt=booking.start_time,
                status__name__in=['active', 'pending_confirmation'],
            ).exclude(pk=booking.pk).exists()

            if conflicting:
                conflicts.append({
                    'booking_id': booking.id,
                    'reason': str(_(
                        "Target employee has a time conflict for %s"
                    ) % booking.start_time.strftime('%Y-%m-%d %H:%M')),
                })
                continue

            # Perform reassignment
            old_employee = booking.employee
            booking.employee = target_employee
            booking.save(update_fields=['employee', 'updated_at'])

            reassigned_ids.append(booking.id)
            reassigned_bookings.append(booking)

            logger.info(
                "Booking #%d reassigned from %s to %s by %s",
                booking.id, old_employee, target_employee, reassigned_by
            )

        if conflicts:
            raise ValidationError({
                'conflicts': conflicts,
                'message': str(_(
                    "Some bookings could not be reassigned due to conflicts."
                )),
                'reassigned_count': len(reassigned_ids),
                'reassigned_booking_ids': reassigned_ids,
            })

        return {
            'reassigned_count': len(reassigned_ids),
            'reassigned_booking_ids': reassigned_ids,
            'reassigned_bookings': reassigned_bookings,
            'conflicts': conflicts,
        }

    @staticmethod
    @transaction.atomic
    def process_granular_resolutions(
        resolutions_data: list,
        performed_by: Any,
    ) -> Dict[str, Any]:
        """
        Process a list of granular resolutions for multiple bookings.
        
        Args:
            resolutions_data: List of dicts:
                {'booking_id': int, 'action': 'cancel'|'reassign', 
                 'target_employee_id': int (optional), 'reason': str (optional)}
            performed_by: User performing the actions
        """
        from booking.models import Booking
        from providers.models import Employee

        cancelled_bookings = []
        reassigned_bookings = []
        errors = []

        for item in resolutions_data:
            b_id = item.get('booking_id')
            action = item.get('action')
            
            try:
                booking = Booking.objects.get(pk=b_id)
                
                if action == 'cancel':
                    res = BookingReassignmentService.cancel_bookings(
                        [booking], performed_by, item.get('reason', '')
                    )
                    cancelled_bookings.extend(res['cancelled_bookings'])
                
                elif action == 'reassign':
                    target_id = item.get('target_employee_id')
                    if not target_id:
                        errors.append({'booking_id': b_id, 'error': 'target_employee_id required'})
                        continue
                    
                    target_emp = Employee.objects.get(pk=target_id)
                    res = BookingReassignmentService.reassign_bookings(
                        [booking], target_emp, performed_by
                    )
                    reassigned_bookings.extend(res['reassigned_bookings'])
                    
            except Exception as e:
                errors.append({'booking_id': b_id, 'error': str(e)})

        # Send notifications
        if cancelled_bookings:
            BookingReassignmentService.send_cancellation_notifications(cancelled_bookings)
        if reassigned_bookings:
            # Note: this sends one by one in the loop above? 
            # Actually better to group by target employee if we want bulk notification.
            # For now, simple:
            for b in reassigned_bookings:
                BookingReassignmentService.send_reassignment_notifications([b], b.employee)

        return {
            'cancelled_count': len(cancelled_bookings),
            'reassigned_count': len(reassigned_bookings),
            'errors': errors
        }

    @staticmethod
    @transaction.atomic
    def deactivate_staff(
        provider_location: Any,
        employee: Any,
        resolution: str = 'cancel',
        target_employee_id: Optional[int] = None,
        reason: str = '',
        performed_by: Any = None,
    ) -> Dict[str, Any]:
        """
        Deactivate staff at a specific location and resolve future bookings.
        """
        from providers.models import EmployeeLocationRole, Employee

        # Get future bookings
        future_bookings = BookingReassignmentService.get_future_bookings(
            employee_id=employee.id,
            location_id=provider_location.id
        )

        result = {'detail': 'success'}

        if future_bookings.exists():
            if resolution == 'cancel':
                res = BookingReassignmentService.cancel_bookings(
                    bookings=future_bookings,
                    cancelled_by=performed_by or employee.user,
                    reason=reason or str(_("Staff member deactivated"))
                )
                BookingReassignmentService.send_cancellation_notifications(
                    res['cancelled_bookings'],
                    reason=reason
                )
                result['cancelled_count'] = res['cancelled_count']
            
            elif resolution == 'reassign':
                if not target_employee_id:
                    raise ValidationError(_("Target employee ID is required for reassignment."))
                
                target_employee = Employee.objects.get(pk=target_employee_id)
                res = BookingReassignmentService.reassign_bookings(
                    bookings=future_bookings,
                    target_employee=target_employee,
                    reassigned_by=performed_by or employee.user
                )
                BookingReassignmentService.send_reassignment_notifications(
                    res['reassigned_bookings'],
                    target_employee
                )
                result['reassigned_count'] = res['reassigned_count']

        # Update role status
        role_obj, _ = EmployeeLocationRole.objects.get_or_create(
            employee=employee,
            provider_location=provider_location,
            defaults={'role': EmployeeLocationRole.ROLE_SERVICE_WORKER}
        )
        role_obj.is_active = False
        role_obj.end_date = timezone.now()
        role_obj.save(update_fields=['is_active', 'end_date'])

        # Notify manager
        BookingReassignmentService.send_manager_notifications(
            provider_location, employee, action='deactivated'
        )

        return result

    @staticmethod
    def send_cancellation_notifications(bookings, reason: str = ''):
        """Sends notifications to clients about booking cancellation."""
        from notifications.models import Notification
        for booking in bookings:
            if booking.user:
                Notification.objects.create(
                    user=booking.user,
                    pet=booking.pet,
                    title=str(_("Booking Cancelled")),
                    message=str(_("Your booking for {} has been cancelled. Reason: {}").format(
                        booking.service.name if booking.service else _("service"),
                        reason or _("Specialist is no longer available")
                    )),
                    notification_type='appointment',
                    priority='high'
                )

    @staticmethod
    def send_reassignment_notifications(bookings, target_employee):
        """Sends notifications to clients about booking reassignment."""
        from notifications.models import Notification
        for booking in bookings:
            if booking.user:
                Notification.objects.create(
                    user=booking.user,
                    pet=booking.pet,
                    title=str(_("Booking Reassigned")),
                    message=str(_("Your booking for {service} has been reassigned to {specialist}.").format(
                        service=booking.service.name if booking.service else _("service"),
                        specialist=f"{target_employee.user.first_name} {target_employee.user.last_name}"
                    )),
                    notification_type='appointment',
                    priority='medium'
                )

    @staticmethod
    def send_manager_notifications(location, employee, action: str):
        """Sends notifications to location managers."""
        from notifications.models import Notification
        from providers.models import EmployeeLocationRole

        # Find manager of this location
        managers = EmployeeLocationRole.objects.filter(
            provider_location=location,
            role=EmployeeLocationRole.ROLE_LOCATION_MANAGER,
            is_active=True
        )

        for mgr in managers:
            Notification.objects.create(
                user=mgr.employee.user,
                title=str(_("Staff Update")),
                message=str(_("Staff member {staff} has been {action} in location {location}.").format(
                    staff=f"{employee.user.first_name} {employee.user.last_name}",
                    action=action,
                    location=location.name
                )),
                notification_type='system',
                priority='medium'
            )

