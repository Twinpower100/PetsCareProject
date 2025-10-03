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

    def has_permission(self, request):
        """
        Проверяет права доступа пользователя к админке.
        Разрешает доступ для:
        - Активных пользователей
        - Сотрудников (is_staff)
        - Суперпользователей (is_superuser)
        - Менеджеров биллинга
        - Администраторов провайдеров
        - Системных администраторов
        """
        if not request.user.is_active:
            return False
            
        # Стандартные права Django
        if request.user.is_staff or request.user.is_superuser:
            return True
            
        # Кастомные права (если методы существуют)
        try:
            return (
                getattr(request.user, 'is_billing_manager', lambda: False)() or
                getattr(request.user, 'is_provider_admin', lambda: False)() or
                getattr(request.user, 'is_system_admin', lambda: False)()
            )
        except:
            return False

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