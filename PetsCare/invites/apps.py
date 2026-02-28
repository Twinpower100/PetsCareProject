"""
Конфигурация приложения invites.

Единая система приглашений: provider_manager, provider_admin, branch_manager,
specialist, pet_co_owner, pet_transfer.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class InvitesConfig(AppConfig):
    """Конфигурация приложения invites."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'invites'
    verbose_name = _('Invites')
