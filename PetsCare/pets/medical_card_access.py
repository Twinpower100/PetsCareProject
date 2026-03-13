from django.db.models import Q

from .models import PetDocument, PetOwner, VisitRecord


def is_pet_owner(user, pet):
    return PetOwner.objects.filter(pet=pet, user=user).exists()


def get_managed_provider_ids(user):
    if not user.is_provider_admin():
        return []
    return list(user.get_managed_providers().values_list('id', flat=True))


def can_manage_visit_record_as_provider(user, visit_record):
    if user.is_superuser or user.is_system_admin():
        return True
    if user.is_employee():
        return bool(
            visit_record.employee_id
            and visit_record.employee
            and visit_record.employee.user_id == user.id
        )
    if user.is_provider_admin():
        managed_provider_ids = set(get_managed_provider_ids(user))
        provider_id = visit_record.provider_id
        if provider_id is None and visit_record.provider_location_id:
            provider_id = visit_record.provider_location.provider_id
        return provider_id in managed_provider_ids
    return False


def can_view_visit_record(user, visit_record):
    if user.is_superuser or user.is_system_admin():
        return True
    if is_pet_owner(user, visit_record.pet):
        return True
    return can_manage_visit_record_as_provider(user, visit_record)


def can_view_health_notes(user, pet):
    if user.is_superuser or user.is_system_admin():
        return True
    return is_pet_owner(user, pet)


def get_accessible_visit_records_queryset(user, pet):
    queryset = get_globally_accessible_visit_records_queryset(user)
    return queryset.filter(pet=pet)


def get_globally_accessible_visit_records_queryset(user):
    queryset = VisitRecord._default_manager.select_related(
        'provider',
        'provider_location',
        'service',
        'employee__user',
    ).prefetch_related(
        'documents',
        'documents__document_type',
        'addenda',
        'addenda__author',
        'source_bookings',
    ).order_by('-date', '-created_at')

    if user.is_superuser or user.is_system_admin():
        return queryset

    filters = Q(pet__owners=user)
    if user.is_employee():
        filters |= Q(employee__user=user)

    managed_provider_ids = get_managed_provider_ids(user)
    if managed_provider_ids:
        filters |= Q(provider_id__in=managed_provider_ids)
        filters |= Q(provider_location__provider_id__in=managed_provider_ids)

    if not filters:
        return queryset.none()

    return queryset.filter(filters).distinct()


def get_accessible_documents_queryset(user, pet):
    queryset = get_globally_accessible_documents_queryset(user)
    return queryset.filter(pet=pet)


def get_globally_accessible_documents_queryset(user):
    queryset = PetDocument._default_manager.select_related(
        'document_type',
        'visit_record',
        'health_note',
        'uploaded_by',
    ).order_by('-uploaded_at', '-created_at')

    if user.is_superuser or user.is_system_admin():
        return queryset

    filters = Q(pet__owners=user)
    if user.is_employee():
        filters |= Q(visit_record__employee__user=user)

    managed_provider_ids = get_managed_provider_ids(user)
    if managed_provider_ids:
        filters |= Q(visit_record__provider_id__in=managed_provider_ids)
        filters |= Q(visit_record__provider_location__provider_id__in=managed_provider_ids)

    if not filters:
        return queryset.none()

    return queryset.filter(filters).distinct()


def can_view_pet_medical_card(user, pet):
    if user.is_superuser or user.is_system_admin() or is_pet_owner(user, pet):
        return True
    return get_accessible_visit_records_queryset(user, pet).exists()
