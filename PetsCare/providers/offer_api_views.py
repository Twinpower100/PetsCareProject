"""
API представления для работы с публичной офертой.

Этот модуль содержит API endpoints для:
1. Получения текста оферты для провайдера
2. Принятия публичной оферты провайдером
3. Проверки VAT номеров через VIES API
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework import status
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from .models import Provider
from billing.services_offer import VATVerificationService
# УДАЛЕНО: OfferGeneratorService - используйте DocumentGeneratorService из приложения legal
from legal.services import DocumentGeneratorService
from legal.models import LegalDocument, CountryLegalConfig, DocumentAcceptance


def _user_has_role(user, role_name):
    """
    Безопасная проверка роли пользователя.
    """
    if not user.is_authenticated:
        return False
    return hasattr(user, 'has_role') and user.has_role(role_name)


class ProviderOfferAPIView(APIView):
    """
    API для получения текста оферты для провайдера.
    
    GET /api/providers/{provider_id}/offer/
    - Возвращает персонализированный текст оферты с подставленными переменными
    - Включает информацию о необходимости акцепта
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, provider_id):
        """
        Получает текст оферты для провайдера.
        
        Returns:
            - content: текст оферты с подставленными переменными
            - variables: использованные переменные
            - offer: информация об оферте
            - pending_acceptance: требуется ли акцепт (True/False)
        """
        # Получаем провайдера
        try:
            provider = Provider.objects.get(id=provider_id)
        except Provider.DoesNotExist:
            return Response(
                {'error': _('Provider not found')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Проверяем права доступа
        if _user_has_role(request.user, 'provider_admin'):
            managed_providers = request.user.get_managed_providers()
            if provider not in managed_providers:
                raise PermissionDenied(
                    _('You can only view offers for your own organization.')
                )
        elif not (_user_has_role(request.user, 'system_admin') or request.user.is_superuser):
            raise PermissionDenied(
                _('You do not have permission to view offers.')
            )
        
        # НОВЫЙ ПОДХОД: Используем DocumentGeneratorService
        language = request.query_params.get('language', 'en')
        doc_service = DocumentGeneratorService()
        doc_result = doc_service.get_global_offer_for_provider(provider, language)
        
        if doc_result.get('success'):
            # Получаем региональные дополнения
            addendums_result = doc_service.get_regional_addendums_for_provider(provider, language)
            addendums = []
            for add_result in addendums_result:
                if add_result.get('success'):
                    addendums.append({
                        'id': add_result['document'].id,
                        'title': add_result['document'].title,
                        'content': add_result['content'],
                        'region_code': add_result['document'].region_code,
                        'addendum_type': add_result['document'].addendum_type,
                        'version': add_result['document'].version,
                    })
            
            # Проверяем, требуется ли акцепт
            pending_offer = provider.get_pending_offer_acceptance()
            
            return Response({
                'content': doc_result['content'],
                'variables': doc_result['variables'],
                'offer': {
                    'id': doc_result['document'].id,
                    'version': doc_result['document'].version,
                    'title': doc_result['document'].title,
                    'effective_date': doc_result['document'].effective_date.isoformat(),
                    'commission_percent': doc_result['variables'].get('commission_percent', '5.00'),
                },
                'regional_addendums': addendums,
                'pending_acceptance': pending_offer is not None,
                'pending_offer_id': pending_offer.id if pending_offer else None,
            })
        
        # Если новый подход не сработал, возвращаем ошибку
        return Response(
            {'error': _('No active offer found for provider country')},
            status=status.HTTP_404_NOT_FOUND
        )


class ProviderAcceptOfferAPIView(APIView):
    """
    API для принятия публичной оферты провайдером.
    
    POST /api/providers/{provider_id}/accept-offer/
    Body: {
        "offer_id": 1,  # опционально, если не указан - берется активная оферта
        "accepted_addendums": [1, 2]  # опционально, ID региональных дополнений
    }
    
    Создает ProviderOfferAcceptance с записью IP, user_agent, времени акцепта.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, provider_id):
        """
        Принимает публичную оферту от провайдера.
        
        Сохраняет:
        - IP адрес
        - User Agent
        - Время акцепта
        - Пользователя, который акцептовал
        - Региональные дополнения (если указаны)
        """
        # Получаем провайдера
        try:
            provider = Provider.objects.get(id=provider_id)
        except Provider.DoesNotExist:
            return Response(
                {'error': _('Provider not found')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Проверяем права доступа
        if _user_has_role(request.user, 'provider_admin'):
            managed_providers = request.user.get_managed_providers()
            if provider not in managed_providers:
                raise PermissionDenied(
                    _('You can only accept offers for your own organization.')
                )
        else:
            raise PermissionDenied(
                _('Only provider admin can accept offers.')
            )
        
        # Используем LegalDocument
        document_id = request.data.get('document_id') or request.data.get('offer_id')
        document = None
        
        if document_id:
            try:
                document = LegalDocument.objects.get(
                    id=document_id,
                    document_type__code='global_offer',
                    is_active=True
                )
            except LegalDocument.DoesNotExist:
                return Response(
                    {'error': _('Document not found or not active')},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Получаем оферту для страны провайдера
            if provider.country:
                try:
                    country_config = CountryLegalConfig.objects.get(country=provider.country)
                    document = country_config.global_offer
                except CountryLegalConfig.DoesNotExist:
                    pass
            
            if not document:
                return Response(
                    {'error': _('No active offer found for provider country')},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Проверяем, не акцептована ли уже эта оферта
        existing_acceptance = DocumentAcceptance.objects.filter(
            provider=provider,
            document=document,
            is_active=True
        ).first()
        
        if existing_acceptance:
            return Response(
                {'error': _('This offer has already been accepted')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Получаем IP и User Agent
        ip_address = self._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Региональные дополнения: из запроса или по стране провайдера (одна запись на документ)
        addendums_documents = []
        document_ids = request.data.get('accepted_addendums_documents', [])
        if document_ids:
            addendums_documents = list(LegalDocument.objects.filter(
                id__in=document_ids,
                document_type__code='regional_addendum',
                is_active=True
            ))
        if not addendums_documents and provider.country:
            _country_code = getattr(provider.country, 'code', None) or (str(provider.country) if provider.country else None)
            if _country_code:
                try:
                    country_config = CountryLegalConfig.objects.get(country=_country_code)
                    addendums_documents = list(country_config.regional_addendums.filter(is_active=True))
                except CountryLegalConfig.DoesNotExist:
                    from utils.countries import get_region_code
                    region_code = get_region_code(_country_code)
                    if region_code:
                        addendums_documents = list(LegalDocument.objects.filter(
                            document_type__code='regional_addendum',
                            region_code=region_code,
                            is_active=True
                        ))
        
        # Одна запись DocumentAcceptance на каждый документ
        acceptance = DocumentAcceptance.objects.create(
            provider=provider,
            document=document,
            accepted_by=request.user,
            document_version=document.version,
            ip_address=ip_address,
            user_agent=user_agent,
            is_active=True
        )
        for addendum in addendums_documents:
            if not DocumentAcceptance.objects.filter(provider=provider, document=addendum, is_active=True).exists():
                DocumentAcceptance.objects.create(
                    provider=provider,
                    document=addendum,
                    accepted_by=request.user,
                    document_version=addendum.version,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    is_active=True
                )
        
        offer_version = document.version
        offer_id = document.id
        
        return Response({
            'success': True,
            'message': _('Offer accepted successfully'),
            'acceptance': {
                'id': acceptance.id,
                'accepted_at': acceptance.accepted_at,
                'offer_version': offer_version,
                'offer_id': offer_id,
            }
        }, status=status.HTTP_201_CREATED)
    
    def _get_client_ip(self, request):
        """
        Получает IP адрес клиента из запроса.
        
        Args:
            request: Django request объект
            
        Returns:
            str: IP адрес или None
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class ProviderVerifyVATAPIView(APIView):
    """
    API для проверки VAT номера через VIES API.
    
    POST /api/providers/{provider_id}/verify-vat/
    Body: {
        "vat_number": "PL12345678"  # опционально, если не указан - берется из provider.vat_number
    }
    
    Проверяет VAT номер через VIES API и сохраняет результат в БД.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, provider_id):
        """
        Проверяет VAT номер провайдера через VIES API.
        
        Returns:
            - valid: валиден ли VAT номер
            - name: название компании (если валидно)
            - address: адрес компании (если валидно)
            - error: текст ошибки (если невалидно)
        """
        # Получаем провайдера
        try:
            provider = Provider.objects.get(id=provider_id)
        except Provider.DoesNotExist:
            return Response(
                {'error': _('Provider not found')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Проверяем права доступа
        if _user_has_role(request.user, 'provider_admin'):
            managed_providers = request.user.get_managed_providers()
            if provider not in managed_providers:
                raise PermissionDenied(
                    _('You can only verify VAT for your own organization.')
                )
        else:
            raise PermissionDenied(
                _('Only provider admin can verify VAT.')
            )
        
        # Проверяем, что страна указана
        if not provider.country:
            return Response(
                {'error': _('Provider country is required for VAT verification')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Проверяем, что страна в ЕС
        from utils.countries import is_eu_country
        if not is_eu_country(provider.country.code):
            return Response(
                {'error': _('VAT verification is only available for EU countries')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Получаем VAT номер
        vat_number = request.data.get('vat_number') or provider.vat_number
        if not vat_number:
            return Response(
                {'error': _('VAT number is required')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Обновляем VAT номер в провайдере, если он был указан в запросе
        if request.data.get('vat_number') and request.data.get('vat_number') != provider.vat_number:
            provider.vat_number = request.data.get('vat_number')
            provider.save(update_fields=['vat_number'])
        
        # Проверяем через VIES
        service = VATVerificationService()
        result = service.verify_and_save(provider)
        
        if result['valid']:
            return Response({
                'success': True,
                'valid': True,
                'name': result.get('name', ''),
                'address': result.get('address', ''),
                'request_date': result.get('request_date', ''),
                'vat_verified': provider.vat_verified,
                'vat_verification_date': provider.vat_verification_date,
            })
        else:
            return Response({
                'success': False,
                'valid': False,
                'error': result.get('error', _('VAT number is not valid')),
                'vat_verified': provider.vat_verified,
            }, status=status.HTTP_400_BAD_REQUEST)

