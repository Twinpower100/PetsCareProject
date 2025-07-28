"""
Сервис для отправки email через Gmail API с OAuth2 аутентификацией.

Этот модуль заменяет стандартный SMTP backend Django на более безопасный
и надежный Gmail API с OAuth2 аутентификацией.
"""

import os
import base64
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional, Dict, Any
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils.translation import gettext_lazy as _

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GMAIL_API_AVAILABLE = True
except ImportError:
    GMAIL_API_AVAILABLE = False
    logging.warning("Gmail API libraries not available. Install: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")

logger = logging.getLogger(__name__)


class GmailAPIService:
    """
    Сервис для работы с Gmail API.
    
    Особенности:
    - OAuth2 аутентификация
    - Автоматическое обновление токенов
    - Поддержка HTML и текстовых писем
    - Поддержка вложений
    - Обработка ошибок и retry логика
    """
    
    # Если изменяете эти области, удалите файл token.json.
    SCOPES = ['https://www.googleapis.com/auth/gmail.send']
    
    def __init__(self):
        """Инициализация сервиса Gmail API."""
        self.service = None
        self.credentials = None
        self._initialize_service()
    
    def _initialize_service(self):
        """Инициализация Gmail API сервиса."""
        if not GMAIL_API_AVAILABLE:
            logger.error("Gmail API libraries not available")
            return
        
        try:
            # Получаем учетные данные
            self.credentials = self._get_credentials()
            
            if self.credentials:
                # Создаем сервис
                self.service = build('gmail', 'v1', credentials=self.credentials)
                logger.info("Gmail API service initialized successfully")
            else:
                logger.error("Failed to get Gmail API credentials")
                
        except Exception as e:
            logger.error(f"Error initializing Gmail API service: {str(e)}")
    
    def _get_credentials(self):
        """
        Получение учетных данных для Gmail API.
        
        Returns:
            Credentials: Объект учетных данных или None
        """
        creds = None
        
        # Путь к файлу с токеном
        token_path = getattr(settings, 'GMAIL_TOKEN_FILE', 'token.json')
        
        # Путь к файлу с учетными данными приложения
        credentials_path = getattr(settings, 'GMAIL_CREDENTIALS_FILE', 'credentials.json')
        
        # Проверяем, есть ли сохраненный токен
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)
                logger.info("Loaded existing Gmail API credentials from token file")
            except Exception as e:
                logger.warning(f"Error loading token file: {str(e)}")
        
        # Если нет действительных учетных данных, запрашиваем их
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("Refreshed Gmail API credentials")
                except Exception as e:
                    logger.error(f"Error refreshing credentials: {str(e)}")
                    creds = None
            
            # Если все еще нет учетных данных, запрашиваем новые
            if not creds:
                if os.path.exists(credentials_path):
                    try:
                        flow = InstalledAppFlow.from_client_secrets_file(
                            credentials_path, self.SCOPES)
                        creds = flow.run_local_server(port=0)
                        logger.info("Generated new Gmail API credentials")
                    except Exception as e:
                        logger.error(f"Error generating credentials: {str(e)}")
                        return None
                else:
                    logger.error(f"Credentials file not found: {credentials_path}")
                    return None
            
            # Сохраняем учетные данные для следующего запуска
            try:
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
                logger.info("Saved Gmail API credentials to token file")
            except Exception as e:
                logger.error(f"Error saving token file: {str(e)}")
        
        return creds
    
    def send_email(self, 
                   subject: str, 
                   message: str, 
                   from_email: str, 
                   recipient_list: List[str],
                   html_message: Optional[str] = None,
                   attachments: Optional[List[Dict[str, Any]]] = None,
                   fail_silently: bool = False) -> bool:
        """
        Отправка email через Gmail API.
        
        Args:
            subject: Тема письма
            message: Текст письма
            from_email: Email отправителя
            recipient_list: Список получателей
            html_message: HTML версия письма (опционально)
            attachments: Список вложений (опционально)
            fail_silently: Не вызывать исключения при ошибке
            
        Returns:
            bool: True если письмо отправлено успешно, False в противном случае
        """
        if not self.service:
            error_msg = "Gmail API service not initialized"
            logger.error(error_msg)
            if not fail_silently:
                raise RuntimeError(error_msg)
            return False
        
        try:
            # Создаем сообщение
            message_obj = self._create_message(
                subject, message, from_email, recipient_list, 
                html_message, attachments
            )
            
            # Отправляем сообщение
            sent_message = self.service.users().messages().send(
                userId='me', body=message_obj
            ).execute()
            
            logger.info(f"Email sent successfully. Message ID: {sent_message['id']}")
            return True
            
        except HttpError as error:
            error_msg = f"Gmail API error: {error}"
            logger.error(error_msg)
            if not fail_silently:
                raise RuntimeError(error_msg)
            return False
        except Exception as e:
            error_msg = f"Error sending email: {str(e)}"
            logger.error(error_msg)
            if not fail_silently:
                raise RuntimeError(error_msg)
            return False
    
    def _create_message(self, 
                       subject: str, 
                       message: str, 
                       from_email: str, 
                       recipient_list: List[str],
                       html_message: Optional[str] = None,
                       attachments: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Создание сообщения для Gmail API.
        
        Args:
            subject: Тема письма
            message: Текст письма
            from_email: Email отправителя
            recipient_list: Список получателей
            html_message: HTML версия письма
            attachments: Список вложений
            
        Returns:
            Dict: Сообщение в формате Gmail API
        """
        # Создаем MIME сообщение
        if html_message:
            msg = MIMEMultipart('alternative')
            text_part = MIMEText(message, 'plain', 'utf-8')
            html_part = MIMEText(html_message, 'html', 'utf-8')
            msg.attach(text_part)
            msg.attach(html_part)
        else:
            msg = MIMEText(message, 'plain', 'utf-8')
        
        # Устанавливаем заголовки
        msg['to'] = ', '.join(recipient_list)
        msg['from'] = from_email
        msg['subject'] = subject
        
        # Добавляем вложения
        if attachments:
            # Если у нас есть вложения, создаем multipart/mixed
            if not isinstance(msg, MIMEMultipart):
                original_msg = msg
                msg = MIMEMultipart('mixed')
                msg['to'] = original_msg['to']
                msg['from'] = original_msg['from']
                msg['subject'] = original_msg['subject']
                msg.attach(original_msg)
            
            for attachment in attachments:
                self._add_attachment(msg, attachment)
        
        # Кодируем сообщение в base64
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
        
        return {'raw': raw_message}
    
    def _add_attachment(self, msg: MIMEMultipart, attachment: Dict[str, Any]):
        """
        Добавление вложения к сообщению.
        
        Args:
            msg: MIME сообщение
            attachment: Словарь с данными вложения
        """
        try:
            filename = attachment.get('filename', 'attachment')
            content = attachment.get('content', b'')
            content_type = attachment.get('content_type', 'application/octet-stream')
            
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {filename}'
            )
            
            msg.attach(part)
            
        except Exception as e:
            logger.error(f"Error adding attachment {filename}: {str(e)}")
    
    def test_connection(self) -> bool:
        """
        Тестирование подключения к Gmail API.
        
        Returns:
            bool: True если подключение работает, False в противном случае
        """
        if not self.service:
            logger.error("Gmail API service not initialized")
            return False
        
        try:
            # Пытаемся получить профиль пользователя
            profile = self.service.users().getProfile(userId='me').execute()
            logger.info(f"Gmail API connection test successful. Email: {profile.get('emailAddress')}")
            return True
        except Exception as e:
            logger.error(f"Gmail API connection test failed: {str(e)}")
            return False


# Глобальный экземпляр сервиса
_gmail_service = None


def get_gmail_service() -> Optional[GmailAPIService]:
    """
    Получение глобального экземпляра Gmail API сервиса.
    
    Returns:
        GmailAPIService: Экземпляр сервиса или None
    """
    global _gmail_service
    
    if _gmail_service is None:
        try:
            _gmail_service = GmailAPIService()
        except Exception as e:
            logger.error(f"Error creating Gmail API service: {str(e)}")
            return None
    
    return _gmail_service


def send_email_via_gmail_api(subject: str, 
                            message: str, 
                            from_email: str, 
                            recipient_list: List[str],
                            html_message: Optional[str] = None,
                            attachments: Optional[List[Dict[str, Any]]] = None,
                            fail_silently: bool = False) -> bool:
    """
    Отправка email через Gmail API (удобная функция-обертка).
    
    Args:
        subject: Тема письма
        message: Текст письма
        from_email: Email отправителя
        recipient_list: Список получателей
        html_message: HTML версия письма (опционально)
        attachments: Список вложений (опционально)
        fail_silently: Не вызывать исключения при ошибке
        
    Returns:
        bool: True если письмо отправлено успешно, False в противном случае
    """
    service = get_gmail_service()
    
    if not service:
        error_msg = "Gmail API service not available"
        logger.error(error_msg)
        if not fail_silently:
            raise RuntimeError(error_msg)
        return False
    
    return service.send_email(
        subject=subject,
        message=message,
        from_email=from_email,
        recipient_list=recipient_list,
        html_message=html_message,
        attachments=attachments,
        fail_silently=fail_silently
    ) 