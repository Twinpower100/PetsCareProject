"""
Email backend для Django, использующий Gmail API с OAuth2.

Этот backend заменяет стандартный SMTP backend на более безопасный
и надежный Gmail API с OAuth2 аутентификацией.
"""

import logging
from typing import List, Optional
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail import EmailMessage
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .gmail_api_service import send_email_via_gmail_api

logger = logging.getLogger(__name__)


class GmailAPIBackend(BaseEmailBackend):
    """
    Email backend для отправки писем через Gmail API.
    
    Особенности:
    - OAuth2 аутентификация
    - Автоматическое обновление токенов
    - Поддержка HTML и текстовых писем
    - Поддержка вложений
    - Fallback на SMTP при ошибках
    """
    
    def __init__(self, fail_silently=False, **kwargs):
        """
        Инициализация backend.
        
        Args:
            fail_silently: Не вызывать исключения при ошибке
            **kwargs: Дополнительные параметры
        """
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.fail_silently = fail_silently
        
        # Проверяем, включен ли Gmail API
        self.use_gmail_api = getattr(settings, 'USE_GMAIL_API', True)
        
        # Fallback на SMTP
        self.fallback_to_smtp = getattr(settings, 'GMAIL_API_FALLBACK_TO_SMTP', True)
        
        logger.info(f"Gmail API Backend initialized. Use Gmail API: {self.use_gmail_api}, Fallback to SMTP: {self.fallback_to_smtp}")
    
    def send_messages(self, email_messages: List[EmailMessage]) -> int:
        """
        Отправка списка email сообщений.
        
        Args:
            email_messages: Список EmailMessage объектов
            
        Returns:
            int: Количество успешно отправленных сообщений
        """
        if not email_messages:
            return 0
        
        num_sent = 0
        
        for message in email_messages:
            if self._send_message(message):
                num_sent += 1
        
        logger.info(f"Sent {num_sent} out of {len(email_messages)} messages via Gmail API")
        return num_sent
    
    def _send_message(self, message: EmailMessage) -> bool:
        """
        Отправка одного email сообщения.
        
        Args:
            message: EmailMessage объект
            
        Returns:
            bool: True если сообщение отправлено успешно
        """
        try:
            # Подготавливаем данные для отправки
            subject = message.subject
            body = message.body
            from_email = message.from_email
            to_emails = message.to
            
            # HTML версия
            html_message = None
            if hasattr(message, 'alternatives') and message.alternatives:
                for content, mimetype in message.alternatives:
                    if mimetype == 'text/html':
                        html_message = content
                        break
            
            # Вложения
            attachments = []
            if message.attachments:
                for filename, content, mimetype in message.attachments:
                    attachments.append({
                        'filename': filename,
                        'content': content,
                        'content_type': mimetype
                    })
            
            # Отправляем через Gmail API
            if self.use_gmail_api:
                success = send_email_via_gmail_api(
                    subject=subject,
                    message=body,
                    from_email=from_email,
                    recipient_list=to_emails,
                    html_message=html_message,
                    attachments=attachments,
                    fail_silently=self.fail_silently
                )
                
                if success:
                    logger.info(f"Email sent successfully via Gmail API to {to_emails}")
                    return True
                else:
                    logger.warning(f"Failed to send email via Gmail API to {to_emails}")
            
            # Fallback на SMTP
            if self.fallback_to_smtp and not self.use_gmail_api:
                return self._send_via_smtp_fallback(message)
            
            return False
            
        except Exception as e:
            error_msg = f"Error sending email via Gmail API: {str(e)}"
            logger.error(error_msg)
            
            # Fallback на SMTP
            if self.fallback_to_smtp:
                logger.info("Attempting SMTP fallback")
                return self._send_via_smtp_fallback(message)
            
            if not self.fail_silently:
                raise
            
            return False
    
    def _send_via_smtp_fallback(self, message: EmailMessage) -> bool:
        """
        Отправка через SMTP fallback.
        
        Args:
            message: EmailMessage объект
            
        Returns:
            bool: True если сообщение отправлено успешно
        """
        try:
            from django.core.mail.backends.smtp import EmailBackend as SMTPBackend
            
            # Создаем SMTP backend
            smtp_backend = SMTPBackend(
                host=settings.EMAIL_HOST,
                port=settings.EMAIL_PORT,
                username=settings.EMAIL_HOST_USER,
                password=settings.EMAIL_HOST_PASSWORD,
                use_tls=settings.EMAIL_USE_TLS,
                use_ssl=settings.EMAIL_USE_SSL,
                fail_silently=self.fail_silently,
                timeout=settings.EMAIL_TIMEOUT
            )
            
            # Отправляем сообщение
            result = smtp_backend.send_messages([message])
            
            if result > 0:
                logger.info(f"Email sent successfully via SMTP fallback to {message.to}")
                return True
            else:
                logger.warning(f"Failed to send email via SMTP fallback to {message.to}")
                return False
                
        except Exception as e:
            error_msg = f"Error sending email via SMTP fallback: {str(e)}"
            logger.error(error_msg)
            
            if not self.fail_silently:
                raise
            
            return False
    
    def test_connection(self) -> bool:
        """
        Тестирование подключения к Gmail API.
        
        Returns:
            bool: True если подключение работает
        """
        if not self.use_gmail_api:
            logger.info("Gmail API disabled, skipping connection test")
            return True
        
        try:
            from .gmail_api_service import get_gmail_service
            
            service = get_gmail_service()
            if service:
                return service.test_connection()
            else:
                logger.error("Gmail API service not available")
                return False
                
        except Exception as e:
            logger.error(f"Error testing Gmail API connection: {str(e)}")
            return False 