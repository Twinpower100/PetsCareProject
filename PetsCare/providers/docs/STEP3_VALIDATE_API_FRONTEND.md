# API валидации шага 3 (реквизиты) — интеграция на фронте

Используется в мастере регистрации провайдера на **шаге 3** перед переходом на следующий шаг и при финальной отправке формы.

## Endpoint

- **URL:** `POST /api/v1/provider-registration/step3-validate/`
- **Auth:** `Authorization: Bearer <token>` (обязательно)

## Тело запроса (JSON)

Отправлять те же поля, что на шаге 3:

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| `country` | string | да | Код страны ISO 3166-1 alpha-2 (например `RU`, `DE`) |
| `tax_id` | string | да | ИНН / Tax ID |
| `registration_number` | string | да | Регистрационный номер |
| `vat_number` | string | нет | НДС номер |
| `kpp` | string | нет | КПП |
| `iban` | string | нет | IBAN |
| `swift_bic` | string | нет | SWIFT/BIC |
| `director_name` | string | нет | ФИО руководителя |
| `bank_name` | string | нет | Название банка |
| `organization_type` | string | нет | Тип организации |
| `is_vat_payer` | boolean | да | Является ли плательщиком НДС |

## Ответы

**Успех (200 OK):**
```json
{ "valid": true }
```

**Ошибки валидации (400 Bad Request):**
```json
{
  "valid": false,
  "errors": {
    "tax_id": "A provider with this Tax ID / INN already exists.",
    "registration_number": "Registration number must be at least 3 characters."
  }
}
```

Ключи в `errors` совпадают с именами полей формы. Сообщения уже переведены на язык запроса (если бэкенд поддерживает `Accept-Language`).

## Что проверяет бэкенд

- Обязательность и минимальная длина (в т.ч. `tax_id`, `registration_number` ≥ 3 символа).
- Максимальная длина всех полей (соответствует модели).
- Форматы по стране (ИНН/рег. номер/VAT/IBAN/KPP и т.д. через `validation_rules`).
- Уникальность `tax_id` и `registration_number` среди провайдеров и среди заявок в статусах `pending`/`approved`.

## Интеграция в Step3Requisites (React)

1. **Добавить метод в API-клиент** (например `providerAPI.ts`):

```ts
async step3Validate(data: {
  country: string;
  tax_id: string;
  registration_number: string;
  vat_number?: string;
  kpp?: string;
  iban?: string;
  swift_bic?: string;
  director_name?: string;
  bank_name?: string;
  organization_type?: string;
  is_vat_payer: boolean;
}): Promise<{ valid: true } | { valid: false; errors: Record<string, string> }> {
  const res = await fetch('/api/v1/provider-registration/step3-validate/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getAccessToken()}`, // ваш способ получения токена
    },
    body: JSON.stringify(data),
  });
  const body = await res.json();
  if (res.ok) return body as { valid: true };
  return body as { valid: false; errors: Record<string, string> };
}
```

2. **При нажатии «Далее» на шаге 3** (перед переходом на следующий шаг):

- Собрать из формы объект с полями `country`, `tax_id`, `registration_number`, `vat_number`, `kpp`, `iban`, `swift_bic`, `director_name`, `bank_name`, `organization_type`, `is_vat_payer`.
- Вызвать `step3Validate(payload)`.
- Если ответ `valid: true` — выполнить переход на следующий шаг.
- Если `valid: false` — установить ошибки полей из `errors` (например, в state формы или в react-hook-form `setError`) и не переходить. Показать сообщения под соответствующими полями.

3. **При финальной отправке мастера** валидация шага 3 уже выполняется на бэкенде в `ProviderRegistrationWizardSerializer`; повторный вызов `step3-validate` перед отправкой не обязателен, но допустим для единообразного UX (ошибки можно показать до отправки всей формы).

## Лимиты длин полей (для локальной проверки min/max на фронте)

| Поле | min | max |
|------|-----|-----|
| tax_id | 3 | 20 |
| registration_number | 3 | 100 |
| vat_number | — | 50 |
| kpp | — | 20 |
| iban | — | 34 |
| swift_bic | — | 11 |
| director_name | — | 200 |
| bank_name | — | 200 |
| organization_type | — | 50 |

Локальная проверка длины не заменяет вызов API: формат и уникальность проверяются только на бэкенде.

---

## Проверка уникальности при уходе с поля (on blur)

Сделать проверку уникальности **как у телефона** (валидация при переходе к другому полю, с debounce) — **можно**.

**Как сейчас у телефона:** есть эндпоинты `GET .../check-provider-phone/?provider_phone=...` и `GET .../check-admin-email/` (или POST с телом), которые фронт вызывает при blur (или с задержкой после ввода). Ответ: `{ exists: true/false, valid: true/false }` или аналог — фронт показывает ошибку под полем.

**Эндпоинты проверки уникальности при уходе с поля (реализованы на бэкенде):**

| Эндпоинт | Метод | Query-параметры | Ответ |
|----------|--------|------------------|--------|
| `/api/v1/provider-registration/check-iban/` | GET | `iban` | `{ iban, exists, valid, error? }` |
| `/api/v1/provider-registration/check-tax-id/` | GET | `country`, `tax_id` | `{ country, tax_id, exists, valid, error? }` |
| `/api/v1/provider-registration/check-registration-number/` | GET | `country`, `registration_number` | `{ country, registration_number, exists, valid, error? }` |
| `/api/v1/provider-registration/check-vat-number/` | GET | `country`, `vat_number` | `{ country, vat_number, exists, valid, error? }` |

- **exists:** `true`, если провайдер или заявка (pending/approved) с таким значением уже есть.
- **valid:** базовая проверка формата/длины.
- **error:** сообщение для отображения под полем (если `exists === true` или параметр не передан).

Auth: `Authorization: Bearer <token>` (обязательно).

На фронте: на полях IBAN, Tax ID, Registration Number, VAT Number вешать `onBlur` (и при желании debounce 300–500 ms), вызывать соответствующий GET с query-параметрами и при `exists === true` выводить `error` под полем. Так пользователь сразу видит конфликт, не дожидаясь нажатия «Далее» или отправки формы.

Итоговая валидация при «Далее» и при финальной отправке (step3-validate и сериализатор мастера) при этом остаётся — она перекрывает случай, если пользователь не ушёл с поля или запрос on blur не выполнялся.
