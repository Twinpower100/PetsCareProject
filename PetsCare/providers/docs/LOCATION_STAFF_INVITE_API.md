# Location staff invite — API and flow (reference: location manager invite)

## Цель
Вкладка «Персонал» на странице филиала: приглашение пользователей системы на роль персонала филиала с подтверждением по токену (аналогично флоу инвайта руководителя филиала).

## Референс: руководитель филиала (Location manager)
- **Модель:** `LocationManagerInvite` (provider_location, email, token, expires_at).
- **API:**
  - `POST provider-locations/<id>/set-manager/` — тело `{ "email": "...", "language": "en" }`. Свой email → сразу назначить manager; чужой → создать инвайт, отправить письмо с 6-значным кодом.
  - `DELETE provider-locations/<id>/manager/` — снять руководителя.
  - `POST location-manager-invite/accept/` — тело `{ "token": "123456" }`. Без авторизации. При успехе пользователь становится manager локации.
- **Фронт:** страница принятия инвайта по коду, мультиязычность.

## Требуемое для персонала (Staff)
1. **Модель** (по аналогии): `LocationStaffInvite`
   - `provider_location` (FK)
   - `email`
   - `token` (6 символов, unique)
   - `expires_at`
   - После принятия: создаётся/обновляется связь Employee–ProviderLocation (персонал филиала). Пользователь (User) должен быть привязан к Employee (или создан Employee при первом инвайте).

2. **API**
   - `POST provider-locations/<id>/invite-staff/` — тело `{ "email": "...", "language": "en" }`. Создать инвайт, отправить письмо с кодом.
   - `DELETE provider-locations/<id>/staff-invites/<invite_id>/` или отмена по email — отменить инвайт.
   - `POST location-staff-invite/accept/` — тело `{ "token": "123456" }`. Без авторизации. При успехе: привязать пользователя как сотрудника к провайдеру и к данной локации (Employee + связь с ProviderLocation).

3. **Список персонала и инвайтов**
   - В ответе локации уже есть `employees_count` и при необходимости можно вернуть список сотрудников/инвайтов через отдельный эндпоинт, например: `GET provider-locations/<id>/staff/` — список сотрудников и ожидающих инвайтов (pending invites).

4. **Письма и мультиязычность**
   - Шаблоны писем для приглашения в персонал (по аналогии с manager), все строки через `_()` / `trans`, язык из параметра `language`.

5. **Фронт (админка)**
   - Вкладка «Персонал»: таблица сотрудников филиала, кнопка «Пригласить» (email + отправка инвайта), отображение ожидающих инвайтов.
   - Страница принятия инвайта персонала (как AcceptLocationManagerInvitePage): ввод 6-значного кода, мультиязычность.

## Связь с существующими моделями
- `ProviderLocation.employees` — связь с сотрудниками (M2M или через Schedule/другую модель). Нужно уточнить в коде, как именно хранится привязка Employee ↔ ProviderLocation.
- `Employee` связан с `Provider` и с пользователем (User). При принятии staff-invite нужно обеспечить создание/обновление Employee и привязку к локации.

После реализации бэкенда (модель, эндпоинты, письма) фронт вкладки «Персонал» и страница принятия инвайта делаются по образцу руководителя филиала.

## Реализовано (бэкенд)
- **Модель:** `LocationStaffInvite` (provider_location, email, token, expires_at), unique_together (provider_location, email).
- **API:**
  - `POST provider-locations/<id>/invite-staff/` — тело `{ "email": "...", "language": "en" }`. Создаёт/обновляет инвайт, отправляет письмо с 6-значным кодом.
  - `GET provider-locations/<id>/staff/` — список сотрудников (employees) и ожидающих инвайтов (invites).
  - `DELETE provider-locations/<id>/staff-invites/<invite_id>/` — отменить инвайт.
  - `POST location-staff-invite/accept/` — тело `{ "token": "123456" }`. Без авторизации. При успехе: создаётся/обновляется Employee, EmployeeProvider (is_confirmed=True), employee.locations добавляется локация.
- Письмо приглашения в персонал отправляется через `send_mail` (как у manager invite).

## Услуги и расписание сотрудника (per location)
- **Услуги:**
  - `GET provider-locations/<location_pk>/staff/<employee_id>/services/` — список `service_ids` сотрудника (только ID, доступные в этой локации).
  - `PATCH provider-locations/<location_pk>/staff/<employee_id>/services/` — тело `{ "service_ids": [1, 2, 3] }`. Все ID должны быть из доступных в локации.
  - `POST provider-locations/<location_pk>/staff/<employee_id>/services/add-by-category/` — тело `{ "category_id": <id> }`. Добавляет все листовые услуги категории, доступные в локации, сотруднику.
- **Расписание (паттерн на неделю):**
  - `GET provider-locations/<location_pk>/staff/<employee_id>/schedules/` — массив `days` (day_of_week, start_time, end_time, break_start, break_end, is_working).
  - `PUT provider-locations/<location_pk>/staff/<employee_id>/schedules/` — тело `{ "days": [ { "day_of_week": 0, "start_time": "09:00", "end_time": "18:00", "break_start": null, "break_end": null, "is_working": true }, ... ] }` (ровно 7 элементов). Создаёт/обновляет записи `Schedule` для сотрудника в этой локации.

Доступ только у provider_admin для данной локации; сотрудник должен быть привязан к локации (`employee.locations`).

## Рекомендация по UI
- **Вкладка «Персонал»:** пустое состояние (нет активных принявших) → надпись + смайл; система инвайтов; после принятия инвайта — настройка услуг и расписания работника на этой вкладке (кнопки «Услуги» и «Расписание» в строке сотрудника).
- **Вкладка «График работы персонала»:** шахматка/визуализация для наглядного просмотра дыр в расписании (настройка паттернов — в «Персонал»).
