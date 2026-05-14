from __future__ import annotations

from django.conf import settings


def _normalize_base_url(value: str | None) -> str:
    return (value or '').strip().rstrip('/')


def _normalize_path(path: str | None) -> str:
    if not path:
        return ''
    stripped = path.strip()
    if not stripped:
        return ''
    return stripped if stripped.startswith('/') else f'/{stripped}'


def _url_from_domain(domain: str | None) -> str:
    clean_domain = (domain or '').strip().rstrip('/')
    if not clean_domain:
        return ''
    if clean_domain.startswith(('http://', 'https://')):
        return clean_domain
    scheme = getattr(settings, 'PUBLIC_SITE_SCHEME', 'http') or 'http'
    return f'{scheme}://{clean_domain}'


def _get_branding_base_url(app_type: str) -> str:
    """Возвращает основной URL фронта из настроек брендинга."""
    try:
        from system_settings.models import PlatformBrandingDomain

        domain = (
            PlatformBrandingDomain.objects.select_related('branding')
            .filter(
                app_type=app_type,
                is_active=True,
                branding__is_active=True,
            )
            .order_by('-is_primary', 'display_order', 'domain')
            .first()
        )
        if domain:
            return _normalize_base_url(domain.absolute_url)
    except Exception:
        pass
    return ''


def _get_django_site_base_url() -> str:
    """Возвращает URL из django.contrib.sites для совместимости с allauth."""
    try:
        from django.contrib.sites.models import Site

        return _url_from_domain(Site.objects.get_current().domain)
    except Exception:
        return ''


def get_public_site_base_url() -> str:
    """
    Returns the public frontend base URL.

    Runtime branding is the primary source. Django Sites remains only as a
    compatibility fallback for allauth/OAuth internals.
    """
    if getattr(settings, 'SITE_URLS_USE_BRANDING', True):
        branding_url = _get_branding_base_url('public')
        if branding_url:
            return branding_url

    if getattr(settings, 'SITE_URLS_USE_DJANGO_SITE', False):
        site_url = _get_django_site_base_url()
        if site_url:
            return site_url

    return _normalize_base_url(
        getattr(settings, 'SITE_URL', None)
        or getattr(settings, 'FRONTEND_URL', None)
        or 'http://localhost:3000'
    )


def build_public_url(path: str | None = '') -> str:
    return f'{get_public_site_base_url()}{_normalize_path(path)}'


def get_provider_admin_base_url() -> str:
    if getattr(settings, 'SITE_URLS_USE_BRANDING', True):
        branding_url = _get_branding_base_url('provider_admin')
        if branding_url:
            return branding_url

    if getattr(settings, 'SITE_URLS_USE_DJANGO_SITE', False):
        return build_public_url(getattr(settings, 'PROVIDER_ADMIN_PATH', '/provider-admin'))

    return _normalize_base_url(
        getattr(settings, 'PROVIDER_ADMIN_URL', None)
        or build_public_url(getattr(settings, 'PROVIDER_ADMIN_PATH', '/provider-admin'))
    )


def build_provider_admin_url(path: str | None = '') -> str:
    return f'{get_provider_admin_base_url()}{_normalize_path(path)}'


def get_django_admin_base_url() -> str:
    if getattr(settings, 'SITE_URLS_USE_DJANGO_SITE', False):
        return build_public_url(getattr(settings, 'DJANGO_ADMIN_PATH', '/admin'))

    return _normalize_base_url(
        getattr(settings, 'DJANGO_ADMIN_URL', None)
        or build_public_url(getattr(settings, 'DJANGO_ADMIN_PATH', '/admin'))
    )


def build_django_admin_url(path: str | None = '') -> str:
    return f'{get_django_admin_base_url()}{_normalize_path(path)}'
