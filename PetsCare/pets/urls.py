from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views
from . import legacy_api
from .api_views import (
    PetListCreateAPIView, PetRetrieveUpdateDestroyAPIView,
    PetHealthNoteListCreateAPIView, PetHealthNoteRetrieveUpdateDestroyAPIView,
    PetAccessListCreateAPIView, PetAccessRetrieveUpdateDestroyAPIView,
    PetDeleteAPIView,
    PetMedicalCardAPIView,
    PetDocumentListCreateAPIView,
    PetDocumentDownloadAPIView, PetDocumentPreviewAPIView,
    PetSearchAPIView, PetTypeSearchAPIView, BreedSearchAPIView,
    ChronicConditionListAPIView,
    PhysicalFeatureListAPIView,
    BehavioralTraitListAPIView,
    PetRecommendationsAPIView, PetStatisticsAPIView,
    ServicesForPetRecordAPIView,
    PetPhotoConstraintsAPIView,
    SizeRulesByPetTypeAPIView,
)

router = DefaultRouter()
router.register(r'pets', api_views.PetViewSet)
router.register(r'visit-records', api_views.VisitRecordViewSet, basename='visit-record')
router.register(r'pet-documents', api_views.PetDocumentViewSet, basename='pet-document')
router.register(r'medical-records', legacy_api.LegacyMedicalRecordViewSet, basename='legacy-medical-record')
router.register(r'pet-records', legacy_api.LegacyVisitRecordViewSet, basename='legacy-pet-record')
router.register(r'pet-access', api_views.PetAccessViewSet)
router.register(r'document-types', api_views.DocumentTypeViewSet)
router.register(r'incapacity', api_views.PetOwnerIncapacityViewSet, basename='incapacity')
router.register(r'incapacity-notifications', api_views.PetIncapacityNotificationViewSet, basename='incapacity-notifications')

app_name = 'pets'

urlpatterns = [
    path('', include(router.urls)),

    # Pet endpoints
    path('pets/<int:pk>/delete/', PetDeleteAPIView.as_view(), name='pet-delete'),
    path('pets/<int:pet_id>/medical-card/', PetMedicalCardAPIView.as_view(), name='pet-medical-card'),
    path('pets/<int:pet_id>/health-notes/', PetHealthNoteListCreateAPIView.as_view(), name='pet-health-note-list-create'),
    path('pets/<int:pet_id>/documents/', PetDocumentListCreateAPIView.as_view(), name='pet-document-list-create'),
    path('health-notes/<int:pk>/', PetHealthNoteRetrieveUpdateDestroyAPIView.as_view(), name='pet-health-note-retrieve-update-destroy'),
    path('records/', legacy_api.LegacyVisitRecordListCreateAPIView.as_view(), name='legacy-record-list-create'),
    path('records/<int:pk>/', legacy_api.LegacyVisitRecordRetrieveUpdateDestroyAPIView.as_view(), name='legacy-record-retrieve-update-destroy'),
    path('records/<int:record_id>/upload_file/', legacy_api.LegacyVisitRecordFileUploadAPIView.as_view(), name='legacy-record-upload-file'),

    # Pet access endpoints
    path('access/', PetAccessListCreateAPIView.as_view(), name='pet-access-list-create'),
    path('access/<int:pk>/', PetAccessRetrieveUpdateDestroyAPIView.as_view(), name='pet-access-retrieve-update-destroy'),

    # Document endpoints
    path('documents/<int:document_id>/download/', PetDocumentDownloadAPIView.as_view(), name='document-download'),
    path('documents/<int:document_id>/preview/', PetDocumentPreviewAPIView.as_view(), name='document-preview'),
    
    # Pet search endpoints
    path('search/', PetSearchAPIView.as_view(), name='pet-search'),
    path('pet-types/search/', PetTypeSearchAPIView.as_view(), name='pet-type-search'),
    path('size-rules-by-pet-type/', SizeRulesByPetTypeAPIView.as_view(), name='size-rules-by-pet-type'),
    path('breeds/search/', BreedSearchAPIView.as_view(), name='breed-search'),
    path('chronic-conditions/', ChronicConditionListAPIView.as_view(), name='chronic-conditions-list'),
    path('physical-features/', PhysicalFeatureListAPIView.as_view(), name='physical-features-list'),
    path('behavioral-traits/', BehavioralTraitListAPIView.as_view(), name='behavioral-traits-list'),
    path('services-for-record/', ServicesForPetRecordAPIView.as_view(), name='services-for-record'),
    path('pet-photo-constraints/', PetPhotoConstraintsAPIView.as_view(), name='pet-photo-constraints'),
    path('recommendations/', PetRecommendationsAPIView.as_view(), name='pet-recommendations'),
    path('statistics/', PetStatisticsAPIView.as_view(), name='pet-statistics'),
]
