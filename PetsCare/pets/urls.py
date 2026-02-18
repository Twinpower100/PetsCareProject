from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views
from .api_views import (
    PetListCreateAPIView, PetRetrieveUpdateDestroyAPIView,
    MedicalRecordListCreateAPIView, MedicalRecordRetrieveUpdateDestroyAPIView,
    PetRecordListCreateAPIView, PetRecordRetrieveUpdateDestroyAPIView,
    PetAccessListCreateAPIView, PetAccessRetrieveUpdateDestroyAPIView,
    PetDeleteAPIView, PetInviteAPIView, PetAcceptInviteAPIView, PetInviteQRCodeAPIView,
    PetRecordFileUploadAPIView, PetDocumentDownloadAPIView, PetDocumentPreviewAPIView,
    PetSearchAPIView, PetTypeSearchAPIView, BreedSearchAPIView,
    PetRecommendationsAPIView, PetStatisticsAPIView,
    ServicesForPetRecordAPIView,
    PetPhotoConstraintsAPIView,
    SizeRulesByPetTypeAPIView,
)

router = DefaultRouter()
router.register(r'pets', api_views.PetViewSet)
router.register(r'medical-records', api_views.MedicalRecordViewSet)
router.register(r'pet-records', api_views.PetRecordViewSet)
router.register(r'pet-access', api_views.PetAccessViewSet)
router.register(r'document-types', api_views.DocumentTypeViewSet)
router.register(r'incapacity', api_views.PetOwnerIncapacityViewSet, basename='incapacity')
router.register(r'incapacity-notifications', api_views.PetIncapacityNotificationViewSet, basename='incapacity-notifications')

app_name = 'pets'

urlpatterns = [
    path('', include(router.urls)),

    # Pet endpoints
    path('pets/<int:pk>/delete/', PetDeleteAPIView.as_view(), name='pet-delete'),

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
    
    # Pet search endpoints
    path('search/', PetSearchAPIView.as_view(), name='pet-search'),
    path('pet-types/search/', PetTypeSearchAPIView.as_view(), name='pet-type-search'),
    path('size-rules-by-pet-type/', SizeRulesByPetTypeAPIView.as_view(), name='size-rules-by-pet-type'),
    path('breeds/search/', BreedSearchAPIView.as_view(), name='breed-search'),
    path('services-for-record/', ServicesForPetRecordAPIView.as_view(), name='services-for-record'),
    path('pet-photo-constraints/', PetPhotoConstraintsAPIView.as_view(), name='pet-photo-constraints'),
    path('recommendations/', PetRecommendationsAPIView.as_view(), name='pet-recommendations'),
    path('statistics/', PetStatisticsAPIView.as_view(), name='pet-statistics'),
]
