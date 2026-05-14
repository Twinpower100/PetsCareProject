"""
Тесты runtime-настроек платформы и обращений в поддержку.
"""

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from custom_admin import custom_admin_site
from legal.services import DocumentGeneratorService
from system_settings.branding import get_branding_document_variables
from .models import PlatformBrandingSettings, SupportRequest


class PublicSupportRequestCreateAPITest(APITestCase):
    """Тесты публичного API создания обращений в поддержку."""

    def test_creates_new_support_request_from_contact_form(self):
        """Публичная контактная форма создает новое обращение со статусом New."""
        response = self.client.post(
            '/api/v1/support-requests/',
            {
                'author_name': 'Alex Customer',
                'author_email': 'alex@example.com',
                'subject': 'Booking question',
                'message': 'I need help with a booking.',
                'language': 'en',
                'page_url': 'http://localhost:3000/contact',
            },
            format='json',
            HTTP_X_FORWARDED_FOR='203.0.113.10',
            HTTP_USER_AGENT='Support form test',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        support_request = SupportRequest.objects.get()
        self.assertEqual(support_request.status, SupportRequest.STATUS_NEW)
        self.assertEqual(support_request.source, SupportRequest.SOURCE_CONTACT_FORM)
        self.assertEqual(support_request.author_email, 'alex@example.com')
        self.assertEqual(support_request.ip_address, '203.0.113.10')

    def test_requires_message_body(self):
        """Публичная контактная форма не принимает пустой текст обращения."""
        response = self.client.post(
            '/api/v1/support-requests/',
            {
                'author_name': 'Alex Customer',
                'author_email': 'alex@example.com',
                'subject': 'Booking question',
                'message': '   ',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(SupportRequest.objects.exists())


class PlatformBrandingAdminTest(TestCase):
    """Тесты админского перехода к singleton-настройкам бренда."""

    def test_branding_changelist_redirects_to_change_form_without_loop(self):
        """Список настроек бренда открывает форму активного профиля."""
        user = get_user_model().objects.create_superuser(
            email='admin@example.com',
            password='password123',
        )
        branding = PlatformBrandingSettings.objects.create(
            product_name='PetCare',
            short_name='PetCare',
            public_site_title='PetsCare',
            provider_admin_site_title='PetCare - Provider Admin',
            legal_footer_name='PetCare',
            support_email='support@petcare.com',
            is_active=True,
        )
        self.client.force_login(user)

        changelist_url = reverse(f'{custom_admin_site.name}:system_settings_platformbrandingsettings_changelist')
        response = self.client.get(changelist_url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'],
            reverse(
                f'{custom_admin_site.name}:system_settings_platformbrandingsettings_change',
                args=(branding.pk,),
            ),
        )


class PlatformBrandingUsageTest(TestCase):
    """Тесты использования runtime-бренда в письмах и юридических текстах."""

    def setUp(self):
        self.branding = PlatformBrandingSettings.objects.create(
            product_name='Brand Name',
            short_name='Brand Name',
            public_site_title='Brand Name',
            provider_admin_site_title='Brand Name - Provider Admin',
            legal_footer_name='Brand Name',
            support_email='support@brandname.com',
            support_phone='+1 (555) 123-4567',
            is_active=True,
        )

    def test_email_templates_use_platform_branding(self):
        """Письма берут название бренда и support email из активной модели."""
        user = get_user_model()(email='user@example.com', first_name='Alex')
        provider = type('ProviderStub', (), {'name': 'Test Provider'})()

        output = render_to_string(
            'email/provider_blocked.html',
            {
                'subject': 'Test',
                'user': user,
                'provider': provider,
                'reason': 'Test reason',
            },
        )

        self.assertIn('Brand Name', output)
        self.assertIn('support@brandname.com', output)
        self.assertNotIn('support@petcare.com', output)

    def test_legal_document_variables_include_platform_branding(self):
        """Юридические шаблоны могут подставлять переменные активного бренда."""
        variables = get_branding_document_variables()
        output = DocumentGeneratorService()._substitute_variables(
            '{{ brand_name }} / {{support_email}} / {{ provider_admin_site_title }}',
            variables,
        )

        self.assertEqual(
            output,
            'Brand Name / support@brandname.com / Brand Name - Provider Admin',
        )
