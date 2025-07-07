from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views
from .api_views import (
    PetListCreateAPIView, PetRetrieveUpdateDestroyAPIView,
    MedicalRecordListCreateAPIView, MedicalRecordRetrieveUpdateDestroyAPIView,
    PetRecordListCreateAPIView, PetRecordRetrieveUpdateDestroyAPIView,
    PetAccessListCreateAPIView, PetAccessRetrieveUpdateDestroyAPIView,
    PetDeleteAPIView, PetInviteAPIView, PetAcceptInviteAPIView, PetInviteQRCodeAPIView,
    PetRecordFileUploadAPIView, PetDocumentDownloadAPIView, PetDocumentPreviewAPIView
)

router = DefaultRouter()
router.register(r'pets', api_views.PetViewSet)
router.register(r'medical-records', api_views.MedicalRecordViewSet)
router.register(r'pet-records', api_views.PetRecordViewSet)
router.register(r'pet-access', api_views.PetAccessViewSet)
router.register(r'document-types', api_views.DocumentTypeViewSet)

app_name = 'pets'

urlpatterns = [
    path('api/', include(router.urls)),

    # Pet endpoints
    path('pets/', PetListCreateAPIView.as_view(), name='pet-list-create'),
    path('pets/<int:pk>/', PetRetrieveUpdateDestroyAPIView.as_view(), name='pet-retrieve-update-destroy'),
    path('pets/<int:pk>/delete/', PetDeleteAPIView.as_view(), name='pet-delete'),

    # Medical records endpoints
    path('medical-records/', MedicalRecordListCreateAPIView.as_view(), name='medical-record-list-create'),
    path('medical-records/<int:pk>/', MedicalRecordRetrieveUpdateDestroyAPIView.as_view(), name='medical-record-retrieve-update-destroy'),

    # Pet records endpoints
    path('records/', PetRecordListCreateAPIView.as_view(), name='pet-record-list-create'),
    path('records/<int:pk>/', PetRecordRetrieveUpdateDestroyAPIView.as_view(), name='pet-record-retrieve-update-destroy'),
    path('records/<int:record_id>/upload_file/', PetRecordFileUploadAPIView.as_view(), name='petrecordfile-upload'),

    # Pet access endpoints
    path('access/', PetAccessListCreateAPIView.as_view(), name='pet-access-list-create'),
    path('access/<int:pk>/', PetAccessRetrieveUpdateDestroyAPIView.as_view(), name='pet-access-retrieve-update-destroy'),

    # Pet invite endpoints
    path('pets/<int:pet_id>/invite/', PetInviteAPIView.as_view(), name='pet-invite'),
    path('pets/accept-invite/', PetAcceptInviteAPIView.as_view(), name='pet-accept-invite'),
    path('pets/invite/<uuid:token>/qr/', PetInviteQRCodeAPIView.as_view(), name='pet-invite-qr'),

    # Document endpoints
    path('documents/<int:document_id>/download/', PetDocumentDownloadAPIView.as_view(), name='document-download'),
    path('documents/<int:document_id>/preview/', PetDocumentPreviewAPIView.as_view(), name='document-preview'),
]
