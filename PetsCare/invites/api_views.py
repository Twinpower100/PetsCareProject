"""
Единые API-представления для создания, приёма, отклонения и просмотра инвайтов.
"""
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView
from django.utils.translation import gettext_lazy as _
from users.email_verification_permissions import require_verified_email_for_owner_action

from .models import Invite
from .serializers import (
    InviteSerializer,
    InviteCreateSerializer,
    InviteAcceptSerializer,
    InviteDeclineSerializer,
)
from .email import send_invite_email


def _can_create_invite(request, invite_type, provider=None, provider_location=None, pet=None):
    """
    Проверяет, может ли request.user создать инвайт данного типа.
    Возвращает (True, None) или (False, error_message).
    """
    from providers.api_views import _user_is_owner_for_provider, _location_manager_queryset
    from users.models import User

    user = request.user
    if not user or not user.is_authenticated:
        return False, _('Authentication required.')

    if invite_type in (Invite.TYPE_PROVIDER_MANAGER, Invite.TYPE_PROVIDER_ADMIN):
        if not provider:
            return False, _('Provider is required.')
        if not _user_is_owner_for_provider(user, provider):
            return False, _('Only the owner can invite a manager or admin.')
        return True, None

    if invite_type in (Invite.TYPE_BRANCH_MANAGER, Invite.TYPE_SPECIALIST):
        if not provider_location:
            return False, _('Provider location is required.')
        resource_code = 'staff.roles' if invite_type == Invite.TYPE_BRANCH_MANAGER else 'staff.invite'
        action = 'update' if invite_type == Invite.TYPE_BRANCH_MANAGER else 'create'
        qs = _location_manager_queryset(request, resource_code, action)
        if not qs.filter(pk=provider_location.pk).exists():
            return False, _('You do not manage this location.')
        return True, None

    if invite_type in (Invite.TYPE_PET_CO_OWNER, Invite.TYPE_PET_TRANSFER):
        if not pet:
            return False, _('Pet is required.')
        if pet.main_owner_id != user.pk:
            return False, _('Only the main owner can invite or transfer ownership.')
        return True, None

    return False, _('Unknown invite type.')


def _get_invite_accept_link(invite: Invite) -> str:
    provider_admin_url = getattr(settings, 'PROVIDER_ADMIN_URL', 'http://localhost:5173').rstrip('/')
    frontend_url = getattr(settings, 'FRONTEND_URL', provider_admin_url).rstrip('/')

    if invite.invite_type in (Invite.TYPE_PROVIDER_MANAGER, Invite.TYPE_PROVIDER_ADMIN):
        return f'{provider_admin_url}/accept-organization-role-invite'
    if invite.invite_type == Invite.TYPE_BRANCH_MANAGER:
        return f'{provider_admin_url}/accept-location-manager-invite'
    if invite.invite_type == Invite.TYPE_SPECIALIST:
        return f'{provider_admin_url}/accept-location-staff-invite'
    if invite.invite_type in (Invite.TYPE_PET_CO_OWNER, Invite.TYPE_PET_TRANSFER):
        return f'{frontend_url}/pet-invite/{invite.token}/'
    return f'{provider_admin_url}/invite/{invite.token}/'


class InviteListCreateAPIView(APIView):
    """
    Список инвайтов (GET) и создание (POST). GET/POST /api/v1/invites/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Invite.objects.all().select_related(
            'provider', 'provider_location', 'pet', 'created_by', 'accepted_by',
        )
        managed = request.user.get_managed_providers()
        from django.db.models import Q
        qs = qs.filter(
            Q(created_by=request.user) |
            Q(provider__in=managed) |
            Q(provider_location__provider__in=managed)
        ).distinct()
        for key in ('invite_type', 'status', 'provider', 'provider_location'):
            val = request.query_params.get(key)
            if val is not None and val != '':
                qs = qs.filter(**{key: val})
        ser = InviteSerializer(qs, many=True)
        return Response(ser.data)

    def post(self, request):
        require_verified_email_for_owner_action(request.user)
        from providers.models import Provider, ProviderLocation
        from pets.models import Pet
        from users.models import User

        ser = InviteCreateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        invite_type = data['invite_type']
        email = data['email'].strip().lower()
        provider = None
        provider_location = None
        pet = None
        if data.get('provider_id'):
            provider = get_object_or_404(Provider, pk=data['provider_id'])
        if data.get('provider_location_id'):
            provider_location = get_object_or_404(ProviderLocation, pk=data['provider_location_id'])
            if not provider and provider_location:
                provider = provider_location.provider
        if data.get('pet_id'):
            pet = get_object_or_404(Pet, pk=data['pet_id'])

        ok, err = _can_create_invite(request, invite_type, provider, provider_location, pet)
        if not ok:
            return Response({'detail': err}, status=status.HTTP_403_FORBIDDEN)

        try:
            User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {'email': [_('No user with this email address was found.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Дополнительные проверки: уже есть роль / уже приглашён
        if invite_type == Invite.TYPE_PROVIDER_MANAGER and provider:
            from providers.models import EmployeeProvider
            from providers.api_views import _active_employee_provider_q
            if EmployeeProvider.objects.filter(
                provider=provider,
                employee__user__email__iexact=email,
                is_provider_manager=True,
            ).filter(_active_employee_provider_q()).exists():
                return Response(
                    {'email': [_('This user already has this role for this provider.')]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if invite_type == Invite.TYPE_SPECIALIST and provider_location:
            if provider_location.employees.filter(user__email__iexact=email).exists():
                return Response(
                    {'email': [_('This user is already a staff member at this location.')]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Удаляем старые pending инвайты того же типа/контекста
        old_filter = {
            'invite_type': invite_type,
            'email__iexact': email,
            'status': Invite.STATUS_PENDING,
        }
        if provider:
            old_filter['provider'] = provider
        if provider_location:
            old_filter['provider_location'] = provider_location
        if pet:
            old_filter['pet'] = pet
        Invite.objects.filter(**old_filter).delete()

        try:
            token = Invite.generate_token()
        except Exception:
            return Response(
                {'detail': _('Could not generate a unique activation code. Please try again.')},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        expires_at = timezone.now() + timezone.timedelta(days=7)
        invite = Invite(
            invite_type=invite_type,
            email=email,
            token=token,
            expires_at=expires_at,
            created_by=request.user,
            provider=provider,
            provider_location=provider_location,
            pet=pet,
            position=data.get('position', ''),
            comment=data.get('comment', ''),
        )
        invite.save()
        language = (data.get('language') or 'en').strip() or 'en'
        send_invite_email(invite, language)
        return Response(
            {
                'detail': _('Invitation sent.'),
                'invite_id': invite.pk,
                'expires_at': invite.expires_at,
            },
            status=status.HTTP_201_CREATED,
        )


class InviteAcceptAPIView(APIView):
    """
    Приём инвайта по 6-значному коду. POST /api/v1/invites/accept/
    AllowAny: код является секретом.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from users.models import User

        ser = InviteAcceptSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        token = (ser.validated_data['token'] or '').strip()
        if len(token) != 6 or not token.isdigit():
            return Response(
                {'token': [_('Enter the 6-digit code from the email.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invite = Invite.objects.filter(token=token).select_related(
            'provider', 'provider_location', 'pet',
        ).first()
        if not invite:
            return Response(
                {'token': [_('Invalid or expired code.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if invite.is_expired():
            invite.status = Invite.STATUS_EXPIRED
            invite.save(update_fields=['status'])
            return Response(
                {'token': [_('This invitation has expired. You can ask the administrator to send a new one.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if invite.status != Invite.STATUS_PENDING:
            return Response(
                {'token': [_('This invitation has already been used.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            user = User.objects.get(email__iexact=invite.email)
        except User.DoesNotExist:
            return Response(
                {'detail': _('User no longer exists.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                invite.accept(user)
        except ValueError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            'detail': _('You have accepted the invitation.'),
            'invite_type': invite.invite_type,
        })


class InviteDeclineAPIView(APIView):
    """Отклонение инвайта. POST /api/v1/invites/decline/"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from users.models import User

        ser = InviteDeclineSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        token = (ser.validated_data['token'] or '').strip()
        invite = Invite.objects.filter(token=token).first()
        if not invite:
            return Response(
                {'token': [_('Invalid or expired code.')]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if invite.status != Invite.STATUS_PENDING:
            return Response(
                {'detail': _('This invitation has already been used or declined.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            user = User.objects.get(email__iexact=invite.email)
        except User.DoesNotExist:
            return Response(
                {'detail': _('User no longer exists.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            invite.decline(user)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': _('Invitation declined.')})


class InviteDetailAPIView(APIView):
    """
    Детали инвайта (GET) и отмена (DELETE). GET/DELETE /api/v1/invites/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get_queryset(self, request):
        qs = Invite.objects.all().select_related(
            'provider', 'provider_location', 'pet', 'created_by', 'accepted_by',
        )
        managed = request.user.get_managed_providers()
        from django.db.models import Q
        return qs.filter(
            Q(created_by=request.user) |
            Q(provider__in=managed) |
            Q(provider_location__provider__in=managed)
        ).distinct()

    def get(self, request, pk):
        invite = get_object_or_404(self._get_queryset(request), pk=pk)
        return Response(InviteSerializer(invite).data)

    def delete(self, request, pk):
        invite = get_object_or_404(self._get_queryset(request), pk=pk)
        if invite.status != Invite.STATUS_PENDING:
            return Response(
                {'detail': _('Only pending invites can be cancelled.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invite.cancel()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InviteCancelAPIView(APIView):
    """
    Отмена инвайта создателем. DELETE /api/v1/invites/<id>/ или POST /api/v1/invites/<id>/cancel/
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get_invite(self, request, pk):
        invite = get_object_or_404(Invite, pk=pk)
        managed = request.user.get_managed_providers()
        from django.db.models import Q
        can_see = (
            invite.created_by_id == request.user.pk or
            (invite.provider_id and invite.provider_id in managed.values_list('pk', flat=True)) or
            (invite.provider_location_id and invite.provider_location.provider_id in managed.values_list('pk', flat=True))
        )
        if not can_see:
            raise PermissionDenied(_('You cannot cancel this invite.'))
        return invite

    def delete(self, request, pk):
        invite = self._get_invite(request, pk)
        if invite.status != Invite.STATUS_PENDING:
            return Response(
                {'detail': _('Only pending invites can be cancelled.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invite.cancel()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def post(self, request, pk):
        """POST .../cancel/ для отмены."""
        invite = self._get_invite(request, pk)
        if invite.status != Invite.STATUS_PENDING:
            return Response(
                {'detail': _('Only pending invites can be cancelled.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invite.cancel()
        return Response({'detail': _('Invitation cancelled.')})


class InvitePendingAPIView(ListAPIView):
    """Список pending инвайтов для текущего пользователя (по email). GET /api/v1/invites/pending/"""
    serializer_class = InviteSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        email = self.request.query_params.get('email', '').strip().lower()
        if not email:
            return Invite.objects.none()
        return Invite.objects.filter(
            email__iexact=email,
            status=Invite.STATUS_PENDING,
            expires_at__gt=timezone.now(),
        ).select_related('provider', 'provider_location', 'pet')


class InviteByTokenAPIView(APIView):
    """Информация по токену без приёма. GET /api/v1/invites/token/<token>/"""
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        invite = Invite.objects.filter(token=token).select_related(
            'provider', 'provider_location', 'pet',
        ).first()
        if not invite:
            return Response(
                {'detail': _('Invalid or expired code.')},
                status=status.HTTP_404_NOT_FOUND,
            )
        if invite.status != Invite.STATUS_PENDING:
            return Response(
                {'detail': _('This invitation has already been used.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if invite.is_expired():
            return Response(
                {'detail': _('This invitation has expired.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = InviteSerializer(invite)
        return Response(ser.data)


class InviteQRCodeAPIView(APIView):
    """QR-код инвайта. GET /api/v1/invites/<id>/qr-code/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        invite = get_object_or_404(Invite, pk=pk)
        if invite.created_by_id != request.user.pk:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(_('Only the creator can view this invite QR code.'))
        if invite.status != Invite.STATUS_PENDING or invite.is_expired():
            return Response(
                {'detail': _('This invitation is no longer valid.')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        link = _get_invite_accept_link(invite)
        import qrcode
        from io import BytesIO
        import base64
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(link)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return Response({'qr_code_base64': img_base64, 'link': link})
