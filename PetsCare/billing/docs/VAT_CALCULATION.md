# Расчет НДС в системе биллинга

## Обзор

Система поддерживает автоматический расчет НДС (VAT) при создании счетов (Invoice) для провайдеров услуг.

## Логика расчета НДС

### Если провайдер НЕ плательщик НДС (`is_vat_payer = False`):
- Базовая комиссия = `booking_amount * commission_percent / 100`
- НДС начисляется сверх комиссии
- Итого в счете = `commission * (1 + vat_rate/100)`
- Пример: 100€ услуга, 5% комиссия, 20% НДС
  - Комиссия = 5€
  - НДС = 5€ * 0.20 = 1€
  - С НДС = 5€ + 1€ = 6€

### Если провайдер плательщик НДС (`is_vat_payer = True`):
- Для ЕС: Reverse Charge (0% НДС, провайдер сам начисляет)
- Для других стран: зависит от законодательства

## Модели

### VATRate
Модель для хранения ставок НДС по странам:
- `country` - код страны (ISO 3166-1 alpha-2)
- `rate` - ставка НДС (например, 20.00 для 20%)
- `effective_date` - дата вступления в силу
- `is_active` - активна ли ставка

### InvoiceLine
Добавлены поля для НДС:
- `vat_rate` - ставка НДС (Decimal, nullable)
- `vat_amount` - сумма НДС (Decimal, default=0.00)
- `total_with_vat` - итоговая сумма с НДС (Decimal, default=0.00)

## Использование

### Расчет комиссии с НДС

```python
from providers.models import Provider
from decimal import Decimal

# Получаем провайдера
provider = Provider.objects.get(id=1)

# Рассчитываем комиссию с НДС
result = provider.calculate_commission_with_vat(
    booking_amount=Decimal('100.00'),
    booking_currency=currency,
    provider_currency=provider.invoice_currency
)

# Результат:
# {
#     'commission': Decimal('5.00'),      # Базовая комиссия без НДС
#     'vat_rate': Decimal('20.00'),     # Ставка НДС (или None)
#     'vat_amount': Decimal('1.00'),    # Сумма НДС
#     'total_with_vat': Decimal('6.00') # Итоговая сумма с НДС
# }
```

### Создание InvoiceLine с НДС

```python
from billing.models import InvoiceLine, Invoice
from providers.models import Provider

# Получаем провайдера и booking
provider = Provider.objects.get(id=1)
booking = Booking.objects.get(id=1)

# Рассчитываем комиссию с НДС
commission_data = provider.calculate_commission_with_vat(
    booking_amount=booking.amount,
    booking_currency=booking.currency,
    provider_currency=provider.invoice_currency
)

# Создаем InvoiceLine
invoice_line = InvoiceLine.objects.create(
    invoice=invoice,
    booking=booking,
    amount=booking.amount,
    commission=commission_data['commission'],
    rate=commission_percent,  # Процент комиссии из оферты
    currency=provider.invoice_currency,
    vat_rate=commission_data['vat_rate'],
    vat_amount=commission_data['vat_amount'],
    total_with_vat=commission_data['total_with_vat']
)
```

## Получение ставки НДС для страны

```python
from billing.models import VATRate

# Получить актуальную ставку НДС для страны
vat_rate = VATRate.get_rate_for_country('RU')  # Для России
# Возвращает Decimal или None если не найдена

# Получить ставку на конкретную дату
from django.utils import timezone
from datetime import date

vat_rate = VATRate.get_rate_for_country('DE', date=date(2025, 1, 1))
```

## Администрирование

Ставки НДС можно управлять через Django Admin:
- Путь: `/admin/billing/vatrate/`
- Доступ: только системные администраторы
- Биллинг-менеджеры могут только просматривать

## Важные замечания

1. **Ставки НДС по странам**: Необходимо заполнить ставки НДС для всех стран, где работают провайдеры
2. **Reverse Charge для ЕС**: Для провайдеров из ЕС с валидным VAT ID применяется Reverse Charge (0% НДС)
3. **Обновление ставок**: При изменении ставок НДС в стране создается новая запись с новой `effective_date`
4. **Исторические данные**: Старые InvoiceLine сохраняют ставку НДС, которая была актуальна на момент создания

