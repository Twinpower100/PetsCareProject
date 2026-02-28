"""
Сериализаторы для унифицированной модели Invite.
"""
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import Invite


class InviteSerializer(serializers.ModelSerializer):
    """Сериализатор для чтения инвайта."""
    provider_name = serializers.CharField(source='provider.name', read_only=True, default='')
    provider_location_name = serializers.CharField(
        source='provider_location.name', read_only=True, default='',
    )

    class Meta:
        model = Invite
        fields = [
            'id',
            'invite_type',
            'email',
            'status',
            'expires_at',
            'created_at',
            'created_by',
            'provider',
            'provider_location',
            'pet',
            'provider_name',
            'provider_location_name',
            'accepted_at',
            'accepted_by',
            'declined_at',
            'position',
            'comment',
        ]
        read_only_fields = [
            'id',
            'token',
            'status',
            'created_at',
            'accepted_at',
            'accepted_by',
            'declined_at',
        ]


class InviteCreateSerializer(serializers.Serializer):
    """
    Сериализатор создания инвайта.
    POST /api/v1/invites/ body зависит от invite_type.
    """
    invite_type = serializers.ChoiceField(choices=Invite.TYPE_CHOICES)
    email = serializers.EmailField()
    provider_id = serializers.IntegerField(required=False, allow_null=True)
    provider_location_id = serializers.IntegerField(required=False, allow_null=True)
    pet_id = serializers.IntegerField(required=False, allow_null=True)
    language = serializers.CharField(required=False, default='en', max_length=10)
    position = serializers.CharField(required=False, allow_blank=True, max_length=100)
    comment = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        invite_type = attrs['invite_type']
        provider_types = (Invite.TYPE_PROVIDER_MANAGER, Invite.TYPE_PROVIDER_ADMIN)
        location_types = (Invite.TYPE_BRANCH_MANAGER, Invite.TYPE_SPECIALIST)
        pet_types = (Invite.TYPE_PET_CO_OWNER, Invite.TYPE_PET_TRANSFER)

        if invite_type in provider_types:
            if not attrs.get('provider_id'):
                raise serializers.ValidationError({
                    'provider_id': _('Required for this invite type.'),
                })
        elif invite_type in location_types:
            if not attrs.get('provider_location_id'):
                raise serializers.ValidationError({
                    'provider_location_id': _('Required for this invite type.'),
                })
        elif invite_type in pet_types:
            if not attrs.get('pet_id'):
                raise serializers.ValidationError({
                    'pet_id': _('Required for this invite type.'),
                })
        return attrs


class InviteAcceptSerializer(serializers.Serializer):
    """Сериализатор приёма инвайта. POST /api/v1/invites/accept/"""
    token = serializers.CharField(max_length=6, trim_whitespace=True)


class InviteDeclineSerializer(serializers.Serializer):
    """Сериализатор отклонения инвайта. POST /api/v1/invites/decline/"""
    token = serializers.CharField(max_length=6, trim_whitespace=True)
