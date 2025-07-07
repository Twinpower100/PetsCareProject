from rest_framework import viewsets, permissions, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework.views import APIView
from django.utils import timezone
from datetime import timedelta
from users.models import User
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Pet, MedicalRecord, PetRecord, PetAccess, PetOwnershipInvite, PetRecordFile, DocumentType
from .serializers import (
    PetSerializer,
    MedicalRecordSerializer,
    PetRecordSerializer,
    PetAccessSerializer,
    PetRecordFileSerializer,
    PetOwnershipInviteSerializer,
    DocumentTypeSerializer
)
from providers.models import EmployeeProvider
from django.core.mail import send_mail
from django.conf import settings
import uuid
import qrcode
from io import BytesIO
import base64
from django.core.exceptions import ValidationError


class PetViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing pets.
    
    Features:
    - CRUD operations
    - Search for pets
    - Filtering and sorting
    """
    queryset = Pet.objects.all()
    serializer_class = PetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает список питомцев текущего пользователя"""
        return self.queryset.filter(owners=self.request.user)

    @action(detail=False, methods=['get'])
    def my_pets(self, request):
        """Возвращает список питомцев текущего пользователя"""
        pets = self.get_queryset()
        serializer = self.get_serializer(pets, many=True)
        return Response(serializer.data)


class MedicalRecordViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing medical records.
    """
    queryset = MedicalRecord.objects.all()
    serializer_class = MedicalRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает медицинские записи питомцев текущего пользователя"""
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
    queryset = PetRecord.objects.all()
    serializer_class = PetRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает записи питомцев текущего пользователя"""
        return self.queryset.filter(pet__owners=self.request.user)

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
                employee = Employee.objects.get(pk=employee_id)
                # Проверяем, что этот сотрудник — текущий пользователь
                if employee.user == user:
                    # Проверяем, что сотрудник активен в этом провайдере
                    is_employee_for_provider = EmployeeProvider.objects.filter(
                        employee=employee,
                        provider_id=provider_id,
                        end_date__isnull=True
                    ).exists()
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
    queryset = PetAccess.objects.all()
    serializer_class = PetAccessSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает доступы к питомцам текущего пользователя"""
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
    queryset = DocumentType.objects.all()
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
        if category_id:
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

    def delete(self, request, pet_id):
        """Удаляет питомца"""
        pet = get_object_or_404(Pet, pk=pet_id)
        user = request.user
        is_main_owner = (pet.main_owner == user)
        is_admin = user.is_staff or user.is_superuser

        if not (is_main_owner or is_admin):
            raise permissions.PermissionDenied(_('Only main owner or admin can delete this pet'))
        pet.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PetListCreateAPIView(generics.ListCreateAPIView):
    """
    API for creating and getting a list of pets.
    """
    queryset = Pet.objects.all()
    serializer_class = PetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает список питомцев текущего пользователя"""
        return self.queryset.filter(owners=self.request.user)


class PetRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Pet.objects.all()
    serializer_class = PetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(owners=self.request.user)


class MedicalRecordListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = MedicalRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return MedicalRecord.objects.filter(pet__owners=self.request.user)


class MedicalRecordRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MedicalRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return MedicalRecord.objects.filter(pet__owners=self.request.user)


class PetRecordListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = PetRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PetRecord.objects.filter(pet__owners=self.request.user)


class PetRecordRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PetRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PetRecord.objects.filter(pet__owners=self.request.user)


class PetAccessListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = PetAccessSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PetAccess.objects.filter(pet__owners=self.request.user)


class PetAccessRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PetAccessSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PetAccess.objects.filter(pet__owners=self.request.user)


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
        
        # Сотрудник может загружать в записи где он исполнитель или своего учреждения
        if user.has_role('employee'):
            from providers.models import Employee, EmployeeProvider
            
            try:
                employee = Employee.objects.get(user=user)
                # Проверяем, что сотрудник является исполнителем записи
                if record.employee == employee:
                    return True
                
                # Проверяем, что сотрудник работает в учреждении записи
                is_employee_for_provider = EmployeeProvider.objects.filter(
                    employee=employee,
                    provider=record.provider,
                    status__in=['active', 'temporary']
                ).exists()
                
                if is_employee_for_provider:
                    return True
            except Employee.DoesNotExist:
                pass
        
        # Администратор учреждения может загружать в записи своего учреждения
        if user.has_role('provider_admin'):
            from providers.models import EmployeeProvider
            
            # Проверяем, что пользователь является админом учреждения записи
            is_admin_for_provider = EmployeeProvider.objects.filter(
                employee__user=user,
                provider=record.provider,
                is_manager=True,
                status__in=['active', 'temporary']
            ).exists()
            
            if is_admin_for_provider:
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
            pet_record_file = PetRecordFile.objects.create(**document_data)
            
            # Сериализуем результат
            serializer = PetRecordFileSerializer(pet_record_file)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': _('Error saving document')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PetInviteAPIView(APIView):
    """
    API for generating an invite (email/QR) for adding a co-owner or transferring the main owner's rights.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pet_id):
        """Генерирует инвайт"""
        pet = get_object_or_404(Pet, id=pet_id)
        invite_type = request.data.get('type')  # 'invite' или 'transfer'
        email = request.data.get('email')
        expires_in = int(request.data.get('expires_in', 24))  # часов
        if pet.main_owner != request.user:
            return Response({'error': _('Only main owner can invite or transfer ownership')}, status=403)
        if invite_type not in ['invite', 'transfer']:
            return Response({'error': _('Invalid invite type')}, status=400)
        if not email:
            return Response({'error': _('Email is required')}, status=400)
        token = uuid.uuid4()
        expires_at = timezone.now() + timezone.timedelta(hours=expires_in)
        invite = PetOwnershipInvite.objects.create(
            pet=pet,
            email=email,
            token=token,
            expires_at=expires_at,
            type=invite_type,
            invited_by=request.user
        )
        # Email отправка (stub)
        link = f"{settings.FRONTEND_URL}/pet-invite/{token}/"
        send_mail(
            subject=_('Pet ownership invitation'),
            message=_('You have been invited to become an owner of pet "{pet}". Use this link: {link}').format(pet=pet.name, link=link),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True
        )
        serializer = PetOwnershipInviteSerializer(invite)
        return Response(serializer.data)


class PetAcceptInviteAPIView(APIView):
    """
    API for confirming an invite (by token).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Подтверждает инвайт"""
        token = request.data.get('token')
        if not token:
            return Response({'error': _('Token is required')}, status=400)
        try:
            invite = PetOwnershipInvite.objects.get(token=token, is_used=False)
        except PetOwnershipInvite.DoesNotExist:
            return Response({'error': _('Invalid or expired invite')}, status=404)
        if invite.is_expired():
            return Response({'error': _('Invite expired')}, status=400)
        pet = invite.pet
        user = request.user
        if invite.type == 'invite':
            pet.owners.add(user)
        elif invite.type == 'transfer':
            pet.main_owner = user
            if user not in pet.owners.all():
                pet.owners.add(user)
        pet.save()
        invite.is_used = True
        invite.save()
        return Response({'status': 'success'})


class PetInviteQRCodeAPIView(APIView):
    """
    API for generating a QR code by invite token (transfer rights or adding a co-owner).
    Returns base64 PNG.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, token):
        """Генерирует QR-код по токену"""
        try:
            invite = PetOwnershipInvite.objects.get(token=token, is_used=False)
        except PetOwnershipInvite.DoesNotExist:
            return Response({'error': _('Invalid or expired invite')}, status=404)
        if invite.is_expired():
            return Response({'error': _('Invite expired')}, status=400)
        # Генерируем ссылку для подтверждения
        link = f"{settings.FRONTEND_URL}/pet-invite/{token}/"
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return Response({'qr_code_base64': img_base64, 'link': link})


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
                employee = Employee.objects.get(user=user)
                # Проверяем, что сотрудник работает в учреждении, где есть записи питомца
                has_records_for_pet = PetRecord.objects.filter(
                    pet=document.pet,
                    employee=employee
                ).exists()
                
                if has_records_for_pet:
                    return True
                
                # Проверяем, что сотрудник работает в учреждении, где есть записи питомца
                provider_records = PetRecord.objects.filter(
                    pet=document.pet
                ).values_list('provider', flat=True).distinct()
                
                is_employee_for_providers = EmployeeProvider.objects.filter(
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
            
            provider_records = PetRecord.objects.filter(
                pet=document.pet
            ).values_list('provider', flat=True).distinct()
            
            is_admin_for_providers = EmployeeProvider.objects.filter(
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