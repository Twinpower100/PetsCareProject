"""Сериализаторы operational dashboard провайдера."""

from rest_framework import serializers


class ProviderDashboardQuerySerializer(serializers.Serializer):
    """Параметры запроса для provider dashboard."""

    provider_id = serializers.IntegerField(required=False)
    alerts_minutes = serializers.IntegerField(required=False, min_value=5, max_value=240, default=30)


class ProviderDashboardScopeSerializer(serializers.Serializer):
    """Сериализует scope дашборда."""

    provider_id = serializers.IntegerField()
    provider_name = serializers.CharField()
    scope_type = serializers.ChoiceField(choices=('provider', 'location'))
    location_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=True)
    location_names = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    can_view_financials = serializers.BooleanField()


class ProviderDashboardAppointmentsSerializer(serializers.Serializer):
    """Сериализует KPI по записям текущей смены."""

    completed = serializers.IntegerField()
    total = serializers.IntegerField()
    has_overload = serializers.BooleanField()


class ProviderDashboardStaffSerializer(serializers.Serializer):
    """Сериализует KPI по сотрудникам текущей смены."""

    total = serializers.IntegerField()
    busy = serializers.IntegerField()
    available = serializers.IntegerField()


class ProviderDashboardIncidentSerializer(serializers.Serializer):
    """Сериализует карточку инцидента."""

    code = serializers.CharField()
    count = serializers.IntegerField()


class ProviderDashboardFinancialsSerializer(serializers.Serializer):
    """Сериализует финансовые показатели dashboard."""

    expected_revenue_today = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    month_actual_revenue = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    currency_code = serializers.CharField(allow_null=True)


class ProviderDashboardAlertSerializer(serializers.Serializer):
    """Сериализует событие ленты системных уведомлений."""

    id = serializers.CharField()
    event_type = serializers.CharField()
    severity = serializers.CharField()
    created_at = serializers.DateTimeField()
    booking_id = serializers.IntegerField(required=False, allow_null=True)
    booking_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    pet_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    service_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    location_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    source = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    cancelled_by = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    title = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    message = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ProviderDashboardSerializer(serializers.Serializer):
    """Корневой сериализатор provider dashboard."""

    timestamp = serializers.DateTimeField()
    scope = ProviderDashboardScopeSerializer()
    appointments = ProviderDashboardAppointmentsSerializer()
    staff = ProviderDashboardStaffSerializer()
    incidents = ProviderDashboardIncidentSerializer(many=True)
    system_alerts = ProviderDashboardAlertSerializer(many=True)
    financials = ProviderDashboardFinancialsSerializer(required=False, allow_null=True)
