from django.db import migrations


def seed_current_branding(apps, schema_editor):
    """Заполняет настройки бренда текущими значениями фронтов."""
    PlatformBrandingSettings = apps.get_model('system_settings', 'PlatformBrandingSettings')
    PlatformBrandingDomain = apps.get_model('system_settings', 'PlatformBrandingDomain')

    if PlatformBrandingSettings.objects.filter(is_active=True).exists():
        return

    branding = PlatformBrandingSettings.objects.create(
        product_name='PetCare',
        short_name='PetCare',
        public_site_title='PetsCare',
        provider_admin_site_title='PetCare - Provider Admin',
        legal_footer_name='PetCare',
        support_email='support@petcare.com',
        support_phone='+1 (555) 123-4567',
        contact_path='/contact',
        is_active=True,
    )

    domains = [
        {
            'app_type': 'public',
            'scheme': 'http',
            'domain': '178.104.199.240.nip.io',
            'base_path': '/',
            'is_primary': True,
            'display_order': 10,
        },
        {
            'app_type': 'provider_admin',
            'scheme': 'http',
            'domain': '178.104.199.240.nip.io',
            'base_path': '/provider-admin/',
            'is_primary': True,
            'display_order': 10,
        },
        {
            'app_type': 'public',
            'scheme': 'http',
            'domain': 'localhost:3000',
            'base_path': '/',
            'is_primary': False,
            'display_order': 20,
        },
        {
            'app_type': 'public',
            'scheme': 'http',
            'domain': '127.0.0.1:3000',
            'base_path': '/',
            'is_primary': False,
            'display_order': 30,
        },
        {
            'app_type': 'provider_admin',
            'scheme': 'http',
            'domain': 'localhost:5173',
            'base_path': '/',
            'is_primary': False,
            'display_order': 40,
        },
        {
            'app_type': 'provider_admin',
            'scheme': 'http',
            'domain': '127.0.0.1:5173',
            'base_path': '/',
            'is_primary': False,
            'display_order': 50,
        },
    ]

    PlatformBrandingDomain.objects.bulk_create(
        PlatformBrandingDomain(branding=branding, **domain)
        for domain in domains
    )


def remove_current_branding(apps, schema_editor):
    """Удаляет seed-данные брендинга при откате миграции."""
    PlatformBrandingSettings = apps.get_model('system_settings', 'PlatformBrandingSettings')
    PlatformBrandingSettings.objects.filter(
        product_name='PetCare',
        support_email='support@petcare.com',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('system_settings', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_current_branding, remove_current_branding),
    ]
