from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SchedulingConfig(AppConfig):
    """
    Конфигурация приложения для системы автоматического планирования расписания.
    
    Основные функции:
    - Управление рабочими местами учреждений
    - Автоматическое планирование расписаний сотрудников
    - Управление отсутствиями (отпуска, больничные, отгулы)
    - Настройка потребности в специалистах
    - Приоритизация услуг при планировании
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scheduling'
    verbose_name = _('Scheduling')

    def ready(self):
        """
        Инициализация приложения при запуске.
        
        Примечание:
        Здесь можно добавить импорт сигналов или другие
        операции инициализации при необходимости.
        """
        pass 