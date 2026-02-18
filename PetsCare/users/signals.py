"""
Сигналы для автоматизации процессов пользователей.

Содержит:
- Автоматическое назначение ролей при регистрации
- Создание Provider при одобрении заявки
- Управление связями пользователей и учреждений
"""

import logging

from django.db.models import Q, Count, F, Value
from django.db.models.functions import Coalesce
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Проверяем, что Django полностью инициализирован
if settings.configured:
    from .models import UserType, ProviderForm
    
    # Все сигналы должны быть внутри этой проверки


def _parse_address_components(address_components):
    """
    Парсит компоненты адреса из ответа Google Maps API.
    
    Args:
        address_components: Список компонентов адреса из Google Maps API
        
    Returns:
        dict: Словарь с распарсенными компонентами адреса
    """
    parsed = {}
    
    for component in address_components:
        types = component.get('types', [])
        long_name = component.get('long_name', '')
        
        # Используем if вместо elif, чтобы проверить все типы
        if 'country' in types:
            parsed['country'] = long_name
        if 'administrative_area_level_1' in types:
            parsed['region'] = long_name
        if 'locality' in types:
            parsed['city'] = long_name
        if 'sublocality' in types:
            parsed['district'] = long_name
        if 'route' in types:
            parsed['street'] = long_name
        if 'street_number' in types:
            parsed['house_number'] = long_name
        if 'subpremise' in types:
            # Корпус или подъезд может быть в subpremise
            parsed['building'] = long_name
        if 'postal_code' in types:
            parsed['postal_code'] = long_name
        
        # Дополнительные типы для улиц и номеров домов
        if 'premise' in types and 'house_number' not in parsed:
            parsed['house_number'] = long_name
        if 'subpremise' in types and 'house_number' not in parsed:
            parsed['house_number'] = long_name
        if 'establishment' in types and 'street' not in parsed:
            parsed['street'] = long_name
        if 'point_of_interest' in types and 'street' not in parsed:
            parsed['street'] = long_name
        
        # Дополнительные типы для улиц
        if 'political' in types and 'street' not in parsed:
            parsed['street'] = long_name
        if 'sublocality_level_1' in types and 'street' not in parsed:
            parsed['street'] = long_name
        if 'sublocality_level_2' in types and 'street' not in parsed:
            parsed['street'] = long_name
    
    # Специальная обработка для адресов в Черногории
    if 'Montenegro' in parsed.get('country', ''):
        # Если не найдена улица, попробуем найти в других полях
        if 'street' not in parsed:
            # Ищем в formatted_address
            for component in address_components:
                if 'formatted_address' in component:
                    formatted = component['formatted_address']
                    # Пытаемся извлечь улицу из отформатированного адреса
                    parts = formatted.split(',')
                    if len(parts) > 0:
                        potential_street = parts[0].strip()
                        if potential_street and potential_street not in ['Montenegro', 'Bar']:
                            parsed['street'] = potential_street
                            break
    
    return parsed


# @receiver(post_save, sender=UserType)
def assign_default_role(sender, instance, created, **kwargs):
    """
    Автоматически назначает роль пользователю при создании типа пользователя.
    """
    # Проверяем, что Django полностью инициализирован
    if not settings.configured:
        return
        
    if created:
        # Логика назначения роли
        pass


@receiver(post_save, sender=UserType)
def assign_sitter_role(sender, instance, created, **kwargs):
    """
    Автоматически назначает роль ситтера при создании типа пользователя.
    """
    if created:
        # Логика назначения роли ситтера
        pass


@receiver(post_save, sender=UserType)
def assign_vet_role(sender, instance, created, **kwargs):
    """
    Автоматически назначает роль ветеринара при создании типа пользователя.
    """
    if created:
        # Логика назначения роли ветеринара
        pass


@receiver(post_save, sender=UserType)
def assign_provider_admin_role(sender, instance, created, **kwargs):
    """
    Автоматически назначает роль администратора провайдера при создании типа пользователя.
    """
    if created:
        # Логика назначения роли администратора провайдера
        pass


@receiver(post_save, sender=ProviderForm)
def create_provider_on_approval(sender, instance, created, **kwargs):
    """
    УПРОЩЕННЫЙ ПРОЦЕСС: Автоматически создает объект Provider сразу при создании заявки.
    Реквизиты и оферта уже обязательны в ProviderForm, поэтому провайдер создается сразу.
    """
    # Проверяем, что Django полностью инициализирован
    from django.conf import settings
    if not settings.configured:
        return
        
    # УПРОЩЕННЫЙ ПРОЦЕСС: создаем Provider сразу при создании заявки (не при одобрении)
    if created:
        import logging
        logger = logging.getLogger(__name__)
        
        # Импортируем User в начале функции, чтобы избежать UnboundLocalError
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Проверяем, не создан ли уже Provider для этой заявки
        from providers.models import Provider
        existing_provider = Provider.objects.filter(name=instance.provider_name).first()
        if not existing_provider:
            from django.db import transaction
            try:
                with transaction.atomic():
                    # Создаем структурированный адрес
                    from geolocation.models import Address
                    structured_address = None
                    
                    # Создаем структурированный адрес (с опциональными address_components из Google Places)
                    comp = getattr(instance, 'address_components', None)
                    if not isinstance(comp, dict):
                        comp = None
                    formatted_from_comp = (comp.get('formatted_address') or '').strip() if comp else ''
                    formatted_from_field = (instance.provider_address or '').strip()
                    has_address = bool(formatted_from_comp or formatted_from_field)

                    if has_address:
                        formatted_address = formatted_from_comp or formatted_from_field or ''
                        structured_address = Address.objects.create(
                            formatted_address=formatted_address,
                            validation_status='pending'
                        )
                        # Заполняем из address_components (Google Places Autocomplete), если есть
                        if comp:
                            for key, max_len in [
                                ('street', 200), ('house_number', 20), ('city', 100),
                                ('postal_code', 20), ('country', 100), ('region', 100), ('district', 100)
                            ]:
                                val = comp.get(key)
                                if val is not None and str(val).strip():
                                    setattr(structured_address, key, str(val).strip()[:max_len])
                            if formatted_from_comp:
                                structured_address.formatted_address = formatted_from_comp
                            lat, lng = comp.get('latitude'), comp.get('longitude')
                            if lat is not None and lng is not None:
                                try:
                                    from django.contrib.gis.geos import Point
                                    la, ln = float(lat), float(lng)
                                    structured_address.point = Point(ln, la, srid=4326)
                                    structured_address.latitude = la
                                    structured_address.longitude = ln
                                    structured_address.validation_status = 'valid'
                                    # location_type из Places API, если фронт передаёт
                                    structured_address.geocoding_accuracy = (
                                        comp.get('location_type') or
                                        comp.get('geometry', {}).get('location_type') or
                                        ''
                                    )
                                except (TypeError, ValueError):
                                    pass
                            structured_address.save()

                        # Геокодирование, если ещё нет координат
                        from django.conf import settings
                        import googlemaps
                        from django.contrib.gis.geos import Point

                        api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
                        address_text = formatted_address
                        
                        # Пытаемся улучшить формат адреса для лучшего распознавания
                        # Пробуем разные форматы адреса для Google Maps API
                        original_address = address_text
                        improved_addresses = [address_text]
                        
                        if ',' in address_text and address_text.count(',') >= 2:
                            parts = [p.strip() for p in address_text.split(',')]
                            if len(parts) >= 3:
                                street_part = parts[0]
                                number_part = parts[1] if parts[1].strip().isdigit() else None
                                city_part = parts[-1] if len(parts) > 2 else None
                                
                                if number_part and city_part:
                                    # Формат 1: "улица, город" (без номера дома)
                                    format1 = f"{street_part}, {city_part}"
                                    # Формат 2: "Ul. улица номер, город" (с префиксом Ul.)
                                    format2 = f"Ul. {street_part} {number_part}, {city_part}"
                                    improved_addresses = [format2, format1, address_text]
                        
                        if api_key and address_text and not structured_address.point:
                            gmaps = googlemaps.Client(key=api_key)
                            geocode_result = None
                            
                            # Пробуем разные форматы адреса
                            for test_address in improved_addresses:
                                geocode_result = gmaps.geocode(test_address)
                                
                                if geocode_result:
                                    # Проверяем, есть ли в результате улица и номер дома
                                    result = geocode_result[0]
                                    components = result.get('address_components', [])
                                    has_street = any('route' in comp.get('types', []) for comp in components)
                                    has_number = any('street_number' in comp.get('types', []) for comp in components)
                                    
                                    if has_street and has_number:
                                        break
                                    else:
                                        geocode_result = None
                            
                            if geocode_result:
                                result = geocode_result[0]
                                location = result['geometry']['location']
                                
                                # Преобразуем в float для избежания ошибок сериализации
                                lat = float(location['lat'])
                                lng = float(location['lng'])
                                
                                # Парсим компоненты адреса
                                address_components = result.get('address_components', [])
                                components = _parse_address_components(address_components)
                                
                                # Если не найдены улица и номер дома, попробуем обратное геокодирование
                                if not components.get('street') or not components.get('house_number'):
                                    try:
                                        reverse_result = gmaps.reverse_geocode((lat, lng))
                                        if reverse_result:
                                            reverse_components = reverse_result[0].get('address_components', [])
                                            reverse_parsed = _parse_address_components(reverse_components)
                                            
                                            # Дополняем недостающие поля из обратного геокодирования
                                            if not components.get('street') and reverse_parsed.get('street'):
                                                components['street'] = reverse_parsed['street']
                                            if not components.get('house_number') and reverse_parsed.get('house_number'):
                                                components['house_number'] = reverse_parsed['house_number']
                                            if not components.get('postal_code') and reverse_parsed.get('postal_code'):
                                                components['postal_code'] = reverse_parsed['postal_code']
                                    except Exception as e:
                                        logger.warning(f"Reverse geocoding failed: {e}")
                                
                                # Обновляем координаты
                                structured_address.point = Point(lng, lat, srid=4326)
                                structured_address.latitude = lat
                                structured_address.longitude = lng
                                structured_address.geocoding_accuracy = result.get('geometry', {}).get('location_type', '') or ''

                                # Обновляем структурированные поля
                                structured_address.formatted_address = result.get('formatted_address', '')
                                structured_address.country = components.get('country', '')
                                structured_address.region = components.get('region', '')
                                structured_address.city = components.get('city', '')
                                structured_address.district = components.get('district', '')
                                structured_address.street = components.get('street', '')
                                structured_address.house_number = components.get('house_number', '')
                                structured_address.building = components.get('building', '')
                                structured_address.postal_code = components.get('postal_code', '')
                                
                                # Пытаемся извлечь корпус из исходного адреса, если Google Maps не вернул его
                                if not structured_address.building and instance.provider_address:
                                    import re
                                    # Ищем паттерны типа "корп.1", "корпус 1", "к.1", "корп 1"
                                    building_patterns = [
                                        r'корп\.?\s*(\d+)',
                                        r'корпус\s*(\d+)',
                                        r'к\.?\s*(\d+)',
                                        r'корп\s*(\d+)',
                                        r'building\s*(\d+)',
                                        r'bld\.?\s*(\d+)',
                                    ]
                                    for pattern in building_patterns:
                                        match = re.search(pattern, instance.provider_address, re.IGNORECASE)
                                        if match:
                                            structured_address.building = match.group(1)
                                            break
                                
                                structured_address.validation_status = 'valid'
                                structured_address.save()
                            else:
                                logger.warning(f"No geocoding results for address '{address_text}'")
                        elif not structured_address.point:
                            logger.warning("Geocoding skipped - no API key or empty address")
                    else:
                        # Если адрес пустой, создаем пустой структурированный адрес
                        structured_address = Address.objects.create(
                            formatted_address="",
                            validation_status='pending'
                        )
                    
                    # Создаем объект Provider (организацию)
                    # УПРОЩЕННЫЙ ПРОЦЕСС: реквизиты и оферта уже заполнены в ProviderForm
                    # Код страны для проверки ЕС и активации (CountryField возвращает объект, EU_COUNTRIES — set строк)
                    from utils.countries import EU_COUNTRIES
                    _country_code = getattr(instance.country, 'code', None) or (str(instance.country) if instance.country else None)
                    is_eu = _country_code in EU_COUNTRIES if _country_code else False
                    # Для ЕС + плательщик НДС: активация только при valid/override; иначе activation_required
                    _vat_ok_or_not_required = (
                        instance.vat_verification_status == 'valid' or
                        instance.vat_verification_manual_override or
                        not instance.is_vat_payer or
                        not is_eu
                    )
                    
                    # Копируем реквизиты из ProviderForm в Provider
                    provider = Provider.objects.create(
                        name=instance.provider_name,
                        structured_address=structured_address,  # Юридический адрес организации
                        phone_number=str(instance.provider_phone),  # Преобразуем PhoneNumber в строку
                        email=instance.provider_email,  # provider_email теперь обязателен
                        # Копируем реквизиты из ProviderForm
                        tax_id=instance.tax_id,
                        registration_number=instance.registration_number,
                        country=instance.country,
                        invoice_currency=instance.invoice_currency,
                        # Дополнительные реквизиты
                        organization_type=instance.organization_type or '',
                        director_name=instance.director_name or '',
                        kpp=instance.kpp or '',
                        is_vat_payer=instance.is_vat_payer or False,
                        vat_number=instance.vat_number or '',
                        iban=instance.iban or '',
                        swift_bic=instance.swift_bic or '',
                        bank_name=instance.bank_name or '',
                        is_eu=is_eu,  # Автоматически устанавливаем принадлежность к ЕС
                        # Копируем результаты проверки VAT ID
                        vat_verification_status=instance.vat_verification_status,
                        vat_verification_result=instance.vat_verification_result,
                        vat_verification_date=instance.vat_verification_date,
                        vat_verification_manual_override=instance.vat_verification_manual_override,
                        vat_verification_manual_comment=instance.vat_verification_manual_comment or '',
                        vat_verification_manual_by=instance.vat_verification_manual_by,
                        vat_verification_manual_at=instance.vat_verification_manual_at,
                        # Активация: только при принятой оферте и (VAT ок или проверка не требуется)
                        activation_status='active' if (instance.offer_accepted and _vat_ok_or_not_required) else 'activation_required',
                        is_active=(instance.offer_accepted and _vat_ok_or_not_required)
                    )
                    logger.info(f"Provider created: {provider.name} (ID: {provider.id}), activation_status={provider.activation_status}")
                    
                    # Устанавливаем выбранные категории в available_category_levels.
                    # При created=True M2M ещё пустой: view вызовет .set(categories) после create().
                    # Предупреждение только при обновлении заявки без категорий.
                    if instance.selected_categories.exists():
                        provider.available_category_levels.set(instance.selected_categories.all())
                    elif not created:
                        logger.warning(f"No categories selected for provider form: {instance.id}")

                    # Получаем пользователя-администратора из admin_email
                    try:
                        admin_user = User.objects.get(email=instance.admin_email, is_active=True)
                    except User.DoesNotExist:
                        logger.error(f'Admin user with email {instance.admin_email} not found for provider form {instance.id}')
                        return
                    
                    # Создаем связь ProviderAdmin как связь «пользователь ↔ провайдер» для доступа.
                    # Роли owner/provider_manager назначаются через UserType (отдельно, по self-assign).
                    from .models import ProviderAdmin
                    ProviderAdmin.objects.create(
                        user=admin_user,
                        provider=provider,
                        role=ProviderAdmin.ROLE_PROVIDER_ADMIN,
                        is_active=True
                    )

                    # Назначаем роль provider_admin указанному администратору.
                    # Доступ в приложение «Админка провайдеров» по API; в Django admin провайдеры не входят.
                    try:
                        provider_admin_role = UserType.objects.get(name='provider_admin')
                        if not admin_user.user_types.filter(name='provider_admin').exists():
                            admin_user.user_types.add(provider_admin_role)
                    except UserType.DoesNotExist:
                        provider_admin_role = UserType.objects.create(
                            name='provider_admin',
                            description='Provider administrator role with rights to manage provider settings',
                            permissions=['providers.add_provider', 'providers.change_provider', 'providers.view_provider',
                                       'providers.add_employee', 'providers.change_employee', 'providers.view_employee',
                                       'booking.view_booking', 'notifications.view_notification']
                        )
                        admin_user.user_types.add(provider_admin_role)
                    
                    # УПРОЩЕННЫЙ ПРОЦЕСС: создаем DocumentAcceptance, если оферта принята.
                    # Источник оферты тот же, что в мастере регистрации: одна глобальная оферта для всех +
                    # региональные дополнения по get_region_code(country). Не полагаемся только на CountryLegalConfig.
                    if instance.offer_accepted:
                        from legal.models import LegalDocument, DocumentAcceptance, CountryLegalConfig
                        from utils.countries import get_region_code
                        
                        # Глобальная оферта: сначала из CountryLegalConfig для страны, иначе одна для всех (как в API регистрации)
                        global_offer = None
                        # Код страны для поиска конфига и региона (CountryField может быть объектом)
                        _country_code = getattr(provider.country, 'code', None) or (str(provider.country) if provider.country else None)
                        if _country_code:
                            try:
                                country_config = CountryLegalConfig.objects.get(country=_country_code)
                                global_offer = country_config.global_offer
                            except CountryLegalConfig.DoesNotExist:
                                pass
                        if not global_offer:
                            global_offer = LegalDocument.objects.filter(
                                document_type__code='global_offer', is_active=True
                            ).first()
                        
                        if not global_offer:
                            logger.warning(
                                "No active global offer in DB; DocumentAcceptance for provider %s was not created.",
                                provider.id,
                            )
                        else:
                            accepted_at = instance.offer_accepted_at or timezone.now()
                            ip_address = instance.offer_accepted_ip or '127.0.0.1'
                            user_agent = instance.offer_accepted_user_agent or 'ProviderForm'
                            # Один DocumentAcceptance на глобальную оферту (кто принял — accepted_by)
                            DocumentAcceptance.objects.create(
                                provider=provider,
                                document=global_offer,
                                accepted_by=instance.created_by,
                                document_version=global_offer.version,
                                accepted_at=accepted_at,
                                ip_address=ip_address,
                                user_agent=user_agent,
                                is_active=True
                            )
                            logger.info("DocumentAcceptance created for provider %s, document=global_offer %s", provider.id, global_offer.version)
                            # Региональные дополнения: отдельная запись DocumentAcceptance на каждый документ (как в мастере — приняты 2 документа = 2 записи)
                            region_code = get_region_code(_country_code) if _country_code else None
                            if region_code:
                                addendums = LegalDocument.objects.filter(
                                    document_type__code='regional_addendum',
                                    region_code=region_code,
                                    is_active=True
                                )
                                for addendum in addendums:
                                    DocumentAcceptance.objects.create(
                                        provider=provider,
                                        document=addendum,
                                        accepted_by=instance.created_by,
                                        document_version=addendum.version,
                                        accepted_at=accepted_at,
                                        ip_address=ip_address,
                                        user_agent=user_agent,
                                        is_active=True
                                    )
                                    logger.info(
                                        "DocumentAcceptance created for provider %s, document=regional_addendum %s (region=%s)",
                                        provider.id, addendum.version, region_code
                                    )
                    
                    # УПРОЩЕННЫЙ ПРОЦЕСС: автоматически назначаем биллинг-менеджера (первый доступный)
                    from billing.models import BillingManagerProvider, BillingManagerEvent
                    from django.utils import timezone
                    
                    # User уже определен в начале функции
                    
                    # Проверяем, был ли биллинг-менеджер назначен вручную (для обратной совместимости)
                    billing_manager_id = None
                    if hasattr(instance, '_selected_billing_manager_id') and instance._selected_billing_manager_id:
                        billing_manager_id = instance._selected_billing_manager_id
                    elif hasattr(instance, '_selected_billing_manager') and instance._selected_billing_manager:
                        billing_manager_id = instance._selected_billing_manager.pk if hasattr(instance._selected_billing_manager, 'pk') else None
                    
                    # Если не назначен вручную — наименее загруженный менеджер (минимальное число активных провайдеров: 0, 1, 2, …)
                    if not billing_manager_id:
                        try:
                            billing_manager_role = UserType.objects.get(name='billing_manager')
                            billing_manager = (
                                User.objects.filter(
                                    user_types=billing_manager_role,
                                    is_active=True
                                )
                                .annotate(
                                    _active_count=Count(
                                        'managed_providers',
                                        filter=Q(managed_providers__status__in=['active', 'temporary'])
                                    )
                                )
                                .annotate(active_providers_count=Coalesce(F('_active_count'), Value(0)))
                                .order_by('active_providers_count', 'id')
                                .first()
                            )
                            if billing_manager:
                                billing_manager_id = billing_manager.id
                                logger.info(f"Auto-assigned billing manager: {billing_manager.email}")
                            else:
                                logger.warning("No active billing manager found, skipping BillingManagerProvider creation")
                        except UserType.DoesNotExist:
                            logger.warning("Billing manager role not found, skipping BillingManagerProvider creation")
                    
                    if billing_manager_id:
                        try:
                            billing_manager = User.objects.get(pk=billing_manager_id, is_active=True)
                            
                            # Проверяем, не существует ли уже связь
                            existing_link = BillingManagerProvider.objects.filter(
                                billing_manager=billing_manager,
                                provider=provider,
                                status__in=['active', 'vacation', 'temporary']
                            ).first()
                            
                            if existing_link:
                                logger.warning(f"BillingManagerProvider already exists for provider {provider.id} and billing manager {billing_manager.id}")
                                billing_manager_provider = existing_link
                            else:
                                # Создаем связь менеджера с провайдером
                                billing_manager_provider = BillingManagerProvider.objects.create(
                                    billing_manager=billing_manager,
                                    provider=provider,
                                    start_date=timezone.now().date(),
                                    status='active'
                                )
                                logger.info(f"BillingManagerProvider created: provider={provider.id}, manager={billing_manager.id}")
                            
                            # Создаем событие назначения только если его еще нет
                            existing_event = BillingManagerEvent.objects.filter(
                                billing_manager_provider=billing_manager_provider,
                                event_type='assigned',
                                effective_date=timezone.now().date()
                            ).first()
                            
                            if not existing_event:
                                # Убеждаемся, что created_by существует и активен
                                event_created_by = instance.approved_by if instance.approved_by else billing_manager
                                # Проверяем, что пользователь существует в users_user
                                if event_created_by:
                                    event_created_by = User.objects.get(pk=event_created_by.pk, is_active=True)
                                    created_by_value = event_created_by
                                else:
                                    created_by_value = None
                                
                                BillingManagerEvent.objects.create(
                                    billing_manager_provider=billing_manager_provider,
                                    event_type='assigned',
                                    effective_date=timezone.now().date(),
                                    created_by=created_by_value,
                                    notes=_('Assigned during provider form approval')
                                )
                        except User.DoesNotExist:
                            logger.error(f"Billing manager with ID {billing_manager_id} does not exist or is not active")
                            raise ValidationError(_('Selected billing manager does not exist or is not active.'))
                        except Exception as e:
                            logger.error(f"Error creating BillingManagerProvider: {e}", exc_info=True)
                            raise
                    
                    # Отправляем письма после регистрации
                    _send_registration_emails(provider, instance, admin_user)
                    
            except Exception as e:
                logger.error(f"Error creating provider from form {instance.id}: {e}", exc_info=True)
                raise


def _send_registration_emails(provider, provider_form, admin_user):
    """
    Отправляет письма после регистрации провайдера по спецификации
    PROVIDER_REGISTRATION_EMAIL_RECIPIENTS.md.

    Два момента: заявка подана (submitted) и провайдер активирован (activated).
    Роли: author, organization, admin. Один email = одно письмо (дедупликация);
    при совпадении ролей приоритет: activated → admin; submitted → author.
    Язык письма = язык автора заявки.
    """
    from django.core.mail import send_mail
    from django.conf import settings
    from django.utils import translation
    from django.template.loader import render_to_string
    from django.contrib.auth import get_user_model
    UserModel = get_user_model()

    raw_lang = (getattr(provider_form, 'language', None) or '').strip() or None
    if not raw_lang and provider_form.created_by:
        raw_lang = getattr(provider_form.created_by, 'preferred_language', None) or getattr(provider_form.created_by, 'language', None)
    if not raw_lang:
        raw_lang = translation.get_language() or 'en'
    language = (raw_lang or 'en').split('-')[0].lower()
    if language not in ['en', 'ru', 'de', 'me']:
        language = 'en'

    is_activated = provider.activation_status == 'active' and provider.is_active

    base_admin_url = (getattr(settings, 'PROVIDER_ADMIN_URL', 'http://localhost:5173') or '').rstrip('/')
    admin_login_url = f"{base_admin_url}/login" if base_admin_url else 'http://localhost:5173/login'
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
    setup_guide_url = f"{frontend_url}/provider-setup-guide"

    billing_manager_contacts = []
    if is_activated:
        try:
            from billing.models import BillingManagerProvider
            for manager_provider in BillingManagerProvider.get_active_managers_for_provider(provider):
                effective = manager_provider.get_effective_manager()
                if effective and effective.email:
                    billing_manager_contacts.append({
                        'name': effective.get_full_name() or effective.email,
                        'email': effective.email,
                    })
        except Exception as e:
            logger.warning(f"Error getting billing manager contacts for provider {provider.id}: {e}")

    # Кандидаты: (email_key, email_original, role, user, display_name)
    # organization: user=None, display_name — безличное приветствие по языку
    IMPERSONAL_GREETING = {
        'en': 'Dear representative',
        'ru': 'Уважаемые представители организации',
        'de': 'Sehr geehrte Damen und Herren',
        'me': 'Poštovani',
    }
    impersonal = IMPERSONAL_GREETING.get(language, IMPERSONAL_GREETING['en'])

    candidates = []
    if provider_form.created_by and provider_form.created_by.email:
        e = provider_form.created_by.email
        name = (provider_form.created_by.first_name or _('User')).strip() or _('User')
        candidates.append((e.lower(), e, 'author', provider_form.created_by, name))
    if provider.email:
        e = provider.email.strip()
        if e and (not provider_form.created_by or e.lower() != (provider_form.created_by.email or '').lower()):
            candidates.append((e.lower(), e, 'organization', None, impersonal))
    # Админ добавляется всегда (даже при совпадении с author/org). Дедупликация выберет роль по приоритету.
    if provider_form.admin_email:
        e = provider_form.admin_email.strip().lower()
        if e:
            try:
                admin_user_obj = UserModel.objects.get(email__iexact=provider_form.admin_email, is_active=True)
                name = (admin_user_obj.first_name or _('User')).strip() or _('User')
                candidates.append((e, provider_form.admin_email.strip(), 'admin', admin_user_obj, name))
            except UserModel.DoesNotExist:
                logger.warning(f"Admin email user {provider_form.admin_email} not found for provider {provider.id}")

    # Дедупликация: один email — одна роль. Приоритет: activated → admin > organization > author; submitted → author > organization. В момент submitted админ не получает письма.
    ROLE_PRIORITY_ACTIVATED = {'admin': 3, 'organization': 2, 'author': 1}
    ROLE_PRIORITY_SUBMITTED = {'author': 2, 'organization': 1}
    recipients_by_email = {}
    for email_key, email_orig, role, user, display_name in candidates:
        if not is_activated and role == 'admin':
            continue
        prev = recipients_by_email.get(email_key)
        if prev is None:
            recipients_by_email[email_key] = {'email': email_orig, 'role': role, 'user': user, 'display_name': display_name}
        elif is_activated and ROLE_PRIORITY_ACTIVATED.get(role, 0) > ROLE_PRIORITY_ACTIVATED.get(prev['role'], 0):
            recipients_by_email[email_key] = {'email': email_orig, 'role': role, 'user': user, 'display_name': display_name}
        elif not is_activated and ROLE_PRIORITY_SUBMITTED.get(role, 0) > ROLE_PRIORITY_SUBMITTED.get(prev['role'], 0):
            recipients_by_email[email_key] = {'email': email_orig, 'role': role, 'user': user, 'display_name': display_name}

    recipients = list(recipients_by_email.values())

    # Тема и шаблон по роли и моменту (все 4 языка, хардкод по спецификации)
    SUBJECTS_SUBMITTED_HARDCODED = {
        'author': {'en': 'Your provider registration request has been submitted', 'ru': 'Ваша заявка на регистрацию провайдера зарегистрирована', 'de': 'Ihr Antrag auf Anbieter-Registrierung wurde eingereicht', 'me': 'Vaš zahtev za registraciju pružaoca usluga je poslat'},
        'organization': {'en': 'Provider registration request received: %(name)s', 'ru': 'Получена заявка на регистрацию: %(name)s', 'de': 'Antrag auf Anbieter-Registrierung eingegangen: %(name)s', 'me': 'Zahtev za registraciju pružaoca primljen: %(name)s'},
    }
    SUBJECTS_ACTIVATED_HARDCODED = {
        'author': {'en': 'Your provider registration has been confirmed', 'ru': 'Ваша регистрация провайдера подтверждена', 'de': 'Ihre Anbieter-Registrierung wurde bestätigt', 'me': 'Vaša registracija pružaoca usluga je potvrđena'},
        'organization': {'en': 'Provider registration confirmed: %(name)s', 'ru': 'Регистрация организации подтверждена: %(name)s', 'de': 'Anbieter-Registrierung bestätigt: %(name)s', 'me': 'Registracija pružaoca potvrđena: %(name)s'},
        'admin': {'en': 'Your provider account has been activated', 'ru': 'Ваш аккаунт провайдера активирован', 'de': 'Ihr Anbieter-Konto wurde aktiviert', 'me': 'Vaš nalog pružaoca usluga je aktiviran'},
    }

    provider_admin_email = (provider_form.admin_email or '').strip()

    for recipient in recipients:
        try:
            translation.activate(language)
            role = recipient['role']
            user_obj = recipient['user']
            display_name = recipient['display_name']

            if is_activated:
                subject_map = SUBJECTS_ACTIVATED_HARDCODED.get(role, SUBJECTS_ACTIVATED_HARDCODED['author'])
                subject = subject_map.get(language, subject_map['en'])
                if '%(name)s' in subject:
                    subject = subject % {'name': provider.name}
                template_map = {'author': 'email/provider_registration_activated_author.html', 'organization': 'email/provider_registration_activated_organization.html', 'admin': 'email/provider_registration_activated_admin.html'}
                template_name = template_map.get(role, template_map['author'])
            else:
                subject_map = SUBJECTS_SUBMITTED_HARDCODED.get(role, SUBJECTS_SUBMITTED_HARDCODED['author'])
                subject = subject_map.get(language, subject_map['en'])
                if '%(name)s' in subject:
                    subject = subject % {'name': provider.name}
                template_map = {'author': 'email/provider_registration_submitted_author.html', 'organization': 'email/provider_registration_submitted_organization.html'}
                template_name = template_map.get(role, 'email/provider_registration_submitted_author.html')

            has_password = user_obj.has_usable_password() if user_obj else False
            context = {
                'display_name': display_name,
                'provider_name': provider.name,
                'provider_admin_email': provider_admin_email,
                'admin_login_url': admin_login_url,
                'setup_guide_url': setup_guide_url,
                'login_method': 'password' if has_password else 'google',
                'login_email': recipient['email'],
                'billing_manager_contacts': billing_manager_contacts if is_activated else [],
                'recipient_role': role,
            }
            email_body = render_to_string(template_name, context)

            send_mail(
                subject=subject,
                message='',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient['email']],
                html_message=email_body,
                fail_silently=False,
            )

            logger.info(f"Registration email sent to {recipient['email']} for provider {provider.id} (role={role}, language: {language}, activated: {is_activated})")
            translation.deactivate()

        except Exception as e:
            logger.error(f"Error sending registration email to {recipient['email']} for provider {provider.id}: {e}", exc_info=True)
            translation.deactivate()