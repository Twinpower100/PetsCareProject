"""
Сервисы для обработки недееспособности владельцев питомцев.

Этот модуль содержит сервисы для:
1. Автоматического обнаружения неактивных владельцев
2. Обработки отчетов о недееспособности от совладельцев
3. Отправки уведомлений
4. Выполнения автоматических действий
"""

import logging
from datetime import timedelta
from typing import List, Optional, Dict, Any
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.mail import send_mail
from django.conf import settings

from .models import Pet, PetOwnerIncapacity, PetIncapacityNotification
from billing.models import BlockingSystemSettings
from users.models import User

logger = logging.getLogger(__name__)


class PetOwnerIncapacityService:
    """
    Сервис для обработки недееспособности владельцев питомцев.
    
    Особенности:
    - Автоматическое обнаружение неактивных владельцев
    - Обработка отчетов от совладельцев
    - Отправка уведомлений
    - Выполнение автоматических действий
    """
    
    def __init__(self):
        """Инициализация сервиса."""
        self.settings = BlockingSystemSettings.get_settings()
    
    def check_inactive_owners(self) -> List[PetOwnerIncapacity]:
        """
        Проверяет неактивных основных владельцев и создает записи о недееспособности.
        
        Returns:
            List[PetOwnerIncapacity]: Список созданных записей о недееспособности
        """
        logger.info("Starting inactive owners check")
        
        threshold_days = self.settings.get_inactive_owner_threshold_days()
        inactive_date = timezone.now() - timedelta(days=threshold_days)
        
        # Находим питомцев с неактивными основными владельцами
        inactive_pets = Pet.objects.filter(
            main_owner__last_login__lt=inactive_date,
            main_owner__is_active=True
        ).exclude(
            incapacity_records__status__in=['pending_confirmation', 'confirmed_incapacity']
        )
        
        created_records = []
        
        for pet in inactive_pets:
            try:
                with transaction.atomic():
                    # Создаем запись о недееспособности
                    incapacity_record = PetOwnerIncapacity.objects.create(
                        pet=pet,
                        main_owner=pet.main_owner,
                        reported_by=pet.main_owner,  # Система обнаружила автоматически
                        flow_type='automatic_detection',
                        status='pending_confirmation'
                    )
                    
                    # Отправляем уведомления всем владельцам
                    self._send_confirmation_notifications(incapacity_record)
                    
                    created_records.append(incapacity_record)
                    logger.info(f"Created incapacity record for pet {pet.id} (owner: {pet.main_owner.id})")
                    
            except Exception as e:
                logger.error(f"Error creating incapacity record for pet {pet.id}: {str(e)}")
        
        logger.info(f"Created {len(created_records)} incapacity records")
        return created_records
    
    def report_pet_lost(self, pet: Pet, reported_by: User, reason: str = "") -> PetOwnerIncapacity:
        """
        Обрабатывает отчет о потере питомца от основного владельца.
        
        Args:
            pet: Питомец
            reported_by: Пользователь, сообщивший о потере (должен быть основной владелец)
            reason: Причина потери (опционально)
            
        Returns:
            PetOwnerIncapacity: Созданная запись о недееспособности
        """
        logger.info(f"Processing pet lost report for pet {pet.id} by user {reported_by.id}")
        
        try:
            with transaction.atomic():
                # Создаем запись о недееспособности
                incapacity_record = PetOwnerIncapacity.objects.create(
                    pet=pet,
                    main_owner=pet.main_owner,
                    reported_by=reported_by,
                    flow_type='coowner_report_pet_lost',
                    status='pending_confirmation',
                    incapacity_reason=reason
                )
                
                # Отправляем уведомления всем владельцам
                self._send_confirmation_notifications(incapacity_record)
                
                logger.info(f"Created pet lost incapacity record {incapacity_record.id}")
                return incapacity_record
                
        except Exception as e:
            logger.error(f"Error creating pet lost incapacity record: {str(e)}")
            raise
    
    def report_owner_incapacity(self, pet: Pet, reported_by: User, reason: str) -> PetOwnerIncapacity:
        """
        Обрабатывает отчет о недееспособности основного владельца от совладельца.
        
        Args:
            pet: Питомец
            reported_by: Пользователь, сообщивший о недееспособности
            reason: Причина недееспособности
            
        Returns:
            PetOwnerIncapacity: Созданная запись о недееспособности
        """
        logger.info(f"Processing owner incapacity report for pet {pet.id} by user {reported_by.id}")
        
        try:
            with transaction.atomic():
                # Создаем запись о недееспособности
                incapacity_record = PetOwnerIncapacity.objects.create(
                    pet=pet,
                    main_owner=pet.main_owner,
                    reported_by=reported_by,
                    flow_type='coowner_report_owner_incapacity',
                    status='pending_confirmation',
                    incapacity_reason=reason
                )
                
                # Отправляем уведомления всем владельцам
                self._send_confirmation_notifications(incapacity_record)
                
                logger.info(f"Created owner incapacity record {incapacity_record.id}")
                return incapacity_record
                
        except Exception as e:
            logger.error(f"Error creating owner incapacity record: {str(e)}")
            raise
    
    def confirm_pet_status(self, incapacity_record: PetOwnerIncapacity, confirmed_by: User, 
                          pet_is_ok: bool, notes: str = "") -> bool:
        """
        Подтверждает статус питомца основным владельцем.
        
        Args:
            incapacity_record: Запись о недееспособности
            confirmed_by: Пользователь, подтвердивший статус (должен быть основной владелец)
            pet_is_ok: True если питомец в порядке, False если потерян/умер
            notes: Дополнительные заметки
            
        Returns:
            bool: True если подтверждение успешно обработано
        """
        logger.info(f"Processing pet status confirmation for record {incapacity_record.id}")
        
        try:
            with transaction.atomic():
                # Проверяем права доступа - только основной владелец может подтвердить статус
                if incapacity_record.pet.main_owner != confirmed_by:
                    logger.error(f"User {confirmed_by.id} is not the main owner and cannot confirm pet status")
                    return False
                
                # Используем select_for_update для предотвращения гонки
                incapacity_record = PetOwnerIncapacity.objects.select_for_update().get(id=incapacity_record.id)
                
                if pet_is_ok:
                    # Питомец в порядке - разрешаем случай
                    incapacity_record.status = 'resolved'
                    incapacity_record.resolved_at = timezone.now()
                    incapacity_record.notes = f"Confirmed OK by {confirmed_by.email}: {notes}"
                    incapacity_record.save()
                    
                    # Отправляем уведомление о разрешении
                    self._send_resolution_notification(incapacity_record, confirmed_by)
                    
                else:
                    # Питомец потерян/умер - устанавливаем статус
                    incapacity_record.status = 'pet_lost'
                    incapacity_record.notes = f"Confirmed lost/deceased by {confirmed_by.email}: {notes}"
                    incapacity_record.save()
                    
                    # Отправляем уведомления о потере
                    self._send_pet_lost_notifications(incapacity_record)
                
                logger.info(f"Pet status confirmed for record {incapacity_record.id}")
                return True
                
        except Exception as e:
            logger.error(f"Error confirming pet status: {str(e)}")
            return False
    
    def process_deadline_actions(self) -> Dict[str, int]:
        """
        Обрабатывает автоматические действия для записей с истекшим дедлайном.
        
        Returns:
            Dict[str, int]: Статистика выполненных действий
        """
        logger.info("Processing deadline actions for incapacity records")
        
        # Находим записи с истекшим дедлайном
        overdue_records = PetOwnerIncapacity.objects.filter(
            status='pending_confirmation',
            confirmation_deadline__lt=timezone.now()
        )
        
        stats = {
            'pets_deleted': 0,
            'coowners_assigned': 0,
            'errors': 0
        }
        
        for record in overdue_records:
            try:
                # Используем select_for_update для предотвращения гонки
                with transaction.atomic():
                    record = PetOwnerIncapacity.objects.select_for_update().get(id=record.id)
                    
                    if record.take_auto_action():
                        if record.auto_action_taken == 'pet_deleted':
                            stats['pets_deleted'] += 1
                        elif record.auto_action_taken == 'coowner_assigned':
                            stats['coowners_assigned'] += 1
                        
                        # Отправляем уведомления о выполненных действиях
                        self._send_auto_action_notifications(record)
                        
                    else:
                        stats['errors'] += 1
                        
            except Exception as e:
                logger.error(f"Error processing deadline action for record {record.id}: {str(e)}")
                stats['errors'] += 1
        
        logger.info(f"Processed deadline actions: {stats}")
        return stats
    
    def _send_confirmation_notifications(self, incapacity_record: PetOwnerIncapacity) -> None:
        """Отправляет уведомления о необходимости подтверждения статуса питомца основному владельцу."""
        deadline_days = self.settings.get_pet_confirmation_deadline_days()
        
        # Отправляем уведомление только основному владельцу
        main_owner = incapacity_record.main_owner
        try:
            notification = PetIncapacityNotification.objects.create(
                incapacity_record=incapacity_record,
                notification_type='confirmation_request',
                recipient=main_owner,
                subject=_('Pet Status Confirmation Required'),
                message=self._get_confirmation_message(incapacity_record, main_owner, deadline_days)
            )
            
            # Отправляем email
            self._send_email_notification(notification)
            
            # Добавляем в список отправленных уведомлений
            incapacity_record.notifications_sent.append(notification.id)
            
        except Exception as e:
            logger.error(f"Error sending confirmation notification to {main_owner.email}: {str(e)}")
        
        incapacity_record.save()
    
    def _send_resolution_notification(self, incapacity_record: PetOwnerIncapacity, confirmed_by: User) -> None:
        """Отправляет уведомления о разрешении случая недееспособности."""
        owners = list(incapacity_record.pet.owners.all())
        if incapacity_record.main_owner not in owners:
            owners.append(incapacity_record.main_owner)
        
        for owner in owners:
            if owner != confirmed_by:  # Не отправляем тому, кто подтвердил
                try:
                    notification = PetIncapacityNotification.objects.create(
                        incapacity_record=incapacity_record,
                        notification_type='resolution_notification',
                        recipient=owner,
                        subject=_('Pet Status Confirmed - Case Resolved'),
                        message=self._get_resolution_message(incapacity_record, confirmed_by)
                    )
                    
                    self._send_email_notification(notification)
                    
                except Exception as e:
                    logger.error(f"Error sending resolution notification to {owner.email}: {str(e)}")
    
    def _send_pet_lost_notifications(self, incapacity_record: PetOwnerIncapacity) -> None:
        """Отправляет уведомления о потере питомца."""
        owners = list(incapacity_record.pet.owners.all())
        if incapacity_record.main_owner not in owners:
            owners.append(incapacity_record.main_owner)
        
        for owner in owners:
            try:
                notification = PetIncapacityNotification.objects.create(
                    incapacity_record=incapacity_record,
                    notification_type='auto_action_notification',
                    recipient=owner,
                    subject=_('Pet Status Confirmed - Pet Lost/Deceased'),
                    message=self._get_pet_lost_message(incapacity_record)
                )
                
                self._send_email_notification(notification)
                
            except Exception as e:
                logger.error(f"Error sending pet lost notification to {owner.email}: {str(e)}")
    
    def _send_auto_action_notifications(self, incapacity_record: PetOwnerIncapacity) -> None:
        """Отправляет уведомления о выполненных автоматических действиях."""
        if incapacity_record.auto_action_taken == 'pet_deleted':
            # Питомец удален - уведомляем всех владельцев
            owners = list(incapacity_record.pet.owners.all())
            if incapacity_record.main_owner not in owners:
                owners.append(incapacity_record.main_owner)
            
            for owner in owners:
                try:
                    notification = PetIncapacityNotification.objects.create(
                        incapacity_record=incapacity_record,
                        notification_type='auto_action_notification',
                        recipient=owner,
                        subject=_('Pet Data Automatically Deleted'),
                        message=self._get_pet_deleted_message(incapacity_record)
                    )
                    
                    self._send_email_notification(notification)
                    
                except Exception as e:
                    logger.error(f"Error sending pet deleted notification to {owner.email}: {str(e)}")
        
        elif incapacity_record.auto_action_taken == 'coowner_assigned':
            # Назначен новый основной владелец
            owners = list(incapacity_record.pet.owners.all())
            if incapacity_record.main_owner not in owners:
                owners.append(incapacity_record.main_owner)
            
            for owner in owners:
                try:
                    notification = PetIncapacityNotification.objects.create(
                        incapacity_record=incapacity_record,
                        notification_type='auto_action_notification',
                        recipient=owner,
                        subject=_('New Main Owner Assigned'),
                        message=self._get_coowner_assigned_message(incapacity_record)
                    )
                    
                    self._send_email_notification(notification)
                    
                except Exception as e:
                    logger.error(f"Error sending coowner assigned notification to {owner.email}: {str(e)}")
    
    def _send_email_notification(self, notification: PetIncapacityNotification) -> bool:
        """Отправляет email уведомление."""
        try:
            success = send_mail(
                subject=notification.subject,
                message=notification.message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.recipient.email],
                fail_silently=False
            )
            
            if success:
                notification.mark_as_sent()
                logger.info(f"Email notification sent to {notification.recipient.email}")
                return True
            else:
                notification.mark_as_failed("Email sending failed")
                logger.error(f"Failed to send email notification to {notification.recipient.email}")
                return False
                
        except Exception as e:
            notification.mark_as_failed(str(e))
            logger.error(f"Error sending email notification to {notification.recipient.email}: {str(e)}")
            return False
    
    def _get_confirmation_message(self, incapacity_record: PetOwnerIncapacity, owner: User, deadline_days: int) -> str:
        """Формирует сообщение для запроса подтверждения статуса питомца."""
        return _("""
Dear {owner_name},

We have detected that the main owner of the pet "{pet_name}" has been inactive for an extended period.

Please confirm the current status of the pet "{pet_name}" within {deadline_days} days.

If no confirmation is received within this period, the system will automatically:
- Delete the pet's data if auto-deletion is enabled, OR
- Assign a co-owner as the new main owner if auto-assignment is enabled

To confirm the pet's status, please log into your account and respond to this notification.

Best regards,
PetsCare Team
        """).format(
            owner_name=owner.get_full_name() or owner.email,
            pet_name=incapacity_record.pet.name,
            deadline_days=deadline_days
        )
    
    def _get_resolution_message(self, incapacity_record: PetOwnerIncapacity, confirmed_by: User) -> str:
        """Формирует сообщение о разрешении случая недееспособности."""
        return _("""
Dear {owner_name},

The pet "{pet_name}" status has been confirmed as OK by {confirmed_by_name}.

The incapacity case has been resolved and no further action is required.

Best regards,
PetsCare Team
        """).format(
            owner_name=incapacity_record.main_owner.get_full_name() or incapacity_record.main_owner.email,
            pet_name=incapacity_record.pet.name,
            confirmed_by_name=confirmed_by.get_full_name() or confirmed_by.email
        )
    
    def _get_pet_lost_message(self, incapacity_record: PetOwnerIncapacity) -> str:
        """Формирует сообщение о потере питомца."""
        return _("""
Dear {owner_name},

The pet "{pet_name}" has been confirmed as lost/deceased.

The pet's data will be automatically deleted within {deadline_days} days if no further action is taken.

Best regards,
PetsCare Team
        """).format(
            owner_name=incapacity_record.main_owner.get_full_name() or incapacity_record.main_owner.email,
            pet_name=incapacity_record.pet.name,
            deadline_days=self.settings.get_pet_confirmation_deadline_days()
        )
    
    def _get_pet_deleted_message(self, incapacity_record: PetOwnerIncapacity) -> str:
        """Формирует сообщение об автоматическом удалении питомца."""
        return _("""
Dear {owner_name},

The pet "{pet_name}" data has been automatically deleted due to lack of confirmation within the deadline.

Best regards,
PetsCare Team
        """).format(
            owner_name=incapacity_record.main_owner.get_full_name() or incapacity_record.main_owner.email,
            pet_name=incapacity_record.pet.name
        )
    
    def _get_coowner_assigned_message(self, incapacity_record: PetOwnerIncapacity) -> str:
        """Формирует сообщение о назначении нового основного владельца."""
        return _("""
Dear {owner_name},

A new main owner has been automatically assigned for the pet "{pet_name}" due to the previous main owner's inactivity.

New main owner: {new_owner_name}

Best regards,
PetsCare Team
        """).format(
            owner_name=incapacity_record.main_owner.get_full_name() or incapacity_record.main_owner.email,
            pet_name=incapacity_record.pet.name,
            new_owner_name=incapacity_record.new_main_owner.get_full_name() or incapacity_record.new_main_owner.email
        ) 