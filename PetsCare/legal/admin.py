"""
Админка для приложения legal.

Содержит административные представления для:
1. Типов юридических документов
2. Юридических документов
3. Переводов документов
4. Конфигурации стран
5. Принятия документов
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.contrib import messages
from django.utils.html import format_html
import logging

from .models import (
    LegalDocumentType,
    LegalDocument,
    DocumentTranslation,
    CountryLegalConfig,
    DocumentAcceptance
)
from custom_admin import custom_admin_site

logger = logging.getLogger(__name__)


def user_has_role(user, role_name):
    """Безопасная проверка роли пользователя"""
    if not user.is_authenticated:
        return False
    return hasattr(user, 'has_role') and user.has_role(role_name)


def _is_system_admin(user):
    """Безопасная проверка, является ли пользователь системным администратором"""
    from django.contrib.auth.models import AnonymousUser
    if isinstance(user, AnonymousUser):
        return False
    if not hasattr(user, 'is_system_admin'):
        return False
    try:
        return user.is_system_admin()
    except (AttributeError, TypeError):
        return False


# ============================================================================
# АДМИНКА ДЛЯ ТИПОВ ДОКУМЕНТОВ
# ============================================================================

class LegalDocumentTypeAdmin(admin.ModelAdmin):
    """Административное представление для типов юридических документов"""
    list_display = ('name', 'code', 'is_active', 'display_order', 'requires_billing_config', 'requires_region_code', 'requires_provider', 'allows_financial_terms')
    list_filter = ('is_active', 'requires_billing_config', 'requires_region_code', 'requires_addendum_type', 'requires_provider', 'allows_financial_terms')
    search_fields = ('name', 'code', 'description')
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('code', 'name', 'description', 'is_active', 'display_order')
        }),
        (_('Behavior Flags'), {
            'fields': (
                'requires_billing_config',
                'requires_region_code',
                'requires_addendum_type',
                'allows_variables',
                'requires_provider',
                'allows_financial_terms'
            ),
            'description': _('Flags that determine which fields are required for documents of this type')
        }),
        (_('Country Config Settings'), {
            'fields': (
                'is_required_for_all_countries',
                'is_multiple_allowed'
            ),
            'description': _('Settings for how this document type is used in country configurations')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')
    
    def has_module_permission(self, request):
        """Только системный админ имеет доступ к типам документов"""
        return request.user.is_superuser or _is_system_admin(request.user)


# ============================================================================
# АДМИНКА ДЛЯ ЮРИДИЧЕСКИХ ДОКУМЕНТОВ
# ============================================================================

class LegalDocumentAdmin(admin.ModelAdmin):
    """Административное представление для юридических документов"""
    list_display = ('title', 'document_type', 'version', 'region_code', 'is_active', 'effective_date')
    list_filter = ('document_type', 'is_active', 'effective_date', 'region_code', 'addendum_type')
    search_fields = ('title', 'version')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('document_type', 'title', 'version', 'is_active', 'effective_date')
        }),
        (_('Conditional Fields'), {
            'fields': ('billing_config', 'region_code', 'addendum_type', 'variables'),
            'description': _('These fields appear/disappear based on document type settings')
        }),
        (_('Side Letter Fields'), {
            'fields': ('providers', 'modified_clauses', 'document_file', 'signed_at'),
            'description': _('Fields for Side Letter documents (only for side_letter type)'),
            'classes': ('collapse',)
        }),
        (_('Financial Terms'), {
            'fields': (
                'commission_type', 'commission_percent', 'commission_fixed',
                'commission_min', 'commission_max', 'tiered_rates',
                'payment_deferral_days',
                'debt_threshold', 'overdue_threshold_1', 'overdue_threshold_2', 'overdue_threshold_3',
                'volume_discount_enabled', 'volume_discount_rules',
                'activity_bonus_enabled', 'activity_bonus_rules'
            ),
            'description': _('Financial terms (only for documents with allows_financial_terms=True)'),
            'classes': ('collapse',)
        }),
        (_('Change Notification'), {
            'fields': ('change_notification_days', 'notification_sent_at'),
            'description': _('Settings for notifying about document changes')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at', 'notification_sent_at')
    filter_horizontal = ('providers',)  # Для удобного выбора провайдеров
    
    def get_fieldsets(self, request, obj=None):
        """Динамически показываем/скрываем поля в зависимости от типа документа"""
        fieldsets = list(super().get_fieldsets(request, obj))
        
        # Определяем тип документа
        doc_type = None
        if obj and obj.document_type:
            doc_type = obj.document_type
        elif request.method == 'POST' and 'document_type' in request.POST:
            # При создании нового документа получаем тип из POST данных
            try:
                from .models import LegalDocumentType
                doc_type = LegalDocumentType.objects.get(pk=request.POST['document_type'])
            except (LegalDocumentType.DoesNotExist, ValueError, KeyError):
                pass
        elif request.method == 'GET' and 'document_type' in request.GET:
            # При выборе типа в форме создания
            try:
                from .models import LegalDocumentType
                doc_type = LegalDocumentType.objects.get(pk=request.GET['document_type'])
            except (LegalDocumentType.DoesNotExist, ValueError, KeyError):
                pass
        
        # Если тип документа определен, обновляем fieldsets
        if doc_type:
            # Обновляем Conditional Fields
            conditional_fields = []
            if doc_type.requires_billing_config:
                conditional_fields.append('billing_config')
            if doc_type.requires_region_code:
                conditional_fields.append('region_code')
            if doc_type.requires_addendum_type:
                conditional_fields.append('addendum_type')
            if doc_type.allows_variables:
                conditional_fields.append('variables')
            
            # Обновляем Side Letter Fields
            side_letter_fields = []
            if doc_type.requires_provider:
                side_letter_fields.append('providers')
                side_letter_fields.append('modified_clauses')
                side_letter_fields.append('document_file')
                side_letter_fields.append('signed_at')
            
            # Обновляем Financial Terms
            financial_fields = []
            if doc_type.allows_financial_terms:
                financial_fields = [
                    'commission_type', 'commission_percent', 'commission_fixed',
                    'commission_min', 'commission_max', 'tiered_rates',
                    'payment_deferral_days',
                    'debt_threshold', 'overdue_threshold_1', 'overdue_threshold_2', 'overdue_threshold_3',
                    'volume_discount_enabled', 'volume_discount_rules',
                    'activity_bonus_enabled', 'activity_bonus_rules'
                ]
            
            # Обновляем fieldsets
            for fieldset in fieldsets:
                # Ensure classes are mutable (tuple -> list)
                fieldset[1]['classes'] = list(fieldset[1].get('classes', []))
                if fieldset[0] == _('Conditional Fields'):
                    if conditional_fields:
                        fieldset[1]['fields'] = conditional_fields
                        if 'collapse' in fieldset[1]['classes']:
                            fieldset[1]['classes'].remove('collapse')
                    else:
                        # Скрываем, если нет полей
                        fieldset[1]['fields'] = None
                        if 'collapse' not in fieldset[1].get('classes', []):
                            fieldset[1].setdefault('classes', []).append('collapse')
                elif fieldset[0] == _('Side Letter Fields'):
                    if side_letter_fields:
                        fieldset[1]['fields'] = side_letter_fields
                        if 'collapse' in fieldset[1]['classes']:
                            fieldset[1]['classes'].remove('collapse')
                    else:
                        # Скрываем, если нет полей (для global_offer и других типов)
                        fieldset[1]['fields'] = None
                        if 'collapse' not in fieldset[1].get('classes', []):
                            fieldset[1].setdefault('classes', []).append('collapse')
                elif fieldset[0] == _('Financial Terms'):
                    if financial_fields:
                        fieldset[1]['fields'] = financial_fields
                        if 'collapse' in fieldset[1]['classes']:
                            fieldset[1]['classes'].remove('collapse')
                    else:
                        # Скрываем, если нет полей
                        fieldset[1]['fields'] = None
                        if 'collapse' not in fieldset[1].get('classes', []):
                            fieldset[1].setdefault('classes', []).append('collapse')
        else:
            # Если тип документа не выбран, скрываем все условные поля
            for fieldset in fieldsets:
                if fieldset[0] in (_('Side Letter Fields'), _('Financial Terms')):
                    fieldset[1]['fields'] = None
                    if 'collapse' not in fieldset[1].get('classes', []):
                        fieldset[1].setdefault('classes', []).append('collapse')
        
        # Удаляем пустые fieldsets (где fields = None)
        fieldsets = [fs for fs in fieldsets if fs[1].get('fields') is not None]
        
        return fieldsets
    
    def has_module_permission(self, request):
        """Только системный админ имеет доступ к юридическим документам"""
        return request.user.is_superuser or _is_system_admin(request.user)


# ============================================================================
# АДМИНКА ДЛЯ ПЕРЕВОДОВ (ОТДЕЛЬНАЯ)
# ============================================================================

class DocumentTranslationAdmin(admin.ModelAdmin):
    """
    Административное представление для переводов документов.
    
    Контент можно редактировать двумя способами:
    1. Через CKEditor (WYSIWYG редактор) - напрямую в поле Content
    2. Загрузить DOCX файл - будет автоматически сконвертирован в HTML
    """
    list_display = ('document', 'language', 'document_region', 'has_docx_file', 'has_content', 'created_at')
    list_filter = ('language', 'document__document_type', 'document__region_code')
    search_fields = ('document__title', 'language')
    
    fieldsets = (
        (_('Translation'), {
            'fields': ('document', 'language')
        }),
        (_('Content'), {
            'fields': ('content',),
            'description': _('Edit content directly using the WYSIWYG editor, or upload a DOCX file below to auto-convert.')
        }),
        (_('DOCX File (Optional)'), {
            'fields': ('content_docx_file',),
            'description': _('Upload DOCX file to auto-convert to HTML. This will REPLACE the content above.'),
            'classes': ('collapse',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')
    
    def document_region(self, obj):
        """Регион документа"""
        return obj.document.region_code if obj and obj.document and obj.document.region_code else '-'
    document_region.short_description = _('Region')
    document_region.admin_order_field = 'document__region_code'
    
    def has_docx_file(self, obj):
        """Проверка наличия DOCX файла"""
        return bool(obj.content_docx_file) if obj else False
    has_docx_file.boolean = True
    has_docx_file.short_description = _('Has DOCX File')
    
    def has_content(self, obj):
        """Проверка наличия HTML контента"""
        return bool(obj.content) if obj else False
    has_content.boolean = True
    has_content.short_description = _('Has Content')
    
    def get_urls(self):
        """Добавляем кастомный URL для конвертации DOCX файлов"""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/convert-docx/',
                self.admin_site.admin_view(self.convert_docx_view),
                name='legal_documenttranslation_convert_docx',
            ),
            path(
                'convert-docx-preview/',
                self.admin_site.admin_view(self.convert_docx_preview_view),
                name='legal_documenttranslation_convert_docx_preview',
            ),
        ]
        return custom_urls + urls
    
    def convert_docx_preview_view(self, request):
        """View для конвертации DOCX файлов БЕЗ сохранения объекта (для страницы создания)"""
        if request.method != 'POST':
            return JsonResponse({'error': _('Only POST method allowed')}, status=405)
        
        try:
            try:
                import mammoth
            except ImportError:
                return JsonResponse({
                    'error': _('Mammoth library is not installed')
                }, status=500)
            
            converted_content = {}
            
            # Настройка style_map для сохранения форматирования, включая нумерацию
            style_map = """
            p[style-name='List Paragraph'] => ol > li:fresh
            p[style-name='List Number'] => ol > li:fresh
            p[style-name='List Number 2'] => ol > li:fresh
            p[style-name='List Number 3'] => ol > li:fresh
            p[style-name='List Bullet'] => ul > li:fresh
            p[style-name='List Bullet 2'] => ul > li:fresh
            p[style-name='List Bullet 3'] => ul > li:fresh
            p[style-name='Heading 1'] => h1:fresh
            p[style-name='Heading 2'] => h2:fresh
            p[style-name='Heading 3'] => h3:fresh
            p[style-name='Title'] => h1.title:fresh
            p[style-name='Subtitle'] => h2.subtitle:fresh
            """
            
            # Опции конвертации для сохранения форматирования
            convert_options = {
                'style_map': style_map,
                'include_default_style_map': True,  # Сохраняет базовое форматирование
            }
            
            # Обрабатываем загруженный файл
            if 'content_docx_file' in request.FILES:
                docx_file = request.FILES['content_docx_file']
                try:
                    result = mammoth.convert_to_html(docx_file, **convert_options)
                    html_content = result.value
                    if html_content and len(html_content.strip()) > 0:
                        # Постобработка HTML для сохранения явной нумерации и форматирования
                        # Используем метод из модели DocumentTranslation
                        from .models import DocumentTranslation
                        temp_translation = DocumentTranslation()
                        html_content = temp_translation._postprocess_html_numbering(html_content)
                        converted_content['content'] = html_content
                except Exception as e:
                    logger.error(f'Error converting DOCX: {str(e)}', exc_info=True)
                    return JsonResponse({
                        'error': _('Error converting DOCX file: {error}').format(error=str(e))
                    }, status=500)
            
            if not converted_content:
                return JsonResponse({
                    'error': _('No DOCX file provided or conversion failed')
                }, status=400)
            
            return JsonResponse({
                'success': True,
                'content': converted_content,
                'message': _('Successfully converted DOCX file')
            })
            
        except Exception as e:
            logger.error(f'Error in convert_docx_preview_view: {str(e)}', exc_info=True)
            return JsonResponse({
                'error': _('Internal server error: {error}').format(error=str(e))
            }, status=500)
    
    def convert_docx_view(self, request, object_id):
        """View для конвертации DOCX файлов"""
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404
        
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        
        result = obj.convert_docx_file()
        
        if result['success']:
            messages.success(request, result['message'])
        else:
            messages.error(request, result['message'])
        
        return HttpResponseRedirect(
            reverse('admin:legal_documenttranslation_change', args=[object_id])
        )
    
    def has_module_permission(self, request):
        """Только системный админ имеет доступ к переводам"""
        return request.user.is_superuser or _is_system_admin(request.user)


# ============================================================================
# АДМИНКА ДЛЯ КОНФИГУРАЦИИ СТРАН
# ============================================================================

class CountryLegalConfigAdmin(admin.ModelAdmin):
    """Административное представление для конфигурации стран"""
    list_display = ('country', 'global_offer', 'has_regional_addendums', 'privacy_policy', 'terms_of_service')
    list_filter = ('country',)
    search_fields = ('country',)
    filter_horizontal = ('regional_addendums',)
    
    fieldsets = (
        (_('Country'), {
            'fields': ('country',)
        }),
        (_('Required Documents'), {
            'fields': ('global_offer',)
        }),
        (_('Regional Addendums'), {
            'fields': ('regional_addendums',),
            'description': _('Regional addendums required for this country (can be multiple)')
        }),
        (_('Optional Documents'), {
            'fields': ('privacy_policy', 'terms_of_service', 'cookie_policy'),
            'description': _('Optional legal documents for this country')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')
    
    def has_regional_addendums(self, obj):
        """Проверка наличия региональных дополнений"""
        return obj.regional_addendums.exists() if obj else False
    has_regional_addendums.boolean = True
    has_regional_addendums.short_description = _('Has Regional Addendums')
    
    def has_module_permission(self, request):
        """Только системный админ имеет доступ к конфигурации стран"""
        return request.user.is_superuser or _is_system_admin(request.user)


# ============================================================================
# АДМИНКА ДЛЯ ПРИНЯТИЯ ДОКУМЕНТОВ
# ============================================================================

class DocumentAcceptanceAdmin(admin.ModelAdmin):
    """Административное представление для принятия документов"""
    list_display = ('document', 'accepted_by', 'provider', 'document_version', 'accepted_at', 'is_active')
    list_filter = ('is_active', 'accepted_at', 'document__document_type')
    search_fields = ('accepted_by__email', 'provider__name', 'document__title')
    readonly_fields = ('accepted_at',)
    
    fieldsets = (
        (_('Acceptance'), {
            'fields': ('document', 'document_version', 'accepted_by', 'provider', 'is_active')
        }),
        (_('Metadata'), {
            'fields': ('accepted_at', 'ip_address', 'user_agent'),
            'description': _('Metadata about when and how the document was accepted')
        })
    )
    
    def has_module_permission(self, request):
        """Только системный админ имеет доступ к принятию документов"""
        return request.user.is_superuser or _is_system_admin(request.user)


# Регистрация в кастомном админ-сайте
custom_admin_site.register(LegalDocumentType, LegalDocumentTypeAdmin)
custom_admin_site.register(LegalDocument, LegalDocumentAdmin)
custom_admin_site.register(DocumentTranslation, DocumentTranslationAdmin)
custom_admin_site.register(CountryLegalConfig, CountryLegalConfigAdmin)
custom_admin_site.register(DocumentAcceptance, DocumentAcceptanceAdmin)
