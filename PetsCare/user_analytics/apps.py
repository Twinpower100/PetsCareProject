from django.apps import AppConfig


class UserAnalyticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user_analytics'
    verbose_name = 'Аналитика пользователей'
    
    def ready(self):
        """Импортируем сигналы при запуске приложения"""
        import user_analytics.signals
