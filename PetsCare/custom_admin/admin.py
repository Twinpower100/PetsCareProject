from django.contrib.admin import AdminSite
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render

class CustomAdminSite(AdminSite):
    """
    Кастомный админ-сайт для проекта PetsCare.
    Расширяет стандартный AdminSite для добавления дополнительных прав доступа.
    """
    site_header = _("PetsCare Administration")
    site_title = _("PetsCare Admin")
    index_title = _("Welcome to PetsCare Admin - Custom User & Role Management")

    def _is_system_admin(self, user):
        """Проверка системного администратора (поддержка/админы проекта). Доступ в Django admin только у них и суперпользователей."""
        from django.contrib.auth.models import AnonymousUser
        if isinstance(user, AnonymousUser):
            return False
        try:
            return getattr(user, 'is_system_admin', None) and callable(user.is_system_admin) and user.is_system_admin()
        except (AttributeError, TypeError):
            return False

    def has_permission(self, request):
        """
        Проверяет права доступа к админке Django (MVP: только персонал проекта).
        Доступ только у is_superuser или system_admin (поддержка и админы проекта).
        Биллинг-менеджеры, администраторы и персонал провайдеров в Django admin не входят.
        """
        from django.contrib.auth.models import AnonymousUser
        if isinstance(request.user, AnonymousUser):
            return False
        try:
            if not request.user.is_authenticated or not request.user.is_active:
                return False
        except (AttributeError, TypeError):
            return False
        try:
            if request.user.is_superuser:
                return True
        except (AttributeError, TypeError):
            pass
        if self._is_system_admin(request.user):
            return True
        return False
    
    def has_module_permission(self, request):
        """
        Доступ к модулям только у is_superuser или system_admin.
        Биллинг-менеджеры, админы и персонал провайдеров не входят.
        """
        return self.has_permission(request)

    def get_urls(self):
        """
        Добавляет URL-паттерны админки.
        """
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('reports/dashboard/', self.admin_view(self.reports_dashboard), name='reports-dashboard'),
        ]
        return custom_urls + urls

    def reports_dashboard(self, request):
        """
        Представление для дашборда отчетов.
        """
        context = dict(
            self.each_context(request),
            title=_('Reports Dashboard'),
        )
        return render(request, 'admin/reports/dashboard.html', context)
    
    def index(self, request, extra_context=None):
        """
        Переопределяем главную страницу админки для добавления информации о кастомной системе.
        """
        extra_context = extra_context or {}
        extra_context.update({
            'custom_system_info': _(
                'This admin uses custom User and Role management system. '
                'Use "User Types" instead of "Groups" and "Users" for role management.'
            )
        })
        return super().index(request, extra_context)

# Создаем экземпляр кастомного админ-сайта
custom_admin_site = CustomAdminSite(name='custom_admin')

def register_admin_models():
    """
    Регистрирует стандартные модели админки.
    """
    from django.contrib.admin.models import LogEntry

    # Регистрируем только LogEntry для аудита
    # User и Group скрыты, так как используем кастомные UserType и User
    custom_admin_site.register(LogEntry)

    # Глобальный производственный календарь (Level 1) — регистрация здесь гарантирует появление в админке
    from production_calendar.models import ProductionCalendar
    from production_calendar.admin import ProductionCalendarAdmin
    custom_admin_site.register(ProductionCalendar, ProductionCalendarAdmin) 