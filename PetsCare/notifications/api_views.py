"""
API views для работы с уведомлениями.

Этот модуль содержит API endpoints для:
1. Получения списка уведомлений пользователя
2. Отметки уведомлений как прочитанных
3. Управления настройками уведомлений
4. Отправки тестовых уведомлений
"""

import logging
from typing import Dict, Any
from django.utils.translation import gettext as _
from django.db import transaction
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters import rest_framework as filters
from .models import Notification, NotificationPreference, UserNotificationSettings, NotificationTemplate
from .serializers import (
    NotificationSerializer,
    NotificationPreferenceSerializer,
    UserNotificationSettingsSerializer,
    NotificationListSerializer,
    NotificationTemplateSerializer
)
from .services import NotificationService, PreferenceService
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Count

logger = logging.getLogger(__name__)


class NotificationPagination(PageNumberPagination):
    """
    Пагинация для списка уведомлений.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class NotificationFilter(filters.FilterSet):
    """
    Фильтры для уведомлений.
    """
    notification_type = filters.CharFilter(field_name='notification_type')
    is_read = filters.BooleanFilter(field_name='is_read')
    priority = filters.CharFilter(field_name='priority')
    created_after = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = Notification
        fields = ['notification_type', 'is_read', 'priority', 'created_after', 'created_before']


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для работы с уведомлениями пользователя.
    
    Предоставляет endpoints для:
    - Получения списка уведомлений
    - Отметки уведомлений как прочитанных
    - Получения статистики уведомлений
    """
    serializer_class = NotificationSerializer
    pagination_class = NotificationPagination
    filterset_class = NotificationFilter
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Возвращает queryset уведомлений текущего пользователя.
        
        Returns:
            QuerySet: Уведомления пользователя
        """
        return Notification.objects.filter(user=self.request.user)

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """
        Получает количество непрочитанных уведомлений.
        
        Returns:
            Response: Количество непрочитанных уведомлений
        """
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread_count': count})

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """
        Отмечает уведомление как прочитанное.
        
        Args:
            request: HTTP запрос
            pk: ID уведомления
            
        Returns:
            Response: Результат операции
        """
        try:
            notification = self.get_object()
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save()
            
            return Response({
                'message': _('Notification marked as read'),
                'notification_id': notification.id
            })
            
        except Exception as e:
            logger.error(f"Failed to mark notification {pk} as read: {e}")
            return Response(
                {'error': _('Failed to mark notification as read')},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """
        Отмечает все уведомления пользователя как прочитанные.
        
        Args:
            request: HTTP запрос
            
        Returns:
            Response: Результат операции
        """
        try:
            with transaction.atomic():
                updated_count = self.get_queryset().filter(is_read=False).update(is_read=True, read_at=timezone.now())
                
                return Response({
                    'message': _('All notifications marked as read'),
                    'updated_count': updated_count
                })
                
        except Exception as e:
            logger.error(f"Failed to mark all notifications as read for user {request.user.id}: {e}")
            return Response(
                {'error': _('Failed to mark all notifications as read')},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Получает статистику уведомлений пользователя.
        
        Args:
            request: HTTP запрос
            
        Returns:
            Response: Статистика уведомлений
        """
        try:
            queryset = self.get_queryset()
            
            # Общая статистика
            total_count = queryset.count()
            unread_count = queryset.filter(is_read=False).count()
            read_count = total_count - unread_count
            
            # Статистика по типам
            type_stats = {}
            for notification_type, _ in Notification.NOTIFICATION_TYPES:
                count = queryset.filter(notification_type=notification_type).count()
                if count > 0:
                    type_stats[notification_type] = count
            
            # Статистика по приоритетам
            priority_stats = {}
            for priority, _ in Notification.PRIORITY_CHOICES:
                count = queryset.filter(priority=priority).count()
                if count > 0:
                    priority_stats[priority] = count
            
            return Response({
                'total_count': total_count,
                'unread_count': unread_count,
                'read_count': read_count,
                'type_stats': type_stats,
                'priority_stats': priority_stats
            })
            
        except Exception as e:
            logger.error(f"Failed to get notification statistics for user {request.user.id}: {e}")
            return Response(
                {'error': _('Failed to get notification statistics')},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def test_notification(self, request):
        """
        Отправляет тестовое уведомление пользователю.
        
        Args:
            request: HTTP запрос
            
        Returns:
            Response: Результат отправки
        """
        try:
            notification_service = NotificationService()
            
            notification = notification_service.send_notification(
                user=request.user,
                notification_type='system',
                title=_('Test Notification'),
                message=_('This is a test notification'),
                channels=['email', 'push', 'in_app'],
                priority='low',
                data={'test': True}
            )
            
            return Response({
                'message': _('Test notification sent successfully'),
                'notification_id': notification.id
            })
            
        except Exception as e:
            logger.error(f"Failed to send test notification to user {request.user.id}: {e}")
            return Response(
                {'error': _('Failed to send test notification')},
                status=status.HTTP_400_BAD_REQUEST
            )


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления настройками уведомлений пользователя.
    
    Предоставляет endpoints для:
    - Получения настроек уведомлений
    - Обновления настроек уведомлений
    - Сброса настроек к значениям по умолчанию
    """
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Возвращает queryset настроек текущего пользователя.
        
        Returns:
            QuerySet: Настройки пользователя
        """
        return NotificationPreference.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        """
        Создает новую настройку уведомлений.
        
        Args:
            serializer: Сериализатор с данными
        """
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def all_preferences(self, request):
        """
        Получает все настройки уведомлений пользователя.
        
        Args:
            request: HTTP запрос
            
        Returns:
            Response: Все настройки пользователя
        """
        try:
            preference_service = PreferenceService()
            preferences = preference_service.get_user_preferences(request.user)
            
            return Response(preferences)
            
        except Exception as e:
            logger.error(f"Failed to get all preferences for user {request.user.id}: {e}")
            return Response(
                {'error': _('Failed to get preferences')},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def reset_to_defaults(self, request):
        """
        Сбрасывает настройки уведомлений к значениям по умолчанию.
        
        Args:
            request: HTTP запрос
            
        Returns:
            Response: Результат сброса
        """
        try:
            with transaction.atomic():
                # Удаляем текущие настройки
                self.get_queryset().delete()
                
                # Создаем настройки по умолчанию
                preference_service = PreferenceService()
                preference_service.create_default_preferences(request.user)
                
                return Response({
                    'message': _('Preferences reset to defaults successfully')
                })
                
        except Exception as e:
            logger.error(f"Failed to reset preferences for user {request.user.id}: {e}")
            return Response(
                {'error': _('Failed to reset preferences')},
                status=status.HTTP_400_BAD_REQUEST
            )


class UserNotificationSettingsViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления детальными настройками уведомлений пользователя.
    
    Предоставляет endpoints для:
    - Получения детальных настроек
    - Обновления детальных настроек
    - Массового обновления настроек
    """
    serializer_class = UserNotificationSettingsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Возвращает queryset детальных настроек текущего пользователя.
        
        Returns:
            QuerySet: Детальные настройки пользователя
        """
        return UserNotificationSettings.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        """
        Создает новую детальную настройку уведомлений.
        
        Args:
            serializer: Сериализатор с данными
        """
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['post'])
    def bulk_update(self, request):
        """
        Массово обновляет настройки уведомлений.
        
        Args:
            request: HTTP запрос с данными для обновления
            
        Returns:
            Response: Результат массового обновления
        """
        try:
            settings_data = request.data.get('settings', [])
            updated_count = 0
            
            with transaction.atomic():
                for setting_data in settings_data:
                    event_type = setting_data.get('event_type')
                    channel = setting_data.get('channel')
                    notification_time = setting_data.get('notification_time')
                    is_enabled = setting_data.get('is_enabled', True)
                    
                    if all([event_type, channel, notification_time]):
                        setting, created = UserNotificationSettings.objects.get_or_create(
                            user=request.user,
                            event_type=event_type,
                            channel=channel,
                            notification_time=notification_time,
                            defaults={'is_enabled': is_enabled}
                        )
                        
                        if not created:
                            setting.is_enabled = is_enabled
                            setting.save()
                        
                        updated_count += 1
            
            return Response({
                'message': _('Settings updated successfully'),
                'updated_count': updated_count
            })
            
        except Exception as e:
            logger.error(f"Failed to bulk update settings for user {request.user.id}: {e}")
            return Response(
                {'error': _('Failed to update settings')},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def available_options(self, request):
        """
        Получает доступные опции для настроек уведомлений.
        
        Args:
            request: HTTP запрос
            
        Returns:
            Response: Доступные опции
        """
        return Response({
            'event_types': dict(UserNotificationSettings.NOTIFICATION_EVENTS),
            'channels': dict(UserNotificationSettings.NOTIFICATION_CHANNELS),
            'notification_times': dict(UserNotificationSettings.NOTIFICATION_TIMES)
        })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_notification_as_read(request, notification_id):
    """
    Отмечает уведомление как прочитанное.
    
    Args:
        request: HTTP запрос
        notification_id: ID уведомления
    
    Returns:
        JSON ответ с результатом операции
    """
    try:
        notification = Notification.objects.get(
            id=notification_id,
            user=request.user
        )
        
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        
        return Response({
            'success': True,
            'message': _('Notification marked as read')
        })
        
    except Notification.DoesNotExist:
        return Response({
            'success': False,
            'message': _('Notification not found')
        }, status=404)
    except Exception as e:
        logger.error(f"Failed to mark notification {notification_id} as read: {e}")
        return Response({
            'success': False,
            'message': _('Failed to mark notification as read')
        }, status=500)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_all_notifications_as_read(request):
    """
    Отмечает все уведомления пользователя как прочитанные.
    
    Args:
        request: HTTP запрос
    
    Returns:
        JSON ответ с результатом операции
    """
    try:
        updated_count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).update(
            is_read=True,
            read_at=timezone.now()
        )
        
        return Response({
            'success': True,
            'message': _('All notifications marked as read'),
            'updated_count': updated_count
        })
        
    except Exception as e:
        logger.error(f"Failed to mark all notifications as read for user {request.user.id}: {e}")
        return Response({
            'success': False,
            'message': _('Failed to mark notifications as read')
        }, status=500)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_notification(request, notification_id):
    """
    Удаляет уведомление.
    
    Args:
        request: HTTP запрос
        notification_id: ID уведомления
    
    Returns:
        JSON ответ с результатом операции
    """
    try:
        notification = Notification.objects.get(
            id=notification_id,
            user=request.user
        )
        
        notification.delete()
        
        return Response({
            'success': True,
            'message': _('Notification deleted')
        })
        
    except Notification.DoesNotExist:
        return Response({
            'success': False,
            'message': _('Notification not found')
        }, status=404)
    except Exception as e:
        logger.error(f"Failed to delete notification {notification_id}: {e}")
        return Response({
            'success': False,
            'message': _('Failed to delete notification')
        }, status=500)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_all_notifications(request):
    """
    Удаляет все уведомления пользователя.
    
    Args:
        request: HTTP запрос
    
    Returns:
        JSON ответ с результатом операции
    """
    try:
        deleted_count = Notification.objects.filter(user=request.user).count()
        Notification.objects.filter(user=request.user).delete()
        
        return Response({
            'success': True,
            'message': _('All notifications deleted'),
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        logger.error(f"Failed to delete all notifications for user {request.user.id}: {e}")
        return Response({
            'success': False,
            'message': _('Failed to delete notifications')
        }, status=500)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_notification_stats(request):
    """
    Получает статистику уведомлений пользователя.
    
    Args:
        request: HTTP запрос
    
    Returns:
        JSON ответ со статистикой
    """
    try:
        total_notifications = Notification.objects.filter(user=request.user).count()
        unread_notifications = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()
        
        # Статистика по типам уведомлений
        notification_types = Notification.objects.filter(
            user=request.user
        ).values('notification_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Статистика по каналам
        channel_stats = {}
        for channel in ['email', 'push', 'in_app']:
            channel_stats[channel] = Notification.objects.filter(
                user=request.user,
                channels__contains=channel
            ).count()
        
        return Response({
            'success': True,
            'stats': {
                'total': total_notifications,
                'unread': unread_notifications,
                'read': total_notifications - unread_notifications,
                'types': list(notification_types),
                'channels': channel_stats
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get notification stats for user {request.user.id}: {e}")
        return Response({
            'success': False,
            'message': _('Failed to get notification statistics')
        }, status=500)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_notification_preferences(request):
    """
    Обновляет настройки уведомлений пользователя.
    
    Args:
        request: HTTP запрос
    
    Returns:
        JSON ответ с результатом операции
    """
    try:
        serializer = NotificationPreferenceSerializer(
            instance=request.user.notification_preferences,
            data=request.data,
            partial=True
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': _('Notification preferences updated'),
                'preferences': serializer.data
            })
        else:
            return Response({
                'success': False,
                'message': _('Invalid data'),
                'errors': serializer.errors
            }, status=400)
            
    except Exception as e:
        logger.error(f"Failed to update notification preferences for user {request.user.id}: {e}")
        return Response({
            'success': False,
            'message': _('Failed to update notification preferences')
        }, status=500)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_notification_templates(request):
    """
    Получает список шаблонов уведомлений.
    
    Args:
        request: HTTP запрос
    
    Returns:
        JSON ответ со списком шаблонов
    """
    try:
        templates = NotificationTemplate.objects.filter(is_active=True)
        serializer = NotificationTemplateSerializer(templates, many=True)
        
        return Response({
            'success': True,
            'templates': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Failed to get notification templates: {e}")
        return Response({
            'success': False,
            'message': _('Failed to get notification templates')
        }, status=500)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def test_notification(request):
    """
    Отправляет тестовое уведомление пользователю.
    
    Args:
        request: HTTP запрос
    
    Returns:
        JSON ответ с результатом операции
    """
    try:
        notification_service = NotificationService()
        
        notification = notification_service.send_notification(
            user=request.user,
            notification_type='system',
            title=_('Test Notification'),
            message=_('This is a test notification to verify your settings.'),
            channels=['email', 'push', 'in_app'],
            priority='low'
        )
        
        return Response({
            'success': True,
            'message': _('Test notification sent'),
            'notification_id': notification.id
        })
        
    except Exception as e:
        logger.error(f"Failed to send test notification to user {request.user.id}: {e}")
        return Response({
            'success': False,
            'message': _('Failed to send test notification')
        }, status=500)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_notification_history(request):
    """
    Получает историю уведомлений пользователя с фильтрацией.
    
    Args:
        request: HTTP запрос
    
    Returns:
        JSON ответ с историей уведомлений
    """
    try:
        # Параметры фильтрации
        notification_type = request.GET.get('type')
        is_read = request.GET.get('read')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        # Базовый queryset
        notifications = Notification.objects.filter(user=request.user)
        
        # Применяем фильтры
        if notification_type:
            notifications = notifications.filter(notification_type=notification_type)
        
        if is_read is not None:
            is_read_bool = is_read.lower() == 'true'
            notifications = notifications.filter(is_read=is_read_bool)
        
        if start_date:
            notifications = notifications.filter(created_at__gte=start_date)
        
        if end_date:
            notifications = notifications.filter(created_at__lte=end_date)
        
        # Сортируем по дате создания (новые сначала)
        notifications = notifications.order_by('-created_at')
        
        # Пагинация
        paginator = Paginator(notifications, page_size)
        page_obj = paginator.get_page(page)
        
        serializer = NotificationSerializer(page_obj.object_list, many=True)
        
        return Response({
            'success': True,
            'notifications': serializer.data,
            'pagination': {
                'current_page': page_obj.number,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get notification history for user {request.user.id}: {e}")
        return Response({
            'success': False,
            'message': _('Failed to get notification history')
        }, status=500) 