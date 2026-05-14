"""
Утилиты runtime-брендинга для писем, юридических документов и внутренних ссылок.
"""

from .models import PlatformBrandingSettings


def get_platform_branding():
    """Возвращает активные настройки бренда с безопасным fallback."""
    return PlatformBrandingSettings.get_active()


def get_branding_template_context():
    """Возвращает контекст бренда для Django templates."""
    branding = get_platform_branding()
    return {
        'branding': branding,
        'brand_name': branding.product_name,
        'brand_short_name': branding.short_name,
        'brand_legal_name': branding.legal_footer_name,
        'public_site_title': branding.public_site_title,
        'provider_admin_site_title': branding.provider_admin_site_title,
        'support_email': branding.support_email,
        'support_phone': branding.support_phone,
        'contact_path': branding.contact_path,
    }


def get_branding_document_variables():
    """Возвращает переменные бренда для юридических шаблонов и оферт."""
    context = get_branding_template_context()
    return {
        'brand_name': context['brand_name'],
        'brand_short_name': context['brand_short_name'],
        'brand_legal_name': context['brand_legal_name'],
        'public_site_title': context['public_site_title'],
        'provider_admin_site_title': context['provider_admin_site_title'],
        'support_email': context['support_email'],
        'support_phone': context['support_phone'],
        'contact_path': context['contact_path'],
    }
