"""API views для Manual Booking V2."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from booking.manual_v2_models import ManualBooking
from booking.constants import CANCELLED_BY_PROVIDER
from booking.manual_v2_serializers import (
    ManualBookingCancelSerializer,
    ManualBookingCreateUpdateSerializer,
    ManualBookingDetailSerializer,
    ManualBookingListSerializer,
    ManualBookingProtocolUpsertSerializer,
    ManualBookingResolveConflictSerializer,
    ManualVisitProtocolSerializer,
)
from booking.manual_v2_services import (
    ManualBookingAccessService,
    ManualBookingDocumentService,
    ManualBookingOptionsService,
    ManualBookingServiceV2,
)
from booking.models import BookingCancellationReason
from booking.unified_services import BookingDomainError
from providers.models import Provider


class ManualBookingOptionsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            provider_id = int(request.query_params.get('provider_id'))
        except (TypeError, ValueError):
            return Response({'code': 'provider_required', 'message': 'provider_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        start_time = request.query_params.get('start_time')
        try:
            payload = ManualBookingOptionsService.get_options(
                actor=request.user,
                provider_id=provider_id,
                location_id=self._optional_int(request.query_params.get('location_id')),
                pet_type_id=self._optional_int(request.query_params.get('pet_type_id')),
                size_code=request.query_params.get('size_code'),
                service_id=self._optional_int(request.query_params.get('service_id')),
                start_time=self._optional_datetime(start_time),
            )
            return Response(payload)
        except BookingDomainError as exc:
            return Response(exc.to_dict(), status=exc.status_code)

    @staticmethod
    def _optional_int(value):
        if value in (None, ''):
            return None
        return int(value)

    @staticmethod
    def _optional_datetime(value):
        if not value:
            return None
        serializer = ManualBookingCreateUpdateSerializer(data={
            'provider_id': 1,
            'service_id': 1,
            'pet_type_id': 1,
            'breed_id': 1,
            'size_code': 'S',
            'owner_first_name': 'X',
            'owner_last_name': 'Y',
            'owner_phone_number': '+38267000000',
            'pet_name': 'Pet',
            'start_time': value,
        })
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data['start_time']


class ManualBookingListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        provider_id = request.query_params.get('provider')
        if not provider_id:
            return Response({'code': 'provider_required', 'message': 'provider query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        provider = get_object_or_404(Provider, id=provider_id)
        try:
            ManualBookingAccessService.ensure_provider_staff(request.user, provider)
        except BookingDomainError as exc:
            return Response(exc.to_dict(), status=exc.status_code)

        queryset = ManualBooking.objects.filter(provider=provider).select_related(
            'provider',
            'provider_location',
            'employee__user',
            'service',
            'service__parent',
            'pet_type',
            'breed',
            'lead',
            'cancellation_reason',
        ).order_by('start_time')
        return Response(ManualBookingListSerializer(queryset, many=True, context={'request': request}).data)

    def post(self, request):
        serializer = ManualBookingCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            booking = ManualBookingServiceV2.create_manual_booking(actor=request.user, payload=serializer.validated_data)
            return Response(ManualBookingDetailSerializer(booking, context={'request': request}).data, status=status.HTTP_201_CREATED)
        except BookingDomainError as exc:
            return Response(exc.to_dict(), status=exc.status_code)


class ManualBookingDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, booking_id: int):
        booking = self._get_booking(request.user, booking_id)
        return Response(ManualBookingDetailSerializer(booking, context={'request': request}).data)

    def patch(self, request, booking_id: int):
        booking = self._get_booking(request.user, booking_id)
        serializer = ManualBookingCreateUpdateSerializer(data={**request.data, 'provider_id': booking.provider_id}, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            updated = ManualBookingServiceV2.update_manual_booking(
                actor=request.user,
                manual_booking=booking,
                payload=serializer.validated_data,
            )
            return Response(ManualBookingDetailSerializer(updated, context={'request': request}).data)
        except BookingDomainError as exc:
            return Response(exc.to_dict(), status=exc.status_code)

    @staticmethod
    def _get_booking(user, booking_id: int) -> ManualBooking:
        booking = get_object_or_404(
            ManualBooking.objects.select_related(
                'provider',
                'provider_location',
                'employee__user',
                'service',
                'service__parent',
                'pet_type',
                'breed',
                'lead',
                'cancellation_reason',
                'manual_visit_protocol',
            ),
            id=booking_id,
        )
        try:
            ManualBookingAccessService.ensure_provider_staff(user, booking.provider)
        except BookingDomainError as exc:
            raise PermissionDenied(str(exc.message)) from exc
        return booking


class ManualBookingProtocolAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, booking_id: int):
        return self._upsert(request, booking_id)

    def patch(self, request, booking_id: int):
        return self._upsert(request, booking_id)

    def _upsert(self, request, booking_id: int):
        booking = ManualBookingDetailAPIView._get_booking(request.user, booking_id)
        serializer = ManualBookingProtocolUpsertSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            protocol = ManualBookingServiceV2.upsert_protocol(
                actor=request.user,
                manual_booking=booking,
                payload=serializer.validated_data,
            )
            return Response(ManualVisitProtocolSerializer(protocol).data)
        except BookingDomainError as exc:
            return Response(exc.to_dict(), status=exc.status_code)


class ManualBookingResolveConflictAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ManualBookingResolveConflictSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            booking = ManualBookingServiceV2.resolve_emergency_conflict(actor=request.user, payload=serializer.validated_data)
            return Response(ManualBookingDetailSerializer(booking, context={'request': request}).data, status=status.HTTP_201_CREATED)
        except BookingDomainError as exc:
            return Response(exc.to_dict(), status=exc.status_code)


class ManualBookingCancelAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, booking_id: int):
        booking = ManualBookingDetailAPIView._get_booking(request.user, booking_id)
        serializer = ManualBookingCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancellation_reason_id = serializer.validated_data.get('cancellation_reason_id')
        if cancellation_reason_id is not None:
            cancellation_reason = get_object_or_404(
                BookingCancellationReason,
                id=cancellation_reason_id,
                is_active=True,
            )
        else:
            BookingCancellationReason.ensure_default_reasons()
            cancellation_reason = BookingCancellationReason.get_default_reason(CANCELLED_BY_PROVIDER)
            if cancellation_reason is None:
                cancellation_reason = BookingCancellationReason.objects.filter(
                    scope=CANCELLED_BY_PROVIDER,
                    is_active=True,
                ).order_by('sort_order', 'id').first()
            if cancellation_reason is None:
                cancellation_reason = BookingCancellationReason.objects.create(
                    scope=CANCELLED_BY_PROVIDER,
                    code='manual_provider_other',
                    label=str(_('Other')),
                    is_active=True,
                )
        try:
            booking = ManualBookingServiceV2.cancel_manual_booking(
                actor=request.user,
                manual_booking=booking,
                cancellation_reason=cancellation_reason,
                cancellation_reason_text=serializer.validated_data.get('cancellation_reason_text', ''),
            )
            return Response(ManualBookingDetailSerializer(booking, context={'request': request}).data)
        except BookingDomainError as exc:
            return Response(exc.to_dict(), status=exc.status_code)


class ManualBookingCompleteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, booking_id: int):
        booking = ManualBookingDetailAPIView._get_booking(request.user, booking_id)
        try:
            booking = ManualBookingServiceV2.complete_manual_booking(actor=request.user, manual_booking=booking)
            return Response(ManualBookingDetailSerializer(booking, context={'request': request}).data)
        except BookingDomainError as exc:
            return Response(exc.to_dict(), status=exc.status_code)


class ManualBookingPrintAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, booking_id: int):
        booking = ManualBookingDetailAPIView._get_booking(request.user, booking_id)
        if not booking.requires_protocol or not hasattr(booking, 'manual_visit_protocol'):
            return Response(
                {'code': 'manual_booking_protocol_unavailable', 'message': 'Protocol is not available for this manual booking.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return ManualBookingDocumentService.render_print_response(booking.manual_visit_protocol)


class ManualBookingPdfAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, booking_id: int):
        booking = ManualBookingDetailAPIView._get_booking(request.user, booking_id)
        if not booking.requires_protocol or not hasattr(booking, 'manual_visit_protocol'):
            return Response(
                {'code': 'manual_booking_protocol_unavailable', 'message': 'Protocol is not available for this manual booking.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return ManualBookingDocumentService.render_pdf_response(booking.manual_visit_protocol)
