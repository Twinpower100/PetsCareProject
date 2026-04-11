"""
Сериализаторы для API модуля передержки питомцев.

Этот модуль формирует стабильный frontend-friendly контракт для:
1. Профилей ситтеров
2. Объявлений о передержке
3. Откликов ситтеров
4. Жизненного цикла передержки
5. Отзывов и чатов
"""

from django.db.models import Avg, Count
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from geolocation.models import Address
from users.models import User

from .models import (
    Conversation,
    Message,
    PetSitting,
    PetSittingAd,
    PetSittingRequest,
    PetSittingResponse,
    SitterProfile,
    SitterReview,
)


def _serialize_user_brief(user: User | None) -> dict | None:
    """
    Возвращает компактное представление пользователя для API.
    """
    if user is None:
        return None

    profile_picture = getattr(user, 'profile_picture', None)
    return {
        'id': user.id,
        'full_name': user.get_full_name() or user.email,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'profile_picture': profile_picture.url if profile_picture else None,
    }


def _serialize_pet_brief(pet) -> dict | None:
    """
    Возвращает компактное представление питомца для API.
    """
    if pet is None:
        return None

    pet_type = getattr(pet, 'pet_type', None)
    breed = getattr(pet, 'breed', None)
    return {
        'id': pet.id,
        'name': pet.name,
        'pet_type': pet_type.id if pet_type else None,
        'pet_type_name': pet_type.get_localized_name() if pet_type else None,
        'breed': breed.id if breed else None,
        'breed_name': breed.get_localized_name() if breed else None,
        'photo': pet.photo.url if getattr(pet, 'photo', None) else None,
        'weight': float(pet.weight) if getattr(pet, 'weight', None) is not None else None,
        'description': getattr(pet, 'description', '') or '',
        'behavioral_traits': list(getattr(pet, 'behavioral_traits', []) or []),
        'special_needs': getattr(pet, 'special_needs', None),
        'medical_conditions': getattr(pet, 'medical_conditions', None),
        'chronic_conditions': [
            condition.get_localized_name() if hasattr(condition, 'get_localized_name') else condition.name
            for condition in pet.chronic_conditions.all()
        ] if hasattr(pet, 'chronic_conditions') else [],
        'has_medical_conditions': bool(getattr(pet, 'medical_conditions', None)),
        'has_special_needs': bool(getattr(pet, 'special_needs', None)),
    }


def _serialize_location_detail(address: Address | None, fallback_label: str | None = None) -> dict | None:
    """
    Возвращает компактное представление локации объявления.
    """
    if address is None and not fallback_label:
        return None

    if address is None:
        return {
            'formatted_address': fallback_label,
            'latitude': None,
            'longitude': None,
            'city': None,
            'district': None,
            'country': None,
        }

    return {
        'formatted_address': address.formatted_address or fallback_label or address.get_full_address(),
        'latitude': float(address.latitude) if address.latitude is not None else None,
        'longitude': float(address.longitude) if address.longitude is not None else None,
        'city': address.city or None,
        'district': address.district or None,
        'country': address.country or None,
    }


class SitterProfileSerializer(serializers.ModelSerializer):
    """
    Сериализатор профиля ситтера с данными для поиска и кабинета.
    """

    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    full_name = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()

    class Meta:
        model = SitterProfile
        fields = [
            'id',
            'user',
            'user_id',
            'full_name',
            'description',
            'experience_years',
            'pet_types',
            'max_pets',
            'available_from',
            'available_to',
            'max_distance_km',
            'compensation_type',
            'hourly_rate',
            'is_active',
            'is_verified',
            'rating',
            'reviews_count',
            'location',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'full_name',
            'is_verified',
            'rating',
            'reviews_count',
            'location',
            'created_at',
            'updated_at',
        ]

    def get_full_name(self, obj: SitterProfile) -> str:
        """
        Возвращает отображаемое имя ситтера.
        """
        return obj.user.get_full_name() or obj.user.email

    def get_rating(self, obj: SitterProfile) -> float | None:
        """
        Возвращает средний рейтинг ситтера.
        """
        annotated_rating = getattr(obj, 'rating_value', None)
        if annotated_rating is not None:
            return round(float(annotated_rating), 2)

        rating_value = obj.sittings.aggregate(avg=Avg('reviews__rating'))['avg']
        return round(float(rating_value), 2) if rating_value is not None else None

    def get_reviews_count(self, obj: SitterProfile) -> int:
        """
        Возвращает количество отзывов ситтера.
        """
        annotated_count = getattr(obj, 'reviews_count_value', None)
        if annotated_count is not None:
            return int(annotated_count)

        return obj.sittings.aggregate(count=Count('reviews'))['count'] or 0

    def get_location(self, obj: SitterProfile) -> dict | None:
        """
        Возвращает компактную геолокацию ситтера.
        """
        user_location = getattr(obj.user, 'user_location', None)
        if not user_location or not user_location.point:
            return None

        return {
            'latitude': float(user_location.point.y),
            'longitude': float(user_location.point.x),
            'source': user_location.source,
        }

    def validate(self, attrs: dict) -> dict:
        """
        Проверяет согласованность профиля ситтера.
        """
        available_from = attrs.get('available_from', getattr(self.instance, 'available_from', None))
        available_to = attrs.get('available_to', getattr(self.instance, 'available_to', None))
        compensation_type = attrs.get('compensation_type', getattr(self.instance, 'compensation_type', None))
        hourly_rate = attrs.get('hourly_rate', getattr(self.instance, 'hourly_rate', None))

        if available_from and available_to and available_from > available_to:
            raise serializers.ValidationError({'available_to': _('End date must be after start date')})

        if compensation_type == 'paid' and not hourly_rate:
            raise serializers.ValidationError({'hourly_rate': _('Hourly rate is required for paid services')})

        if compensation_type == 'unpaid':
            attrs['hourly_rate'] = None

        return attrs


class PetSittingAdSerializer(serializers.ModelSerializer):
    """
    Сериализатор объявления владельца о поиске передержки.
    """

    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    owner_detail = serializers.SerializerMethodField()
    pet_detail = serializers.SerializerMethodField()
    location_detail = serializers.SerializerMethodField()
    responses_count = serializers.IntegerField(read_only=True)
    address_label = serializers.CharField(write_only=True, required=False, allow_blank=True)
    address_latitude = serializers.FloatField(write_only=True, required=False)
    address_longitude = serializers.FloatField(write_only=True, required=False)
    address_city = serializers.CharField(write_only=True, required=False, allow_blank=True)
    address_country = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = PetSittingAd
        fields = [
            'id',
            'pet',
            'pet_detail',
            'owner',
            'owner_detail',
            'start_date',
            'end_date',
            'description',
            'status',
            'visibility',
            'location',
            'structured_address',
            'location_detail',
            'max_distance_km',
            'compensation_type',
            'responses_count',
            'address_label',
            'address_latitude',
            'address_longitude',
            'address_city',
            'address_country',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'owner_detail',
            'pet_detail',
            'status',
            'visibility',
            'responses_count',
            'location_detail',
            'created_at',
            'updated_at',
        ]

    def get_owner_detail(self, obj: PetSittingAd) -> dict | None:
        """
        Возвращает данные владельца объявления.
        """
        return _serialize_user_brief(obj.owner)

    def get_pet_detail(self, obj: PetSittingAd) -> dict | None:
        """
        Возвращает данные питомца из объявления.
        """
        return _serialize_pet_brief(obj.pet)

    def get_location_detail(self, obj: PetSittingAd) -> dict | None:
        """
        Возвращает структурированную локацию объявления.
        """
        return _serialize_location_detail(obj.structured_address, obj.location)

    def _extract_address_payload(self, validated_data: dict) -> dict:
        return {
            'label': validated_data.pop('address_label', '').strip(),
            'latitude': validated_data.pop('address_latitude', None),
            'longitude': validated_data.pop('address_longitude', None),
            'city': validated_data.pop('address_city', '').strip(),
            'country': validated_data.pop('address_country', '').strip(),
        }

    def _upsert_structured_address(self, instance: PetSittingAd | None, address_payload: dict) -> Address | None:
        label = address_payload['label']
        latitude = address_payload['latitude']
        longitude = address_payload['longitude']
        city = address_payload['city']
        country = address_payload['country']

        has_payload = bool(label or city or country or latitude is not None or longitude is not None)
        if not has_payload:
            return instance.structured_address if instance is not None else None

        address = instance.structured_address if instance and instance.structured_address_id else Address()
        address.formatted_address = label or address.formatted_address
        address.city = city or address.city
        address.country = country or address.country
        if latitude is not None and longitude is not None:
            address.latitude = latitude
            address.longitude = longitude
            address.validation_status = 'valid'
        address.save()
        return address

    def validate(self, attrs: dict) -> dict:
        """
        Проверяет корректность объявления и принадлежность питомца.
        """
        request = self.context.get('request')
        pet = attrs.get('pet', getattr(self.instance, 'pet', None))
        start_date = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end_date = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        address_label = attrs.get('address_label')
        address_latitude = attrs.get('address_latitude')
        address_longitude = attrs.get('address_longitude')

        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({'end_date': _('End date must be after start date')})

        if request and pet and not pet.owners.filter(id=request.user.id).exists():
            raise serializers.ValidationError({'pet': _('You can create pet sitting ads only for your own pets')})

        if (address_latitude is None) != (address_longitude is None):
            raise serializers.ValidationError({'address_latitude': _('Latitude and longitude must be provided together.')})

        if address_label and not attrs.get('location'):
            attrs['location'] = address_label.strip()

        return attrs

    def create(self, validated_data: dict) -> PetSittingAd:
        address_payload = self._extract_address_payload(validated_data)
        structured_address = self._upsert_structured_address(None, address_payload)
        if structured_address is not None:
            validated_data['structured_address'] = structured_address
            validated_data['location'] = address_payload['label'] or validated_data.get('location', '')
        return super().create(validated_data)

    def update(self, instance: PetSittingAd, validated_data: dict) -> PetSittingAd:
        address_payload = self._extract_address_payload(validated_data)
        structured_address = self._upsert_structured_address(instance, address_payload)
        if structured_address is not None:
            validated_data['structured_address'] = structured_address
            if address_payload['label']:
                validated_data['location'] = address_payload['label']
        return super().update(instance, validated_data)


class PetSittingResponseSerializer(serializers.ModelSerializer):
    """
    Сериализатор отклика ситтера на объявление владельца.
    """

    ad_detail = serializers.SerializerMethodField()
    sitter_detail = serializers.SerializerMethodField()

    class Meta:
        model = PetSittingResponse
        fields = [
            'id',
            'ad',
            'ad_detail',
            'sitter',
            'sitter_detail',
            'message',
            'status',
            'created_at',
        ]
        read_only_fields = ['id', 'ad_detail', 'status', 'sitter', 'sitter_detail', 'created_at']

    def get_ad_detail(self, obj: PetSittingResponse) -> dict:
        """
        Возвращает сокращённую информацию по объявлению.
        """
        return {
            'id': obj.ad.id,
            'status': obj.ad.status,
            'start_date': obj.ad.start_date,
            'end_date': obj.ad.end_date,
            'compensation_type': obj.ad.compensation_type,
            'location': obj.ad.location,
            'location_detail': _serialize_location_detail(obj.ad.structured_address, obj.ad.location),
            'pet': _serialize_pet_brief(obj.ad.pet),
            'owner': _serialize_user_brief(obj.ad.owner),
        }

    def get_sitter_detail(self, obj: PetSittingResponse) -> dict | None:
        """
        Возвращает сокращённую информацию о ситтере.
        """
        return {
            'id': obj.sitter.id,
            'user': _serialize_user_brief(obj.sitter.user),
            'description': obj.sitter.description,
            'experience_years': obj.sitter.experience_years,
            'max_pets': obj.sitter.max_pets,
            'compensation_type': obj.sitter.compensation_type,
            'hourly_rate': obj.sitter.hourly_rate,
            'is_active': obj.sitter.is_active,
        }


class PetSittingRequestSerializer(serializers.ModelSerializer):
    """
    Сериализатор явного owner -> sitter запроса на передержку.
    """

    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    initiated_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    owner_detail = serializers.SerializerMethodField()
    sitter_detail = serializers.SerializerMethodField()
    pet_detail = serializers.SerializerMethodField()
    location_detail = serializers.SerializerMethodField()
    conversation_id = serializers.IntegerField(source='conversation.id', read_only=True)
    pet_sitting_id = serializers.IntegerField(source='pet_sitting.id', read_only=True)
    can_accept = serializers.SerializerMethodField()
    can_reject = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    address_label = serializers.CharField(write_only=True, required=False, allow_blank=True)
    address_latitude = serializers.FloatField(write_only=True, required=False)
    address_longitude = serializers.FloatField(write_only=True, required=False)
    address_city = serializers.CharField(write_only=True, required=False, allow_blank=True)
    address_country = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = PetSittingRequest
        fields = [
            'id',
            'owner',
            'owner_detail',
            'sitter',
            'sitter_detail',
            'pet',
            'pet_detail',
            'initiated_by',
            'status',
            'source',
            'start_date',
            'end_date',
            'message',
            'location',
            'structured_address',
            'location_detail',
            'conversation_id',
            'pet_sitting_id',
            'can_accept',
            'can_reject',
            'can_cancel',
            'address_label',
            'address_latitude',
            'address_longitude',
            'address_city',
            'address_country',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'owner_detail',
            'sitter_detail',
            'pet_detail',
            'status',
            'location_detail',
            'conversation_id',
            'pet_sitting_id',
            'can_accept',
            'can_reject',
            'can_cancel',
            'created_at',
            'updated_at',
        ]

    def get_owner_detail(self, obj: PetSittingRequest) -> dict | None:
        """
        Возвращает компактные данные владельца.
        """
        return _serialize_user_brief(obj.owner)

    def get_sitter_detail(self, obj: PetSittingRequest) -> dict | None:
        """
        Возвращает компактные данные ситтера.
        """
        return {
            'id': obj.sitter.id,
            'user': _serialize_user_brief(obj.sitter.user),
            'description': obj.sitter.description,
            'experience_years': obj.sitter.experience_years,
            'max_pets': obj.sitter.max_pets,
            'compensation_type': obj.sitter.compensation_type,
            'hourly_rate': obj.sitter.hourly_rate,
            'is_active': obj.sitter.is_active,
        }

    def get_pet_detail(self, obj: PetSittingRequest) -> dict | None:
        """
        Возвращает краткие данные питомца.
        """
        return _serialize_pet_brief(obj.pet)

    def get_location_detail(self, obj: PetSittingRequest) -> dict | None:
        """
        Возвращает структурированную локацию запроса.
        """
        return _serialize_location_detail(obj.structured_address, obj.location)

    def get_can_accept(self, obj: PetSittingRequest) -> bool:
        """
        Возвращает возможность принять запрос текущим пользователем.
        """
        request = self.context.get('request')
        return bool(
            request
            and request.user.id == obj.sitter.user_id
            and obj.status == PetSittingRequest.STATUS_PENDING
        )

    def get_can_reject(self, obj: PetSittingRequest) -> bool:
        """
        Возвращает возможность отклонить запрос текущим пользователем.
        """
        request = self.context.get('request')
        return bool(
            request
            and request.user.id == obj.sitter.user_id
            and obj.status == PetSittingRequest.STATUS_PENDING
        )

    def get_can_cancel(self, obj: PetSittingRequest) -> bool:
        """
        Возвращает возможность отменить исходящий запрос текущим пользователем.
        """
        request = self.context.get('request')
        return bool(
            request
            and request.user.id == obj.owner_id
            and obj.status == PetSittingRequest.STATUS_PENDING
        )

    def _extract_address_payload(self, validated_data: dict) -> dict:
        """
        Извлекает входные поля адреса из validated_data.
        """
        return {
            'label': validated_data.pop('address_label', '').strip(),
            'latitude': validated_data.pop('address_latitude', None),
            'longitude': validated_data.pop('address_longitude', None),
            'city': validated_data.pop('address_city', '').strip(),
            'country': validated_data.pop('address_country', '').strip(),
        }

    def _upsert_structured_address(self, address_payload: dict) -> Address | None:
        """
        Создаёт структурированный адрес для прямого запроса.
        """
        label = address_payload['label']
        latitude = address_payload['latitude']
        longitude = address_payload['longitude']
        city = address_payload['city']
        country = address_payload['country']

        has_payload = bool(label or city or country or latitude is not None or longitude is not None)
        if not has_payload:
            return None

        address = Address()
        address.formatted_address = label
        address.city = city or None
        address.country = country or None
        if latitude is not None and longitude is not None:
            address.latitude = latitude
            address.longitude = longitude
            address.validation_status = 'valid'
        address.save()
        return address

    def validate(self, attrs: dict) -> dict:
        """
        Проверяет корректность дат, питомца и координат.
        """
        request = self.context.get('request')
        pet = attrs.get('pet', getattr(self.instance, 'pet', None))
        sitter = attrs.get('sitter', getattr(self.instance, 'sitter', None))
        start_date = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end_date = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        address_label = attrs.get('address_label')
        address_latitude = attrs.get('address_latitude')
        address_longitude = attrs.get('address_longitude')

        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({'end_date': _('End date must be after start date')})

        if request and pet and not pet.owners.filter(id=request.user.id).exists():
            raise serializers.ValidationError({'pet': _('You can create pet sitting requests only for your own pets.')})

        if request and sitter and sitter.user_id == request.user.id:
            raise serializers.ValidationError({'sitter': _('You cannot create a pet sitting request for yourself.')})

        if (address_latitude is None) != (address_longitude is None):
            raise serializers.ValidationError({'address_latitude': _('Latitude and longitude must be provided together.')})

        if address_label and not attrs.get('location'):
            attrs['location'] = address_label.strip()

        return attrs

    def create(self, validated_data: dict) -> PetSittingRequest:
        """
        Создаёт прямой запрос на передержку с опциональным структурированным адресом.
        """
        address_payload = self._extract_address_payload(validated_data)
        structured_address = self._upsert_structured_address(address_payload)
        if structured_address is not None:
            validated_data['structured_address'] = structured_address
            validated_data['location'] = address_payload['label'] or validated_data.get('location', '')
        return super().create(validated_data)


class PetSittingSerializer(serializers.ModelSerializer):
    """
    Сериализатор жизненного цикла передержки.
    """

    pet_detail = serializers.SerializerMethodField()
    sitter_detail = serializers.SerializerMethodField()
    owner_detail = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    can_confirm_start = serializers.SerializerMethodField()
    can_confirm_end = serializers.SerializerMethodField()
    can_leave_review = serializers.SerializerMethodField()

    class Meta:
        model = PetSitting
        fields = [
            'id',
            'ad',
            'response',
            'sitter',
            'pet',
            'pet_detail',
            'sitter_detail',
            'owner_detail',
            'start_date',
            'end_date',
            'status',
            'status_display',
            'owner_confirmed_start',
            'sitter_confirmed_start',
            'owner_confirmed_end',
            'sitter_confirmed_end',
            'review_left',
            'can_confirm_start',
            'can_confirm_end',
            'can_leave_review',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_pet_detail(self, obj: PetSitting) -> dict | None:
        """
        Возвращает компактные данные питомца.
        """
        return _serialize_pet_brief(obj.pet)

    def get_sitter_detail(self, obj: PetSitting) -> dict | None:
        """
        Возвращает компактные данные ситтера.
        """
        return {
            'id': obj.sitter.id,
            'user': _serialize_user_brief(obj.sitter.user),
            'description': obj.sitter.description,
            'experience_years': obj.sitter.experience_years,
            'max_pets': obj.sitter.max_pets,
            'hourly_rate': obj.sitter.hourly_rate,
            'is_active': obj.sitter.is_active,
        }

    def get_owner_detail(self, obj: PetSitting) -> dict | None:
        """
        Возвращает компактные данные владельца.
        """
        return _serialize_user_brief(obj.ad.owner)

    def get_can_confirm_start(self, obj: PetSitting) -> bool:
        """
        Проверяет, может ли текущий пользователь подтвердить старт.
        """
        request = self.context.get('request')
        if request is None or obj.status != 'waiting_start':
            return False

        if request.user.id == obj.ad.owner_id:
            return not obj.owner_confirmed_start
        if request.user.id == obj.sitter.user_id:
            return not obj.sitter_confirmed_start
        return False

    def get_can_confirm_end(self, obj: PetSitting) -> bool:
        """
        Проверяет, может ли текущий пользователь подтвердить завершение.
        """
        request = self.context.get('request')
        if request is None or obj.status != 'active':
            return False

        if request.user.id == obj.ad.owner_id:
            return not obj.owner_confirmed_end
        if request.user.id == obj.sitter.user_id:
            return not obj.sitter_confirmed_end
        return False

    def get_can_leave_review(self, obj: PetSitting) -> bool:
        """
        Проверяет, может ли текущий пользователь оставить отзыв.
        """
        request = self.context.get('request')
        return bool(
            request
            and request.user.id == obj.ad.owner_id
            and obj.status == 'waiting_review'
            and not obj.review_left
        )


class SitterReviewSerializer(serializers.ModelSerializer):
    """
    Сериализатор отзыва о завершённой передержке.
    """

    author_detail = serializers.SerializerMethodField()

    class Meta:
        model = SitterReview
        fields = ['id', 'history', 'author', 'author_detail', 'rating', 'text', 'created_at']
        read_only_fields = ['id', 'author', 'author_detail', 'created_at']

    def get_author_detail(self, obj: SitterReview) -> dict | None:
        """
        Возвращает краткие данные автора отзыва.
        """
        return _serialize_user_brief(obj.author)


class MessageSerializer(serializers.ModelSerializer):
    """
    Сериализатор сообщений чата с расшифрованным текстом.
    """

    sender_name = serializers.CharField(source='sender.get_full_name', read_only=True)
    sender_avatar = serializers.SerializerMethodField()
    recipient_name = serializers.CharField(source='recipient.get_full_name', read_only=True)
    recipient_avatar = serializers.SerializerMethodField()
    text = serializers.CharField(source='decrypted_text', read_only=True)

    class Meta:
        model = Message
        fields = [
            'id',
            'sender',
            'sender_name',
            'sender_avatar',
            'recipient',
            'recipient_name',
            'recipient_avatar',
            'text',
            'created_at',
            'is_read',
        ]
        read_only_fields = fields

    def get_sender_avatar(self, obj: Message) -> str | None:
        """
        Возвращает URL аватара отправителя.
        """
        picture = getattr(obj.sender, 'profile_picture', None)
        return picture.url if picture else None

    def get_recipient_avatar(self, obj: Message) -> str | None:
        """
        Возвращает URL аватара получателя.
        """
        picture = getattr(obj.recipient, 'profile_picture', None)
        return picture.url if picture else None


class ConversationSerializer(serializers.ModelSerializer):
    """
    Сериализатор списка диалогов.
    """

    participants = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()
    pet_sitting_ad_id = serializers.IntegerField(source='pet_sitting_ad.id', read_only=True)
    pet_sitting_id = serializers.IntegerField(source='pet_sitting.id', read_only=True)
    other_participant_sitter_profile_id = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id',
            'participants',
            'other_participant',
            'other_participant_sitter_profile_id',
            'pet_sitting_ad_id',
            'pet_sitting_id',
            'last_message',
            'unread_count',
            'created_at',
            'updated_at',
            'is_active',
        ]
        read_only_fields = fields

    def get_participants(self, obj: Conversation) -> list[dict]:
        """
        Возвращает список участников диалога.
        """
        return [_serialize_user_brief(user) for user in obj.participants.all()]

    def get_last_message(self, obj: Conversation) -> dict | None:
        """
        Возвращает краткое описание последнего сообщения.
        """
        last_message = obj.messages.last()
        if last_message is None:
            return None

        decrypted_text = last_message.decrypted_text
        preview = decrypted_text[:100] + '...' if len(decrypted_text) > 100 else decrypted_text
        return {
            'id': last_message.id,
            'text': preview,
            'sender_name': last_message.sender.get_full_name() or last_message.sender.email,
            'created_at': last_message.created_at,
        }

    def get_unread_count(self, obj: Conversation) -> int:
        """
        Возвращает количество непрочитанных сообщений.
        """
        request = self.context.get('request')
        if request is None:
            return 0
        return obj.messages.filter(is_read=False, recipient=request.user).count()

    def get_other_participant(self, obj: Conversation) -> dict | None:
        """
        Возвращает второго участника диалога.
        """
        request = self.context.get('request')
        if request is None:
            return None
        return _serialize_user_brief(obj.get_other_participant(request.user))

    def get_other_participant_sitter_profile_id(self, obj: Conversation) -> int | None:
        """
        Возвращает ID профиля ситтера второго участника, если он существует.
        """
        request = self.context.get('request')
        if request is None:
            return None

        other_participant = obj.get_other_participant(request.user)
        if other_participant is None:
            return None

        sitter_profile = getattr(other_participant, 'sitter', None)
        return sitter_profile.id if sitter_profile else None


class ConversationDetailSerializer(ConversationSerializer):
    """
    Детальный сериализатор диалога с сообщениями.
    """

    messages = MessageSerializer(many=True, read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ['messages']
