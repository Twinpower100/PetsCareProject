"""
Helpers for service catalog fields in Django Admin.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from .models import Service


def get_service_tree_label(service: Service) -> str:
    """Возвращает человекочитаемую подпись услуги с отступом по уровню дерева."""
    indent = "    " * service.level
    marker = "+-- " if service.level else ""
    return f"{indent}{marker}{service.get_full_path()}"


def apply_service_tree_labels(field) -> None:
    """Назначает admin-only подписи для ModelChoiceField/ModelMultipleChoiceField."""
    field.label_from_instance = get_service_tree_label


def get_client_facing_root_categories() -> QuerySet[Service]:
    """Возвращает активные клиентские категории верхнего уровня."""
    return Service.objects.filter(
        level=0,
        parent__isnull=True,
        is_active=True,
        is_client_facing=True,
    ).order_by("hierarchy_order", "name")


def get_descendant_ids(root_ids) -> list[int]:
    """Возвращает id всех потомков для списка корневых узлов."""
    root_ids = list(root_ids)
    descendants: list[int] = []
    frontier = root_ids
    while frontier:
        children = list(Service.objects.filter(parent_id__in=frontier).values_list("id", flat=True))
        descendants.extend(children)
        frontier = children
    return descendants


def get_client_facing_leaf_services_for_categories(category_queryset, *, include_service_id=None) -> QuerySet[Service]:
    """Возвращает активные клиентские leaf-услуги внутри выбранных категорий."""
    category_ids = list(category_queryset.values_list("id", flat=True))
    service_ids = get_descendant_ids(category_ids)
    queryset_filter = Q(id__in=service_ids)
    if include_service_id:
        queryset_filter |= Q(id=include_service_id)
    return (
        Service.objects.filter(queryset_filter, is_active=True, is_client_facing=True, children__isnull=True)
        .distinct()
        .order_by("hierarchy_order", "name")
    )


def get_all_client_facing_leaf_services(*, include_service_id=None) -> QuerySet[Service]:
    """Возвращает все активные клиентские leaf-услуги для fallback-форм админки."""
    queryset_filter = Q(is_active=True, is_client_facing=True, children__isnull=True)
    if include_service_id:
        queryset_filter |= Q(id=include_service_id)
    return Service.objects.filter(queryset_filter).distinct().order_by("hierarchy_order", "name")
