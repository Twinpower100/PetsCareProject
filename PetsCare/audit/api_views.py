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

from .models import AuditLog, UserActivity, SystemEvent
from .serializers import (
    AuditLogSerializer, UserActivitySerializer, 
    SystemEventSerializer, AuditStatisticsSerializer
)
from users.models import User

logger = logging.getLogger(__name__)


class AuditLogFilter(filters.FilterSet):
    """Фильтры для логов аудита."""
    user = filters.NumberFilter(field_name='user_id')
    action = filters.CharFilter(field_name='action')
    resource_type = filters.CharFilter(field_name='resource_type')
    resource_id = filters.NumberFilter(field_name='resource_id')
    created_after = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    ip_address = filters.CharFilter(field_name='ip_address')
    user_agent = filters.CharFilter(field_name='user_agent')

    class Meta:
        model = AuditLog
        fields = ['user', 'action', 'resource_type', 'resource_id', 'created_after', 'created_before', 'ip_address', 'user_agent']


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для работы с логами аудита.
    
    Предоставляет endpoints для:
    - Просмотра логов аудита
    - Фильтрации логов
    - Экспорта логов
    """
    serializer_class = AuditLogSerializer
    filterset_class = AuditLogFilter
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        """Возвращает queryset логов аудита."""
        return AuditLog.objects.select_related('user').order_by('-created_at')

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Получает статистику логов аудита."""
        try:
            # Общая статистика
            total_logs = AuditLog.objects.count()
            today_logs = AuditLog.objects.filter(
                created_at__date=timezone.now().date()
            ).count()
            
            # Статистика по действиям
            action_stats = AuditLog.objects.values('action').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            
            # Статистика по пользователям
            user_stats = AuditLog.objects.values('user__email').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            
            # Статистика по ресурсам
            resource_stats = AuditLog.objects.values('resource_type').annotate(
                count=Count('id')
            ).order_by('-count')
            
            return Response({
                'total_logs': total_logs,
                'today_logs': today_logs,
                'action_stats': list(action_stats),
                'user_stats': list(user_stats),
                'resource_stats': list(resource_stats)
            })
            
        except Exception as e:
            logger.error(f"Failed to get audit statistics: {e}")
            return Response(
                {'error': _('Failed to get audit statistics')},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def export(self, request):
        """Экспортирует логи аудита в CSV."""
        try:
            format_type = request.data.get('format', 'csv')
            filters = request.data.get('filters', {})
            
            # Применяем фильтры
            queryset = self.get_queryset()
            if filters:
                for key, value in filters.items():
                    if hasattr(AuditLog, key):
                        queryset = queryset.filter(**{key: value})
            
            if format_type == 'csv':
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = f'attachment; filename="audit_logs_{timezone.now().strftime("%Y%m%d")}.csv"'
                
                writer = csv.writer(response)
                writer.writerow(['ID', 'User', 'Action', 'Resource Type', 'Resource ID', 'IP Address', 'User Agent', 'Created At'])
                
                for log in queryset[:10000]:  # Ограничиваем экспорт
                    writer.writerow([
                        log.id,
                        log.user.email if log.user else 'Anonymous',
                        log.action,
                        log.resource_type,
                        log.resource_id,
                        log.ip_address,
                        log.user_agent,
                        log.created_at.isoformat()
                    ])
                
                return response
            else:
                return Response(
                    {'error': _('Unsupported export format')},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Failed to export audit logs: {e}")
            return Response(
                {'error': _('Failed to export audit logs')},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def cleanup(self, request):
        """Очищает старые логи аудита."""
        try:
            days_to_keep = request.data.get('days', 90)
            cutoff_date = timezone.now() - timedelta(days=days_to_keep)
            
            deleted_count = AuditLog.objects.filter(
                created_at__lt=cutoff_date
            ).delete()[0]
            
            return Response({
                'message': _('Audit logs cleaned up successfully'),
                'deleted_count': deleted_count,
                'cutoff_date': cutoff_date.isoformat()
            })
            
        except Exception as e:
            logger.error(f"Failed to cleanup audit logs: {e}")
            return Response(
                {'error': _('Failed to cleanup audit logs')},
                status=status.HTTP_400_BAD_REQUEST
            )


class UserActivityView(APIView):
    """API для просмотра активности пользователя."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, user_id):
        """Получает активность пользователя."""
        try:
            user = User.objects.get(id=user_id)
            
            # Получаем логи активности пользователя
            activity_logs = AuditLog.objects.filter(
                user=user
            ).order_by('-created_at')[:100]
            
            # Статистика активности
            activity_stats = AuditLog.objects.filter(
                user=user
            ).values('action').annotate(
                count=Count('id')
            ).order_by('-count')
            
            # Последние действия
            recent_actions = activity_logs[:10]
            
            return Response({
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'is_active': user.is_active
                },
                'activity_stats': list(activity_stats),
                'recent_actions': AuditLogSerializer(recent_actions, many=True).data,
                'total_actions': activity_logs.count()
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


class SystemEventsView(APIView):
    """API для просмотра системных событий."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        """Получает системные события."""
        try:
            # Получаем системные события
            events = SystemEvent.objects.order_by('-created_at')[:100]
            
            # Статистика событий
            event_stats = SystemEvent.objects.values('event_type').annotate(
                count=Count('id')
            ).order_by('-count')
            
            return Response({
                'events': SystemEventSerializer(events, many=True).data,
                'event_stats': list(event_stats)
            })
            
        except Exception as e:
            logger.error(f"Failed to get system events: {e}")
            return Response(
                {'error': _('Failed to get system events')},
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
            total_logs = AuditLog.objects.filter(
                created_at__gte=start_date
            ).count()
            
            # Статистика по дням
            daily_stats = AuditLog.objects.filter(
                created_at__gte=start_date
            ).extra(
                select={'day': 'date(created_at)'}
            ).values('day').annotate(
                count=Count('id')
            ).order_by('day')
            
            # Топ пользователей по активности
            top_users = AuditLog.objects.filter(
                created_at__gte=start_date
            ).values('user__email').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            
            # Топ действий
            top_actions = AuditLog.objects.filter(
                created_at__gte=start_date
            ).values('action').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            
            return Response({
                'period': {
                    'days': days,
                    'start_date': start_date.isoformat(),
                    'end_date': timezone.now().isoformat()
                },
                'total_logs': total_logs,
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