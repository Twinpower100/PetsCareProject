"""
API views для системы аудита.

Этот модуль содержит API endpoints для:
1. Просмотра логов аудита
2. Экспорта логов
3. Аналитики активности пользователей
4. Системных событий
"""

import logging
from datetime import datetime, timedelta
from django.utils.translation import gettext as _
from django.utils import timezone
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters import rest_framework as filters
from django.db.models import Count, Q
from django.http import HttpResponse
import csv
import json

from .models import UserAction, SecurityAudit, AuditSettings
from .serializers import (
    UserActionSerializer, SecurityAuditSerializer, 
    AuditSettingsSerializer, AuditStatisticsSerializer
)
from users.models import User

logger = logging.getLogger(__name__)


class UserActionFilter(filters.FilterSet):
    """Фильтры для действий пользователей."""
    user = filters.NumberFilter(field_name='user_id')
    action_type = filters.CharFilter(field_name='action_type')
    content_type = filters.NumberFilter(field_name='content_type_id')
    object_id = filters.NumberFilter(field_name='object_id')
    created_after = filters.DateTimeFilter(field_name='timestamp', lookup_expr='gte')
    created_before = filters.DateTimeFilter(field_name='timestamp', lookup_expr='lte')
    ip_address = filters.CharFilter(field_name='ip_address')
    user_agent = filters.CharFilter(field_name='user_agent')
    http_method = filters.CharFilter(field_name='http_method')

    class Meta:
        model = UserAction
        fields = ['user', 'action_type', 'content_type', 'object_id', 'created_after', 'created_before', 'ip_address', 'user_agent', 'http_method']


class UserActionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для работы с действиями пользователей.
    
    Предоставляет endpoints для:
    - Просмотра действий пользователей
    - Фильтрации действий
    - Экспорта действий
    """
    serializer_class = UserActionSerializer
    filterset_class = UserActionFilter
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        """Возвращает queryset действий пользователей."""
        return UserAction.objects.select_related('user', 'content_type').order_by('-timestamp')

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Получает статистику действий пользователей."""
        try:
            # Общая статистика
            total_actions = UserAction.objects.count()
            today_actions = UserAction.objects.filter(
                timestamp__date=timezone.now().date()
            ).count()
            
            # Статистика по типам действий
            action_stats = UserAction.objects.values('action_type').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            
            # Статистика по пользователям
            user_stats = UserAction.objects.values('user__email').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            
            # Статистика по типам контента
            content_stats = UserAction.objects.values('content_type__model').annotate(
                count=Count('id')
            ).order_by('-count')
            
            return Response({
                'total_actions': total_actions,
                'today_actions': today_actions,
                'action_stats': list(action_stats),
                'user_stats': list(user_stats),
                'content_stats': list(content_stats)
            })
            
        except Exception as e:
            logger.error(f"Failed to get audit statistics: {e}")
            return Response(
                {'error': _('Failed to get audit statistics')},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def export(self, request):
        """Экспортирует действия пользователей в CSV."""
        try:
            format_type = request.data.get('format', 'csv')
            filters = request.data.get('filters', {})
            
            # Применяем фильтры
            queryset = self.get_queryset()
            if filters:
                for key, value in filters.items():
                    if hasattr(UserAction, key):
                        queryset = queryset.filter(**{key: value})
            
            if format_type == 'csv':
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = f'attachment; filename="user_actions_{timezone.now().strftime("%Y%m%d")}.csv"'
                
                writer = csv.writer(response)
                writer.writerow(['ID', 'User', 'Action Type', 'Content Type', 'Object ID', 'IP Address', 'User Agent', 'HTTP Method', 'URL', 'Timestamp'])
                
                for action in queryset[:10000]:  # Ограничиваем экспорт
                    writer.writerow([
                        action.id,
                        action.user.email if action.user else 'Anonymous',
                        action.action_type,
                        action.content_type.model if action.content_type else '',
                        action.object_id,
                        action.ip_address,
                        action.user_agent,
                        action.http_method,
                        action.url,
                        action.timestamp.isoformat()
                    ])
                
                return response
            else:
                return Response(
                    {'error': _('Unsupported export format')},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Failed to export user actions: {e}")
            return Response(
                {'error': _('Failed to export user actions')},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def cleanup(self, request):
        """Очищает старые действия пользователей."""
        try:
            days_to_keep = request.data.get('days', 90)
            cutoff_date = timezone.now() - timedelta(days=days_to_keep)
            
            deleted_count = UserAction.objects.filter(
                timestamp__lt=cutoff_date
            ).delete()[0]
            
            return Response({
                'message': _('User actions cleaned up successfully'),
                'deleted_count': deleted_count,
                'cutoff_date': cutoff_date.isoformat()
            })
            
        except Exception as e:
            logger.error(f"Failed to cleanup user actions: {e}")
            return Response(
                {'error': _('Failed to cleanup user actions')},
                status=status.HTTP_400_BAD_REQUEST
            )


class UserActivityView(APIView):
    """API для просмотра активности пользователя."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, user_id):
        """Получает активность пользователя."""
        try:
            user = User.objects.get(id=user_id)
            
            # Получаем действия пользователя
            user_actions = UserAction.objects.filter(
                user=user
            ).order_by('-timestamp')[:100]
            
            # Статистика активности
            activity_stats = UserAction.objects.filter(
                user=user
            ).values('action_type').annotate(
                count=Count('id')
            ).order_by('-count')
            
            # Последние действия
            recent_actions = user_actions[:10]
            
            return Response({
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'is_active': user.is_active
                },
                'activity_stats': list(activity_stats),
                'recent_actions': UserActionSerializer(recent_actions, many=True).data,
                'total_actions': user_actions.count()
            })
            
        except User.DoesNotExist:
            return Response(
                {'error': _('User not found')},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Failed to get user activity: {e}")
            return Response(
                {'error': _('Failed to get user activity')},
                status=status.HTTP_400_BAD_REQUEST
            )


class SecurityAuditView(APIView):
    """API для просмотра аудита безопасности."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        """Получает записи аудита безопасности."""
        try:
            # Получаем записи аудита безопасности
            security_audits = SecurityAudit.objects.order_by('-timestamp')[:100]
            
            # Статистика аудита
            audit_stats = SecurityAudit.objects.values('audit_type').annotate(
                count=Count('id')
            ).order_by('-count')
            
            return Response({
                'security_audits': SecurityAuditSerializer(security_audits, many=True).data,
                'audit_stats': list(audit_stats)
            })
            
        except Exception as e:
            logger.error(f"Failed to get security audit: {e}")
            return Response(
                {'error': _('Failed to get security audit')},
                status=status.HTTP_400_BAD_REQUEST
            )


class AuditStatisticsView(APIView):
    """API для получения статистики аудита."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        """Получает статистику аудита."""
        try:
            # Параметры фильтрации
            days = int(request.GET.get('days', 30))
            start_date = timezone.now() - timedelta(days=days)
            
            # Общая статистика
            total_actions = UserAction.objects.filter(
                timestamp__gte=start_date
            ).count()
            
            # Статистика по дням
            daily_stats = UserAction.objects.filter(
                timestamp__gte=start_date
            ).extra(
                select={'day': 'date(timestamp)'}
            ).values('day').annotate(
                count=Count('id')
            ).order_by('day')
            
            # Топ пользователей по активности
            top_users = UserAction.objects.filter(
                timestamp__gte=start_date
            ).values('user__email').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            
            # Топ действий
            top_actions = UserAction.objects.filter(
                timestamp__gte=start_date
            ).values('action_type').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            
            return Response({
                'period': {
                    'days': days,
                    'start_date': start_date.isoformat(),
                    'end_date': timezone.now().isoformat()
                },
                'total_actions': total_actions,
                'daily_stats': list(daily_stats),
                'top_users': list(top_users),
                'top_actions': list(top_actions)
            })
            
        except Exception as e:
            logger.error(f"Failed to get audit statistics: {e}")
            return Response(
                {'error': _('Failed to get audit statistics')},
                status=status.HTTP_400_BAD_REQUEST
            ) 