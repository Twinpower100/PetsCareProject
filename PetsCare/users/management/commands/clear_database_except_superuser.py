"""
Команда для очистки базы данных с сохранением суперюзера.

Эта команда удаляет все данные из всех таблиц, кроме суперюзера.
Используется перед применением миграций для новой архитектуры ProviderLocation.

ВАЖНО: Эта команда необратимо удаляет все данные!
Используйте только в development окружении!

Использование:
    python manage.py clear_database_except_superuser
    python manage.py clear_database_except_superuser --confirm
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.apps import apps
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Очищает базу данных, сохраняя только суперюзера'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Подтверждение очистки базы данных',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    '⚠️  ВНИМАНИЕ: Эта команда удалит ВСЕ данные из базы данных!\n'
                    'Будет сохранен только суперпользователь.\n'
                    'Для подтверждения используйте флаг --confirm'
                )
            )
            return

        self.stdout.write(self.style.WARNING('Начинаю очистку базы данных...'))

        # Сохраняем суперюзера
        superuser = None
        try:
            superuser = User.objects.filter(is_superuser=True).first()
            if not superuser:
                raise CommandError('Суперпользователь не найден! Создайте его перед очисткой.')
            
            superuser_data = {
                'id': superuser.id,
                'email': superuser.email,
                'username': superuser.username if hasattr(superuser, 'username') else None,
                'password': superuser.password,
                'is_superuser': superuser.is_superuser,
                'is_staff': superuser.is_staff,
                'is_active': superuser.is_active,
            }
            self.stdout.write(f'✓ Сохранен суперпользователь: {superuser.email}')
        except Exception as e:
            raise CommandError(f'Ошибка при сохранении суперпользователя: {e}')

        # Порядок удаления моделей (с учетом зависимостей)
        # Начинаем с моделей, которые имеют внешние ключи на другие модели
        deletion_order = [
            # Бронирования и слоты
            ('booking', 'BookingPayment'),
            ('booking', 'BookingCancellation'),
            ('booking', 'TimeSlot'),
            ('booking', 'Booking'),
            ('booking', 'BookingNote'),
            ('booking', 'BookingReview'),
            ('booking', 'BookingStatus'),
            ('booking', 'AbuseRule'),
            ('booking', 'BookingAutoCompleteSettings'),
            
            # Записи о питомцах
            ('pets', 'PetRecordFile'),
            ('pets', 'PetRecord'),
            ('pets', 'MedicalRecord'),
            ('pets', 'PetAccess'),
            ('pets', 'PetOwnerIncapacity'),
            ('pets', 'PetIncapacityNotification'),
            ('pets', 'PetOwnershipInvite'),
            ('pets', 'Pet'),
            # PetType и Breed оставляем (справочники)
            
            # Услуги провайдера
            ('providers', 'ProviderService'),
            ('providers', 'ProviderLocationService'),  # Если уже существует
            
            # Расписания
            ('scheduling', 'WorkSlot'),
            ('scheduling', 'SchedulePreference'),
            ('scheduling', 'DayOff'),
            ('scheduling', 'SickLeave'),
            ('scheduling', 'Vacation'),
            ('scheduling', 'StaffingRequirement'),
            ('scheduling', 'ServicePriority'),
            ('scheduling', 'Workplace'),
            ('providers', 'Schedule'),
            ('providers', 'PatternDay'),
            ('providers', 'SchedulePattern'),
            
            # Сотрудники
            ('providers', 'EmployeeProvider'),
            ('providers', 'EmployeeWorkSlot'),
            ('providers', 'ManagerInvite'),
            ('providers', 'JoinRequest'),
            ('providers', 'Employee'),
            
            # Локации (если уже существуют)
            ('providers', 'ProviderLocation'),
            
            # Организации
            ('providers', 'ProviderAdmin'),
            ('providers', 'Provider'),
            
            # Заявки провайдеров
            ('users', 'ProviderForm'),
            
            # Биллинг
            ('billing', 'BlockingNotification'),
            ('billing', 'ProviderBlocking'),
            ('billing', 'BlockingRule'),
            ('billing', 'BlockingTemplate'),
            ('billing', 'BillingManagerEvent'),
            ('billing', 'BillingManagerProvider'),
            ('billing', 'Payment'),
            ('billing', 'Refund'),
            ('billing', 'Invoice'),
            
            # Рейтинги
            ('ratings', 'SuspiciousActivity'),
            ('ratings', 'ComplaintResponse'),
            ('ratings', 'Complaint'),
            ('ratings', 'Review'),
            ('ratings', 'Rating'),
            
            # Передержка
            ('sitters', 'SitterReview'),
            ('sitters', 'PetSitting'),
            ('sitters', 'PetSittingResponse'),
            ('sitters', 'PetSittingAd'),
            ('sitters', 'SitterProfile'),
            
            # Диалоги
            ('sitters', 'Message'),
            ('sitters', 'Conversation'),
            
            # Уведомления
            ('notifications', 'Notification'),
            ('notifications', 'UserNotificationSettings'),
            ('notifications', 'NotificationPreference'),
            ('notifications', 'ReminderSettings'),
            ('notifications', 'Reminder'),
            ('notifications', 'NotificationRule'),
            ('notifications', 'NotificationTemplate'),
            # NotificationType оставляем (справочник)
            
            # Доступ
            ('access', 'AccessLog'),
            ('access', 'Access'),
            
            # Аудит
            ('audit', 'ModelChange'),
            ('audit', 'UserAction'),
            ('audit', 'AuditLog'),
            
            # Геолокация
            ('geolocation', 'AddressValidation'),
            ('geolocation', 'AddressCache'),
            ('geolocation', 'UserLocation'),
            ('geolocation', 'Address'),
            # Service и DocumentType оставляем (справочники)
            
            # Роли и инвайты
            ('users', 'RoleInvite'),
            ('users', 'RoleTermination'),
            
            # Пользователи (кроме суперюзера)
            ('users', 'User'),
        ]

        deleted_count = 0
        errors = []

        with transaction.atomic():
            for app_label, model_name in deletion_order:
                try:
                    model = apps.get_model(app_label, model_name)
                    count = model.objects.all().count()
                    
                    if count > 0:
                        # Для User удаляем всех кроме суперюзера
                        if app_label == 'users' and model_name == 'User':
                            User.objects.exclude(id=superuser.id).delete()
                            deleted = User.objects.exclude(id=superuser.id).count()
                            self.stdout.write(
                                f'  ✓ {app_label}.{model_name}: удалено {deleted} записей (суперпользователь сохранен)'
                            )
                        else:
                            model.objects.all().delete()
                            self.stdout.write(
                                f'  ✓ {app_label}.{model_name}: удалено {count} записей'
                            )
                        deleted_count += count
                    else:
                        self.stdout.write(
                            f'  - {app_label}.{model_name}: нет данных'
                        )
                except LookupError:
                    # Модель не найдена (возможно, еще не создана)
                    self.stdout.write(
                        self.style.WARNING(f'  ⚠ {app_label}.{model_name}: модель не найдена (пропущено)')
                    )
                except Exception as e:
                    error_msg = f'Ошибка при удалении {app_label}.{model_name}: {e}'
                    errors.append(error_msg)
                    self.stdout.write(self.style.ERROR(f'  ✗ {error_msg}'))

        # Восстанавливаем суперюзера (на случай если он был удален)
        if superuser_data:
            try:
                existing_user = User.objects.filter(id=superuser_data['id']).first()
                if not existing_user:
                    # Создаем суперюзера заново
                    User.objects.create(
                        id=superuser_data['id'],
                        email=superuser_data['email'],
                        username=superuser_data['username'] or superuser_data['email'],
                        password=superuser_data['password'],
                        is_superuser=True,
                        is_staff=True,
                        is_active=True,
                    )
                    self.stdout.write(self.style.SUCCESS('✓ Суперпользователь восстановлен'))
                else:
                    self.stdout.write(self.style.SUCCESS('✓ Суперпользователь сохранен'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Ошибка при восстановлении суперпользователя: {e}'))

        # Очищаем системные таблицы Django
        try:
            from django.contrib.admin.models import LogEntry
            from django.contrib.sessions.models import Session
            from django.contrib.contenttypes.models import ContentType
            
            LogEntry.objects.all().delete()
            Session.objects.all().delete()
            # ContentType не удаляем - они нужны для миграций
            
            self.stdout.write(self.style.SUCCESS('✓ Системные таблицы Django очищены'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'⚠ Ошибка при очистке системных таблиц: {e}'))

        # Итоги
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'✓ Очистка завершена! Удалено записей: {deleted_count}'))
        
        if errors:
            self.stdout.write(self.style.WARNING(f'⚠ Обнаружено ошибок: {len(errors)}'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f'  - {error}'))
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('База данных готова для применения миграций!'))

