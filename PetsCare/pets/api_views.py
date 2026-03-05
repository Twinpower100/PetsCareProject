from rest_framework import viewsets, permissions, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework.views import APIView
from django.utils import timezone
from datetime import timedelta
from users.models import User
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
from .models import Pet, MedicalRecord, PetRecord, PetAccess, PetRecordFile, DocumentType, ChronicCondition, PhysicalFeature, BehavioralTrait, PetOwner
from .serializers import (
    PetSerializer,
    MedicalRecordSerializer,
    PetRecordSerializer,
    PetAccessSerializer,
    PetRecordFileSerializer,
    DocumentTypeSerializer,
    ChronicConditionSerializer,
    PhysicalFeatureSerializer,
    BehavioralTraitSerializer,
    PetOwnerIncapacitySerializer,
    PetIncapacityNotificationSerializer,
    PetTypeSerializer,
    BreedSerializer,
    PetOwnerSerializer
)
from invites.models import Invite
from invites.serializers import InviteSerializer
from providers.models import EmployeeProvider, Employee, Provider, ProviderLocation
from catalog.models import Service
from catalog.serializers import ServiceSerializer as CatalogServiceSerializer
from django.core.mail import send_mail
from django.conf import settings
import uuid
from django.core.exceptions import ValidationError
from .services import PetOwnerIncapacityService
from .models import PetOwnerIncapacity, PetIncapacityNotification
from django.db import models
import logging
from .filters import PetFilter, PetTypeFilter, BreedFilter
from .models import PetType, Breed, SizeRule
from .constants import get_pet_photo_constraints_for_api
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q


logger = logging.getLogger(__name__)


class PetViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing pets.
    
    Features:
    - CRUD operations
    - Search for pets
    - Filtering and sorting
    """
    queryset = Pet._default_manager.all()
    serializer_class = PetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает список питомцев текущего пользователя с prefetch для избежания N+1"""
        if getattr(self, 'swagger_fake_view', False):
            return Pet._default_manager.none()
        return (
            self.queryset
            .filter(owners=self.request.user, is_active=True)
            .prefetch_related('petowner_set', 'petowner_set__user')
        )

    def perform_destroy(self, instance):
        """Мягкое удаление питомца"""
        instance.is_active = False
        instance.save()

    @action(detail=False, methods=['get'])
    def my_pets(self, request):
        """Возвращает список питомцев текущего пользователя"""
        pets = self.get_queryset()
        serializer = self.get_serializer(pets, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def remove_myself_as_coowner(self, request, pk=None):
        """
        Самостоятельное снятие обязанностей совладельца.
        
        Позволяет совладельцу самостоятельно отказаться от роли совладельца питомца.
        Проверяет, что пользователь является совладельцем (не основным владельцем).
        Уведомляет основного владельца о снятии роли.
        """
        pet = self.get_object()
        user = request.user
        
        # Проверяем роль через PetOwner
        try:
            po = PetOwner.objects.get(pet=pet, user=user)
        except PetOwner.DoesNotExist:
            return Response({
                'error': _('You do not have access to this pet.')
            }, status=status.HTTP_403_FORBIDDEN)
        
        if po.role == 'main':
            return Response({
                'error': _('You are the main owner of this pet. To transfer ownership, please use the transfer function.')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Проверяем, нет ли активных передержек или критических операций
        if self._has_active_pet_sittings(pet, user):
            return Response({
                'error': _('You cannot remove yourself as co-owner while you have active pet sitting responsibilities. Please complete or cancel any ongoing pet sitting arrangements first.')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Удаляем PetOwner запись
                po.delete()
                
                # Логируем действие
                self._log_coowner_removal(pet, user)
                
                # Уведомляем основного владельца
                main_owner = pet.main_owner
                if main_owner:
                    self._notify_main_owner(pet, user)
                
                # Удаляем все временные доступы этого пользователя к этому питомцу
                try:
                    from access.models import PetAccess
                    PetAccess.objects.filter(pet=pet, granted_to=user).delete()
                except ImportError:
                    pass
                
                return Response({
                    'message': _('You have successfully removed yourself as a co-owner of this pet.'),
                    'pet_id': pet.id,
                    'removed_user_id': user.id
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response({
                'error': _('Unable to process your request at this time. Please try again later.')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def owners(self, request, pk=None):
        """
        Возвращает список совладельцев и зависших инвайтов.
        Только владелец (main/coowner) может просматривать этот список.
        """
        pet = self.get_object()
        user = request.user
        
        # Проверяем, что запрашивающий - владелец
        if user not in pet.owners.all():
            return Response({'error': _('You do not have access to this pet.')}, status=status.HTTP_403_FORBIDDEN)
            
        owners_qs = pet.petowner_set.select_related('user').all()
        owners_data = PetOwnerSerializer(owners_qs, many=True).data
        
        # Инвайты 
        invites_qs = Invite.objects.filter(
            pet=pet,
            status=Invite.STATUS_PENDING
        )
        invites_data = InviteSerializer(invites_qs, many=True).data
        
        return Response({
            'owners': owners_data,
            'pending_invites': invites_data
        })

    @action(detail=True, methods=['post'], url_path='transfer-ownership')
    def transfer_ownership(self, request, pk=None):
        """
        Передача прав основного владельца.
        Только основной владелец может передать права.
        Новый владелец должен быть совладельцем.
        """
        pet = self.get_object()
        user = request.user
        new_owner_id = request.data.get('new_owner_id')
        
        if not new_owner_id:
            return Response({'error': _('new_owner_id is required.')}, status=status.HTTP_400_BAD_REQUEST)
            
        if user.pk == new_owner_id:
            return Response({'error': _('You cannot transfer ownership to yourself.')}, status=status.HTTP_400_BAD_REQUEST)
            
        if pet.main_owner_id != user.pk:
            return Response({'error': _('Only the main owner can transfer ownership.')}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            with transaction.atomic():
                # Блокируем строки PetOwner для этого питомца
                owners = list(PetOwner.objects.select_for_update().filter(pet=pet))
                
                new_owner_po = None
                current_owner_po = None
                
                for po in owners:
                    if po.user_id == new_owner_id:
                        new_owner_po = po
                    if po.user_id == user.pk:
                        current_owner_po = po
                        
                if not new_owner_po:
                    return Response({'error': _('The new owner must be a co-owner first.')}, status=status.HTTP_400_BAD_REQUEST)
                    
                # Меняем роли
                current_owner_po.role = 'coowner'
                current_owner_po.save(update_fields=['role'])
                
                new_owner_po.role = 'main'
                new_owner_po.save(update_fields=['role'])
                
                # Обновляем роли пользователей
                user.remove_role('pet_owner')  # maybe_remove_role in real life if needed, but they remain coowner so pet_owner logic will keep the role
                new_owner_po.user.add_role('pet_owner')

                try:
                    subject = _('Pet ownership transferred')
                    message = _(
                        'Ownership of pet {pet_name} has been transferred to {new_owner_email}.'
                    ).format(
                        pet_name=pet.name,
                        new_owner_email=new_owner_po.user.email
                    )
                    send_mail(
                        subject, message, settings.DEFAULT_FROM_EMAIL,
                        [user.email, new_owner_po.user.email], fail_silently=True
                    )
                except Exception:
                    pass
                    
                return Response({'message': _('Ownership transferred successfully.')}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': _('Unable to process your request at this time. Please try again later.')}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['delete'], url_path=r'co-owners/(?P<user_id>\d+)')
    def remove_coowner(self, request, pk=None, user_id=None):
        """
        Удаление совладельца. Осуществляется основным владельцем.
        """
        pet = self.get_object()
        user = request.user
        
        if not user_id:
            return Response({'error': _('user_id is required.')}, status=status.HTTP_400_BAD_REQUEST)
        
        user_id = int(user_id)
        if user.pk == user_id:
            return Response({'error': _('To remove yourself, use remove_myself_as_coowner endpoint.')}, status=status.HTTP_400_BAD_REQUEST)
            
        if pet.main_owner_id != user.pk:
            return Response({'error': _('Only the main owner can remove other co-owners.')}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            with transaction.atomic():
                po = PetOwner.objects.get(pet=pet, user_id=user_id)
                if po.role == 'main':
                    return Response({'error': _('Cannot remove the main owner.')}, status=status.HTTP_400_BAD_REQUEST)
                    
                removed_user = po.user
                
                if self._has_active_pet_sittings(pet, removed_user):
                     return Response({
                        'error': _('You cannot remove the co-owner while they have active pet sitting responsibilities.')
                    }, status=status.HTTP_400_BAD_REQUEST)
                    
                po.delete()
                
                try:
                    from access.models import PetAccess
                    PetAccess.objects.filter(pet=pet, granted_to=removed_user).delete()
                except ImportError:
                    pass
                    
                # убираем роль из удаляемого
                from invites.services import maybe_remove_role
                maybe_remove_role(removed_user, 'pet_owner')

                self._log_coowner_removal(pet, removed_user)
                
                return Response({'message': _('Co-owner removed.')}, status=status.HTTP_200_OK)
        except PetOwner.DoesNotExist:
            return Response({'error': _('Co-owner not found.')}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': _('Unable to process your request.')}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _has_active_pet_sittings(self, pet, user):
        """
        Проверяет, есть ли активные передержки для данного питомца и пользователя.
        
        Args:
            pet: Объект питомца
            user: Пользователь для проверки
            
        Returns:
            bool: True если есть активные передержки
        """
        try:
            from sitters.models import PetSitting
            
            # Проверяем активные передержки где пользователь является ситтером
            active_sittings = PetSitting._default_manager.filter(
                pet=pet,
                sitter__user=user,
                status__in=['waiting_start', 'in_progress']
            ).exists()
            
            return active_sittings
            
        except ImportError:
            # Если модуль sitters недоступен, считаем что активных передержек нет
            return False
    
    def _log_coowner_removal(self, pet, user):
        """
        Логирует снятие совладельца.
        
        Args:
            pet: Объект питомца
            user: Пользователь, который снял себя как совладельца
        """
        try:
            from audit.models import UserAction
            from django.contrib.contenttypes.models import ContentType
            
            pet_content_type = ContentType.objects.get_for_model(pet)
            
            UserAction._default_manager.create(
                user=user,
                action_type='update',
                content_type=pet_content_type,
                object_id=pet.id,
                details={
                    'action': 'coowner_self_removal',
                    'pet_name': pet.name,
                    'pet_id': pet.id,
                    'removed_user_id': user.id,
                    'removed_user_email': user.email,
                    'timestamp': timezone.now().isoformat()
                }
            )
        except ImportError:
            # Если модуль audit недоступен, пропускаем логирование
            pass
    
    def _notify_main_owner(self, pet, removed_user):
        """
        Уведомляет основного владельца о снятии совладельца.
        
        Args:
            pet: Объект питомца
            removed_user: Пользователь, который снял себя как совладельца
        """
        if not pet.main_owner or not pet.main_owner.email:
            return
        
        try:
            subject = _('Co-owner removed themselves from pet')
            message = _(
                'User {email} has removed themselves as a co-owner of your pet {pet_name}. '
                'They will no longer have access to the pet\'s information and records.'
            ).format(
                email=removed_user.email,
                pet_name=pet.name
            )
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[pet.main_owner.email],
                fail_silently=True
            )
            
        except Exception as e:
            # Логируем ошибку отправки уведомления, но не прерываем основную операцию
            pass


class MedicalRecordViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing medical records.
    """
    queryset = MedicalRecord._default_manager.all()
    serializer_class = MedicalRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает медицинские записи питомцев текущего пользователя"""
        if getattr(self, 'swagger_fake_view', False):
            return MedicalRecord._default_manager.none()
        return self.queryset.filter(pet__owners=self.request.user)

    def perform_create(self, serializer):
        """Создает медицинскую запись"""
        pet = get_object_or_404(Pet, pk=self.request.data.get('pet'))
        if self.request.user not in pet.owners.all():
            raise permissions.PermissionDenied(_('You do not have permission to create medical records for this pet'))
        serializer.save()


class PetRecordViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing pet records in the pet's map (PetRecord).

    - This class manages CONTENT (medical, procedural, service records) in the pet's history.
    - Allows creating, viewing, editing, deleting records about procedures, services, medical manipulations for the pet.
    - A record can be created only by the pet owner (owners) or an employee of the provider, if specified in the employee field and active in this provider.
    - Does not manage access rights to other users' information about the pet.
    """
    queryset = PetRecord._default_manager.all()
    serializer_class = PetRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Владельцы видят записи своих питомцев; сотрудник — записи, где он исполнитель (по полю employee)."""
        if getattr(self, 'swagger_fake_view', False):
            return PetRecord._default_manager.none()
        user = self.request.user
        from django.db.models import Q
        return self.queryset.filter(
            Q(pet__owners=user) | Q(employee__user=user)
        ).distinct()

    def perform_create(self, serializer):
        """Создает запись в карте питомца"""
        pet = get_object_or_404(Pet, pk=self.request.data.get('pet'))
        provider_id = self.request.data.get('provider')
        employee_id = self.request.data.get('employee')
        user = self.request.user

        is_owner = user in pet.owners.all()
        is_employee_for_provider = False

        if provider_id and employee_id:
            from providers.models import Employee, EmployeeProvider
            try:
                employee = Employee._default_manager.get(pk=employee_id)
                # Проверяем, что этот сотрудник — текущий пользователь и может проводить приёмы (не technical_worker)
                if employee.user == user:
                    ep = EmployeeProvider.get_active_ep_for_user_provider(user, get_object_or_404(Provider, pk=provider_id))
                    if ep and ep.can_conduct_visits():
                        is_employee_for_provider = True
            except Employee.DoesNotExist:
                pass

        if not (is_owner or is_employee_for_provider):
            raise permissions.PermissionDenied(_('You do not have permission to add records for this pet'))

        serializer.save(created_by=user)


class PetAccessViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing temporary access to the pet's map (PetAccess).

    - This class manages ACCESS RIGHTS to information about the pet for other users.
    - Allows the pet owner to grant temporary access to information about the pet to another user (for example, only for reading, with the right to booking or editing), set the expiration date, generate a QR code.
    - Allows revoking previously granted access.
    - Does not manage creating or editing records in the pet's history.
    """
    queryset = PetAccess._default_manager.all()
    serializer_class = PetAccessSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает доступы к питомцам текущего пользователя"""
        if getattr(self, 'swagger_fake_view', False):
            return PetAccess._default_manager.none()
        return self.queryset.filter(pet__owners=self.request.user)

    def perform_create(self, serializer):
        """Создает доступ к карте питомца"""
        pet = get_object_or_404(Pet, pk=self.request.data.get('pet'))
        if self.request.user not in pet.owners.all():
            raise permissions.PermissionDenied(_('You do not have permission to grant access to this pet'))
        serializer.save(granted_by=self.request.user)

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        """Отзывает доступ к карте питомца"""
        access = self.get_object()
        if request.user not in access.pet.owners.all():
            raise permissions.PermissionDenied(_('You do not have permission to revoke access to this pet'))
        access.delete()
        return Response({'status': 'Access revoked'})


class DocumentTypeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing pet document types.
    
    Features:
    - CRUD operations for document types
    - Link with service categories
    - Setting mandatory fields
    - Filtering by activity
    """
    queryset = DocumentType._default_manager.all()
    serializer_class = DocumentTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает активные типы документов"""
        return self.queryset.filter(is_active=True)

    def perform_create(self, serializer):
        """Создает тип документа"""
        # Только системные администраторы могут создавать типы документов
        if not (self.request.user.is_staff or self.request.user.is_superuser):
            raise permissions.PermissionDenied(_('Only administrators can create document types'))
        serializer.save()

    def perform_update(self, serializer):
        """Обновляет тип документа"""
        # Только системные администраторы могут обновлять типы документов
        if not (self.request.user.is_staff or self.request.user.is_superuser):
            raise permissions.PermissionDenied(_('Only administrators can update document types'))
        serializer.save()

    def perform_destroy(self, instance):
        """Удаляет тип документа"""
        # Только системные администраторы могут удалять типы документов
        if not (self.request.user.is_staff or self.request.user.is_superuser):
            raise permissions.PermissionDenied(_('Only administrators can delete document types'))
        instance.delete()

    @action(detail=False, methods=['get'])
    def by_service_category(self, request):
        """Возвращает типы документов для конкретной категории услуг"""
        category_id = request.query_params.get('category_id')
        if category_id and hasattr(self.queryset.model, 'service_categories'):
            document_types = self.queryset.filter(
                service_categories__id=category_id,
                is_active=True
            )
            serializer = self.get_serializer(document_types, many=True)
            return Response(serializer.data)
        return Response([])


class PetDeleteAPIView(APIView):
    """
    API for deleting a pet.
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk=None, pet_id=None):
        """Удаляет питомца"""
        target_id = pk if pk is not None else pet_id
        if target_id is None:
            return Response(
                {'error': _('Pet ID is required')},
                status=status.HTTP_400_BAD_REQUEST
            )

        pet = get_object_or_404(Pet, pk=target_id)
        user = request.user
        is_main_owner = (pet.main_owner == user)
        is_admin = user.is_staff or user.is_superuser

        if not (is_main_owner or is_admin):
            raise permissions.PermissionDenied(_('Only main owner or admin can delete this pet'))
        pet.is_active = False
        pet.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PetListCreateAPIView(generics.ListCreateAPIView):
    """
    API for creating and getting a list of pets.
    """
    queryset = Pet._default_manager.all()
    serializer_class = PetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает список питомцев текущего пользователя"""
        if getattr(self, 'swagger_fake_view', False):
            return Pet._default_manager.none()
        return self.queryset.filter(owners=self.request.user, is_active=True)


class PetRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Pet._default_manager.all()
    serializer_class = PetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Pet._default_manager.none()
        return self.queryset.filter(owners=self.request.user, is_active=True)

    def perform_destroy(self, instance):
        """Мягкое удаление питомца"""
        instance.is_active = False
        instance.save()


class MedicalRecordListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = MedicalRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return MedicalRecord._default_manager.none()
        return MedicalRecord._default_manager.filter(pet__owners=self.request.user)


class MedicalRecordRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MedicalRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return MedicalRecord._default_manager.none()
        return MedicalRecord._default_manager.filter(pet__owners=self.request.user)


class PetRecordListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = PetRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return PetRecord._default_manager.none()
        from django.db.models import Q
        user = self.request.user
        return PetRecord._default_manager.filter(
            Q(pet__owners=user) | Q(employee__user=user)
        ).distinct()


class PetRecordRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PetRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return PetRecord._default_manager.none()
        from django.db.models import Q
        user = self.request.user
        return PetRecord._default_manager.filter(
            Q(pet__owners=user) | Q(employee__user=user)
        ).distinct()


class PetAccessListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = PetAccessSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return PetAccess._default_manager.none()
        return PetAccess._default_manager.filter(pet__owners=self.request.user)


class PetAccessRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PetAccessSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return PetAccess._default_manager.none()
        return PetAccess._default_manager.filter(pet__owners=self.request.user)


class PetRecordFileUploadAPIView(APIView):
    """
    API for uploading a file to a record in the pet's map.
    
    Access rights:
    - Employee (employee): can upload to records where he is executor or his institution
    - Pet owner: can upload to records of his pets
    - Institution administrator (provider_admin): can upload to records of his institution
    - System administrator (system_admin): can upload everywhere
    """
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [permissions.IsAuthenticated]

    def validate_file(self, file):
        """
        File validation.
        
        Args:
            file: Uploaded file
            
        Raises:
            ValidationError: If the file failed validation
        """
        # Проверка размера файла (10MB)
        if file.size > 10 * 1024 * 1024:
            raise ValidationError(_('File is too large (max 10MB)'))
        
        # Разрешенные типы файлов
        allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx', '.xls', '.xlsx']
        file_extension = file.name.lower()
        
        if not any(file_extension.endswith(ext) for ext in allowed_extensions):
            raise ValidationError(_('Unsupported file type. Allowed: PDF, images, Excel/Word documents'))
        
        # Проверка MIME-типа
        allowed_mime_types = [
            'application/pdf',
            'image/jpeg',
            'image/png',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ]
        
        if hasattr(file, 'content_type') and file.content_type not in allowed_mime_types:
            raise ValidationError(_('Unsupported MIME type'))

    def check_permissions(self, user, record):
        """
        Check access rights for uploading a file.
        
        Args:
            user: User trying to upload a file
            record: PetRecord
            
        Returns:
            bool: True if the user has rights
        """
        # Системный администратор может все
        if user.has_role('system_admin') or user.is_superuser:
            return True
        
        # Владелец питомца может загружать в записи своих питомцев
        if user in record.pet.owners.all():
            return True
        
        # Сотрудник с правом приёмов (service_worker, provider_admin, provider_manager, owner) может загружать в записи, где он исполнитель или в записи своего учреждения
        ep = EmployeeProvider.get_active_ep_for_user_provider(user, record.provider)
        if ep and ep.can_conduct_visits():
            if record.employee_id == ep.employee_id:
                return True
            if ep.provider_id == record.provider_id:
                return True

        return False

    def post(self, request, record_id):
        """
        Uploads a document to a record in the pet's map.
        
        Args:
            request: HTTP request with file and metadata
            record_id: ID of PetRecord
            
        Returns:
            Response: Document upload result
        """
        # Получаем запись
        record = get_object_or_404(PetRecord, pk=record_id)
        
        # Проверяем права доступа
        if not self.check_permissions(request.user, record):
            raise permissions.PermissionDenied(
                _('You do not have permission to upload documents to this record')
            )
        
        # Проверяем наличие файла в запросе
        if 'file' not in request.FILES:
            return Response(
                {'error': _('File is required')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file = request.FILES['file']
        
        # Валидируем файл
        try:
            self.validate_file(file)
        except ValidationError as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Создаем документ
        try:
            # Подготавливаем данные для создания документа
            document_data = {
                'file': file,
                'name': request.data.get('name', file.name),
                'description': request.data.get('description', ''),
                'pet': record.pet,
                'pet_record': record,
                'uploaded_by': request.user,
            }
            
            # Добавляем опциональные поля
            if 'document_type' in request.data:
                document_data['document_type'] = request.data['document_type']
            
            if 'issue_date' in request.data:
                document_data['issue_date'] = request.data['issue_date']
            
            if 'expiry_date' in request.data:
                document_data['expiry_date'] = request.data['expiry_date']
            
            if 'document_number' in request.data:
                document_data['document_number'] = request.data['document_number']
            
            if 'issuing_authority' in request.data:
                document_data['issuing_authority'] = request.data['issuing_authority']
            
            # Создаем документ
            pet_record_file = PetRecordFile._default_manager.create(**document_data)
            
            # Сериализуем результат
            serializer = PetRecordFileSerializer(pet_record_file)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': _('Error saving document')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PetDocumentDownloadAPIView(APIView):
    """
    API for downloading a pet document with access rights check.
    
    Access rights:
    - Pet owner: can download documents of his pets
    - Employee: can download documents of pets serviced by
    - Institution administrator: can download documents of pets of his institution
    - System administrator: can download all documents
    """
    permission_classes = [permissions.IsAuthenticated]

    def check_permissions(self, user, document):
        """
        Check access rights for downloading a document.
        
        Args:
            user: User trying to download a document
            document: PetRecordFile
            
        Returns:
            bool: True if the user has rights
        """
        # Системный администратор может все
        if user.is_superuser or user.has_role('system_admin'):
            return True
        
        # Владелец питомца может скачивать документы своих питомцев
        if user in document.pet.owners.all():
            return True
        
        # Сотрудник может скачивать документы питомцев, которых обслуживает
        if user.has_role('employee'):
            from providers.models import Employee, EmployeeProvider
            
            try:
                employee = Employee._default_manager.get(user=user)
                # Проверяем, что сотрудник работает в учреждении, где есть записи питомца
                has_records_for_pet = PetRecord._default_manager.filter(
                    pet=document.pet,
                    employee=employee
                ).exists()
                
                if has_records_for_pet:
                    return True
                
                # Проверяем, что сотрудник работает в учреждении, где есть записи питомца
                provider_records = PetRecord._default_manager.filter(
                    pet=document.pet
                ).values_list('provider', flat=True).distinct()
                
                is_employee_for_providers = EmployeeProvider._default_manager.filter(
                    employee=employee,
                    provider__in=provider_records,
                    status__in=['active', 'temporary']
                ).exists()
                
                if is_employee_for_providers:
                    return True
            except Employee.DoesNotExist:
                pass
        
        # Администратор учреждения может скачивать документы питомцев своего учреждения
        if user.has_role('provider_admin'):
            from providers.models import EmployeeProvider
            
            provider_records = PetRecord._default_manager.filter(
                pet=document.pet
            ).values_list('provider', flat=True).distinct()
            
            is_admin_for_providers = EmployeeProvider._default_manager.filter(
                employee__user=user,
                provider__in=provider_records,
                is_manager=True,
                status__in=['active', 'temporary']
            ).exists()
            
            if is_admin_for_providers:
                return True
        
        return False

    def get(self, request, document_id):
        """
        Downloads a pet document.
        
        Args:
            request: HTTP request
            document_id: ID of PetRecordFile
            
        Returns:
            Response: Download file
        """
        document = get_object_or_404(PetRecordFile, pk=document_id)
        
        # Проверяем права доступа
        if not self.check_permissions(request.user, document):
            raise permissions.PermissionDenied(
                _('You do not have permission to download this document')
            )
        
        # Проверяем, что файл существует
        if not document.file:
            return Response(
                {'error': _('File not found')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            # Открываем файл для чтения
            file_handle = document.file.open('rb')
            
            # Определяем MIME-тип
            import mimetypes
            content_type, _ = mimetypes.guess_type(document.file.name)
            if not content_type:
                content_type = 'application/octet-stream'
            
            # Создаем ответ с файлом
            from django.http import FileResponse
            response = FileResponse(
                file_handle,
                content_type=content_type
            )
            
            # Устанавливаем заголовки для скачивания
            response['Content-Disposition'] = f'attachment; filename="{document.name}"'
            response['Content-Length'] = document.file.size
            
            return response
            
        except Exception as e:
            return Response(
                {'error': _('Error downloading file')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PetDocumentPreviewAPIView(APIView):
    """
    API for previewing a pet document (only for images).
    
    Access rights: same as for downloading
    """
    permission_classes = [permissions.IsAuthenticated]

    def check_permissions(self, user, document):
        """
        Check access rights for previewing a document.
        """
        # Используем ту же логику, что и для скачивания
        download_view = PetDocumentDownloadAPIView()
        return download_view.check_permissions(user, document)

    def get(self, request, document_id):
        """
        Document preview (only for images).
        
        Args:
            request: HTTP request
            document_id: ID of PetRecordFile
            
        Returns:
            Response: Preview image
        """
        document = get_object_or_404(PetRecordFile, pk=document_id)
        
        # Проверяем права доступа
        if not self.check_permissions(request.user, document):
            raise permissions.PermissionDenied(
                _('You do not have permission to view this document')
            )
        
        # Проверяем, что файл существует
        if not document.file:
            return Response(
                {'error': _('File not found')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Проверяем, что это изображение
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        file_extension = document.file.name.lower()
        
        if not any(file_extension.endswith(ext) for ext in image_extensions):
            return Response(
                {'error': _('Preview is only available for images')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Открываем файл для чтения
            file_handle = document.file.open('rb')
            
            # Определяем MIME-тип
            import mimetypes
            content_type, _ = mimetypes.guess_type(document.file.name)
            if not content_type:
                content_type = 'image/jpeg'
            
            # Создаем ответ с изображением
            from django.http import FileResponse
            response = FileResponse(
                file_handle,
                content_type=content_type
            )
            
            # Устанавливаем заголовки для предпросмотра
            response['Content-Disposition'] = f'inline; filename="{document.name}"'
            response['Content-Length'] = document.file.size
            
            return response
            
        except Exception as e:
            return Response(
                {'error': _('Error loading image')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 


class PetOwnerIncapacityViewSet(viewsets.ModelViewSet):
    """
    API для управления случаями недееспособности владельцев питомцев.
    
    Особенности:
    - Создание отчетов о недееспособности
    - Подтверждение статуса питомца
    - Просмотр истории случаев
    """
    serializer_class = PetOwnerIncapacitySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Возвращает queryset в зависимости от роли пользователя."""
        if getattr(self, 'swagger_fake_view', False):
            return PetOwnerIncapacity._default_manager.none()
        
        user = self.request.user
        
        if user.is_staff:
            # Администраторы видят все случаи
            return PetOwnerIncapacity._default_manager.all()
        else:
            # Обычные пользователи видят только случаи с их питомцами
            return PetOwnerIncapacity._default_manager.filter(
                models.Q(pet__petowner__user=user) | 
                models.Q(reported_by=user)
            ).distinct()
    
    @action(detail=False, methods=['post'])
    def report_pet_lost(self, request):
        """
        Сообщает о потере питомца.
        
        Только основной владелец может сообщить о потере питомца.
        
        Args:
            pet_id: ID питомца
            reason: Причина потери (опционально)
        """
        pet_id = request.data.get('pet_id')
        reason = request.data.get('reason', '')
        
        if not pet_id:
            return Response({
                'error': _('Pet ID is required.')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            pet = Pet._default_manager.get(id=pet_id)
        except ObjectDoesNotExist:
            return Response({
                'error': _('Pet not found.')
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Проверяем права доступа - только основной владелец может сообщить о потере питомца
        user = request.user
        if pet.main_owner != user:
            return Response({
                'error': _('Only the main owner can report pet loss.')
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Проверяем, что нет активных случаев недееспособности
        if pet.incapacity_records.filter(status='pending_confirmation').exists():
            return Response({
                'error': _('There is already an active incapacity case for this pet.')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            service = PetOwnerIncapacityService()
            incapacity_record = service.report_pet_lost(pet, user, reason)
            
            return Response({
                'message': _('Pet lost report submitted successfully.'),
                'incapacity_record_id': incapacity_record.id
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error reporting pet lost: {str(e)}")
            return Response({
                'error': _('Unable to process your request at this time. Please try again later.')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def report_owner_incapacity(self, request):
        """
        Сообщает о недееспособности основного владельца.
        
        Args:
            pet_id: ID питомца
            reason: Причина недееспособности
        """
        pet_id = request.data.get('pet_id')
        reason = request.data.get('reason', '')
        
        if not pet_id:
            return Response({
                'error': _('Pet ID is required.')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not reason:
            return Response({
                'error': _('Reason for incapacity is required.')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            pet = Pet._default_manager.get(id=pet_id)
        except ObjectDoesNotExist:
            return Response({
                'error': _('Pet not found.')
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Проверяем права доступа (только совладельцы могут сообщать о недееспособности)
        user = request.user
        if pet.main_owner == user:
            return Response({
                'error': _('You cannot report incapacity for yourself.')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if user not in pet.owners.all():
            return Response({
                'error': _('You do not have access to this pet.')
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Проверяем, что нет активных случаев недееспособности
        if pet.incapacity_records.filter(status='pending_confirmation').exists():
            return Response({
                'error': _('There is already an active incapacity case for this pet.')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            service = PetOwnerIncapacityService()
            incapacity_record = service.report_owner_incapacity(pet, user, reason)
            
            return Response({
                'message': _('Owner incapacity report submitted successfully.'),
                'incapacity_record_id': incapacity_record.id
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error reporting owner incapacity: {str(e)}")
            return Response({
                'error': _('Unable to process your request at this time. Please try again later.')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def confirm_pet_status(self, request, pk=None):
        """
        Подтверждает статус питомца.
        
        Только основной владелец может подтвердить статус питомца.
        
        Args:
            pet_is_ok: True если питомец в порядке, False если потерян/умер
            notes: Дополнительные заметки (опционально)
        """
        incapacity_record = self.get_object()
        pet_is_ok = request.data.get('pet_is_ok')
        notes = request.data.get('notes', '')
        
        if pet_is_ok is None:
            return Response({
                'error': _('Pet status confirmation is required.')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Проверяем права доступа - только основной владелец может подтвердить статус питомца
        user = request.user
        if incapacity_record.pet.main_owner != user:
            return Response({
                'error': _('Only the main owner can confirm pet status.')
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Проверяем статус записи
        if incapacity_record.status != 'pending_confirmation':
            return Response({
                'error': _('This incapacity case cannot be confirmed.')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            service = PetOwnerIncapacityService()
            success = service.confirm_pet_status(incapacity_record, user, pet_is_ok, notes)
            
            if success:
                return Response({
                    'message': _('Pet status confirmed successfully.'),
                    'status': incapacity_record.status
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'error': _('Unable to confirm pet status. Please try again later.')
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            logger.error(f"Error confirming pet status: {str(e)}")
            return Response({
                'error': _('Unable to process your request at this time. Please try again later.')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def my_cases(self, request):
        """Возвращает случаи недееспособности, связанные с пользователем."""
        user = request.user
        
        # Получаем случаи, где пользователь является основным владельцем или совладельцем
        cases = PetOwnerIncapacity._default_manager.filter(
            models.Q(pet__petowner__user=user) |
            models.Q(reported_by=user)
        ).distinct().order_by('-created_at')
        
        page = self.paginate_queryset(cases)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(cases, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def notifications(self, request, pk=None):
        """Возвращает уведомления для случая недееспособности."""
        incapacity_record = self.get_object()
        
        # Проверяем права доступа
        user = request.user
        if not (incapacity_record.pet.main_owner == user or user in incapacity_record.pet.owners.all()):
            return Response({
                'error': _('You do not have access to this case.')
            }, status=status.HTTP_403_FORBIDDEN)
        
        notifications = incapacity_record.notifications.filter(recipient=user).order_by('-created_at')
        
        page = self.paginate_queryset(notifications)
        if page is not None:
            serializer = PetIncapacityNotificationSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = PetIncapacityNotificationSerializer(notifications, many=True)
        return Response(serializer.data)


class PetIncapacityNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API для просмотра уведомлений о недееспособности владельцев.
    """
    serializer_class = PetIncapacityNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Возвращает уведомления пользователя."""
        if getattr(self, 'swagger_fake_view', False):
            return PetIncapacityNotification._default_manager.none()
        return PetIncapacityNotification._default_manager.filter(recipient=self.request.user).order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Отмечает уведомление как прочитанное."""
        notification = self.get_object()
        
        # Проверяем, что уведомление принадлежит пользователю
        if notification.recipient != request.user:
            return Response({
                'error': _('You do not have access to this notification.')
            }, status=status.HTTP_403_FORBIDDEN)
        
        # В данной реализации просто возвращаем успех
        # В будущем можно добавить поле is_read в модель
        return Response({
            'message': _('Notification marked as read.')
        }, status=status.HTTP_200_OK) 


class PetSearchPagination(PageNumberPagination):
    """Пагинация для результатов поиска питомцев."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class PetSearchAPIView(generics.ListAPIView):
    """
    API для расширенного поиска питомцев.
    
    Поддерживает:
    - Фильтрацию по типу, породе, возрасту, весу
    - Фильтрацию по медицинским условиям и особым потребностям
    - Фильтрацию по геолокации
    - Сортировку по различным параметрам
    - Пагинацию результатов
    """
    serializer_class = PetSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = PetFilter
    pagination_class = PetSearchPagination
    ordering_fields = [
        'name', 'birth_date', 'weight', 'created_at', 'updated_at',
        'pet_type__name', 'breed__name'
    ]
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Возвращает queryset с учетом прав доступа пользователя."""
        if getattr(self, 'swagger_fake_view', False):
            return Pet._default_manager.none()
        
        user = self.request.user
        
        if user.is_staff:
            # Администраторы видят всех питомцев
            return Pet._default_manager.all()
        else:
            # Обычные пользователи видят только своих активных питомцев
            return Pet._default_manager.filter(owners=user, is_active=True)
    
    def get_serializer_context(self):
        """Добавляет контекст для сериализатора."""
        context = super().get_serializer_context()
        if getattr(self, 'swagger_fake_view', False):
            return context
        context['include_medical_info'] = self.request.query_params.get('include_medical_info', 'false').lower() == 'true'
        context['include_records_count'] = self.request.query_params.get('include_records_count', 'false').lower() == 'true'
        return context


class PetTypeSearchAPIView(generics.ListAPIView):
    """
    API для поиска типов питомцев.
    """
    serializer_class = PetTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = PetTypeFilter
    ordering_fields = ['name', 'code']
    ordering = ['name']
    
    def get_queryset(self):
        """Возвращает активные типы питомцев."""
        if getattr(self, 'swagger_fake_view', False):
            return PetType._default_manager.none()
        return PetType._default_manager.all()


class BreedSearchAPIView(generics.ListAPIView):
    """
    API для поиска пород питомцев.
    """
    serializer_class = BreedSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = BreedFilter
    ordering_fields = ['name', 'code', 'pet_type__name']
    ordering = ['pet_type__name', 'name']
    
    def get_queryset(self):
        """Возвращает породы с предзагрузкой типов питомцев."""
        if getattr(self, 'swagger_fake_view', False):
            return Breed._default_manager.none()
        return Breed._default_manager.select_related('pet_type').all()


class ChronicConditionListAPIView(generics.ListAPIView):
    """
    Список справочника хронических заболеваний для выбора при редактировании карточки питомца.
    GET /api/v1/chronic-conditions/
    """
    serializer_class = ChronicConditionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ChronicCondition._default_manager.none()
        return ChronicCondition._default_manager.all()


class PhysicalFeatureListAPIView(generics.ListAPIView):
    """
    Список справочника физических особенностей (отсутствие конечностей, слепота и т.д.).
    GET /api/v1/physical-features/
    """
    serializer_class = PhysicalFeatureSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return PhysicalFeature._default_manager.none()
        return PhysicalFeature._default_manager.all()


class BehavioralTraitListAPIView(generics.ListAPIView):
    """
    Список справочника поведенческих особенностей.
    GET /api/v1/behavioral-traits/
    """
    serializer_class = BehavioralTraitSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return BehavioralTrait._default_manager.none()
        return BehavioralTrait._default_manager.all()


class SizeRulesByPetTypeAPIView(APIView):
    """
    Список допустимых размеров (size_code) по типу животного из таблицы SizeRule.
    GET /api/v1/size-rules-by-pet-type/
    Ответ: { "<pet_type_id>": ["S", "M", "L", "XL"], ... } — только те размеры, что заданы в SizeRule для каждого типа.
    Используется на вкладке «Услуги и цены» филиала: выбор размера доступен только после выбора типа животного
    и ограничен размерами этого типа (например, для кошек только S и L).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .models import SIZE_CATEGORY_ORDER
        qs = SizeRule._default_manager.values_list('pet_type_id', 'size_code').order_by('pet_type_id', 'min_weight_kg')
        by_pet_type = {}
        for pet_type_id, size_code in qs:
            if pet_type_id not in by_pet_type:
                by_pet_type[pet_type_id] = []
            if size_code not in by_pet_type[pet_type_id]:
                by_pet_type[pet_type_id].append(size_code)
        from .models import SIZE_CATEGORY_ORDER
        for key in by_pet_type:
            by_pet_type[key] = sorted(
                by_pet_type[key],
                key=lambda c: SIZE_CATEGORY_ORDER.get(c, 99),
            )
        return Response({str(k): v for k, v in by_pet_type.items()})


class ServicesForPetRecordAPIView(APIView):
    """
    Список услуг для формы записи в медкарту.
    - Владелец: ?pet_id=X — глобальный каталог, отфильтрованный по типу питомца.
    - Работник провайдера: ?pet_id=X&provider_location_id=Y — услуги локации (где работает сотрудник),
      отфильтрованные по типу питомца.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        pet_id = request.query_params.get('pet_id')
        if not pet_id:
            return Response(
                {'error': _('pet_id is required')},
                status=status.HTTP_400_BAD_REQUEST
            )
        pet = get_object_or_404(Pet, pk=pet_id)
        if request.user not in pet.owners.all():
            return Response(
                {'error': _('You do not have access to this pet')},
                status=status.HTTP_403_FORBIDDEN
            )
        pet_type = pet.pet_type if hasattr(pet.pet_type, 'id') else Pet._default_manager.get(pk=pet_id).pet_type
        provider_location_id = request.query_params.get('provider_location_id')

        if provider_location_id:
            location = get_object_or_404(ProviderLocation, pk=provider_location_id)
            employee = getattr(request.user, 'employee_profile', None)
            if not employee or not location.employees.filter(pk=employee.pk).exists():
                return Response(
                    {'error': _('You are not an employee of this location')},
                    status=status.HTTP_403_FORBIDDEN
                )
            queryset = location.available_services.filter(
                Q(allowed_pet_types__isnull=True) | Q(allowed_pet_types=pet_type)
            ).filter(children__isnull=False).distinct().order_by('hierarchy_order', 'name')
        else:
            queryset = Service._default_manager.filter(
                Q(allowed_pet_types__isnull=True) | Q(allowed_pet_types=pet_type)
            ).filter(children__isnull=False).distinct().order_by('hierarchy_order', 'name')

        serializer = CatalogServiceSerializer(queryset, many=True)
        return Response(serializer.data)


class PetPhotoConstraintsAPIView(APIView):
    """
    Лимиты и подсказки для загрузки фото питомца (для фронта).
    Возвращает max размер, разрешение, допустимые форматы и мультиязычную подсказку (hints: { en, ru, de, me }).
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        hints = {}
        for lang_code, _lang_name in getattr(settings, 'LANGUAGES', [('en', 'English'), ('ru', 'Russian'), ('me', 'Montenegrin'), ('de', 'German')]):
            data = get_pet_photo_constraints_for_api(language_code=lang_code)
            hints[lang_code] = data['hint']
        data = get_pet_photo_constraints_for_api()
        data['hints'] = hints
        return Response(data)


class PetRecommendationsAPIView(generics.ListAPIView):
    """
    API для получения персонализированных рекомендаций питомцев.
    
    Основано на:
    - Истории посещений
    - Предпочтениях пользователя
    - Похожих питомцах
    """
    serializer_class = PetSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PetSearchPagination
    
    def get_queryset(self):
        """Возвращает персонализированные рекомендации."""
        if getattr(self, 'swagger_fake_view', False):
            return Pet._default_manager.none()
        
        user = self.request.user
        limit = int(self.request.query_params.get('limit', 10))
        
        # Получаем питомцев пользователя
        user_pets = Pet._default_manager.filter(owners=user)
        
        if not user_pets.exists():
            # Если у пользователя нет питомцев, возвращаем популярные типы
            return Pet._default_manager.filter(
                pet_type__in=PetType._default_manager.all()[:3]
            ).order_by('?')[:limit]
        
        # Анализируем предпочтения пользователя
        user_pet_types = user_pets.values_list('pet_type', flat=True).distinct()
        user_breeds = user_pets.values_list('breed', flat=True).distinct()
        
        # Находим похожих питомцев
        similar_pets = Pet._default_manager.exclude(owners=user).filter(
            Q(pet_type__in=user_pet_types) |
            Q(breed__in=user_breeds)
        ).distinct()
        
        # Если похожих питомцев мало, добавляем случайные
        if similar_pets.count() < limit:
            additional_pets = Pet._default_manager.exclude(
                Q(owners=user) | Q(id__in=similar_pets.values_list('id', flat=True))
            ).order_by('?')[:limit - similar_pets.count()]
            similar_pets = list(similar_pets) + list(additional_pets)
        
        return similar_pets[:limit]


class PetStatisticsAPIView(APIView):
    """
    API для получения статистики по питомцам.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Возвращает статистику по питомцам пользователя."""
        user = request.user
        
        # Получаем питомцев пользователя
        user_pets = Pet._default_manager.filter(owners=user)
        
        # Базовая статистика
        total_pets = user_pets.count()
        pets_by_type = user_pets.values('pet_type__name').annotate(
            count=models.Count('id')
        ).order_by('-count')
        
        # Статистика по возрасту
        age_stats = {
            'young': user_pets.filter(birth_date__gte=timezone.now().date() - timedelta(days=365*2)).count(),
            'adult': user_pets.filter(
                birth_date__lt=timezone.now().date() - timedelta(days=365*2),
                birth_date__gte=timezone.now().date() - timedelta(days=365*7)
            ).count(),
            'senior': user_pets.filter(birth_date__lt=timezone.now().date() - timedelta(days=365*7)).count(),
        }
        
        # Статистика по медицинским условиям
        pets_with_medical_conditions = user_pets.filter(
            ~Q(medical_conditions={}) & ~Q(medical_conditions__isnull=True)
        ).count()
        
        pets_with_special_needs = user_pets.filter(
            ~Q(special_needs={}) & ~Q(special_needs__isnull=True)
        ).count()
        
        # Статистика по последним посещениям
        recent_visits = user_pets.filter(
            records__date__gte=timezone.now() - timedelta(days=30)
        ).distinct().count()
        
        return Response({
            'total_pets': total_pets,
            'pets_by_type': list(pets_by_type),
            'age_distribution': age_stats,
            'pets_with_medical_conditions': pets_with_medical_conditions,
            'pets_with_special_needs': pets_with_special_needs,
            'recent_visits': recent_visits,
        }) 