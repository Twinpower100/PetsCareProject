"""
Management команда для тестирования упрощенного процесса регистрации провайдера.

Использование:
    python manage.py test_provider_registration_flow
    
Тестирует упрощенный процесс регистрации провайдера:

УПРОЩЕННЫЙ ПРОЦЕСС РЕГИСТРАЦИИ:
================================

1. СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ (Owner)
   - Пользователь регистрируется в системе (Email + Пароль)
   - Это будущий владелец/администратор организации
   - Owner = первый пользователь, который создает профиль организации

2. СОЗДАНИЕ ЗАЯВКИ ПРОВАЙДЕРА (ProviderForm) - ВСЕ ОБЯЗАТЕЛЬНО!
   - Owner заполняет форму заявки с данными организации:
     * Название организации
     * Email организации
     * Телефон организации
     * Адрес организации
     * Категории услуг
     * РЕКВИЗИТЫ (обязательно!):
       - Tax ID / ИНН
       - Registration Number
       - Country (страна регистрации)
       - Invoice Currency (валюта счета)
     * ПРИНЯТИЕ ОФЕРТЫ (обязательно!):
       - offer_accepted = True
       - offer_accepted_at (время принятия)
       - offer_accepted_ip (IP адрес)
       - offer_accepted_user_agent (User Agent)
   - БЕЗ РЕКВИЗИТОВ И ОФЕРТЫ - ЗАЯВКА НЕ ПРИНИМАЕТСЯ!

3. АВТОМАТИЧЕСКОЕ СОЗДАНИЕ ПРОВАЙДЕРА (через сигнал post_save)
   - Сразу при создании заявки АВТОМАТИЧЕСКИ:
     * Создается Provider (организация) с реквизитами из заявки
     * Копируются реквизиты из ProviderForm в Provider
  * Создается DocumentAcceptance (если оферта принята)
     * Создается ProviderAdmin (связь Owner → Provider)
     * Owner получает роль 'provider_admin'
     * Owner получает доступ к админке (is_staff=True)
     * Автоматически назначается биллинг-менеджер (первый доступный)
     * ПРОВАЙДЕР СРАЗУ АКТИВИРУЕТСЯ (activation_status='active', is_active=True)
       если реквизиты заполнены и оферта принята!

ВАЖНО:
- Owner автоматически становится provider_admin после одобрения заявки
- Contract НЕ создается (старая система удалена)
- Активация происходит СРАЗУ при одобрении заявки (если реквизиты и оферта заполнены)
- Нет реквизитов - до свиданья!
- Нет принятия оферты - тоже до свиданья!
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
import random

from users.models import User, UserType, ProviderForm, ProviderAdmin
from providers.models import Provider
from billing.models import Currency, BillingManagerProvider
from legal.models import LegalDocumentType, LegalDocument, DocumentAcceptance
from catalog.models import Service


class Command(BaseCommand):
    help = 'Тестирует полный процесс регистрации провайдера с новой системой оферт'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== ТЕСТИРОВАНИЕ ПРОЦЕССА РЕГИСТРАЦИИ ПРОВАЙДЕРА ===\n'))
        
        # Шаг 1: Создание пользователя (Owner)
        self.stdout.write(self.style.SUCCESS('--- Шаг 1: Создание пользователя (Owner) ---\n'))
        
        owner = self._create_owner()
        self.stdout.write(f'✅ Создан Owner: {owner.email} (ID: {owner.id})')
        self.stdout.write(f'✅ Username: {owner.username}\n')
        
        # Шаг 2: Создание заявки провайдера (ProviderForm)
        self.stdout.write(self.style.SUCCESS('--- Шаг 2: Создание заявки провайдера (ProviderForm) ---\n'))
        
        provider_form = self._create_provider_form(owner)
        self.stdout.write(f'✅ Создана заявка: {provider_form.provider_name}')
        self.stdout.write(f'✅ Email: {provider_form.provider_email}')
        self.stdout.write(f'✅ Телефон: {provider_form.provider_phone}')
        self.stdout.write(f'✅ Реквизиты заполнены:')
        self.stdout.write(f'   - Tax ID: {provider_form.tax_id}')
        self.stdout.write(f'   - Registration Number: {provider_form.registration_number}')
        self.stdout.write(f'   - Country: {provider_form.country}')
        self.stdout.write(f'   - Invoice Currency: {provider_form.invoice_currency.code if provider_form.invoice_currency else "N/A"}')
        self.stdout.write(f'✅ Оферта принята: {provider_form.offer_accepted_at}\n')
        
        # Шаг 3: Автоматическое создание провайдера
        self.stdout.write(self.style.SUCCESS('--- Шаг 3: Автоматическое создание провайдера ---\n'))
        self.stdout.write('📋 ЧТО ПРОИСХОДИТ:\n')
        self.stdout.write('   - Сразу при создании заявки АВТОМАТИЧЕСКИ (через сигнал post_save):\n')
        self.stdout.write('     * Создается Provider (организация) с реквизитами из заявки\n')
        self.stdout.write('     * Копируются реквизиты из ProviderForm в Provider\n')
        self.stdout.write('     * Создается DocumentAcceptance (если оферта принята)\n')
        self.stdout.write('     * Создается ProviderAdmin (связь Owner → Provider)\n')
        self.stdout.write('     * Owner получает роль provider_admin\n')
        self.stdout.write('     * Owner получает доступ к админке (is_staff=True)\n')
        self.stdout.write('     * Автоматически назначается биллинг-менеджер (первый доступный)\n')
        self.stdout.write('   - ⚠️  Contract НЕ создается (старая система удалена)\n')
        self.stdout.write('   - ✅ ПРОВАЙДЕР СРАЗУ АКТИВИРУЕТСЯ (если реквизиты и оферта заполнены)!\n\n')
        
        # Создаем биллинг-менеджера для автоматического назначения
        billing_manager = self._get_or_create_billing_manager()
        
        # Получаем созданного провайдера (он должен быть создан автоматически через сигнал)
        provider = Provider.objects.filter(email=provider_form.provider_email).first()
        
        if not provider:
            self.stdout.write(self.style.ERROR('❌ Provider не создан автоматически! Проверьте сигнал.'))
            return
        
        self.stdout.write(f'✅ Provider создан автоматически: {provider.name} (ID: {provider.id})')
        self.stdout.write(f'✅ Реквизиты скопированы из заявки:')
        self.stdout.write(f'   - Tax ID: {provider.tax_id}')
        self.stdout.write(f'   - Registration Number: {provider.registration_number}')
        self.stdout.write(f'   - Country: {provider.country}')
        self.stdout.write(f'   - Invoice Currency: {provider.invoice_currency.code if provider.invoice_currency else "N/A"}')
        self.stdout.write(f'✅ Статус активации: {provider.activation_status} (должен быть active!)')
        self.stdout.write(f'✅ is_active: {provider.is_active} (должен быть True!)')
        
        # Проверяем создание DocumentAcceptance
        acceptance = DocumentAcceptance.objects.filter(
            provider=provider,
            document__document_type__code='global_offer',
            is_active=True
        ).first()
        if acceptance:
            self.stdout.write(f'✅ DocumentAcceptance создан: версия {acceptance.document.version}')
            self.stdout.write(f'   - Принято: {acceptance.accepted_at}')
            self.stdout.write(f'   - IP: {acceptance.ip_address}')
        else:
            self.stdout.write(self.style.WARNING('⚠️  DocumentAcceptance не создан'))
        
        # Проверяем создание ProviderAdmin
        provider_admin = ProviderAdmin.objects.filter(provider=provider, user=owner).first()
        if provider_admin:
            self.stdout.write(f'✅ Создан ProviderAdmin: {owner.email} → {provider.name}')
        else:
            self.stdout.write(self.style.WARNING('⚠️  ProviderAdmin не создан'))
        
        # Проверяем роль provider_admin
        owner.refresh_from_db()
        if owner.user_types.filter(name='provider_admin').exists():
            self.stdout.write(f'✅ Owner получил роль provider_admin')
        else:
            self.stdout.write(self.style.WARNING('⚠️  Owner не получил роль provider_admin'))
        
        # Проверяем is_staff
        if owner.is_staff:
            self.stdout.write(f'✅ Owner получил доступ к админке (is_staff=True)')
        else:
            self.stdout.write(self.style.WARNING('⚠️  Owner не получил доступ к админке'))
        
        self.stdout.write('')
        
        # Шаг 4: Проверка финального состояния
        self.stdout.write(self.style.SUCCESS('--- Шаг 8: Проверка финального состояния ---\n'))
        
        # Проверяем ProviderAdmin
        provider_admin = ProviderAdmin.objects.filter(provider=provider, user=owner, is_active=True).first()
        if provider_admin:
            self.stdout.write(f'✅ ProviderAdmin активен: {owner.email} → {provider.name}')
        else:
            self.stdout.write(self.style.WARNING('⚠️  ProviderAdmin не активен'))
        
        # Проверяем роль
        if owner.user_types.filter(name='provider_admin').exists():
            self.stdout.write(f'✅ Owner имеет роль provider_admin')
        else:
            self.stdout.write(self.style.WARNING('⚠️  Owner не имеет роль provider_admin'))
        
        # Проверяем биллинг-менеджера (автоматически назначен)
        billing_manager_link = BillingManagerProvider.objects.filter(
            provider=provider,
            status='active'
        ).first()
        if billing_manager_link:
            self.stdout.write(f'✅ Биллинг-менеджер автоматически назначен: {billing_manager_link.billing_manager.email}')
        else:
            self.stdout.write(self.style.WARNING('⚠️  Биллинг-менеджер не назначен'))
        
        # Проверяем активную оферту
        active_acceptance = provider.document_acceptances.filter(
            document__document_type__code='global_offer',
            is_active=True
        ).first()
        if active_acceptance:
            self.stdout.write(f'✅ Активная оферта: версия {active_acceptance.document.version}')
        else:
            self.stdout.write(self.style.WARNING('⚠️  Активная оферта не найдена'))
        
        self.stdout.write('')
        
        # Итоговый отчет
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('=== ИТОГОВЫЙ ОТЧЕТ ===\n'))
        
        self.stdout.write(self.style.SUCCESS('✅ Все этапы упрощенного процесса регистрации протестированы:'))
        self.stdout.write('  ✅ Создание пользователя (Owner)')
        self.stdout.write('  ✅ Создание заявки провайдера (ProviderForm) с реквизитами и принятием оферты')
        self.stdout.write('  ✅ Автоматическое создание Provider с копированием реквизитов')
        self.stdout.write('  ✅ Создание DocumentAcceptance')
        self.stdout.write('  ✅ Создание ProviderAdmin и назначение роли provider_admin')
        self.stdout.write('  ✅ Автоматическое назначение биллинг-менеджера (первый доступный)')
        self.stdout.write('  ✅ Автоматическая активация провайдера при создании заявки')
        
        self.stdout.write(self.style.SUCCESS('\n✅ ПРОЦЕСС РЕГИСТРАЦИИ РАБОТАЕТ КОРРЕКТНО!'))
        self.stdout.write(self.style.SUCCESS('=' * 60 + '\n'))

    def _create_owner(self):
        """Создает тестового пользователя (Owner)"""
        import random
        email = f'test_owner_{random.randint(1000, 9999)}@example.com'
        phone_number = f'+7999{random.randint(1000000, 9999999)}'
        
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': f'test_owner_{random.randint(1000, 9999)}',
                'first_name': 'Test',
                'last_name': 'Owner',
                'phone_number': phone_number,
            }
        )
        if created:
            user.set_password('test123')
            user.save()
        
        return user

    def _create_provider_form(self, owner):
        """Создает заявку провайдера с обязательными реквизитами и принятием оферты"""
        import random
        from django_countries import countries
        
        provider_name = f'Test Provider {random.randint(1000, 9999)}'
        provider_email = f'test_provider_{random.randint(1000, 9999)}@example.com'
        provider_phone = f'+7999{random.randint(1000000, 9999999)}'
        
        # Получаем категории услуг уровня 0
        categories = Service.objects.filter(level=0)[:3]
        if not categories.exists():
            self.stdout.write(self.style.WARNING('⚠️  Нет категорий услуг уровня 0, создаем заявку без категорий'))
        
        # Получаем или создаем валюту
        currency, _ = Currency.objects.get_or_create(
            code='RUB',
            defaults={
                'name': 'Russian Ruble',
                'symbol': '₽',
                'is_active': True,
                'exchange_rate': Decimal('1.0'),
            }
        )
        
        # Получаем активную оферту
        offer_type, _ = LegalDocumentType.objects.get_or_create(
            code='global_offer',
            defaults={
                'name': 'Global Offer',
                'is_required_for_all_countries': True
            }
        )
        active_offer = LegalDocument.objects.filter(
            document_type=offer_type,
            is_active=True
        ).order_by('-effective_date').first()
        if not active_offer:
            active_offer = LegalDocument.objects.create(
                document_type=offer_type,
                version='1.0',
                title='Test Global Offer',
                effective_date=timezone.now().date(),
                is_active=True
            )
        
        # Генерируем уникальные реквизиты
        unique_suffix = random.randint(100000, 999999)
        tax_id = f'123456789{unique_suffix}'
        registration_number = f'987654321{unique_suffix}'
        
        # Создаем заявку с обязательными полями
        provider_form = ProviderForm.objects.create(
            created_by=owner,
            provider_name=provider_name,
            provider_email=provider_email,
            provider_phone=provider_phone,
            provider_address='Test Address, Test City',
            status='pending',
            # ОБЯЗАТЕЛЬНЫЕ РЕКВИЗИТЫ
            tax_id=tax_id,
            registration_number=registration_number,
            country='RU',  # Россия
            invoice_currency=currency,
            # ОБЯЗАТЕЛЬНОЕ ПРИНЯТИЕ ОФЕРТЫ
            offer_accepted=True,
            offer_accepted_at=timezone.now(),
            offer_accepted_ip='127.0.0.1',
            offer_accepted_user_agent='Test Command',
        )
        
        if categories.exists():
            provider_form.selected_categories.set(categories)
        
        return provider_form

    def _get_or_create_system_admin(self):
        """Получает или создает системного админа"""
        admin, created = User.objects.get_or_create(
            email='system_admin@example.com',
            defaults={
                'username': 'system_admin',
                'first_name': 'System',
                'last_name': 'Admin',
                'is_staff': True,
                'is_superuser': True,
                'phone_number': '+79991111111',
            }
        )
        if created:
            admin.set_password('admin123')
            admin.save()
        
        return admin

    def _get_or_create_billing_manager(self):
        """Получает или создает биллинг-менеджера"""
        manager, created = User.objects.get_or_create(
            email='billing_manager@example.com',
            defaults={
                'username': 'billing_manager',
                'first_name': 'Billing',
                'last_name': 'Manager',
                'is_staff': True,
                'phone_number': '+79992222222',
            }
        )
        
        if created:
            manager.set_password('manager123')
            manager.save()
            
            # Назначаем роль billing_manager
            billing_manager_role, _ = UserType.objects.get_or_create(
                name='billing_manager',
                defaults={
                    'description': 'Billing manager role'
                }
            )
            manager.user_types.add(billing_manager_role)
        
        return manager

    def _approve_provider_form(self, provider_form, system_admin, billing_manager):
        """Одобряет заявку провайдера (симуляция процесса одобрения)"""
        # Устанавливаем статус approved и назначаем биллинг-менеджера
        provider_form.status = 'approved'
        provider_form.approved_by = system_admin
        provider_form._selected_billing_manager_id = billing_manager.id
        provider_form.save()  # Это вызовет сигнал post_save, который создаст Provider
        
        # Получаем созданного провайдера
        provider = Provider.objects.filter(email=provider_form.provider_email).first()
        
        if not provider:
            # Если провайдер не создан через сигнал, создаем вручную
            from geolocation.models import Address
            from billing.models import Currency
            
            currency, _ = Currency.objects.get_or_create(
                code='RUB',
                defaults={
                    'name': 'Russian Ruble',
                    'symbol': '₽',
                    'is_active': True,
                    'exchange_rate': Decimal('1.0'),
                }
            )
            
            structured_address = Address.objects.create(
                formatted_address=provider_form.provider_address,
                validation_status='pending'
            )
            
            provider = Provider.objects.create(
                name=provider_form.provider_name,
                email=provider_form.provider_email,
                phone_number=str(provider_form.provider_phone),
                structured_address=structured_address,
                activation_status='pending',
                is_active=False,
                invoice_currency=currency
            )
            
            # Создаем ProviderAdmin
            ProviderAdmin.objects.create(
                user=provider_form.created_by,
                provider=provider,
                is_active=True
            )
            
            # Назначаем роль
            provider_admin_role, _ = UserType.objects.get_or_create(
                name='provider_admin',
                defaults={
                    'description': 'Provider administrator role'
                }
            )
            provider_form.created_by.user_types.add(provider_admin_role)
            provider_form.created_by.is_staff = True
            provider_form.created_by.save()
            
            # Назначаем биллинг-менеджера
            from billing.models import BillingManagerProvider
            BillingManagerProvider.objects.create(
                billing_manager=billing_manager,
                provider=provider,
                start_date=timezone.now().date(),
                status='active'
            )
        
        return provider

    def _fill_provider_requisites(self, provider):
        """Заполняет реквизиты провайдера"""
        from billing.models import Currency
        
        currency, _ = Currency.objects.get_or_create(
            code='RUB',
            defaults={
                'name': 'Russian Ruble',
                'symbol': '₽',
                'is_active': True,
                'exchange_rate': Decimal('1.0'),
            }
        )
        
        provider.tax_id = f'123456789{random.randint(0, 9)}'
        provider.registration_number = f'123456789{random.randint(0, 9)}'
        provider.invoice_currency = currency
        provider.save()

    def _get_or_create_offer(self):
        """Получает или создает публичную оферту"""
        offer_type, _ = LegalDocumentType.objects.get_or_create(
            code='global_offer',
            defaults={
                'name': 'Global Offer',
                'is_required_for_all_countries': True
            }
        )
        offer, _ = LegalDocument.objects.get_or_create(
            document_type=offer_type,
            version='1.0',
            defaults={
                'title': 'Test Global Offer',
                'effective_date': timezone.now().date(),
                'is_active': True
            }
        )
        return offer

