from rest_framework import serializers
from decimal import Decimal
from .models import (
    Payment, Invoice, Refund,
    Currency, ServicePrice, PaymentHistory, BillingManagerProvider, BillingManagerEvent,
    RegionalBlockingPolicy, ProviderBlocking, BlockingNotification
)
from django.utils.translation import gettext_lazy as _


class CurrencySerializer(serializers.ModelSerializer):
    """
    Сериализатор для валюты
    """
    class Meta:
        model = Currency
        fields = ['id', 'code', 'name', 'symbol', 'is_active', 'exchange_rate', 'last_updated']
        read_only_fields = ['last_updated']


class ServicePriceSerializer(serializers.ModelSerializer):
    """
    Сериализатор для цены услуги
    """
    currency = CurrencySerializer(read_only=True)
    currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.filter(is_active=True),
        write_only=True,
        source='currency'
    )

    class Meta:
        model = ServicePrice
        fields = [
            'id', 'service', 'currency', 'currency_id',
            'amount', 'is_active', 'valid_from', 'valid_to',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, data):
        """
        Проверяет, что период действия цены не пересекается с другими ценами
        """
        if data.get('valid_to') and data['valid_to'] < data['valid_from']:
            raise serializers.ValidationError(
                _("Price validity end date cannot be earlier than start date")
            )

        overlapping_prices = ServicePrice.objects.filter(
            service=data['service'],
            currency=data['currency'],
            is_active=True,
            valid_from__lte=data.get('valid_to', data['valid_from']),
            valid_to__gte=data['valid_from']
        ).exclude(id=self.instance.id if self.instance else None)

        if overlapping_prices.exists():
            raise serializers.ValidationError(
                _("Price validity period overlaps with existing price")
            )

        return data


class PaymentHistorySerializer(serializers.ModelSerializer):
    """
    Сериализатор для истории платежей
    """
    currency = CurrencySerializer(read_only=True)
    currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.filter(is_active=True),
        write_only=True,
        source='currency'
    )
    outstanding_amount = serializers.DecimalField(
        source='outstanding_amount',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = PaymentHistory
        fields = [
            'id', 'provider', 'invoice', 'offer_acceptance',
            'amount', 'currency', 'currency_id',
            'paid_amount', 'refunded_amount', 'outstanding_amount',
            'due_date', 'payment_date', 'status', 'description',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['status', 'created_at', 'updated_at']

    def validate(self, data):
        """
        Проверяет, что дата платежа не раньше даты наступления платежа
        """
        if data.get('payment_date') and data['payment_date'] < data['due_date']:
            raise serializers.ValidationError(
                _("Payment date cannot be earlier than due date")
            )
        return data


# ContractTypeSerializer, ContractSerializer, ContractCreateSerializer удалены - используется LegalDocument и DocumentAcceptance


class PaymentSerializer(serializers.ModelSerializer):
    """
    Сериализатор для платежей.
    """
    class Meta:
        model = Payment
        fields = [
            'id', 'provider', 'invoice',
            'amount', 'status', 'payment_method',
            'transaction_id', 'notes', 'applied_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class InvoiceSerializer(serializers.ModelSerializer):
    """
    Сериализатор для счетов.
    """
    provider_name = serializers.ReadOnlyField(source='provider.name')
    currency_code = serializers.ReadOnlyField(source='currency.code')
    payment_status = serializers.SerializerMethodField()
    payment_due_date = serializers.SerializerMethodField()
    payment_date = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    refunded_amount = serializers.SerializerMethodField()
    outstanding_amount = serializers.SerializerMethodField()
    pdf_download_url = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'provider', 'provider_name', 'number',
            'start_date', 'end_date', 'amount', 'currency', 'currency_code', 'status',
            'payment_status', 'payment_due_date', 'payment_date',
            'paid_amount', 'refunded_amount', 'outstanding_amount',
            'pdf_download_url',
            'issued_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'number', 'created_at', 'updated_at']

    def _get_payment_record(self, obj):
        """Возвращает связанную запись оплаты, если она существует."""
        return obj.payment_record

    def get_payment_status(self, obj):
        payment_record = self._get_payment_record(obj)
        return payment_record.status if payment_record else None

    def get_payment_due_date(self, obj):
        payment_record = self._get_payment_record(obj)
        return payment_record.due_date if payment_record else None

    def get_payment_date(self, obj):
        payment_record = self._get_payment_record(obj)
        return payment_record.payment_date if payment_record else None

    def get_paid_amount(self, obj):
        payment_record = self._get_payment_record(obj)
        return payment_record.paid_amount if payment_record else Decimal('0.00')

    def get_refunded_amount(self, obj):
        payment_record = self._get_payment_record(obj)
        return payment_record.refunded_amount if payment_record else Decimal('0.00')

    def get_outstanding_amount(self, obj):
        payment_record = self._get_payment_record(obj)
        return payment_record.outstanding_amount if payment_record else obj.amount

    def get_pdf_download_url(self, obj):
        """Возвращает URL скачивания PDF-файла счета."""
        request = self.context.get('request')
        if request is None:
            return None
        return request.build_absolute_uri(f'/api/v1/invoices/{obj.pk}/download-pdf/')


class RefundSerializer(serializers.ModelSerializer):
    """
    Сериализатор для возвратов.
    """
    class Meta:
        model = Refund
        fields = [
            'id', 'payment', 'amount', 'status',
            'reason', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PaymentCreateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания платежа.
    """
    class Meta:
        model = Payment
        fields = ['provider', 'invoice', 'amount', 'payment_method', 'status', 'notes']


class RefundCreateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания возврата.
    """
    class Meta:
        model = Refund
        fields = ['payment', 'amount', 'reason']


class RegionalBlockingPolicySerializer(serializers.ModelSerializer):
    """Платформенная политика блокировок по региону (код страны / EU / DEFAULT)."""

    currency_code = serializers.ReadOnlyField(source='currency.code')

    class Meta:
        model = RegionalBlockingPolicy
        fields = [
            'id',
            'region_code',
            'currency',
            'currency_code',
            'tolerance_amount',
            'overdue_days_l2_from',
            'overdue_days_l3_from',
            'is_active',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class ProviderBlockingSerializer(serializers.ModelSerializer):
    """
    Сериализатор для блокировок учреждений.
    """
    provider_name = serializers.ReadOnlyField(source='provider.name')
    currency_code = serializers.ReadOnlyField(source='currency.code')
    resolved_by_username = serializers.ReadOnlyField(source='resolved_by.username')
    
    class Meta:
        model = ProviderBlocking
        fields = [
            'id', 'provider', 'provider_name',
            'status', 'blocking_level', 'debt_amount', 'overdue_days',
            'currency', 'currency_code', 'blocked_at', 'resolved_at',
            'resolved_by', 'resolved_by_username', 'notes',
        ]
        read_only_fields = ['blocked_at', 'resolved_at']


class BillingManagerProviderSerializer(serializers.ModelSerializer):
    """
    Сериализатор для связи менеджера по биллингу с провайдером.
    """
    billing_manager_name = serializers.CharField(source='billing_manager.get_full_name', read_only=True)
    provider_name = serializers.CharField(source='provider.name', read_only=True)
    
    class Meta:
        model = BillingManagerProvider
        fields = [
            'id', 'billing_manager', 'billing_manager_name', 'provider', 'provider_name',
            'status', 'start_date', 'end_date', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class BillingManagerProviderCreateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания связи менеджера по биллингу с провайдером.
    """
    
    class Meta:
        model = BillingManagerProvider
        fields = [
            'billing_manager', 'provider', 'status', 'start_date', 'end_date'
        ]


class BillingManagerEventSerializer(serializers.ModelSerializer):
    """
    Сериализатор для событий менеджера по биллингу.
    """
    billing_manager_name = serializers.CharField(source='billing_manager_provider.billing_manager.get_full_name', read_only=True)
    provider_name = serializers.CharField(source='billing_manager_provider.provider.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = BillingManagerEvent
        fields = [
            'id', 'billing_manager_provider', 'billing_manager_name', 'provider_name',
            'event_type', 'effective_date', 'notes', 'created_by', 'created_by_name',
            'created_at'
        ]
        read_only_fields = ['created_at']


class BlockingNotificationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для уведомлений о блокировках.
    """
    provider_name = serializers.ReadOnlyField(source='provider_blocking.provider.name')
    
    class Meta:
        model = BlockingNotification
        fields = [
            'id', 'provider_blocking', 'provider_name', 'notification_type', 
            'status', 'recipient_email', 'recipient_phone', 'subject', 
            'message', 'sent_at', 'error_message', 'created_at'
        ]
        read_only_fields = ['sent_at', 'created_at'] 
