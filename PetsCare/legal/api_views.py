"""
API views для юридических документов.

Этот модуль содержит представления для:
1. Получения документов для провайдеров
2. Получения документов для пользователей
3. Принятия документов
4. Получения конфигурации для стран
"""

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
import sys

from .models import (
    LegalDocument,
    LegalDocumentType,
    DocumentTranslation,
    CountryLegalConfig,
    DocumentAcceptance
)
from .serializers import (
    LegalDocumentSerializer,
    LegalDocumentListSerializer,
    DocumentTranslationSerializer,
    CountryLegalConfigSerializer,
    DocumentAcceptanceSerializer,
    DocumentAcceptanceCreateSerializer
)
from .services import DocumentGeneratorService
from providers.models import Provider
import logging

logger = logging.getLogger(__name__)


class LegalDocumentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для чтения юридических документов.
    Только чтение - создание/изменение через админку.
    """
    queryset = LegalDocument.objects.filter(is_active=True)
    serializer_class = LegalDocumentListSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return LegalDocumentSerializer
        return LegalDocumentListSerializer


class ProviderOfferAPIView(APIView):
    """
    API для получения оферты для провайдера.
    
    GET /api/v1/legal/providers/{provider_id}/offer/?language=en
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, provider_id):
        """Получает оферту для провайдера с подстановкой переменных"""
        provider = get_object_or_404(Provider, id=provider_id)
        
        # Проверяем права доступа
        if not self._has_access_to_provider(request.user, provider):
            return Response(
                {'error': _('You do not have access to this provider')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        language = request.query_params.get('language', 'en')
        service = DocumentGeneratorService()
        result = service.get_global_offer_for_provider(provider, language)
        
        if not result.get('success'):
            return Response(
                {'error': result.get('error', _('Failed to generate offer'))},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response({
            'content': result['content'],
            'document': {
                'id': result['document'].id,
                'title': result['document'].title,
                'version': result['document'].version,
            },
            'variables': result['variables']
        })
    
    def _has_access_to_provider(self, user, provider):
        """Проверяет, имеет ли пользователь доступ к провайдеру"""
        # Суперпользователь имеет доступ
        if user.is_superuser:
            return True
        
        # Проверяем, является ли пользователь администратором провайдера
        if hasattr(user, 'is_provider_admin'):
            try:
                if user.is_provider_admin() and user.provider_admin_providers.filter(id=provider.id).exists():
                    return True
            except:
                pass
        
        # Проверяем, является ли пользователь биллинг-менеджером
        if hasattr(user, 'is_billing_manager'):
            try:
                if user.is_billing_manager():
                    return True
            except:
                pass
        
        return False


class ProviderRegionalAddendumsAPIView(APIView):
    """
    API для получения региональных дополнений для провайдера.
    
    GET /api/v1/legal/providers/{provider_id}/regional-addendums/?language=en
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, provider_id):
        """Получает региональные дополнения для провайдера"""
        provider = get_object_or_404(Provider, id=provider_id)
        
        # Проверяем права доступа
        if not self._has_access_to_provider(request.user, provider):
            return Response(
                {'error': _('You do not have access to this provider')},
                status=status.HTTP_403_FORBIDDEN
            )
        
        language = request.query_params.get('language', 'en')
        service = DocumentGeneratorService()
        results = service.get_regional_addendums_for_provider(provider, language)
        
        addendums = []
        for result in results:
            if result.get('success'):
                addendums.append({
                    'id': result['document'].id,
                    'title': result['document'].title,
                    'content': result['content'],
                    'region_code': result['document'].region_code,
                    'addendum_type': result['document'].addendum_type,
                    'version': result['document'].version,
                })
        
        return Response({'addendums': addendums})
    
    def _has_access_to_provider(self, user, provider):
        """Проверяет, имеет ли пользователь доступ к провайдеру"""
        if user.is_superuser:
            return True
        if hasattr(user, 'is_provider_admin'):
            try:
                if user.is_provider_admin() and user.provider_admin_providers.filter(id=provider.id).exists():
                    return True
            except:
                pass
        if hasattr(user, 'is_billing_manager'):
            try:
                if user.is_billing_manager():
                    return True
            except:
                pass
        return False


class PublicDocumentAPIView(APIView):
    """
    Публичный API для получения документов (без авторизации).
    
    GET /api/v1/legal/documents/{document_type}/?country=DE&language=en
    """
    permission_classes = [permissions.AllowAny]
    
    def dispatch(self, request, *args, **kwargs):
        """Перехватываем dispatch для логирования всех запросов"""
        logger.info(f'PublicDocumentAPIView.dispatch called: path={request.path}, document_type={kwargs.get("document_type")}')
        return super().dispatch(request, *args, **kwargs)
    
    def get(self, request, document_type):
        """
        Получает документ по типу.
        
        Бэкенд сам определяет, нужен ли параметр country на основании флагов типа документа.
        
        Args:
            document_type: Код типа документа (global_offer, privacy_policy, terms_of_service, cookie_policy, regional_addendum)
            language: Язык документа (query param, по умолчанию 'en')
            country: Код страны (query param, опционально - используется только если требуется)
        """
        language = request.query_params.get('language', 'en')
        country_code = request.query_params.get('country')
        
        # Получаем тип документа
        try:
            doc_type = LegalDocumentType.objects.get(code=document_type, is_active=True)
            logger.info(f'Found document type: {doc_type.code}, is_required_for_all_countries={doc_type.is_required_for_all_countries}, requires_region_code={doc_type.requires_region_code}')
        except LegalDocumentType.DoesNotExist:
            logger.warning(f'Document type not found: {document_type}')
            return Response(
                {'error': _('Invalid document type')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Бэкенд сам определяет логику на основании флагов типа документа
        if doc_type.is_required_for_all_countries:
            # Документ одинаков для всех стран - ищем напрямую по типу
            # Параметр country игнорируется, если передан
            document = LegalDocument.objects.filter(
                document_type=doc_type,
                is_active=True
            ).order_by('-effective_date', '-created_at').first()
            
            logger.info(f'Document type requires all countries, found document: {document.id if document else None}')
            
            if not document:
                logger.warning(f'Document not found for type: {document_type}')
                return Response(
                    {'error': _('Document not found')},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Документ специфичен для страны/региона
            # Для regional_addendum используем region_code
            # Для других типов (если появятся) используем CountryLegalConfig
            
            if doc_type.requires_region_code:
                # Документ привязан к региону (например, regional_addendum)
                if not country_code:
                    return Response(
                        {'error': _('Country code is required for this document type')},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                try:
                    config = CountryLegalConfig.objects.get(country=country_code)
                except CountryLegalConfig.DoesNotExist:
                    return Response(
                        {'error': _('Legal configuration not found for this country')},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                document = config.regional_addendums.filter(
                    is_active=True
                ).order_by('-effective_date', '-created_at').first()
                
                if not document:
                    logger.warning(f'Document not found for type: {document_type}, country: {country_code}')
                    return Response(
                        {'error': _('Document not found for this country')},
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                # Документ специфичен для страны, но не требует region_code
                # Используем CountryLegalConfig
                if not country_code:
                    return Response(
                        {'error': _('Country code is required for this document type')},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                try:
                    config = CountryLegalConfig.objects.get(country=country_code)
                except CountryLegalConfig.DoesNotExist:
                    return Response(
                        {'error': _('Legal configuration not found for this country')},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Получаем документ нужного типа из конфигурации
                document = None
                if document_type == 'global_offer':
                    document = config.global_offer
                elif document_type == 'privacy_policy':
                    document = config.privacy_policy
                elif document_type == 'terms_of_service':
                    document = config.terms_of_service
                elif document_type == 'cookie_policy':
                    document = config.cookie_policy
                else:
                    return Response(
                        {'error': _('Invalid document type')},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                if not document:
                    return Response(
                        {'error': _('Document not found for this country')},
                        status=status.HTTP_404_NOT_FOUND
                    )
        
        # Получаем перевод на указанном языке с fallback на английский
        logger.info(f'Looking for translation: document_id={document.id}, language={language}')
        translation = document.translations.filter(language=language).first()
        if not translation:
            logger.warning(f'Translation not found for language={language}, trying fallback to en')
            # Fallback на английский
            translation = document.translations.filter(language='en').first()
            if not translation:
                logger.error(f'No translation found for document_id={document.id}, neither {language} nor en')
                return Response(
                    {'error': _('Translation not found')},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        logger.info(f'Successfully returning document: id={document.id}, language={translation.language}')
        return Response({
            'id': document.id,
            'title': document.title,
            'version': document.version,
            'content': translation.content,
            'language': translation.language,
            'effective_date': document.effective_date.isoformat(),
        })


class DocumentAcceptanceAPIView(APIView):
    """
    API для принятия документов.
    
    POST /api/v1/legal/documents/{document_id}/accept/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @transaction.atomic
    def post(self, request, document_id):
        """Принимает документ от имени пользователя или провайдера"""
        document = get_object_or_404(LegalDocument, id=document_id, is_active=True)
        
        # Определяем, кто принимает документ
        user = request.user
        provider = None
        
        # Если пользователь - администратор провайдера, принимаем от имени провайдера
        if hasattr(user, 'is_provider_admin') and user.is_provider_admin():
            try:
                provider = user.provider_admin_providers.first()
            except:
                pass
        
        # Проверяем, что не указаны оба (user и provider)
        if user and provider:
            # Приоритет - провайдер
            user = None
        
        # Получаем IP и User Agent
        ip_address = self._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Создаем запись о принятии
        acceptance = DocumentAcceptance(
            document=document,
            document_version=document.version,
            user=user if not provider else None,
            provider=provider,
            ip_address=ip_address,
            user_agent=user_agent,
            is_active=True
        )
        try:
            acceptance.full_clean()
        except DjangoValidationError as e:
            return Response(
                {'error': e.message_dict},
                status=status.HTTP_400_BAD_REQUEST
            )
        acceptance.save()
        
        serializer = DocumentAcceptanceSerializer(acceptance)
        return Response({
            'success': True,
            'message': _('Document accepted successfully'),
            'acceptance': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    def _get_client_ip(self, request):
        """Получает IP адрес клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class CountryLegalConfigAPIView(APIView):
    """
    API для получения конфигурации документов для страны.
    
    GET /api/v1/legal/countries/{country_code}/config/
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, country_code):
        """Получает конфигурацию документов для страны"""
        try:
            config = CountryLegalConfig.objects.get(country=country_code)
        except CountryLegalConfig.DoesNotExist:
            return Response(
                {'error': _('Legal configuration not found for this country')},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = CountryLegalConfigSerializer(config)
        return Response(serializer.data)


class CountryOfferForRegistrationAPIView(APIView):
    """
    Одна глобальная оферта для всех + региональные дополнения по региону страны.
    Страна → регион: get_region_code (DE→EU, RU→RU, UA→UA). Германия входит в EU.
    
    GET /api/v1/legal/registration/country/{country_code}/offer/?language=en&is_vat_payer=true
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, country_code):
        """Получает оферту и региональные дополнения для страны с подстановкой переменных"""
        language = request.query_params.get('language', 'en')
        is_vat_payer = request.query_params.get('is_vat_payer', 'true').lower() == 'true'
        
        try:
            from billing.models import VATRate
            from utils.countries import get_region_code
            
            country_upper = (country_code or '').upper()
            
            # Одна глобальная оферта для всех (не от CountryLegalConfig)
            global_offer = LegalDocument.objects.filter(
                document_type__code='global_offer', is_active=True
            ).first()
            if not global_offer:
                return Response(
                    {'error': _('Global offer is not configured'), 'error_code': 'NO_GLOBAL_OFFER_CONFIGURED'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Регион страны: DE→EU, RU→RU, UA→UA и т.д.
            region_code = get_region_code(country_upper)
            
            # VAT rate для страны (для {{vat_rate}} и {{tax_rate}})
            # tax_rate - это ставка НДС страны регистрации Сервиса (используется когда VAT ID невалиден)
            # Всегда получаем ставку для страны, независимо от статуса плательщика НДС
            vat_rate = None
            try:
                vat_rate_obj = VATRate.objects.filter(country=country_upper, is_active=True).first()
                if vat_rate_obj:
                    vat_rate = str(vat_rate_obj.rate)
            except:
                pass
            
            service = DocumentGeneratorService()
            
            # Перевод глобальной оферты
            translation = global_offer.translations.filter(language=language).first()
            if not translation:
                translation = global_offer.translations.filter(language='en').first()
                if not translation:
                    return Response(
                        {'error': _('Translation not found')},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            # Формируем переменные для подстановки
            variables = {}
            if global_offer.billing_config:
                variables['commission_percent'] = str(global_offer.billing_config.commission_percent)
                variables['payment_deferral_days'] = str(global_offer.billing_config.payment_deferral_days)
                variables['invoice_period_days'] = str(global_offer.billing_config.invoice_period_days)
            
            # Добавляем VAT rate (если плательщик НДС)
            if is_vat_payer and vat_rate:
                variables['vat_rate'] = vat_rate
                variables['tax_rate'] = vat_rate  # Алиас для tax_rate
            else:
                variables['vat_rate'] = '0%'  # или "не применяется"
                variables['tax_rate'] = '0%'  # Fallback для tax_rate
            
            # Добавляем переменные из документа
            if global_offer.variables:
                variables.update(global_offer.variables)
            
            # Добавляем дни уведомления об изменениях
            if global_offer.change_notification_days:
                variables['change_notification_days'] = str(global_offer.change_notification_days)
            
            # Подставляем переменные
            content = service._substitute_variables(translation.content, variables)
            
            # Региональные дополнения по региону (EU, RU, UA…); Германия → EU
            regional_addendums = []
            if region_code:
                addendums_qs = LegalDocument.objects.filter(
                    document_type__code='regional_addendum',
                    region_code=region_code,
                    is_active=True
                )
                for addendum in addendums_qs:
                    addendum_translation = addendum.translations.filter(language=language).first()
                    if not addendum_translation:
                        addendum_translation = addendum.translations.filter(language='en').first()
                    if not addendum_translation:
                        continue
                    addendum_variables = {}
                    if addendum.variables:
                        addendum_variables.update(addendum.variables)
                    if addendum.change_notification_days:
                        addendum_variables['change_notification_days'] = str(addendum.change_notification_days)
                    # Добавляем VAT rate для страны (всегда, если есть)
                    # Используется в тексте для случая, когда VAT ID невалиден
                    if vat_rate:
                        addendum_variables['vat_rate'] = vat_rate
                    addendum_content = service._substitute_variables(
                        addendum_translation.content, addendum_variables
                    )
                    regional_addendums.append({
                        'id': addendum.id,
                        'title': addendum.title,
                        'content': addendum_content,
                        'region_code': addendum.region_code,
                        'addendum_type': addendum.addendum_type,
                        'version': addendum.version,
                    })
            
            return Response({
                'global_offer': {
                    'id': global_offer.id,
                    'title': global_offer.title,
                    'content': content,
                    'version': global_offer.version,
                    'variables': variables
                },
                'regional_addendums': regional_addendums,
                'country': country_upper,
                'region_code': region_code
            })
            
        except Exception as e:
            logger.error(f'Error getting offer for country {country_code}: {str(e)}', exc_info=True)
            return Response(
                {'error': _('Failed to get offer for country')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
