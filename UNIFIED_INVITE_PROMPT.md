# Промпт для Cursor: Унификация системы инвайтов PetCare
## Роль - Сеньор Джанго разработчик
## Задача

Объединить все существующие типы инвайтов в **одну модель `Invite`** и один унифицированный процесс создания/приёма. Сейчас в проекте разрозненные модели и API эндпоинты — нужно свести их к единой структуре, сохранив всю бизнес-логику.

---

## Текущее состояние (что есть сейчас)

### 5 отдельных моделей инвайтов:

**1. `ProviderOwnerManagerInvite`** (`providers/models.py`, строки 2394–2444)
- Приглашение менеджера организации (владелец не приглашается)
- Поля: `provider` (FK), `email`, `role` (только `provider_manager`), `token` (6 цифр, unique), `expires_at`, `created_at`
- При приёме: в одной транзакции снимает `is_provider_manager` у всех текущих, назначает принявшего
- Инвайт удаляется после приёма
- Создание: `providers/api_views.py` → `ProviderAdminInviteAPIView` (строки 315–394)
- Приём: `providers/api_views.py` → `AcceptProviderOwnerManagerInviteAPIView` (строки 472–569)
- Email: `_send_provider_owner_manager_invite_email()` (строки 278–312)
- URL создания: `POST providers/<provider_id>/admins/invite/`
- URL приёма: `POST provider-owner-manager-invite/accept/` (AllowAny)
- Админка Django: `ProviderOwnerManagerInviteAdmin` (`providers/admin.py`, строки 1039–1061)

**2. `LocationManagerInvite`** (`providers/models.py`, строки 2364–2391)
- Приглашение руководителя филиала (один на локацию)
- Поля: `provider_location` (FK), `email`, `token` (6 цифр, unique), `expires_at`, `created_at`
- При приёме: `provider_location.manager = user`, инвайт удаляется
- Создание: отдельный view в providers (нужно найти — возможно `InviteLocationManagerAPIView`)
- Приём: `AcceptLocationManagerInviteAPIView` (строки 2398–2436)
- URL приёма: `POST location-manager-invite/accept/` (AllowAny)
- Админка Django: `LocationManagerInviteAdmin` (строки 1064–1072)

**3. `LocationStaffInvite`** (`providers/models.py`, строки 2447–2488)
- Приглашение сотрудника в персонал филиала (многие на локацию)
- Поля: `provider_location` (FK), `email`, `token` (6 цифр, unique), `expires_at`, `created_at`
- `unique_together = [['provider_location', 'email']]`
- При приёме: создаёт `Employee` + `EmployeeProvider` (role=service_worker), добавляет в `employee.locations`, инвайт удаляется
- Создание: `InviteLocationStaffAPIView` (строки 2439–2542)
- Приём: `AcceptLocationStaffInviteAPIView` (строки 2606–2672)
- Удаление: `LocationStaffInviteDestroyAPIView` (строки 2589–2603)
- URL создания: `POST provider-locations/<pk>/invite-staff/`
- URL приёма: `POST location-staff-invite/accept/` (AllowAny)
- URL удаления: `DELETE provider-locations/<pk>/staff-invites/<invite_id>/`
- Админка Django: `LocationStaffInviteAdmin` (строки 1075–1083)

**4. `RoleInvite`** (`users/models.py`, строки 1273–1602)
- Инвайт на роли: employee, billing_manager, owner, provider_manager, provider_admin
- Самая полная модель: `created_by` (FK User), `email`, `role`, `provider` (FK), `position`, `comment`, `token` (max 64, unique), `qr_code`, `status` (pending/accepted/declined/expired), `created_at`, `expires_at`, `accepted_at`, `declined_at`, `accepted_by` (FK User)
- Serializers: `RoleInviteSerializer`, `RoleInviteCreateSerializer`, `RoleInviteAcceptSerializer`, `RoleInviteDeclineSerializer` (`users/serializers.py`, строки 458–616)
- API views: `RoleInviteViewSet`, `RoleInviteDetailView`, `RoleInviteAcceptAPIView`, `RoleInviteDeclineAPIView`, `RoleInviteByTokenAPIView`, `RoleInviteQRCodeAPIView`, `RoleInvitePendingAPIView`, `RoleInviteCleanupAPIView` (`users/api_views.py`)
- URLs: `users/urls.py`, строки 66–74 (`/role-invites/...`)
- Notification signals: `notifications/signals.py`, строки 161–229, 439–458 (post_save на `users.RoleInvite`)
- Notification tasks: `notifications/tasks.py` — `send_role_invite_task`, `send_role_invite_response_task`, `send_role_invite_expired_task`

**5. `PetOwnershipInvite`** (`pets/models.py`, строки 1029–1061)
- Инвайт совладельца питомца или передача прав основного владельца
- Поля: `pet` (FK), `email`, `token` (UUID, unique), `expires_at`, `type` (invite/transfer), `invited_by` (FK User), `is_used` (bool), `created_at`
- API views: `PetInviteAPIView`, `PetAcceptInviteAPIView`, `PetInviteQRCodeAPIView` (`pets/api_views.py`)
- URLs: `pets/urls.py`, строки 44–47

---

## Целевая архитектура (что нужно реализовать)

### Единая модель `Invite`

Размещение: **новое приложение `invites`** (или внутри `users` — на усмотрение, но лучше отдельное app для чистоты).

```python
class Invite(models.Model):
    """
    Единая модель приглашения для всех типов инвайтов в системе.
    
    Поддерживаемые типы:
    - provider_manager: менеджер организации (один на провайдера)
    - provider_admin: админ организации (много на провайдера)
    - branch_manager: руководитель филиала (один на локацию)
    - specialist: специалист/сотрудник в локации (много на локацию)
    - pet_co_owner: совладелец питомца
    - pet_transfer: передача прав основного владельца
    """
    
    # === Тип инвайта ===
    TYPE_PROVIDER_MANAGER = 'provider_manager'
    TYPE_PROVIDER_ADMIN = 'provider_admin'
    TYPE_BRANCH_MANAGER = 'branch_manager'
    TYPE_SPECIALIST = 'specialist'
    TYPE_PET_CO_OWNER = 'pet_co_owner'
    TYPE_PET_TRANSFER = 'pet_transfer'
    
    TYPE_CHOICES = [
        (TYPE_PROVIDER_MANAGER, _('Provider Manager')),
        (TYPE_PROVIDER_ADMIN, _('Provider Admin')),
        (TYPE_BRANCH_MANAGER, _('Branch Manager')),
        (TYPE_SPECIALIST, _('Specialist')),
        (TYPE_PET_CO_OWNER, _('Pet Co-Owner')),
        (TYPE_PET_TRANSFER, _('Pet Transfer')),
    ]
    
    # === Статус ===
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_DECLINED = 'declined'
    STATUS_EXPIRED = 'expired'
    STATUS_CANCELLED = 'cancelled'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, _('Pending')),
        (STATUS_ACCEPTED, _('Accepted')),
        (STATUS_DECLINED, _('Declined')),
        (STATUS_EXPIRED, _('Expired')),
        (STATUS_CANCELLED, _('Cancelled')),
    ]
    
    # === Общие поля (есть у ВСЕХ инвайтов) ===
    invite_type = models.CharField(_('Invite Type'), max_length=30, choices=TYPE_CHOICES)
    email = models.EmailField(_('Email'), help_text=_('Email of the invited user'))
    token = models.CharField(_('Token'), max_length=6, unique=True, help_text=_('6-digit activation code'))
    status = models.CharField(_('Status'), max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    expires_at = models.DateTimeField(_('Expires At'))
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    
    # === Кто создал ===
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='created_invites', verbose_name=_('Created By'),
        null=True, blank=True,  # null для системных/автоматических
    )
    
    # === Контекстные FK (nullable, зависят от invite_type) ===
    provider = models.ForeignKey(
        'providers.Provider', on_delete=models.CASCADE,
        null=True, blank=True, related_name='invites', verbose_name=_('Provider'),
    )
    provider_location = models.ForeignKey(
        'providers.ProviderLocation', on_delete=models.CASCADE,
        null=True, blank=True, related_name='invites', verbose_name=_('Provider Location'),
    )
    pet = models.ForeignKey(
        'pets.Pet', on_delete=models.CASCADE,
        null=True, blank=True, related_name='invites', verbose_name=_('Pet'),
    )
    
    # === Метаданные приёма/отклонения ===
    accepted_at = models.DateTimeField(_('Accepted At'), null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='accepted_invites', verbose_name=_('Accepted By'),
    )
    declined_at = models.DateTimeField(_('Declined At'), null=True, blank=True)
    
    # === Дополнительные поля (для RoleInvite-совместимости) ===
    position = models.CharField(_('Position'), max_length=100, blank=True)
    comment = models.TextField(_('Comment'), blank=True)
    qr_code = models.TextField(_('QR Code'), blank=True)
    
    class Meta:
        verbose_name = _('Invite')
        verbose_name_plural = _('Invites')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['email']),
            models.Index(fields=['invite_type', 'status']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['provider']),
            models.Index(fields=['provider_location']),
        ]
        constraints = [
            # Один активный инвайт на (location_staff, location, email)
            models.UniqueConstraint(
                fields=['provider_location', 'email'],
                condition=models.Q(invite_type='location_staff', status='pending'),
                name='unique_pending_location_staff_invite',
            ),
        ]
```

### Валидация модели (метод `clean`)

    # === Валидация модели (метод clean) ===
    # В методе clean() модели Invite нужно проверять:
    # - provider_manager, provider_admin -> provider обязателен
    # - branch_manager, specialist -> provider_location обязателен (и из него доставать provider)
    # - pet_co_owner, pet_transfer -> pet обязателен
    # - Все остальные FK при этом должны быть null

### Методы модели

```python
def is_expired(self):
    return timezone.now() >= self.expires_at

def can_be_accepted(self):
    return self.status == self.STATUS_PENDING and not self.is_expired()

def accept(self, user):
    """Универсальный метод приёма — вызывает нужный handler по invite_type."""
    ...

def decline(self, user):
    """Отклоняет инвайт."""
    ...

def cancel(self):
    """Отменяет инвайт (создателем)."""
    ...

@staticmethod
def generate_token():
    """Генерирует уникальный 6-значный код."""
    ...
```

### Стратегия приёма инвайта (accept handlers)

Метод `accept(user)` должен маршрутизировать по `invite_type` и вызывать конкретный handler. Каждый handler реализует текущую бизнес-логику:

**`_accept_provider_manager`**: (из `AcceptProviderOwnerManagerInviteAPIView`)
- В транзакции: снять `is_provider_manager=True` у всех текущих `EmployeeProvider` этого провайдера
- Создать/обновить `EmployeeProvider` для принявшего (role=provider_manager, is_provider_manager=True, is_manager=True)
- **Назначить UserType**: `user.add_role('provider_admin')`, `user.add_role('provider_manager')`
- Установить `self.status = 'accepted'`, НЕ удалять запись

**`_accept_provider_admin`**: (новый тип — много на провайдера)
- Создать/обновить `EmployeeProvider` с `is_provider_admin=True`, role=provider_admin
- **Назначить UserType**: `user.add_role('provider_admin')`

**`_accept_branch_manager`**: (из `AcceptLocationManagerInviteAPIView`)
- `provider_location.manager = user`, save
- Создать/обновить `EmployeeProvider` (role=service_worker, чтобы был в штате)
- **Назначить UserType**: `user.add_role('branch_manager')`

**`_accept_specialist`**: (из `AcceptLocationStaffInviteAPIView`)
- Создать `Employee` (если нет)
- Создать `EmployeeProvider` (если нет) с role=service_worker
- Добавить в `employee.locations`
- **Назначить UserType**: `user.add_role('specialist')`

**`_accept_pet_co_owner`**: (из `PetAcceptInviteAPIView`, type='invite')
- `pet.owners.add(user)`
- **Назначить UserType**: `user.add_role('pet_owner')`

**`_accept_pet_transfer`**: (из `PetAcceptInviteAPIView`, type='transfer')
- `pet.main_owner = user`; if user not in owners → `pet.owners.add(user)`
- **Назначить UserType**: `user.add_role('pet_owner')`

---

## Единый API (эндпоинты)

### Создание инвайта
`POST /api/v1/invites/`

Body:
```json
{
  "invite_type": "location_staff",
  "email": "user@example.com",
  "provider_location_id": 42,
  "language": "en"
}
```

Для каждого `invite_type` нужна своя валидация прав доступа создающего:
- `provider_manager` → только владелец провайдера (`is_owner`)
- `provider_admin` → только владелец провайдера (`is_owner`)
- `location_manager` → владелец, менеджер, админ провайдера
- `location_staff` → руководитель филиала или владелец/менеджер/админ
- `pet_co_owner`, `pet_transfer` → только `main_owner` питомца
- `employee` → менеджер провайдера (is_manager)
- `billing_manager` → system_admin

### Приём инвайта
`POST /api/v1/invites/accept/`

Body:
```json
{
  "token": "123456"
}
```
- `permission_classes = [AllowAny]` (6-значный код является секретом)
- Найти инвайт по токену, проверить `is_expired`, вызвать `accept(user)` (user находится из `email`)

### Отклонение инвайта
`POST /api/v1/invites/decline/`

Body:
```json
{
  "token": "123456"
}
```

### Отмена инвайта (создателем)
`DELETE /api/v1/invites/<id>/`

или `POST /api/v1/invites/<id>/cancel/`

### Просмотр инвайтов
`GET /api/v1/invites/` — список (фильтрация по `invite_type`, `status`, `provider`, `provider_location`)
`GET /api/v1/invites/<id>/` — детали
`GET /api/v1/invites/pending/` — только pending для текущего пользователя
`GET /api/v1/invites/token/<token>/` — информация по токену (без приёма)

### QR-код инвайта
`GET /api/v1/invites/<id>/qr-code/`

---

## План миграции (пошагово)

### Фаза 1: Создание новой модели
1. Создать приложение `invites` (или разместить в `users`):
   - `invites/models.py` — модель `Invite`
   - `invites/serializers.py` — `InviteSerializer`, `InviteCreateSerializer`, `InviteAcceptSerializer`
   - `invites/api_views.py` — единые views
   - `invites/urls.py` — новые URL patterns
   - `invites/admin.py` — `InviteAdmin`
   - `invites/services.py` — бизнес-логика accept handlers
   - `invites/email.py` — отправка писем (унифицированная)
2. Написать миграцию создания таблицы `invites_invite`
3. Зарегистрировать приложение в `INSTALLED_APPS` (`settings.py`)
4. Подключить URLs в `urls.py` (корневой)

### Фаза 2: Миграция данных
1. Написать data migration, которая переносит данные из старых моделей в новую.
   **Важно**: Пользователь удалил всех рабочих и провайдеров из базы, поэтому миграция может быть пустой («скелетная»), если данных нет.
2. Для `PetOwnershipInvite`: токен UUID → сгенерировать новый 6-значный Code.
3. Маппинг типов:
   - `LocationStaffInvite` / `RoleInvite(employee)` -> `specialist`
   - `LocationManagerInvite` -> `branch_manager`
   - `RoleInvite(owner/manager/admin)` -> соответственно `provider_manager`/`provider_admin`
   - BillingManager и прочие - не мигрируются.

### Фаза 3: Удаление старого (СРАЗУ)
Поскольку фронт еще не в проде, обратная совместимость не требуется. Сразу заменяем старые эндпоинты на новые.

### Фаза 4: Удаление старого
1. Удалить старые модели: `ProviderOwnerManagerInvite`, `LocationManagerInvite`, `LocationStaffInvite`, `RoleInvite`, `PetOwnershipInvite`
2. Удалить старые serializers, api_views, admin, URLs, notification signals/tasks
3. Написать миграции удаления старых таблиц

---

## Уведомления

Обновить signals в `notifications/signals.py`:
- Удалить `@receiver(post_save, sender='users.RoleInvite')` (3 обработчика: строки 161, 192, 439)
- Создать единые обработчики на `post_save, sender='invites.Invite'`:
  - `handle_invite_created` — при `created=True` и `status='pending'`
  - `handle_invite_status_changed` — при изменении `status` на `accepted` / `declined` / `expired`

Обновить tasks в `notifications/tasks.py`:
- Заменить `send_role_invite_task`, `send_role_invite_response_task`, `send_role_invite_expired_task` на универсальные аналоги, работающие с `Invite`

---

## Отправка email (унифицированная)

Создать `invites/email.py` с единой функцией:

```python
def send_invite_email(invite: Invite, language: str = 'en'):
    """
    Отправляет email с приглашением.
    Шаблон письма определяется по invite.invite_type.
    Все письма содержат 6-значный код и ссылку на страницу приёма.
    """
```

### Страницы приёма на фронте (из `PROVIDER_ADMIN_URL`):
- `provider_manager`, `provider_admin` → `/accept-organization-role-invite`
- `branch_manager` → `/accept-branch-manager-invite`  
- `specialist` → `/accept-specialist-invite`
- Для pet инвайтов → URL на основном фронте (`FRONTEND_URL`) / `/pet-invite/{token}/`

---

## Django Admin

Единый `InviteAdmin` с:
- `list_display`: invite_type, email, status, provider_display, location_display, pet_display, expires_at, created_at
- `list_filter`: invite_type, status, created_at
- `search_fields`: email, provider__name, provider_location__name
- `readonly_fields`: token, created_at, accepted_at, declined_at
- Кастомные methods display для provider/location/pet (показывать только релевантные)

---

## Интеграция с UserType (КРИТИЧЕСКИ ВАЖНО)

### Модель `UserType` (`users/models.py`)

Роли пользователей хранятся в отдельной таблице `UserType`, связанной с `User` через `ManyToManyField(user_types)`. Каждая роль — запись в `UserType` с уникальным `name`.

Определённые роли:
- `basic_user` — базовый пользователь (назначается при регистрации)
- `system_admin` — администратор системы
- `provider_admin` — администратор учреждения
- `billing_manager` — менеджер по биллингу
- `booking_manager` — менеджер по бронированиям
- `employee` — сотрудник учреждения
- `pet_owner` — владелец питомца
- `pet_sitter` — передержка питомцев

### Методы User для работы с ролями

```python
User.has_role(role_name) → bool     # Проверяет наличие роли
User.add_role(role_name)            # Добавляет роль (get_or_create + add)
User.remove_role(role_name)         # Удаляет роль
User.is_employee() → bool           # Shortcut для has_role('employee')
```

### Текущий пробел (FIX в новой системе!)

В текущем коде **не все accept-хендлеры назначают UserType**:
- `AcceptProviderOwnerManagerInviteAPIView` — **НЕ вызывает** `add_role()`
- `AcceptLocationStaffInviteAPIView` — **НЕ вызывает** `add_role('employee')`
- `AcceptLocationManagerInviteAPIView` — **НЕ вызывает** `add_role()`
- `RoleInvite._assign_employee_role` — **НЕ вызывает** `add_role('employee')`
- `RoleInvite._assign_billing_manager_role` — **НЕ вызывает** `add_role('billing_manager')`

Роли назначаются только при создании Provider (в `users/signals.py`, строка 443) и через сигналы pets/sitters.

**В унифицированной системе каждый accept handler ОБЯЗАН назначать UserType!** Маппинг:

| `provider_manager` | `provider_admin`, `provider_manager` |
| `provider_admin` | `provider_admin` |
| `branch_manager` | `branch_manager` |
| `specialist` | `specialist` |
| `pet_co_owner` | `pet_owner` |
| `pet_transfer` | `pet_owner` |

### Пример кода в accept handler

```python
def _accept_specialist(self, user):
    """Принимает инвайт в персонал филиала."""
    from providers.models import Employee, EmployeeProvider
    
    employee, _ = Employee.objects.get_or_create(user=user, defaults={'is_active': True})
    # ... создание EmployeeProvider(role='service_worker'), добавление в locations ...
    
    # ОБЯЗАТЕЛЬНО: назначаем каноничный UserType
    user.add_role('specialist')
```

### Важно: `add_role()` идемпотентен

Метод `add_role()` использует `get_or_create` + `add()`, поэтому безопасно вызывать повторно — дубликаты не создаются.

### СНЯТИЕ UserType при передаче/замене роли (КРИТИЧЕСКИ ВАЖНО!)

При приёме инвайта, который **заменяет** текущего пользователя (например, новый `provider_manager` заменяет старого), нужно **условно снять UserType у старого пользователя**. 

**Ключевое правило**: Нельзя слепо вызывать `remove_role()` — пользователь может занимать ту же роль в **другой организации / филиале / питомце**. Снимать `UserType` можно ТОЛЬКО если у пользователя **не осталось** ни одной активной связи этого типа.

**Существующий паттерн** (из `users/api_views.py`, `_check_co_owner_roles`, строка 1646):
```python
# Проверяем, есть ли у совладельца другие питомцы
other_pets = Pet.objects.filter(owners=co_owner, is_active=True).exists()
if not other_pets:
    co_owner.user_types.remove(pet_owner_role)
```

#### Утилитная функция `maybe_remove_role()`

Создать в `invites/services.py`:

```python
def maybe_remove_role(user, role_name):
    """
    Условно снимает UserType у пользователя.
    Снимает ТОЛЬКО если у пользователя не осталось ни одной
    активной связи, требующей эту роль.
    """
    from providers.models import EmployeeProvider
    from billing.models import BillingManagerProvider
    from pets.models import Pet

    if role_name == 'provider_admin':
        # Проверяем: есть ли ещё активные EmployeeProvider с is_provider_admin=True?
        has_active = EmployeeProvider.objects.filter(
            employee__user=user,
            is_provider_admin=True,
            end_date__isnull=True,
        ).exists()
        if not has_active:
            user.remove_role('provider_admin')

    elif role_name == 'provider_manager':
        has_active = EmployeeProvider.objects.filter(
            employee__user=user,
            is_provider_manager=True,
            end_date__isnull=True,
        ).exists()
        if not has_active:
            user.remove_role('provider_manager')

    elif role_name == 'employee':
        # Проверяем: есть ли ещё активные EmployeeProvider (любая роль)?
        has_active = EmployeeProvider.objects.filter(
            employee__user=user,
            end_date__isnull=True,
        ).exists()
        if not has_active:
            user.remove_role('employee')

    elif role_name == 'billing_manager':
        has_active = BillingManagerProvider.objects.filter(
            billing_manager=user,
            status__in=['active', 'vacation', 'temporary'],
        ).exists()
        if not has_active:
            user.remove_role('billing_manager')

    elif role_name == 'pet_owner':
        has_pets = Pet.objects.filter(
            owners=user,
            is_active=True,
        ).exists()
        if not has_pets:
            user.remove_role('pet_owner')
```

#### Когда вызывать снятие роли

| accept handler | Что происходит со СТАРЫМ пользователем | Вызов `maybe_remove_role()` |
|---|---|---|
| `_accept_provider_manager` | Старый менеджер теряет `is_provider_manager` у **одного** провайдера | `maybe_remove_role(old_user, 'provider_manager')` + `maybe_remove_role(old_user, 'provider_admin')` |
| `_accept_provider_admin` | Без замены (несколько админов допускается) | Не нужно |
| `branch_manager` | Старый менеджер заменяется | `maybe_remove_role(old_manager, 'branch_manager')` |
| `specialist` | Нет замены (добавление нового) | Не нужно |
| `pet_transfer` | Старый `main_owner` теряет статус основного | `maybe_remove_role(old_main_owner, 'pet_owner')` |
| `pet_co_owner` | Нет замены (добавление) | Не нужно |
| `provider_admin` | Нет замены (добавление) | Не нужно |

#### Пример: `_accept_provider_manager` с полным циклом ролей

```python
def _accept_provider_manager(self, user):
    """Принимает инвайт менеджера организации."""
    from providers.models import Employee, EmployeeProvider

    provider = self.provider
    today = timezone.now().date()

    with transaction.atomic():
        # 1. Находим СТАРОГО менеджера (для снятия роли позже)
        old_manager_eps = list(
            EmployeeProvider.objects.filter(
                provider=provider,
                is_provider_manager=True,
                end_date__isnull=True,
            ).select_related('employee__user')
        )
        old_manager_users = [ep.employee.user for ep in old_manager_eps]

        # 2. Снимаем is_provider_manager у всех текущих
        EmployeeProvider.objects.filter(
            provider=provider,
            is_provider_manager=True,
            end_date__isnull=True,
        ).update(is_provider_manager=False, is_manager=False)

        # 3. Назначаем нового менеджера
        employee = _get_employee(user)
        ep, created = EmployeeProvider.objects.get_or_create(
            employee=employee, provider=provider, start_date=today,
            defaults={...}
        )
        # ...

        # 4. Назначаем UserType НОВОМУ
        user.add_role('provider_admin')
        user.add_role('provider_manager')

        # 5. Условно снимаем UserType у СТАРЫХ
        for old_user in old_manager_users:
            if old_user.pk != user.pk:  # Не снимаем у самого себя
                maybe_remove_role(old_user, 'provider_manager')
                maybe_remove_role(old_user, 'provider_admin')
```

#### Пример: `_accept_pet_transfer` с проверкой

```python
def _accept_pet_transfer(self, user):
    """Принимает инвайт передачи прав основного владельца."""
    pet = self.pet
    old_main_owner = pet.main_owner  # Запоминаем

    pet.main_owner = user
    if user not in pet.owners.all():
        pet.owners.add(user)
    pet.save()

    # Назначаем UserType НОВОМУ
    user.add_role('pet_owner')

    # Условно снимаем у СТАРОГО (если он больше не владеет ни одним питомцем)
    if old_main_owner and old_main_owner.pk != user.pk:
        maybe_remove_role(old_main_owner, 'pet_owner')
```

---

## Что НЕ менять

- Модель `EmployeeProvider` и её роли — остаются как есть
- `ProviderLocation.manager` (FK на User) — остаётся как есть
- Модель `Employee`, `EmployeeLocationRole` — остаются как есть
- Модель `Pet` и `Pet.owners`, `Pet.main_owner` — остаются как есть
- Модель `UserType` и методы `User.add_role()`, `User.has_role()` — остаются как есть
- Бизнес-правила каждого accept handler — полностью сохранить текущую логику
- **Мастер регистрации провайдера** (`users/signals.py`, `create_provider_on_approval`, строки 145–612) — это **отдельный процесс**, НЕ связанный с инвайтами. Он назначает роли **напрямую** по email'ам из `ProviderForm` (owner_email, provider_manager_email, admin_email) без токенов и процесса приёма. UserType назначаются через `user.user_types.add()` в строке 443. Этот код **НЕ ТРОГАТЬ**.

---

## Важные правила из `.cursorrules`

1. Весь код на английском, комментарии и docstrings на русском
2. Все пользовательские сообщения на английском, обёрнуты в `_()`
3. `@transaction.atomic` для всех CRUD операций с критическими данными
4. `select_for_update()` при редактировании записей
5. DRF (Django REST Framework)
6. Логи для разработчика на английском, БЕЗ `_()`

---

## Файлы, которые нужно изменить/создать

### Создать:
- `PetsCare/invites/__init__.py`
- `PetsCare/invites/apps.py`
- `PetsCare/invites/models.py` — модель `Invite`
- `PetsCare/invites/serializers.py`
- `PetsCare/invites/api_views.py`
- `PetsCare/invites/urls.py`
- `PetsCare/invites/admin.py`
- `PetsCare/invites/services.py` — accept handlers + `maybe_remove_role()` утилита
- `PetsCare/invites/email.py` — отправка писем
- `PetsCare/invites/migrations/0001_initial.py` (через makemigrations)
- `PetsCare/invites/migrations/0002_migrate_data.py` (data migration)

### Изменить:
- `PetsCare/settings.py` — добавить `'invites'` в `INSTALLED_APPS`
- `PetsCare/urls.py` — подключить `invites.urls`
- `PetsCare/notifications/signals.py` — перевести сигналы на новую модель
- `PetsCare/notifications/tasks.py` — перевести tasks на новую модель

### Удалить (в конце, после проверки):
- Из `providers/models.py`: `ProviderOwnerManagerInvite`, `LocationManagerInvite`, `LocationStaffInvite`
- Из `providers/api_views.py`: `ProviderAdminInviteAPIView`, `AcceptProviderOwnerManagerInviteAPIView`, `AcceptLocationManagerInviteAPIView`, `InviteLocationStaffAPIView`, `LocationStaffInviteDestroyAPIView`, `AcceptLocationStaffInviteAPIView`, `_send_provider_owner_manager_invite_email`
- Из `providers/admin.py`: `ProviderOwnerManagerInviteAdmin`, `LocationManagerInviteAdmin`, `LocationStaffInviteAdmin`
- Из `providers/urls.py`: все invite-related URL patterns
- Из `users/models.py`: `RoleInvite` (строки 1273–1602)
- Из `users/serializers.py`: `RoleInviteSerializer`, `RoleInviteCreateSerializer`, `RoleInviteAcceptSerializer`, `RoleInviteDeclineSerializer`
- Из `users/api_views.py`: все `RoleInvite*` views
- Из `users/urls.py`: все `/role-invites/...` URL patterns
- Из `pets/models.py`: `PetOwnershipInvite`
- Из `pets/api_views.py`: `PetInviteAPIView`, `PetAcceptInviteAPIView`, `PetInviteQRCodeAPIView`
- Из `pets/urls.py`: все pet invite URL patterns
- Миграции удаления старых таблиц

---

## Порядок реализации (рекомендуемый)

1. **Создать приложение `invites`** с моделью, serializers, views, urls, admin, services
2. **Запустить `makemigrations invites` и `migrate`**
3. **Написать data migration** для переноса данных
4. **Переключить `notifications/signals.py` и `tasks.py`** на новую модель
5. **Подключить новые URL** в `urls.py`
6. **Протестировать** каждый тип инвайта:
   - Создание → email → ввод кода → приём
   - **Проверить**: правильный `UserType` назначен через `user.has_role()` после приёма каждого типа
   - **Проверить**: `EmployeeProvider` / `BillingManagerProvider` / `Pet.owners` созданы корректно
7. **Добавить обратную совместимость** старых URL (если нужно)
8. **Удалить** старые модели, views, serializers, admin, urls
9. **Запустить `makemigrations` и `migrate`** для удаления старых таблиц
