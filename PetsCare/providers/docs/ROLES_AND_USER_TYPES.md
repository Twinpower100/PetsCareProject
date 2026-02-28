# Роли провайдера: UserType vs EmployeeProvider.role

## Два уровня ролей

### 1. UserType (модель User, user_types)

**Глобальные роли пользователя** — определяют, в какие приложения и разделы пользователь может войти. Хранятся в M2M `User.user_types` (таблица UserType).

| UserType            | Назначение в коде                    | Доступ в админку провайдера |
|---------------------|--------------------------------------|-----------------------------|
| owner               | assign_provider_staff_from_form      | да                          |
| provider_manager    | инвайт + assign_provider_staff_from_form | да                      |
| provider_admin      | assign_provider_staff_from_form, инвайт | да                      |
| branch_manager      | приём инвайта руководителя филиала  | да                          |
| specialist          | приём инвайта «специалист в филиал» | да                          |
| system_admin        | вручную (админка Django)             | да (для поддержки)          |
| pet_owner, basic_user, billing_manager, employee, … | другие флоу | нет (для админки провайдера) |

**В базе могут быть записи** `service_worker` и `technical_worker` (часто с 0 пользователей). Код нигде не делает `add_role('service_worker')` или `add_role('technical_worker')` — это роли внутри связи (EmployeeProvider.role / EmployeeLocationRole.role). Новым пользователям их не назначать; для входа в админку провайдера использовать UserType **specialist**.

---

### 2. EmployeeProvider.role / EmployeeLocationRole.role

**Роль в рамках одной связи** «пользователь ↔ провайдер» или «сотрудник ↔ филиал». Определяет уровень доступа внутри провайдера (API, админка), а не право входа в приложение.

| Роль (EmployeeProvider / EmployeeLocationRole) | Смысл |
|------------------------------------------------|--------|
| owner                                          | Владелец организации |
| provider_manager                               | Менеджер организации (один на провайдера) |
| provider_admin                                 | Админ организации |
| **service_worker**                             | Оказывает услуги клиентам. Доступ к своему расписанию и визитам. |
| **technical_worker**                           | Техработник (клинер и т.п.). Доступ только к своему расписанию. |
| location_manager                               | Руководитель филиала (только в EmployeeLocationRole) |

---

## Разница specialist / service_worker / technical_worker

- **specialist** — это **UserType**. Выдаётся при принятии инвайта «специалист в филиал». Даёт право входа в админку провайдера. В коде при этом создаётся запись EmployeeProvider с **role=service_worker** (по умолчанию) и пользователю добавляется user_type **specialist**. То есть один человек: `user_types` содержит `specialist`, а в EmployeeProvider у него `role=service_worker` (или при смене роли вручную — `technical_worker`).

- **service_worker** и **technical_worker** — только значения поля **EmployeeProvider.role** (и EmployeeLocationRole.role). Они не дублируются в UserType. Различие:
  - **service_worker**: оказывает услуги клиентам (расписание, визиты).
  - **technical_worker**: техработник (клинер и т.п.), только своё расписание.

Итого: код назначает только UserType **specialist** сотрудникам филиалов; детализация «оказывает услуги / техработник» хранится в EmployeeProvider.role. Записи UserType `service_worker` и `technical_worker` в БД могут существовать (часто 0 пользователей), но код их не назначает — не использовать для новых пользователей.

---

## Текущее состояние в БД (пример)

На момент проверки: 13 UserType. Назначаемые кодом для доступа в админку провайдера: owner, provider_admin, provider_manager, branch_manager, specialist, system_admin. Остальные: basic_user, billing_manager, booking_manager, pet_owner, pet_sitter; service_worker и technical_worker — без назначений в коде.

---

## Рекомендации

1. Не назначать пользователям UserType `service_worker` и `technical_worker` — различать типы работы через EmployeeProvider.role / EmployeeLocationRole.role.
2. Доступ в админку провайдера проверять по UserType: owner, provider_manager, provider_admin, branch_manager, specialist, system_admin.
3. Внутри приложения разграничивать доступ по EmployeeProvider (is_owner, is_provider_manager, is_provider_admin, role) и по EmployeeLocationRole для филиалов.
