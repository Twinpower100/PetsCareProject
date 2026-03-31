from datetime import timedelta

from rest_framework import status
from rest_framework.test import APITestCase
from django.utils import timezone

from booking.constants import CANCELLED_BY_PROVIDER
from booking.models import ManualBooking
from booking.test_booking_flow_logic import BookingFlowBaseMixin
from catalog.models import Service
from pets.models import Breed


class ManualBookingV2Tests(BookingFlowBaseMixin, APITestCase):
    """Регрессии для provider-owned Manual Booking V2."""

    def setUp(self):
        super().setUp()
        self.employee_a.user.add_role('employee')
        self.manual_bookings_url = '/api/v1/manual-bookings/'
        self.breed = Breed.objects.create(
            pet_type=self.pet_type,
            name='Unknown',
            code='unknown_dog',
        )

    def test_service_capabilities_are_inherited_from_hierarchy_node(self):
        emergency_root = Service.objects.create(
            code='emergency_root',
            name='Emergency Root',
            level=0,
            hierarchy_order='99',
            emergency_capability_mode=Service.EmergencyCapabilityMode.ENABLED,
            protocol_family_mode=Service.ProtocolFamilyMode.VETERINARY,
        )
        emergency_leaf = Service.objects.create(
            code='emergency_leaf',
            name='Emergency Leaf',
            parent=emergency_root,
            level=1,
            hierarchy_order='99_1',
        )

        self.assertTrue(emergency_leaf.resolve_emergency_capable())
        self.assertEqual(
            emergency_leaf.resolve_protocol_family(),
            Service.ProtocolFamilyMode.VETERINARY,
        )

        emergency_leaf.emergency_capability_mode = Service.EmergencyCapabilityMode.DISABLED
        emergency_leaf.protocol_family_mode = Service.ProtocolFamilyMode.NONE

        self.assertFalse(emergency_leaf.resolve_emergency_capable())
        self.assertEqual(
            emergency_leaf.resolve_protocol_family(),
            Service.ProtocolFamilyMode.NONE,
        )

    def test_provider_can_cancel_manual_booking_without_explicit_reason_id(self):
        self.client.force_authenticate(self.employee_a.user)
        future_start = timezone.localtime(timezone.now()) + timedelta(hours=1)

        create_response = self.client.post(
            self.manual_bookings_url,
            {
                'provider_id': self.provider.id,
                'provider_location_id': self.location_a.id,
                'employee_id': self.employee_a.id,
                'service_id': self.service.id,
                'pet_type_id': self.pet_type.id,
                'breed_id': self.breed.id,
                'size_code': 'S',
                'owner_first_name': 'Desk',
                'owner_last_name': 'Client',
                'owner_phone_number': '+38267000991',
                'owner_email': 'desk@example.com',
                'pet_name': 'Shadow',
                'start_time': future_start.isoformat(),
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED, create_response.data)

        booking_id = create_response.data['id']  # type: ignore[index]
        cancel_response = self.client.post(
            f'/api/v1/manual-bookings/{booking_id}/cancel/',
            {
                'cancellation_reason_text': 'Desk cancelled after phone confirmation.',
            },
            format='json',
        )

        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
        booking = ManualBooking.objects.get(id=booking_id)
        self.assertEqual(booking.status, 'cancelled')
        self.assertEqual(booking.cancelled_by, CANCELLED_BY_PROVIDER)
        self.assertEqual(booking.cancellation_reason.scope, CANCELLED_BY_PROVIDER)
