"""Helpers for applying provider RBAC to DRF views."""

from __future__ import annotations

from functools import wraps

from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from .models import Provider, ProviderLocation
from .permission_service import ProviderPermissionService


def resolve_request_provider(request, view_kwargs: dict) -> Provider:
    provider_id = view_kwargs.get('provider_id')
    if provider_id is None and request.path.rstrip('/').endswith('/providers'):
        provider_id = view_kwargs.get('pk')
    provider_header = request.headers.get('X-Provider-Id') if hasattr(request, 'headers') else None
    provider_query = request.query_params.get('provider_id') if hasattr(request, 'query_params') else None
    provider_id = provider_id or provider_header or provider_query

    if provider_id is None and 'location_pk' in view_kwargs:
        location = get_object_or_404(ProviderLocation.objects.select_related('provider'), pk=view_kwargs['location_pk'])
        return location.provider
    if provider_id is None and 'pk' in view_kwargs and 'provider-locations' in request.path:
        location = get_object_or_404(ProviderLocation.objects.select_related('provider'), pk=view_kwargs['pk'])
        return location.provider
    if provider_id is None:
        raise ImproperlyConfigured('Provider cannot be resolved from request.')
    return get_object_or_404(Provider, pk=provider_id)


def require_provider_permission(resource, action):
    """Decorator for DRF view methods."""

    def decorator(func):
        @wraps(func)
        def wrapped(self, request, *args, **kwargs):
            provider = resolve_request_provider(request, kwargs)
            if not ProviderPermissionService.check_permission(
                request.user,
                provider,
                resource,
                action,
            ):
                raise PermissionDenied('Provider permission denied.')
            request.provider_permission_provider = provider
            return func(self, request, *args, **kwargs)

        return wrapped

    return decorator


class ProviderPermissionMixin:
    """Mixin for resource-aware queryset filtering."""

    provider_resource: str = ''

    def get_provider_permission_action(self) -> str:
        method_map = {
            'GET': 'read',
            'POST': 'create',
            'PUT': 'update',
            'PATCH': 'update',
            'DELETE': 'delete',
        }
        return method_map.get(self.request.method, 'read')

    def get_permission_provider(self) -> Provider:
        provider = getattr(self.request, 'provider_permission_provider', None)
        if provider is not None:
            return provider
        return resolve_request_provider(self.request, self.kwargs)

    def ensure_provider_permission(self, *, action: str | None = None, target_location=None, target_employee=None) -> Provider:
        provider = self.get_permission_provider()
        action = action or self.get_provider_permission_action()
        if not ProviderPermissionService.check_permission(
            self.request.user,
            provider,
            self.provider_resource,
            action,
            target_location=target_location,
            target_employee=target_employee,
        ):
            raise PermissionDenied('Provider permission denied.')
        return provider

    def filter_queryset_by_provider_scope(self, queryset):
        provider = self.get_permission_provider()
        permission = ProviderPermissionService.get_user_permissions(self.request.user, provider).get(self.provider_resource)
        if not permission:
            return queryset.none()

        scope = permission.get('scope')
        if scope == 'all':
            return queryset

        member_location_ids = list(
            ProviderPermissionService.get_user_member_locations(self.request.user, provider).values_list('id', flat=True)
        )
        branch_location_ids = list(
            ProviderPermissionService.get_user_branch_locations(self.request.user, provider).values_list('id', flat=True)
        )
        employee = getattr(self.request.user, 'employee_profile', None)

        if scope == 'own_branch':
            if hasattr(queryset.model, 'provider_location_id'):
                return queryset.filter(provider_location_id__in=branch_location_ids)
            if queryset.model is ProviderLocation:
                return queryset.filter(id__in=branch_location_ids)
            if hasattr(queryset.model, 'location_id'):
                return queryset.filter(location_id__in=branch_location_ids)
            return queryset.filter(
                Q(provider_location_id__in=branch_location_ids)
                | Q(location_id__in=branch_location_ids)
            )

        if hasattr(queryset.model, 'employee_id') and employee is not None:
            return queryset.filter(employee_id=employee.id)
        if hasattr(queryset.model, 'provider_location_id'):
            return queryset.filter(provider_location_id__in=member_location_ids)
        if queryset.model is ProviderLocation:
            return queryset.filter(id__in=member_location_ids)
        return queryset.none()
