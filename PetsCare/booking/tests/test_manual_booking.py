from rest_framework import status
from rest_framework.test import APITestCase

from booking.test_booking_flow_logic import BookingFlowBaseMixin


class ManualBookingDeprecatedApiTests(BookingFlowBaseMixin, APITestCase):
    """Проверки, что legacy hybrid manual-booking API больше не доступен."""

    def setUp(self):
        super().setUp()
        self.employee_a.user.add_role('employee')
        self.client.force_authenticate(self.employee_a.user)

    def test_legacy_manual_booking_create_endpoint_is_not_available(self):
        response = self.client.post(
            '/api/v1/provider/bookings/manual/',
            {
                'is_guest': True,
                'guest_client_phone': '+38267000111',
                'guest_client_name': 'Walk In Client',
                'guest_pet_name': 'Lucky',
                'guest_pet_species': 'Dog',
                'guest_pet_type_id': self.pet_type.id,
                'provider_location_id': self.location_a.id,
                'employee_id': self.employee_a.id,
                'service_id': self.service.id,
                'start_time': self._dt(12, 0).isoformat(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_legacy_manual_booking_search_endpoint_is_not_available(self):
        response = self.client.get(
            '/api/v1/provider/bookings/manual/search/',
            {'query': 'rex'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
