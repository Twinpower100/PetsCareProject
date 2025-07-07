from rest_framework import serializers
from .models import (
    Payment, Invoice, Refund, Contract, ContractType,
    Currency, ServicePrice, PaymentHistory, BillingManagerProvider, BillingManagerEvent,
    BlockingRule, ProviderBlocking, BlockingNotification
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

    class Meta:
        model = PaymentHistory
        fields = [
            'id', 'contract', 'amount', 'currency', 'currency_id',
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


class ContractTypeSerializer(serializers.ModelSerializer):
    """
    Сериализатор для типа контракта.
    """
    class Meta:
        model = ContractType
        fields = ['id', 'name', 'code', 'description', 'is_active']
        read_only_fields = ['id']


class ContractSerializer(serializers.ModelSerializer):
    """
    Сериализатор для контракта.
    """
    currency = CurrencySerializer(read_only=True)
    currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.filter(is_active=True),
        write_only=True,
        source='currency'
    )
    base_currency = CurrencySerializer(read_only=True)
    base_currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.filter(is_active=True),
        write_only=True,
        source='base_currency'
    )

    class Meta:
        model = Contract
        fields = [
            'id', 'provider', 'contract_type', 'number',
            'start_date', 'end_date', 'status', 'terms',
            'document', 'document_name', 'currency', 'currency_id',
            'base_currency', 'base_currency_id', 'payment_deferral_days',
            'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'document_name']

    def validate(self, data):
        """
        Проверяет, что дата окончания не раньше даты начала
        """
        if data.get('end_date') and data['end_date'] < data['start_date']:
            raise serializers.ValidationError(
                _("Contract end date cannot be earlier than start date")
            )
        return data

    def validate_document(self, value):
        """Валидация загружаемого файла"""
        if value:
            # Проверка размера файла (10MB)
            if value.size > 10 * 1024 * 1024:
                raise serializers.ValidationError(_("File size should not exceed 10MB"))
            
            # Проверка расширения файла
            valid_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
            if not any(value.name.lower().endswith(ext) for ext in valid_extensions):
                raise serializers.ValidationError(
                    _("File type not supported. Please upload PDF, JPG or PNG")
                )
        return value


class ContractCreateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания контракта.
    """
    class Meta:
        model = Contract
        fields = [
            'provider', 'contract_type', 'number', 'start_date',
            'end_date', 'terms', 'document'
        ]


class PaymentSerializer(serializers.ModelSerializer):
    """
    Сериализатор для платежей.
    """
    class Meta:
        model = Payment
        fields = [
            'id', 'booking', 'amount', 'status', 'payment_method',
            'transaction_id', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class InvoiceSerializer(serializers.ModelSerializer):
    """
    Сериализатор для счетов.
    """
    class Meta:
        model = Invoice
        fields = [
            'id', 'booking', 'number', 'amount', 'status',
            'due_date', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'number', 'created_at', 'updated_at']


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
        fields = ['booking', 'amount', 'payment_method']


class RefundCreateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания возврата.
    """
    class Meta:
        model = Refund
        fields = ['payment', 'amount', 'reason']


class BlockingRuleSerializer(serializers.ModelSerializer):
    """
    Сериализатор для правил блокировки.
    """
    created_by = serializers.ReadOnlyField(source='created_by.username')
    
    class Meta:
        model = BlockingRule
        fields = [
            'id', 'name', 'description', 'debt_amount_threshold', 
            'overdue_days_threshold', 'is_mass_rule', 'regions', 
            'service_types', 'priority', 'is_active', 'created_by', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class ProviderBlockingSerializer(serializers.ModelSerializer):
    """
    Сериализатор для блокировок учреждений.
    """
    provider_name = serializers.ReadOnlyField(source='provider.name')
    blocking_rule_name = serializers.ReadOnlyField(source='blocking_rule.name')
    currency_code = serializers.ReadOnlyField(source='currency.code')
    resolved_by_username = serializers.ReadOnlyField(source='resolved_by.username')
    
    class Meta:
        model = ProviderBlocking
        fields = [
            'id', 'provider', 'provider_name', 'blocking_rule', 
            'blocking_rule_name', 'status', 'debt_amount', 'overdue_days', 
            'currency', 'currency_code', 'blocked_at', 'resolved_at', 
            'resolved_by', 'resolved_by_username', 'notes'
        ]
        read_only_fields = ['blocked_at', 'resolved_at']


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