"""
Administrative interface for the users module.

Этот модуль содержит настройки административного интерфейса для:
1. Управления пользователями
2. Настройки отображения и фильтрации
3. Кастомизации действий администратора

Основные классы:
- UserAdmin: Административный интерфейс для модели User
- CustomAdminSite: Кастомный сайт администрирования с разграничением прав
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from django import forms
from .models import User, UserType, ProviderForm, ProviderFormDocument, ProviderAdmin  # noqa: F401
from custom_admin import custom_admin_site


def _is_system_admin(user):
    """
    Безопасная проверка, является ли пользователь системным администратором.
    Работает с AnonymousUser и реальными пользователями.
    """
    from django.contrib.auth.models import AnonymousUser
    if isinstance(user, AnonymousUser):
        return False
    if not hasattr(user, 'is_system_admin'):
        return False
    try:
        return user.is_system_admin()
    except (AttributeError, TypeError):
        return False


def _has_role(user, role_name):
    """
    Безопасная проверка роли пользователя.
    Работает с AnonymousUser и реальными пользователями.
    """
    from django.contrib.auth.models import AnonymousUser
    if isinstance(user, AnonymousUser):
        return False
    if not hasattr(user, 'has_role'):
        return False
    try:
        return user.has_role(role_name)
    except (AttributeError, TypeError):
        return False


class UserAdminForm(forms.ModelForm):
    """
    Кастомная форма для пользователей с улучшенной обработкой ролей.
    """
    class Meta:
        model = User
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Настраиваем queryset для ролей
        self.fields['user_types'].queryset = UserType.objects.filter(is_active=True).order_by('name')
        
        # Добавляем подсказку для новых пользователей
        if not self.instance.pk:
            self.fields['user_types'].help_text = _(
                'Select user roles. If no roles are selected, "basic_user" will be assigned automatically.'
            )
    
    def clean(self):
        cleaned_data = super().clean()
        user_types = cleaned_data.get('user_types')
        
        # Для новых пользователей без ролей, basic_user будет назначен автоматически
        if not self.instance.pk and not user_types:
            # Это нормально, basic_user будет назначен в save_model
            pass
        
        return cleaned_data


class ProviderAdminInline(admin.TabularInline):
    """
    Инлайн: управляемые организации пользователя и роли в них.
    Одна строка = одна роль у одной организации (owner / provider_manager / provider_admin).
    У одного пользователя может быть несколько строк с одним провайдером — разные роли.
    """
    model = ProviderAdmin
    fk_name = 'user'
    extra = 0
    autocomplete_fields = ['provider']
    fields = ('provider', 'role', 'is_active', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')
    verbose_name = _('Managed provider (role)')
    verbose_name_plural = _('Managed providers')


class CustomUserAdmin(UserAdmin):
    """
    Кастомная админка для модели User.
    """
    list_display = ('id', 'username', 'email', 'first_name', 'last_name', 'phone_number', 'get_user_roles', 'get_user_location_roles', 'is_active')
    inlines = [ProviderAdminInline]
    list_filter = ('user_types', 'is_active')
    search_fields = ('email', 'first_name', 'last_name', 'username', 'phone_number', 'user_types__name')
    ordering = ('email',)
    
    def get_user_roles(self, obj):
        """
        Возвращает список ролей пользователя для отображения в списке.
        
        Показывает:
        - Системные права (Superuser, Staff)
        - Назначенные роли (из user_types)
        - Активные роли (роли с данными) - помечаются звездочкой
        
        Args:
            obj: Объект User
            
        Returns:
            str: Строка с ролями пользователя, разделенными запятыми
        """
        roles_display = []
        
        # Системные права
        if obj.is_superuser:
            roles_display.append('Superuser')
        elif obj.is_staff:
            roles_display.append('Staff')
        
        # Функциональные роли (UserType)
        assigned_roles = [role.name for role in obj.user_types.all() if role.is_active]
        active_roles = obj.get_active_roles()
        
        # Роли, которые требуют данных для активации
        data_required_roles = ['pet_owner', 'provider_admin', 'pet_sitter']
        
        for role in assigned_roles:
            if role in data_required_roles:
                # Роли, требующие данных - показываем статус только если неактивна
                if role not in active_roles:
                    # Роль назначена, но не активна (нет данных)
                    roles_display.append(f'{role} (inactive)')
                else:
                    # Активная роль - просто название
                    roles_display.append(role)
            else:
                # Роли, не требующие данных - просто показываем название
                roles_display.append(role)
        
        if not roles_display:
            roles_display = ['No roles']
        
        return ', '.join(roles_display)
    get_user_roles.short_description = _('Roles')
    get_user_roles.admin_order_field = 'user_types__name'

    def get_user_location_roles(self, obj):
        """
        Роли уровня филиала: руководитель филиала (ProviderLocation.manager),
        сервисный работник / техработник (EmployeeLocationRole).
        """
        parts = []
        try:
            managed_locations = list(getattr(obj, 'managed_provider_locations', []))
            location_manager_ids = set()
            for loc in managed_locations:
                loc_name = getattr(loc, 'name', None) or '?'
                parts.append(f"{_('Location manager')} @ {loc_name}")
                location_manager_ids.add(getattr(loc, 'id', None))
            emp = getattr(obj, 'employee_profile', None)
            if emp:
                for lr in getattr(emp, 'location_roles', []):
                    loc = getattr(lr, 'provider_location', None)
                    loc_name = getattr(loc, 'name', None) or '?'
                    role_val = getattr(lr, 'role', None)
                    if role_val == 'location_manager' and loc and getattr(loc, 'id', None) in location_manager_ids:
                        continue
                    role_label = getattr(lr, 'get_role_display', lambda: role_val)()
                    parts.append(f'{role_label} @ {loc_name}')
        except Exception:
            pass
        return ', '.join(parts) if parts else '—'
    get_user_location_roles.short_description = _('Location level')

    def get_queryset(self, request):
        """
        Оптимизирует запросы для загрузки ролей пользователей и связанных данных.
        Использует prefetch_related для избежания N+1 запросов.
        """
        qs = super().get_queryset(request)
        return qs.prefetch_related(
            'user_types', 'pets', 'admin_providers__provider',
            'managed_provider_locations',
            'employee_profile__location_roles__provider_location',
        )
    
    fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'phone_number')}),
        (_('Permissions'), {'fields': ('user_types', 'is_active', 'is_staff', 'is_superuser')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'first_name', 'last_name', 'phone_number', 'password1', 'password2', 'user_types', 'is_active', 'is_staff', 'is_superuser'),
        }),
    )
    form = UserAdminForm
    
    actions = ['safe_delete_user', 'clear_user_roles']
    
    def get_actions(self, request):
        """
        Убираем стандартное действие удаления, оставляем только наше кастомное.
        """
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
    
    def safe_delete_user(self, request, queryset):
        """
        Безопасное удаление пользователей с предварительной очисткой связей.
        """
        deleted_count = 0
        for user in queryset:
            try:
                # Очищаем все роли пользователя
                user.user_types.clear()
                # Удаляем пользователя
                user.delete()
                deleted_count += 1
            except Exception as e:
                self.message_user(request, _('Error deleting user %(username)s: %(error)s') % {'username': user.username, 'error': str(e)}, level='ERROR')
        
        if deleted_count > 0:
            self.message_user(request, _('Successfully deleted %(count)d users.') % {'count': deleted_count}, level='SUCCESS')
    
    safe_delete_user.short_description = _("Safely delete selected users")
    
    def clear_user_roles(self, request, queryset):
        """
        Очистить все роли у выбранных пользователей.
        """
        cleared_count = 0
        for user in queryset:
            user.user_types.clear()
            cleared_count += 1
        
        self.message_user(request, _('Roles cleared for %(count)d users.') % {'count': cleared_count}, level='SUCCESS')
    
    clear_user_roles.short_description = _("Clear roles for selected users")
    
    def delete_model(self, request, obj):
        """
        Кастомное удаление отдельного пользователя с очисткой связей.
        """
        try:
            # Очищаем все роли пользователя
            obj.user_types.clear()
            # Удаляем пользователя
            obj.delete()
            self.message_user(request, _('User %(username)s successfully deleted.') % {'username': obj.username}, level='SUCCESS')
        except Exception as e:
            self.message_user(request, _('Error deleting user %(username)s: %(error)s') % {'username': obj.username, 'error': str(e)}, level='ERROR')

    def save_model(self, request, obj, form, change):
        """
        Переопределяем save_model для автоматического назначения роли basic_user.
        """
        # Сохраняем объект
        super().save_model(request, obj, form, change)
        
        # Для новых пользователей назначаем basic_user
        if not change:
            obj.refresh_from_db()
            if not obj.user_types.exists():
                basic_user_type = self._get_or_create_basic_user_type()
                if basic_user_type:
                    obj.user_types.add(basic_user_type)
                    self.message_user(
                        request, 
                        _('User has been automatically assigned the "basic_user" role.'), 
                        level='SUCCESS'
                    )
    
    
    def _get_or_create_basic_user_type(self):
        """
        Получает или создает роль basic_user.
        """
        try:
            return UserType.objects.get(name='basic_user')
        except UserType.DoesNotExist:
            # Создаем роль basic_user если её нет
            return UserType.objects.create(
                name='basic_user',
                name_en='Basic User',
                name_ru='Базовый пользователь',
                description='Basic user with minimal permissions',
                permissions=['view_own_profile', 'edit_own_profile'],
                is_active=True
            )

    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к модулю пользователей.
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            _is_system_admin(user) or
            user.is_billing_manager()
        )

class UserTypeAdmin(admin.ModelAdmin):
    """
    Админка для типов пользователей.
    """
    list_display = ('name', 'description', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'description', 'is_active')
        }),
        (_('Permissions'), {
            'fields': ('permissions',),
            'description': _('Select permissions for this role. You can choose from predefined sets or add custom permissions.')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Кастомизация полей формы"""
        if db_field.name == 'permissions':
            # Получаем все доступные разрешения
            from .permissions import PERMISSION_DESCRIPTIONS, ROLE_PERMISSION_SETS
            
            # Создаем выборы для предопределенных наборов
            choices = []
            
            # Добавляем предопределенные наборы
            for role_key, role_data in ROLE_PERMISSION_SETS.items():
                choices.append((
                    f"SET:{role_key}",
                    f"{role_data['name']} - {role_data['description']}"
                ))
            
            # Добавляем отдельные разрешения
            for perm, desc in PERMISSION_DESCRIPTIONS.items():
                choices.append((perm, f"{perm} - {desc}"))
            
            # Создаем поле с выбором
            from django import forms
            field = forms.MultipleChoiceField(
                choices=choices,
                widget=admin.widgets.FilteredSelectMultiple(
                    verbose_name=_('Permissions'),
                    is_stacked=False
                ),
                required=False
            )
            return field
            
        return super().formfield_for_dbfield(db_field, request, **kwargs)
    
    def get_permissions_display(self, obj):
        """Показывает разрешения с описаниями."""
        if not obj.permissions:
            return _('No permissions')
        
        from .permissions import get_permission_description
        descriptions = [get_permission_description(perm) for perm in obj.permissions[:5]]
        if len(obj.permissions) > 5:
            descriptions.append(f'... and {len(obj.permissions) - 5} more')
        return ', '.join(descriptions)
    get_permissions_display.short_description = _('Permissions')
    
    def save_model(self, request, obj, form, change):
        """Обработка сохранения модели"""
        # Обработка предопределенных наборов теперь в модели.clean()
        super().save_model(request, obj, form, change)
    
    class Media:
        js = ('admin/js/user_type_admin.js',)

    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к типам пользователей.
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return user.is_superuser or _is_system_admin(user)

class ProviderFormDocumentInline(admin.TabularInline):
    """Инлайн для отображения всех загруженных документов заявки."""
    model = ProviderFormDocument
    extra = 0
    readonly_fields = ('file',)
    can_delete = True


class ProviderFormAdmin(admin.ModelAdmin):
    """
    Админка для форм учреждений.
    """
    inlines = [ProviderFormDocumentInline]
    list_display = ('provider_name', 'status', 'get_created_by', 'created_at', 'get_selected_categories', 'has_documents')
    list_filter = ('status', 'selected_categories')
    search_fields = ('provider_name', 'provider_address', 'created_by__email', 'created_by__first_name', 'created_by__last_name')
    readonly_fields = ('created_at', 'updated_at', 'approved_at', 'approved_by', 'created_by')
    filter_horizontal = ('selected_categories',)
    actions = ['approve_and_assign_billing_manager', 'reset_to_pending']
    change_form_template = 'admin/users/providerform/change_form.html'
    
    def render_change_form(self, request, context, *args, **kwargs):
        """
        Переопределяем для добавления кастомного контекста.
        """
        return super().render_change_form(request, context, *args, **kwargs)
    
    def get_selected_categories(self, obj):
        """Возвращает список выбранных категорий для отображения в списке"""
        if obj.selected_categories.exists():
            return ', '.join([cat.name for cat in obj.selected_categories.all()])
        return _('No categories selected')
    get_selected_categories.short_description = _('Selected Categories')
    
    def get_created_by(self, obj):
        """Возвращает информацию об авторе заявки"""
        if obj.created_by:
            return f"{obj.created_by.email} ({obj.created_by.get_full_name() or obj.created_by.username})"
        return _('Unknown')
    get_created_by.short_description = _('Created By')
    get_created_by.admin_order_field = 'created_by__email'
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'provider_name',
                'provider_address',
                'provider_phone',
                'provider_email',
            )
        }),
        (_('Service Categories'), {
            'fields': (
                'selected_categories',
            ),
            'description': _('Select the service categories that this provider wants to offer')
        }),
        (_('Documents'), {
            'fields': (
                'documents',
            ),
            'description': _('Documents are required only if the institution provides services that require licensing or certification')
        }),
        (_('Status'), {
            'fields': (
                'status',
                'created_by',
                'created_at',
                'updated_at',
                'approved_at',
                'approved_by'
            ),
            'description': _('To approve a form, use the action "Approve and assign billing manager" from the list view. Direct status change to "approved" is not allowed.')
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        """
        Делает поле status доступным только для чтения, если статус pending.
        Одобрение возможно только через действие.
        Разрешаем изменение статуса обратно на pending для тестирования.
        """
        readonly = list(self.readonly_fields)
        if obj and obj.status == 'pending':
            # Если статус pending, запрещаем прямое изменение на approved
            readonly.append('status')
        # Если уже одобрено, разрешаем изменение обратно на pending для тестирования
        return readonly
    
    def get_form(self, request, obj=None, **kwargs):
        """
        Ограничивает queryset для selected_categories и блокирует прямое изменение статуса на approved.
        """
        from django import forms
        from catalog.models import Service
        
        form = super().get_form(request, obj, **kwargs)
        
        # Ограничиваем queryset только категориями уровня 0 (не услугами)
        if 'selected_categories' in form.base_fields:
            form.base_fields['selected_categories'].queryset = Service.objects.filter(
                level=0,
                parent__isnull=True
            ).order_by('hierarchy_order', 'name')
            form.base_fields['selected_categories'].help_text = _(
                'Select service categories (level 0 only). '
                'System administrator can add additional categories later if needed.'
            )
        
        # Блокируем прямое изменение статуса на approved
        if 'status' in form.base_fields:
            if obj and obj.status == 'pending':
                # Если статус pending, запрещаем изменение на approved
                original_choices = form.base_fields['status'].choices
                # Убираем 'approved' из выбора, если статус pending
                form.base_fields['status'].choices = [
                    choice for choice in original_choices 
                    if choice[0] != 'approved'
                ]
                form.base_fields['status'].help_text = _(
                    'To approve this form, use the action "Approve and assign billing manager" from the list view.'
                )
            elif obj and obj.status == 'approved':
                # Если уже одобрено, разрешаем изменение обратно на pending для тестирования
                # Ограничиваем выбор только на pending и rejected
                original_choices = form.base_fields['status'].choices
                form.base_fields['status'].choices = [
                    choice for choice in original_choices 
                    if choice[0] in ['pending', 'rejected', 'approved']
                ]
                form.base_fields['status'].help_text = _('You can change status back to pending for testing purposes.')
        
        return form
    
    def save_model(self, request, obj, form, change):
        """
        Переопределяем save_model для автоматического заполнения полей created_by, approved_by и approved_at.
        Запрещаем прямое изменение статуса на 'approved' - только через действие.
        """
        from django.contrib import messages
        from django.utils import timezone
        
        # Если это новая запись, устанавливаем created_by равным текущему пользователю
        if not change:
            obj.created_by = request.user
        
        # Запрещаем прямое изменение статуса на 'approved' через форму
        # Разрешаем изменение статуса обратно на 'pending' для тестирования
        if change:
            # Получаем старый объект из базы
            try:
                old_obj = self.model.objects.get(pk=obj.pk)
                # Если пытаются изменить статус с approved на pending - разрешаем
                if old_obj.status == 'approved' and obj.status == 'pending':
                    # Сбрасываем approved_by и approved_at
                    obj.approved_by = None
                    obj.approved_at = None
                elif old_obj.status != 'approved' and obj.status == 'approved':
                    # Пытаются изменить статус на approved напрямую
                    # Проверяем, не было ли это сделано через действие (есть _selected_billing_manager)
                    if not hasattr(obj, '_selected_billing_manager') or not obj._selected_billing_manager:
                        messages.error(
                            request,
                            _('Direct status change to "approved" is not allowed. Please use the action "Approve and assign billing manager" from the list view.')
                        )
                        # Возвращаем старый статус
                        obj.status = old_obj.status
                        return
            except self.model.DoesNotExist:
                pass  # Новый объект, пропускаем проверку
        
        # Если статус изменился на approved и approved_by не установлен (через действие)
        if change and obj.status == 'approved' and not obj.approved_by:
            obj.approved_by = request.user
            obj.approved_at = timezone.now()
        
        super().save_model(request, obj, form, change)
    
    def has_documents(self, obj):
        """Показывает, есть ли документы у заявки (основной или в списке загруженных)."""
        return bool(obj.documents) or (getattr(obj, 'registration_documents', None) and obj.registration_documents.exists())
    has_documents.boolean = True
    has_documents.short_description = _('Has Documents')

    def has_module_permission(self, request):
        """
        Проверяет, имеет ли пользователь доступ к формам учреждений.
        Биллинг-менеджер НЕ видит заявки - только системный админ.
        """
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_superuser or
            _is_system_admin(user)
        )
    
    def has_view_permission(self, request, obj=None):
        """Только системный админ может просматривать заявки"""
        return self.has_module_permission(request)
    
    def has_add_permission(self, request):
        """
        Запрещаем добавление заявок через админку.
        Заявки создаются только через форму на сайте.
        """
        return False
    
    def has_change_permission(self, request, obj=None):
        """Только системный админ может изменять заявки"""
        return self.has_module_permission(request)
    
    def has_delete_permission(self, request, obj=None):
        """
        Системный админ может удалять заявки.
        Это может быть полезно, если провайдер отправил форму дважды по ошибке.
        """
        return self.has_module_permission(request)
    
    def get_urls(self):
        """
        Добавляет кастомные URL для админки.
        """
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/approve/',
                self.admin_site.admin_view(self.approve_single_form),
                name='users_providerform_approve',
            ),
            path(
                '<path:object_id>/reject/',
                self.admin_site.admin_view(self.reject_single_form),
                name='users_providerform_reject',
            ),
        ]
        return custom_urls + urls
    
    def approve_single_form(self, request, object_id):
        """
        Одобряет одну заявку с назначением биллинг-менеджера.
        """
        from django.shortcuts import get_object_or_404, redirect
        from django.contrib import messages
        from django.utils import timezone
        from .models import UserType, User
        
        # Получаем заявку
        form_instance = get_object_or_404(ProviderForm, pk=object_id)
        
        # Проверяем права доступа
        if not (request.user.is_superuser or _is_system_admin(request.user)):
            messages.error(request, _('Only system administrators can approve provider forms.'))
            return redirect('custom_admin:users_providerform_change', object_id=object_id)
        
        # Проверяем, что заявка в статусе pending
        if form_instance.status != 'pending':
            messages.warning(request, _('This form is already %(status)s.') % {'status': form_instance.get_status_display()})
            return redirect('custom_admin:users_providerform_change', object_id=object_id)
        
        # Получаем список биллинг-менеджеров
        try:
            billing_manager_type = UserType.objects.get(name='billing_manager')
            billing_managers = User.objects.filter(user_types=billing_manager_type, is_active=True)
        except UserType.DoesNotExist:
            billing_managers = User.objects.none()
            messages.warning(request, _('No billing managers found. Please create billing_manager role first.'))
            return redirect('custom_admin:users_providerform_change', object_id=object_id)
        
        if request.method == 'POST':
            billing_manager_id = request.POST.get('billing_manager')
            if billing_manager_id:
                try:
                    # Проверяем существование и активность пользователя
                    billing_manager = User.objects.get(
                        pk=billing_manager_id,
                        user_types=billing_manager_type,
                        is_active=True
                    )
                    
                    # Дополнительная проверка - пользователь должен существовать в auth_user
                    if not billing_manager.pk:
                        messages.error(request, _('Selected billing manager is invalid.'))
                        return redirect('custom_admin:users_providerform_change', object_id=object_id)
                    
                    # Сохраняем выбранного биллинг-менеджера ПЕРЕД save()
                    form_instance._selected_billing_manager = billing_manager
                    
                    # Устанавливаем статус approved
                    form_instance.status = 'approved'
                    form_instance.approved_by = request.user
                    form_instance.approved_at = timezone.now()
                    form_instance.save()
                    
                    messages.success(
                        request,
                        _('Form approved successfully. Billing manager assigned.')
                    )
                    return redirect('custom_admin:users_providerform_changelist')
                except User.DoesNotExist:
                    messages.error(request, _('Selected billing manager not found.'))
            else:
                messages.error(request, _('Please select a billing manager.'))
        
        # Показываем форму выбора биллинг-менеджера
        from django import forms
        from django.shortcuts import render
        
        class BillingManagerForm(forms.Form):
            billing_manager = forms.ModelChoiceField(
                queryset=billing_managers,
                label=_('Billing Manager'),
                help_text=_('Select billing manager to assign to this provider'),
                required=True
            )
            
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # Настраиваем отображение: имя и фамилия, если есть, иначе email
                def format_billing_manager(obj):
                    name_parts = []
                    if obj.first_name:
                        name_parts.append(obj.first_name)
                    if obj.last_name:
                        name_parts.append(obj.last_name)
                    if name_parts:
                        return ' '.join(name_parts)
                    return obj.email
                
                self.fields['billing_manager'].label_from_instance = format_billing_manager
        
        form = BillingManagerForm()
        
        context = {
            **self.admin_site.each_context(request),
            'title': _('Approve and assign billing manager'),
            'form_instance': form_instance,
            'form': form,
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request, form_instance),
        }
        
        return render(request, 'admin/users/providerform/approve_single.html', context)
    
    def reject_single_form(self, request, object_id):
        """
        Отклоняет одну заявку.
        """
        from django.shortcuts import get_object_or_404, redirect
        from django.contrib import messages
        from django.utils import timezone
        
        # Получаем заявку
        form_instance = get_object_or_404(ProviderForm, pk=object_id)
        
        # Проверяем права доступа
        if not (request.user.is_superuser or _is_system_admin(request.user)):
            messages.error(request, _('Only system administrators can reject provider forms.'))
            return redirect('custom_admin:users_providerform_change', object_id=object_id)
        
        # Проверяем, что заявка в статусе pending
        if form_instance.status != 'pending':
            messages.warning(request, _('This form is already %(status)s.') % {'status': form_instance.get_status_display()})
            return redirect('custom_admin:users_providerform_change', object_id=object_id)
        
        if request.method == 'POST':
            # Отклоняем заявку
            form_instance.status = 'rejected'
            form_instance.approved_by = request.user
            form_instance.approved_at = timezone.now()
            form_instance.save()
            
            messages.success(request, _('Form rejected successfully.'))
            return redirect('custom_admin:users_providerform_changelist')
        
        # Показываем форму подтверждения отклонения
        from django.shortcuts import render
        
        context = {
            **self.admin_site.each_context(request),
            'title': _('Reject provider form'),
            'form_instance': form_instance,
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request, form_instance),
        }
        
        return render(request, 'admin/users/providerform/reject_single.html', context)
    
    def approve_and_assign_billing_manager(self, request, queryset):
        """
        Действие для одобрения заявок и назначения биллинг-менеджера.
        """
        from django import forms
        from django.contrib import messages
        from django.shortcuts import render
        from django.utils import timezone
        from .models import UserType, User
        
        # Проверяем права доступа
        if not (request.user.is_superuser or _is_system_admin(request.user)):
            messages.error(request, _('Only system administrators can approve provider forms.'))
            return
        
        # Получаем список биллинг-менеджеров
        try:
            billing_manager_type = UserType.objects.get(name='billing_manager')
            billing_managers = User.objects.filter(user_types=billing_manager_type, is_active=True)
        except UserType.DoesNotExist:
            billing_managers = User.objects.none()
            messages.warning(request, _('No billing managers found. Please create billing_manager role first.'))
        
        # Фильтруем только pending заявки
        pending_forms = queryset.filter(status='pending')
        
        if not pending_forms.exists():
            messages.warning(request, _('No pending forms selected.'))
            return
        
        # Форма для выбора биллинг-менеджера
        class BillingManagerForm(forms.Form):
            billing_manager = forms.ModelChoiceField(
                queryset=billing_managers,
                label=_('Billing Manager'),
                help_text=_('Select billing manager to assign to approved providers'),
                required=True
            )
            
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # Настраиваем отображение: имя и фамилия, если есть, иначе email
                self.fields['billing_manager'].label_from_instance = lambda obj: (
                    f"{obj.first_name} {obj.last_name}".strip() if (obj.first_name or obj.last_name) 
                    else obj.email
                )
        
        if 'apply' in request.POST:
            form = BillingManagerForm(request.POST)
            if form.is_valid():
                billing_manager = form.cleaned_data['billing_manager']
                approved_count = 0
                
                for form_instance in pending_forms:
                    if form_instance.status == 'pending':
                        # Сохраняем выбранного биллинг-менеджера в поле формы ПЕРЕД save()
                        # Это будет использовано в сигнале post_save
                        form_instance._selected_billing_manager = billing_manager
                        
                        # Устанавливаем статус approved
                        form_instance.status = 'approved'
                        form_instance.approved_by = request.user
                        form_instance.approved_at = timezone.now()
                        form_instance.save()
                        
                        approved_count += 1
                
                if approved_count > 0:
                    messages.success(
                        request,
                        _('Successfully approved %(count)d form(s) and assigned billing manager.') % {'count': approved_count}
                    )
                else:
                    messages.warning(request, _('No forms were approved.'))
                
                return None  # Редирект обратно в админку
        else:
            form = BillingManagerForm()
        
        # Используем стандартный контекст админки
        from django.contrib.admin.views.main import ChangeList
        from django.contrib.admin.options import IS_POPUP_VAR
        
        context = {
            **self.admin_site.each_context(request),
            'title': _('Approve and assign billing manager'),
            'forms': pending_forms,
            'form': form,
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
            'has_change_permission': self.has_change_permission(request),
            'has_add_permission': self.has_add_permission(request),
            'has_delete_permission': self.has_delete_permission(request),
            'is_popup': IS_POPUP_VAR in request.POST or IS_POPUP_VAR in request.GET,
        }
        
        return render(request, 'admin/users/providerform/approve_and_assign.html', context)
    
    approve_and_assign_billing_manager.short_description = _('Approve and assign billing manager')
    
    def reset_to_pending(self, request, queryset):
        """
        Действие для сброса статуса заявок обратно на pending для тестирования.
        """
        from django.contrib import messages
        
        # Проверяем права доступа
        if not (request.user.is_superuser or _is_system_admin(request.user)):
            messages.error(request, _('Only system administrators can reset provider forms.'))
            return
        
        # Фильтруем только approved или rejected заявки
        reset_forms = queryset.filter(status__in=['approved', 'rejected'])
        
        if not reset_forms.exists():
            messages.warning(request, _('No approved or rejected forms selected.'))
            return
        
        reset_count = 0
        for form_instance in reset_forms:
            form_instance.status = 'pending'
            form_instance.approved_by = None
            form_instance.approved_at = None
            form_instance.save()
            reset_count += 1
        
        if reset_count > 0:
            messages.success(
                request,
                _('Successfully reset %(count)d form(s) to pending status.') % {'count': reset_count}
            )
        else:
            messages.warning(request, _('No forms were reset.'))
    
    reset_to_pending.short_description = _('Reset to pending (for testing)')

class ProviderAdministratorAdmin(admin.ModelAdmin):
    """
    Админка для администраторов учреждений.
    """
    list_display = ('user', 'provider', 'is_active', 'created_at')
    list_filter = ('provider', 'is_active')
    search_fields = ('user__email', 'provider__name')
    readonly_fields = ('created_at', 'updated_at')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if (request.user.is_authenticated and 
            hasattr(request.user, 'has_role') and 
            _has_role(request.user, 'provider_admin')):
            return qs.filter(provider__in=request.user.get_managed_providers())
        return qs

    def has_add_permission(self, request):
        if not request.user.is_authenticated:
            return False
        return _has_role(request.user, 'system_admin')

    def has_change_permission(self, request, obj=None):
        if not request.user.is_authenticated:
            return False
        if not obj:
            return True
        if _has_role(request.user, 'provider_admin'):
            return request.user.get_managed_providers().filter(id=obj.provider.id).exists()
        return _has_role(request.user, 'system_admin')

    def has_delete_permission(self, request, obj=None):
        if not request.user.is_authenticated:
            return False
        return _has_role(request.user, 'system_admin')

    def has_module_permission(self, request):
        if not request.user.is_authenticated:
            return False
        return (hasattr(request.user, 'has_role') and 
                (_has_role(request.user, 'system_admin') or _has_role(request.user, 'provider_admin')))

custom_admin_site.register(User, CustomUserAdmin)
custom_admin_site.register(UserType, UserTypeAdmin)
custom_admin_site.register(ProviderForm, ProviderFormAdmin)
custom_admin_site.register(ProviderAdmin, ProviderAdministratorAdmin)
