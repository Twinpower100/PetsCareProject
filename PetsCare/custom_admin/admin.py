from django.contrib.admin import AdminSite
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render

class CustomAdminSite(AdminSite):
    """
    Кастомный админ-сайт для проекта PetsCare.
    Расширяет стандартный AdminSite для добавления дополнительных прав доступа.
    """
    site_header = _("Django Administration")
    site_title = _("PetsCare Admin")
    index_title = _("Welcome to PetsCare Admin")

    def has_permission(self, request):
        """
        Проверяет права доступа пользователя к админке.
        Разрешает доступ для:
        - Активных пользователей
        - Сотрудников (is_staff)
        - Менеджеров биллинга
        - Администраторов провайдеров
        - Системных администраторов
        """
        return (
            request.user.is_active and
            (request.user.is_staff or
             request.user.is_billing_manager() or
             request.user.is_provider_admin() or
             request.user.is_system_admin())
        )

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

# Создаем экземпляр кастомного админ-сайта
custom_admin_site = CustomAdminSite(name='custom_admin')

def register_admin_models():
    """
    Регистрирует стандартные модели админки.
    """
    from django.contrib.auth.models import User, Group
    from django.contrib.admin.models import LogEntry
    from django.contrib.auth.admin import UserAdmin, GroupAdmin
    
    custom_admin_site.register(User, UserAdmin)
    custom_admin_site.register(Group, GroupAdmin)
    custom_admin_site.register(LogEntry) 