from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Count, Avg, Sum, Q
from datetime import timedelta, date
from .models import UserGrowth, UserActivity, UserConversion, UserMetrics

User = get_user_model()

class UserAnalyticsService:
    """Сервис для расчета аналитики пользователей"""
    
    @staticmethod
    def calculate_user_growth(period_type='daily', start_date=None, end_date=None):
        """Расчет роста пользователей за период"""
        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()
        
        # Получаем данные о регистрациях
        registrations = User.objects.filter(
            date_joined__date__range=[start_date, end_date]
        ).values('date_joined__date').annotate(
            count=Count('id')
        ).order_by('date_joined__date')
        
        # Группируем по типам пользователей
        owners = User.objects.filter(
            date_joined__date__range=[start_date, end_date],
            user_types__name='pet_owner'
        ).count()
        
        sitters = User.objects.filter(
            date_joined__date__range=[start_date, end_date],
            user_types__name='sitter'
        ).count()
        
        providers = User.objects.filter(
            date_joined__date__range=[start_date, end_date],
            user_types__name='provider_admin'
        ).count()
        
        # Общее количество новых пользователей
        new_users = owners + sitters + providers
        
        # Общее количество пользователей на конец периода
        total_users = User.objects.filter(date_joined__date__lte=end_date).count()
        
        # Темп роста
        previous_total = User.objects.filter(date_joined__date__lt=start_date).count()
        growth_rate = 0
        if previous_total > 0:
            growth_rate = round(((total_users - previous_total) / previous_total) * 100, 2)
        
        # Создаем или обновляем запись
        growth, created = UserGrowth.objects.get_or_create(
            period_type=period_type,
            period_start=start_date,
            defaults={
                'period_end': end_date,
                'new_registrations': new_users,
                'total_users': total_users,
                'growth_rate': growth_rate,
                'new_owners': owners,
                'new_sitters': sitters,
                'new_providers': providers,
            }
        )
        
        if not created:
            growth.period_end = end_date
            growth.new_registrations = new_users
            growth.total_users = total_users
            growth.growth_rate = growth_rate
            growth.new_owners = owners
            growth.new_sitters = sitters
            growth.new_providers = providers
            growth.save()
        
        return growth
    
    @staticmethod
    def track_user_activity(user, action_type='page_view', duration=0):
        """Отслеживание активности пользователя"""
        today = timezone.now().date()
        
        activity, created = UserActivity.objects.get_or_create(
            user=user,
            date=today,
            defaults={
                'login_count': 0,
                'session_duration': 0,
                'page_views': 0,
                'actions_count': 0,
                'searches_count': 0,
                'bookings_count': 0,
                'reviews_count': 0,
                'messages_count': 0,
                'first_activity': timezone.now(),
                'last_activity': timezone.now(),
            }
        )
        
        # Обновляем метрики в зависимости от типа действия
        if action_type == 'login':
            activity.login_count += 1
        elif action_type == 'page_view':
            activity.page_views += 1
        elif action_type == 'search':
            activity.searches_count += 1
        elif action_type == 'booking':
            activity.bookings_count += 1
        elif action_type == 'review':
            activity.reviews_count += 1
        elif action_type == 'message':
            activity.messages_count += 1
        
        # Обновляем общие метрики
        activity.actions_count += 1
        activity.session_duration += duration
        activity.last_activity = timezone.now()
        
        if created:
            activity.first_activity = timezone.now()
        
        activity.save()
        return activity
    
    @staticmethod
    def track_user_conversion(user, stage, source=''):
        """Отслеживание конверсии пользователя"""
        # Проверяем, не достиг ли пользователь уже этого этапа
        if UserConversion.objects.filter(user=user, stage=stage).exists():
            return None
        
        # Рассчитываем время до достижения этапа
        time_to_achieve = None
        if stage != 'registration':
            registration_time = user.date_joined
            time_to_achieve = int((timezone.now() - registration_time).total_seconds() / 3600)
        
        conversion = UserConversion.objects.create(
            user=user,
            stage=stage,
            time_to_achieve=time_to_achieve,
            source=source
        )
        
        return conversion
    
    @staticmethod
    def calculate_user_metrics(period_type='daily', start_date=None, end_date=None):
        """Расчет агрегированных метрик пользователей"""
        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()
        
        # Общие метрики
        total_users = User.objects.filter(date_joined__date__lte=end_date).count()
        new_users = User.objects.filter(date_joined__date__range=[start_date, end_date]).count()
        
        # Активные пользователи (были активны в последние 7 дней)
        active_threshold = timezone.now() - timedelta(days=7)
        active_users = UserActivity.objects.filter(
            last_activity__gte=active_threshold
        ).values('user').distinct().count()
        
        # Отток пользователей (неактивны более 30 дней)
        churn_threshold = timezone.now() - timedelta(days=30)
        churned_users = User.objects.filter(
            date_joined__date__lt=start_date,
            useractivity__last_activity__lt=churn_threshold
        ).distinct().count()
        
        # Метрики активности
        activity_stats = UserActivity.objects.filter(
            date__range=[start_date, end_date]
        ).aggregate(
            avg_session_duration=Avg('session_duration'),
            avg_page_views=Avg('page_views')
        )
        
        # Коэффициент удержания
        retention_rate = 0
        if total_users > 0:
            retention_rate = round((active_users / total_users) * 100, 2)
        
        # Метрики конверсии
        conversion_stats = UserConversion.objects.filter(
            achieved_at__date__range=[start_date, end_date]
        ).values('stage').annotate(count=Count('id'))
        
        # Детализация по типам пользователей
        owners_count = User.objects.filter(user_types__name='pet_owner').count()
        sitters_count = User.objects.filter(user_types__name='sitter').count()
        providers_count = User.objects.filter(user_types__name='provider_admin').count()
        
        # Создаем или обновляем запись
        metrics, created = UserMetrics.objects.get_or_create(
            period_type=period_type,
            period_start=start_date,
            defaults={
                'period_end': end_date,
                'total_users': total_users,
                'active_users': active_users,
                'new_users': new_users,
                'churned_users': churned_users,
                'avg_session_duration': activity_stats['avg_session_duration'] or 0,
                'avg_page_views': activity_stats['avg_page_views'] or 0,
                'retention_rate': retention_rate,
                'owners_count': owners_count,
                'sitters_count': sitters_count,
                'providers_count': providers_count,
            }
        )
        
        if not created:
            metrics.period_end = end_date
            metrics.total_users = total_users
            metrics.active_users = active_users
            metrics.new_users = new_users
            metrics.churned_users = churned_users
            metrics.avg_session_duration = activity_stats['avg_session_duration'] or 0
            metrics.avg_page_views = activity_stats['avg_page_views'] or 0
            metrics.retention_rate = retention_rate
            metrics.owners_count = owners_count
            metrics.sitters_count = sitters_count
            metrics.providers_count = providers_count
            metrics.save()
        
        return metrics


class ConversionTrackingService:
    """Сервис для отслеживания воронки конверсии"""
    
    @staticmethod
    def get_conversion_funnel(start_date=None, end_date=None):
        """Получение воронки конверсии"""
        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()
        
        funnel = {}
        stages = ['registration', 'profile_completion', 'first_search', 'first_view', 'first_booking', 'first_payment']
        
        for stage in stages:
            count = UserConversion.objects.filter(
                stage=stage,
                achieved_at__date__range=[start_date, end_date]
            ).count()
            funnel[stage] = count
        
        return funnel
    
    @staticmethod
    def get_conversion_rates(start_date=None, end_date=None):
        """Расчет коэффициентов конверсии между этапами"""
        funnel = ConversionTrackingService.get_conversion_funnel(start_date, end_date)
        
        rates = {}
        stages = ['registration', 'profile_completion', 'first_search', 'first_view', 'first_booking', 'first_payment']
        
        for i in range(len(stages) - 1):
            current_stage = stages[i]
            next_stage = stages[i + 1]
            
            current_count = funnel[current_stage]
            next_count = funnel[next_stage]
            
            if current_count > 0:
                rate = round((next_count / current_count) * 100, 2)
            else:
                rate = 0
            
            rates[f"{current_stage}_to_{next_stage}"] = rate
        
        return rates


class ActivityTrackingService:
    """Сервис для мониторинга активности пользователей"""
    
    @staticmethod
    def get_user_engagement_score(user, days=30):
        """Расчет показателя вовлеченности пользователя"""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        activities = UserActivity.objects.filter(
            user=user,
            date__range=[start_date, end_date]
        )
        
        if not activities.exists():
            return 0
        
        # Рассчитываем показатель вовлеченности
        total_actions = activities.aggregate(total=Sum('actions_count'))['total'] or 0
        total_sessions = activities.aggregate(total=Sum('login_count'))['total'] or 0
        avg_session_duration = activities.aggregate(avg=Avg('session_duration'))['avg'] or 0
        
        # Формула вовлеченности (можно настроить)
        engagement_score = (total_actions * 0.4) + (total_sessions * 0.3) + (avg_session_duration / 60 * 0.3)
        
        return round(engagement_score, 2)
    
    @staticmethod
    def get_most_active_users(days=7, limit=10):
        """Получение самых активных пользователей"""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        return UserActivity.objects.filter(
            date__range=[start_date, end_date]
        ).values('user__username', 'user__email').annotate(
            total_actions=Sum('actions_count'),
            total_sessions=Sum('login_count'),
            avg_session_duration=Avg('session_duration')
        ).order_by('-total_actions')[:limit]
    
    @staticmethod
    def get_inactive_users(days=30):
        """Получение неактивных пользователей"""
        threshold = timezone.now() - timedelta(days=days)
        
        return User.objects.filter(
            useractivity__last_activity__lt=threshold
        ).distinct()


# Создаем экземпляры сервисов для удобства использования
user_analytics_service = UserAnalyticsService()
conversion_tracking_service = ConversionTrackingService()
activity_tracking_service = ActivityTrackingService() 