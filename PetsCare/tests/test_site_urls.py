from django.contrib.sites.models import Site
from django.test import TestCase, override_settings
from system_settings.models import PlatformBrandingDomain, PlatformBrandingSettings

from utils.site_urls import (
    build_django_admin_url,
    build_provider_admin_url,
    build_public_url,
)


class SiteURLHelpersTest(TestCase):
    @override_settings(
        SITE_ID=1,
        SITE_URLS_USE_BRANDING=False,
        SITE_URLS_USE_DJANGO_SITE=True,
        PUBLIC_SITE_SCHEME='http',
        PROVIDER_ADMIN_PATH='/provider-admin',
        DJANGO_ADMIN_PATH='/admin',
    )
    def test_builds_application_urls_from_django_site(self):
        Site.objects.update_or_create(
            id=1,
            defaults={
                'domain': '178.104.199.240.nip.io',
                'name': 'PetCare test server',
            },
        )

        self.assertEqual(
            build_public_url('/reset-password/token-123'),
            'http://178.104.199.240.nip.io/reset-password/token-123',
        )
        self.assertEqual(
            build_provider_admin_url('/login'),
            'http://178.104.199.240.nip.io/provider-admin/login',
        )
        self.assertEqual(
            build_django_admin_url('/sites/site/'),
            'http://178.104.199.240.nip.io/admin/sites/site/',
        )

    @override_settings(
        SITE_URLS_USE_BRANDING=True,
        SITE_URLS_USE_DJANGO_SITE=False,
    )
    def test_builds_application_urls_from_branding_domains(self):
        branding = PlatformBrandingSettings.objects.create(
            product_name='PetCare',
            short_name='PetCare',
            public_site_title='PetsCare',
            provider_admin_site_title='PetCare - Provider Admin',
            legal_footer_name='PetCare',
            support_email='support@petcare.com',
            is_active=True,
        )
        PlatformBrandingDomain.objects.create(
            branding=branding,
            app_type=PlatformBrandingDomain.APP_TYPE_PUBLIC,
            scheme='https',
            domain='example.com',
            base_path='/',
            is_primary=True,
        )
        PlatformBrandingDomain.objects.create(
            branding=branding,
            app_type=PlatformBrandingDomain.APP_TYPE_PROVIDER_ADMIN,
            scheme='https',
            domain='admin.example.com',
            base_path='/',
            is_primary=True,
        )

        self.assertEqual(build_public_url('/contact'), 'https://example.com/contact')
        self.assertEqual(build_provider_admin_url('/login'), 'https://admin.example.com/login')

    @override_settings(
        SITE_URLS_USE_BRANDING=False,
        SITE_URLS_USE_DJANGO_SITE=False,
        FRONTEND_URL='http://localhost:3000',
        PROVIDER_ADMIN_URL='http://localhost:5173',
    )
    def test_uses_local_env_urls_when_site_lookup_is_disabled(self):
        self.assertEqual(
            build_public_url('/verify-email?token=abc'),
            'http://localhost:3000/verify-email?token=abc',
        )
        self.assertEqual(
            build_provider_admin_url('/login'),
            'http://localhost:5173/login',
        )
