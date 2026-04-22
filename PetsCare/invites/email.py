"""
Унифицированная отправка писем с приглашениями.
Шаблон и текст зависят от invite_type; во всех письмах — 6-значный код и ссылка на страницу приёма.
"""
from django.core.mail import send_mail
from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from .models import Invite
from utils.site_urls import build_provider_admin_url, build_public_url


def send_invite_email(invite: Invite, language: str = 'en'):
    """
    Отправляет email с приглашением.
    Шаблон письма определяется по invite.invite_type.
    Все письма содержат 6-значный код и ссылку на страницу приёма.
    """
    lang = (language or 'en').strip().lower()
    if lang not in ('en', 'ru', 'de', 'me'):
        lang = 'en'
    translation.activate(lang)
    code = invite.token

    if invite.invite_type in (Invite.TYPE_PROVIDER_MANAGER, Invite.TYPE_PROVIDER_ADMIN):
        accept_page_url = build_provider_admin_url('/accept-organization-role-invite')
        provider_name = invite.provider.name if invite.provider else ''
        role_label = _('Manager') if invite.invite_type == Invite.TYPE_PROVIDER_MANAGER else _('Admin')
        subject = _('Invitation to become %(role)s of the organization "%(name)s"') % {
            'role': role_label, 'name': provider_name,
        }
        body_plain = _(
            'You have been invited to become %(role)s for the organization "%(name)s". '
            'Open the link and enter the activation code. Link: %(url)s Activation code: %(code)s. '
            'Valid for 7 days. If you received this message by mistake, please ignore it.'
        ) % {'role': role_label, 'name': provider_name, 'url': accept_page_url, 'code': code}
    elif invite.invite_type == Invite.TYPE_BRANCH_MANAGER:
        accept_page_url = build_provider_admin_url('/accept-location-manager-invite')
        provider_name = invite.provider_location.provider.name if invite.provider_location else ''
        location_name = invite.provider_location.name if invite.provider_location else ''
        subject = _('Invitation to become the manager of a service location')
        body_plain = _(
            'You have been invited to become the manager of the service location "%(location)s" (%(provider)s). '
            'Open the link and enter the activation code. Link: %(url)s Activation code: %(code)s. '
            'Valid for 7 days. If you received this message by mistake, please ignore it.'
        ) % {'location': location_name, 'provider': provider_name, 'url': accept_page_url, 'code': code}
    elif invite.invite_type == Invite.TYPE_SPECIALIST:
        accept_page_url = build_provider_admin_url('/accept-location-staff-invite')
        provider_name = invite.provider_location.provider.name if invite.provider_location else ''
        location_name = invite.provider_location.name if invite.provider_location else ''
        subject = _('Invitation to join staff at a service location')
        body_plain = _(
            'You have been invited to join the staff of the service location "%(location)s" (%(provider)s). '
            'Open the link and enter the activation code. Link: %(url)s Activation code: %(code)s. '
            'Valid for 7 days. If you received this message by mistake, please ignore it.'
        ) % {'location': location_name, 'provider': provider_name, 'url': accept_page_url, 'code': code}
    elif invite.invite_type in (Invite.TYPE_PET_CO_OWNER, Invite.TYPE_PET_TRANSFER):
        accept_page_url = build_public_url(f'/pet-invite/{code}/')
        pet_name = invite.pet.name if invite.pet else ''
        subject = _('Pet ownership invitation')
        body_plain = _(
            'You have been invited for the pet "%(pet)s". '
            'Open the link and enter the activation code. Link: %(url)s Activation code: %(code)s. '
            'Valid for 7 days. If you received this message by mistake, please ignore it.'
        ) % {'pet': pet_name, 'url': accept_page_url, 'code': code}
    else:
        accept_page_url = build_provider_admin_url(f'/invite/{code}/')
        subject = _('Invitation')
        body_plain = _(
            'You have been invited. Open the link and enter the activation code. '
            'Link: %(url)s Activation code: %(code)s. Valid for 7 days.'
        ) % {'url': accept_page_url, 'code': code}

    body_html = (
        f'<p>{subject}</p>'
        f'<p>{body_plain}</p>'
        f'<p>{_("Activation code:")} <strong>{code}</strong>. {_("Valid for 7 days.")}</p>'
        f'<p><em>{_("If you received this message by mistake, please ignore it.")}</em></p>'
    )
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'noreply@example.com'
    try:
        send_mail(
            subject,
            body_plain,
            from_email,
            [invite.email],
            fail_silently=True,
            html_message=body_html,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning('Failed to send invite email to %s: %s', invite.email, e)
