"""
Тесты для API модуля передержки.

Покрывают:
1. Принятие отклика с проверкой вместимости
2. Создание передержки и отклонение конкурирующих откликов
3. Двухстороннее подтверждение старта и выдачу доступа
4. Двухстороннее подтверждение завершения и отзыв доступа
5. Завершение передержки отзывом
6. Геопоиск ситтеров
"""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from access.models import PetAccess
from geolocation.models import UserLocation
from pets.models import Pet, PetOwner, PetType
from .models import PetSitting, PetSittingAd, PetSittingRequest, PetSittingResponse, SitterProfile, SitterReview

User = get_user_model()


def create_user(email: str, index: int) -> User:
    """
    Создаёт тестового пользователя с обязательными полями.
    """
    return User.objects.create_user(
        email=email,
        password='testpass123',
        first_name=f'User{index}',
        last_name='Tester',
        phone_number=f'+382670000{index:03d}',
    )


def create_pet(owner: User, pet_type: PetType, name: str) -> Pet:
    """
    Создаёт питомца и связывает его с основным владельцем.
    """
    pet = Pet.objects.create(name=name, pet_type=pet_type, weight=10)
    PetOwner.objects.create(pet=pet, user=owner, role='main')
    return pet


class PetSittingApiTestCase(TestCase):
    """
    Интеграционные тесты API передержки.
    """

    def setUp(self):
        """
        Создаёт базовые сущности для сценариев передержки.
        """
        self.client = APIClient()
        self.pet_type = PetType.objects.create(name='Dog', code='dog')

        self.owner = create_user('owner@example.com', 1)
        self.owner_two = create_user('owner2@example.com', 2)
        self.sitter_user = create_user('sitter@example.com', 3)
        self.other_sitter_user = create_user('other-sitter@example.com', 4)

        self.owner_pet = create_pet(self.owner, self.pet_type, 'Buddy')
        self.owner_two_pet = create_pet(self.owner_two, self.pet_type, 'Milo')

        self.sitter_profile = SitterProfile.objects.create(
            user=self.sitter_user,
            description='Reliable sitter',
            pet_types=['dog'],
            max_pets=1,
            is_active=True,
        )
        self.other_sitter_profile = SitterProfile.objects.create(
            user=self.other_sitter_user,
            description='Backup sitter',
            pet_types=['dog'],
            max_pets=2,
            is_active=True,
        )

        UserLocation.objects.create(
            user=self.sitter_user,
            point=Point(19.2624, 42.4411, srid=4326),
            source='map',
        )
        UserLocation.objects.create(
            user=self.other_sitter_user,
            point=Point(19.5000, 42.6000, srid=4326),
            source='map',
        )

    def create_ad(self, owner: User, pet: Pet, start_offset: int = 1, duration_days: int = 2) -> PetSittingAd:
        """
        Создаёт объявление о передержке.
        """
        start_date = timezone.now().date() + timedelta(days=start_offset)
        end_date = start_date + timedelta(days=duration_days)
        return PetSittingAd.objects.create(
            owner=owner,
            pet=pet,
            start_date=start_date,
            end_date=end_date,
            description='Need a sitter',
            location='Podgorica',
            compensation_type='paid',
        )

    def create_response(self, ad: PetSittingAd, sitter: SitterProfile, status_value: str = 'pending') -> PetSittingResponse:
        """
        Создаёт отклик ситтера на объявление.
        """
        return PetSittingResponse.objects.create(
            ad=ad,
            sitter=sitter,
            message='I can help',
            status=status_value,
        )

    def create_sitting(self, ad: PetSittingAd, response: PetSittingResponse, status_value: str = 'waiting_start') -> PetSitting:
        """
        Создаёт передержку на основе объявления и отклика.
        """
        return PetSitting.objects.create(
            ad=ad,
            response=response,
            sitter=response.sitter,
            pet=ad.pet,
            start_date=ad.start_date,
            end_date=ad.end_date,
            status=status_value,
        )

    def create_direct_request(
        self,
        owner: User | None = None,
        sitter: SitterProfile | None = None,
        pet: Pet | None = None,
        start_offset: int = 2,
        duration_days: int = 2,
        source_value: str = PetSittingRequest.SOURCE_OWNER_SEARCH,
    ) -> PetSittingRequest:
        """
        Создаёт прямой owner -> sitter запрос на передержку.
        """
        owner = owner or self.owner
        sitter = sitter or self.sitter_profile
        pet = pet or self.owner_pet
        start_date = timezone.now().date() + timedelta(days=start_offset)
        end_date = start_date + timedelta(days=duration_days)
        return PetSittingRequest.objects.create(
            owner=owner,
            sitter=sitter,
            pet=pet,
            initiated_by=owner,
            start_date=start_date,
            end_date=end_date,
            message='Need a calm home boarding stay',
            source=source_value,
            location='Podgorica',
        )

    def test_accept_response_rejects_when_capacity_exceeded(self):
        """
        Нельзя принять отклик, если ситтер уже заполнен на эти даты.
        """
        existing_ad = self.create_ad(self.owner, self.owner_pet, start_offset=1, duration_days=3)
        existing_response = self.create_response(existing_ad, self.sitter_profile, status_value='accepted')
        self.create_sitting(existing_ad, existing_response, status_value='active')

        new_ad = self.create_ad(self.owner_two, self.owner_two_pet, start_offset=2, duration_days=2)
        new_response = self.create_response(new_ad, self.sitter_profile)

        self.client.force_authenticate(user=self.owner_two)
        response = self.client.post(f'/api/v1/responses/{new_response.id}/accept/')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('max_pets', response.data)
        self.assertFalse(PetSitting.objects.filter(response=new_response).exists())

    def test_accept_response_creates_sitting_and_rejects_other_responses(self):
        """
        Принятие отклика создаёт передержку и отклоняет остальные pending-отклики.
        """
        ad = self.create_ad(self.owner, self.owner_pet)
        selected_response = self.create_response(ad, self.sitter_profile)
        rejected_response = self.create_response(ad, self.other_sitter_profile)

        self.client.force_authenticate(user=self.owner)
        response = self.client.post(f'/api/v1/responses/{selected_response.id}/accept/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        selected_response.refresh_from_db()
        rejected_response.refresh_from_db()
        ad.refresh_from_db()

        self.assertEqual(selected_response.status, 'accepted')
        self.assertEqual(rejected_response.status, 'rejected')
        self.assertEqual(ad.status, 'closed')
        self.assertTrue(PetSitting.objects.filter(response=selected_response, status='waiting_start').exists())

    def test_confirm_start_requires_both_participants_and_grants_pet_access(self):
        """
        Передержка становится active только после двух подтверждений и выдаёт доступ ситтеру.
        """
        ad = self.create_ad(self.owner, self.owner_pet)
        response = self.create_response(ad, self.sitter_profile, status_value='accepted')
        sitting = self.create_sitting(ad, response, status_value='waiting_start')

        self.client.force_authenticate(user=self.owner)
        owner_response = self.client.post(f'/api/v1/pet-sitting/{sitting.id}/confirm_start/')
        self.assertEqual(owner_response.status_code, status.HTTP_200_OK)
        sitting.refresh_from_db()
        self.assertTrue(sitting.owner_confirmed_start)
        self.assertEqual(sitting.status, 'waiting_start')
        self.assertFalse(PetAccess.objects.filter(pet=sitting.pet, granted_to=self.sitter_user, is_active=True).exists())

        self.client.force_authenticate(user=self.sitter_user)
        sitter_response = self.client.post(f'/api/v1/pet-sitting/{sitting.id}/confirm_start/')
        self.assertEqual(sitter_response.status_code, status.HTTP_200_OK)
        sitting.refresh_from_db()
        access = PetAccess.objects.get(pet=sitting.pet, granted_to=self.sitter_user)

        self.assertEqual(sitting.status, 'active')
        self.assertTrue(access.is_active)
        self.assertTrue(access.permissions['read'])
        self.assertTrue(access.permissions['book'])
        self.assertFalse(access.permissions['write'])

    def test_confirm_end_moves_to_waiting_review_and_revokes_access(self):
        """
        После двух подтверждений завершения статус меняется на waiting_review и доступ отключается.
        """
        ad = self.create_ad(self.owner, self.owner_pet)
        response = self.create_response(ad, self.sitter_profile, status_value='accepted')
        sitting = self.create_sitting(ad, response, status_value='active')
        sitting.owner_confirmed_start = True
        sitting.sitter_confirmed_start = True
        sitting.save(update_fields=['owner_confirmed_start', 'sitter_confirmed_start'])
        PetAccess.objects.create(
            pet=sitting.pet,
            granted_to=self.sitter_user,
            granted_by=self.owner,
            expires_at=datetime_for_date(sitting.end_date),
            permissions={'read': True, 'book': True, 'write': False},
            is_active=True,
        )

        self.client.force_authenticate(user=self.owner)
        self.assertEqual(
            self.client.post(f'/api/v1/pet-sitting/{sitting.id}/confirm_end/').status_code,
            status.HTTP_200_OK,
        )
        sitting.refresh_from_db()
        self.assertEqual(sitting.status, 'active')
        self.assertTrue(sitting.owner_confirmed_end)

        self.client.force_authenticate(user=self.sitter_user)
        self.assertEqual(
            self.client.post(f'/api/v1/pet-sitting/{sitting.id}/confirm_end/').status_code,
            status.HTTP_200_OK,
        )
        sitting.refresh_from_db()
        access = PetAccess.objects.get(pet=sitting.pet, granted_to=self.sitter_user)

        self.assertEqual(sitting.status, 'waiting_review')
        self.assertFalse(access.is_active)

    def test_leave_review_completes_sitting(self):
        """
        Отзыв владельца завершает передержку.
        """
        ad = self.create_ad(self.owner, self.owner_pet)
        response = self.create_response(ad, self.sitter_profile, status_value='accepted')
        sitting = self.create_sitting(ad, response, status_value='waiting_review')
        sitting.owner_confirmed_start = True
        sitting.sitter_confirmed_start = True
        sitting.owner_confirmed_end = True
        sitting.sitter_confirmed_end = True
        sitting.save(update_fields=[
            'owner_confirmed_start',
            'sitter_confirmed_start',
            'owner_confirmed_end',
            'sitter_confirmed_end',
        ])

        self.client.force_authenticate(user=self.owner)
        response = self.client.post(
            f'/api/v1/pet-sitting/{sitting.id}/leave_review/',
            {'rating': 5, 'text': 'Excellent care'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sitting.refresh_from_db()

        self.assertEqual(sitting.status, 'completed')
        self.assertTrue(sitting.review_left)
        self.assertTrue(SitterReview.objects.filter(history=sitting, author=self.owner, rating=5).exists())

    def test_search_sitters_returns_only_matching_active_profiles(self):
        """
        Геопоиск возвращает только активных и подходящих ситтеров.
        """
        inactive_sitter = create_user('inactive-sitter@example.com', 5)
        inactive_profile = SitterProfile.objects.create(
            user=inactive_sitter,
            description='Inactive sitter',
            pet_types=['dog'],
            max_pets=1,
            is_active=False,
        )
        UserLocation.objects.create(
            user=inactive_sitter,
            point=Point(19.2625, 42.4410, srid=4326),
            source='map',
        )

        self.client.force_authenticate(user=self.owner)
        response = self.client.get(
            '/api/v1/sitters/search/',
            {
                'latitude': 42.4411,
                'longitude': 19.2624,
                'radius': 5,
                'pet_type': 'dog',
                'available_from': (timezone.now().date() + timedelta(days=1)).isoformat(),
                'available_to': (timezone.now().date() + timedelta(days=3)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.sitter_profile.id)
        self.assertNotEqual(results[0]['id'], inactive_profile.id)

    def test_search_sitters_hides_fully_booked_sitter_for_overlapping_dates(self):
        """
        Геопоиск не должен возвращать ситтера, если его вместимость уже занята на выбранные даты.
        """
        ad = self.create_ad(self.owner, self.owner_pet, start_offset=1, duration_days=3)
        response = self.create_response(ad, self.sitter_profile, status_value='accepted')
        self.create_sitting(ad, response, status_value='waiting_start')

        self.client.force_authenticate(user=self.owner_two)
        response = self.client.get(
            '/api/v1/sitters/search/',
            {
                'latitude': 42.4411,
                'longitude': 19.2624,
                'radius': 50,
                'pet_type': 'dog',
                'available_from': ad.start_date.isoformat(),
                'available_to': ad.end_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [item['id'] for item in response.data['results']]
        self.assertNotIn(self.sitter_profile.id, result_ids)
        self.assertIn(self.other_sitter_profile.id, result_ids)

    def test_public_ads_list_hides_pet_with_already_agreed_boarding(self):
        """
        В публичной выдаче для ситтера не должно быть объявления, по которому уже договорились о передержке.
        """
        closed_ad = self.create_ad(self.owner, self.owner_pet, start_offset=1, duration_days=2)
        accepted_response = self.create_response(closed_ad, self.sitter_profile, status_value='accepted')
        self.create_sitting(closed_ad, accepted_response, status_value='waiting_start')
        closed_ad.status = 'closed'
        closed_ad.save(update_fields=['status', 'updated_at'])

        active_ad = self.create_ad(self.owner_two, self.owner_two_pet, start_offset=5, duration_days=2)

        self.client.force_authenticate(user=self.other_sitter_user)
        response = self.client.get('/api/v1/ads/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [item['id'] for item in response.data['results']]
        self.assertNotIn(closed_ad.id, result_ids)
        self.assertIn(active_ad.id, result_ids)

    def test_create_direct_request_does_not_publish_public_ad_and_sends_localized_email(self):
        """
        Прямой запрос не должен создавать публичное объявление и должен отправлять локализованное письмо ситтеру.
        """
        self.sitter_user.preferred_language = 'ru'
        self.sitter_user.save(update_fields=['preferred_language'])
        mail.outbox.clear()

        start_date = timezone.now().date() + timedelta(days=3)
        end_date = start_date + timedelta(days=2)

        self.client.force_authenticate(user=self.owner)
        response = self.client.post(
            '/api/v1/requests/',
            {
                'sitter': self.sitter_profile.id,
                'pet': self.owner_pet.id,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'message': 'Please keep Buddy at home and send daily updates.',
                'location': 'Podgorica',
                'source': PetSittingRequest.SOURCE_OWNER_SEARCH,
                'address_label': 'Podgorica, Montenegro',
                'address_latitude': 42.4411,
                'address_longitude': 19.2624,
                'address_city': 'Podgorica',
                'address_country': 'Montenegro',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_request = PetSittingRequest.objects.get()

        self.assertEqual(created_request.status, PetSittingRequest.STATUS_PENDING)
        self.assertEqual(created_request.source, PetSittingRequest.SOURCE_OWNER_SEARCH)
        self.assertIsNotNone(created_request.conversation_id)
        self.assertEqual(PetSittingAd.objects.count(), 0)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.sitter_user.email])
        self.assertIn('Уважаемый пользователь PetsCare,', mail.outbox[0].body)
        self.assertIn('запрос на передержку питомца Buddy', mail.outbox[0].body)
        self.assertIn('/boarding?tab=requests&request=', mail.outbox[0].body)

    def test_accept_direct_request_creates_internal_records_and_localized_owner_email(self):
        """
        Принятие прямого запроса должно создать внутреннюю передержку и отправить владельцу локализованное письмо.
        """
        self.owner.preferred_language = 'ru'
        self.owner.save(update_fields=['preferred_language'])
        direct_request = self.create_direct_request()
        mail.outbox.clear()

        self.client.force_authenticate(user=self.sitter_user)
        response = self.client.post(f'/api/v1/requests/{direct_request.id}/accept/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        direct_request.refresh_from_db()
        self.assertEqual(direct_request.status, PetSittingRequest.STATUS_ACCEPTED)
        self.assertEqual(direct_request.version, 2)
        self.assertIsNotNone(direct_request.created_ad_id)
        self.assertIsNotNone(direct_request.created_response_id)
        self.assertIsNotNone(direct_request.pet_sitting_id)
        self.assertIsNotNone(direct_request.conversation_id)

        direct_request.created_ad.refresh_from_db()
        direct_request.created_response.refresh_from_db()
        direct_request.pet_sitting.refresh_from_db()

        self.assertEqual(direct_request.created_ad.visibility, 'internal')
        self.assertEqual(direct_request.created_ad.status, 'closed')
        self.assertEqual(direct_request.created_response.status, 'accepted')
        self.assertEqual(direct_request.pet_sitting.status, 'waiting_start')
        self.assertEqual(PetSittingAd.objects.filter(visibility='public').count(), 0)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.owner.email])
        self.assertIn('Уважаемый пользователь PetsCare,', mail.outbox[0].body)
        self.assertIn('принял(а) ваш запрос на передержку питомца Buddy', mail.outbox[0].body)
        self.assertIn('/boarding?tab=stays&sitting=', mail.outbox[0].body)


def datetime_for_date(target_date):
    """
    Возвращает datetime конца дня для даты.
    """
    return timezone.make_aware(datetime.combine(target_date, time.max.replace(microsecond=0)))
