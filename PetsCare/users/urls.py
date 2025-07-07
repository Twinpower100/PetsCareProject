"""
URL routes for the users module.

Этот модуль определяет API эндпоинты для:
1. Регистрации и аутентификации
2. Управления профилем
3. Google OAuth
4. Системы инвайтов ролей
5. Поиска пользователей по геолокации

Основные маршруты:
- /api/register/ - Регистрация нового пользователя
- /api/login/ - Вход в систему
- /api/profile/ - Профиль пользователя
- /api/google-auth/ - Аутентификация через Google
- /role-invites/ - Управление инвайтами на роли
- /search/distance/ - Поиск пользователей по расстоянию
- /search/sitters/distance/ - Поиск ситтеров по расстоянию
"""

from django.urls import path
from . import api_views
from .api_views import (
    UserSelfDeleteAPIView
)
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView

# Имя приложения для использования в URL
app_name = 'users'

# API маршруты
urlpatterns = [
    path('api/register/', api_views.UserRegistrationAPIView.as_view(), name='api_register'),
    path('api/login/', api_views.UserLoginAPIView.as_view(), name='api_login'),
    path('api/profile/', api_views.UserProfileAPIView.as_view(), name='api_profile'),
    path('api/google-auth/', api_views.GoogleAuthAPIView.as_view(), name='api_google_auth'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/blacklist/', TokenBlacklistView.as_view(), name='token_blacklist'),
    
    # Новые маршруты для управления ролями
    path('assign-role/', api_views.UserRoleAssignmentAPIView.as_view(), name='assign-role'),
    path('deactivate/<int:user_id>/', api_views.UserDeactivationAPIView.as_view(), name='deactivate-user'),
    
    # Маршруты для форм учреждений
    path('provider-forms/', api_views.ProviderFormListCreateAPIView.as_view(), name='provider-forms'),
    path('provider-forms/approve/', api_views.ProviderFormApprovalAPIView.as_view(), name='approve-provider-form'),
    
    # Маршруты для управления сотрудниками
    path('employees/deactivate/<int:employee_id>/', 
         api_views.EmployeeDeactivationAPIView.as_view(), 
         name='deactivate-employee'),
    path('me/delete/', UserSelfDeleteAPIView.as_view(), name='user-self-delete'),
    
    # Маршруты для поиска по геолокации
    path('search/distance/', api_views.UserSearchByDistanceAPIView.as_view(), name='user-search-distance'),
    path('search/sitters/distance/', api_views.SitterSearchByDistanceAPIView.as_view(), name='sitter-search-distance'),
    
    # Маршруты для массовых операций
    path('api/users/bulk-role-assignment/', api_views.BulkRoleAssignmentAPIView.as_view(), name='bulk-role-assignment'),
    path('api/users/bulk-deactivation/', api_views.BulkUserDeactivationAPIView.as_view(), name='bulk-user-deactivation'),
    path('api/users/bulk-activation/', api_views.BulkUserActivationAPIView.as_view(), name='bulk-user-activation'),
    
    # Role Invite URLs
    path('role-invites/', api_views.RoleInviteViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='role-invites'),
    path('role-invites/<int:pk>/', api_views.RoleInviteViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='role-invite-detail'),
    path('role-invites/accept/', api_views.RoleInviteAcceptAPIView.as_view(), name='role-invite-accept'),
    path('role-invites/decline/', api_views.RoleInviteDeclineAPIView.as_view(), name='role-invite-decline'),
    path('role-invites/token/<str:token>/', api_views.RoleInviteByTokenAPIView.as_view(), name='role-invite-by-token'),
    path('role-invites/<int:invite_id>/qr-code/', api_views.RoleInviteQRCodeAPIView.as_view(), name='role-invite-qr-code'),
    path('role-invites/pending/', api_views.RoleInvitePendingAPIView.as_view(), name='role-invites-pending'),
    path('role-invites/cleanup/', api_views.RoleInviteCleanupAPIView.as_view(), name='role-invites-cleanup'),
    path('role-termination/', api_views.RoleTerminationAPIView.as_view(), name='role-termination'),
] 