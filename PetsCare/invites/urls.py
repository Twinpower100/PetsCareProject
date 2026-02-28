"""
URL-маршруты для приложения invites.
"""
from django.urls import path
from . import api_views

app_name = 'invites'

urlpatterns = [
    path('', api_views.InviteListCreateAPIView.as_view(), name='invite-list-create'),
    path('accept/', api_views.InviteAcceptAPIView.as_view(), name='invite-accept'),
    path('decline/', api_views.InviteDeclineAPIView.as_view(), name='invite-decline'),
    path('pending/', api_views.InvitePendingAPIView.as_view(), name='invite-pending'),
    path('token/<str:token>/', api_views.InviteByTokenAPIView.as_view(), name='invite-by-token'),
    path('<int:pk>/', api_views.InviteDetailAPIView.as_view(), name='invite-detail'),
    path('<int:pk>/cancel/', api_views.InviteCancelAPIView.as_view(), name='invite-cancel'),
    path('<int:pk>/qr-code/', api_views.InviteQRCodeAPIView.as_view(), name='invite-qr-code'),
]
