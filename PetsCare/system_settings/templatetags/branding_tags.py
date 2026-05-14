"""
Template tags для доступа к runtime-брендингу в письмах и шаблонах.
"""

from django import template

from system_settings.models import PlatformBrandingSettings

register = template.Library()


@register.simple_tag
def platform_branding():
    """Возвращает активные настройки бренда для шаблонов без request context."""
    return PlatformBrandingSettings.get_active()
