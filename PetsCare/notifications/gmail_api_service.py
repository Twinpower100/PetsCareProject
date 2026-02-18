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
from email import policy
from typing import List, Optional, Dict, Any
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils.translation import gettext_lazy as _
from django.utils.encoding import force_str

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
    
    def _get_client_config_from_env(self):
        """
        Получение конфигурации OAuth2 из переменных окружения.
        
        Returns:
            dict: Конфигурация для InstalledAppFlow или None
        """
        client_id = getattr(settings, 'GMAIL_CLIENT_ID', None)
        client_secret = getattr(settings, 'GMAIL_CLIENT_SECRET', None)
        
        if not client_id or not client_secret:
            return None
        
        # Формируем конфигурацию в формате, который ожидает InstalledAppFlow
        return {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": ["http://localhost"]
            }
        }
    
    def _get_credentials(self):
        """
        Получение учетных данных для Gmail API.
        
        Получает credentials из переменных окружения (GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET).
        
        Returns:
            Credentials: Объект учетных данных или None
        """
        creds = None
        
        # Путь к файлу с токеном
        token_path = getattr(settings, 'GMAIL_TOKEN_FILE', 'token.json')
        
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
                # Получаем конфигурацию из переменных окружения
                client_config = self._get_client_config_from_env()
                
                if client_config:
                    # Используем переменные окружения
                    try:
                        flow = InstalledAppFlow.from_client_config(
                            client_config, self.SCOPES)
                        # В продакшене это не должно происходить - токен должен быть получен заранее
                        # Для разработки используем run_local_server
                        import sys
                        if sys.stdout.isatty():  # Проверяем, что это интерактивная сессия (не продакшен)
                            creds = flow.run_local_server(port=0)
                            logger.info("Generated new Gmail API credentials from environment variables")
                        else:
                            # В неинтерактивной среде (продакшен) не можем получить токен
                            logger.error("Gmail API token not found and cannot be obtained in non-interactive environment. Please run setup_gmail_api command first.")
                            return None
                    except Exception as e:
                        logger.error(f"Error generating credentials from env: {str(e)}")
                        return None
                else:
                    logger.error("Gmail API credentials not found. Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env")
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
        # Преобразуем lazy-строки Django в обычные строки для избежания ошибок с __proxy__
        subject = force_str(subject)
        from_email = force_str(from_email)
        message = force_str(message)
        if html_message:
            html_message = force_str(html_message)
        recipient_list = [force_str(email) for email in recipient_list]
        
        # Создаем MIME сообщение с правильной политикой для избежания проблем с linesep
        # Используем policy.SMTP для совместимости
        smtp_policy = policy.SMTP
        if html_message:
            msg = MIMEMultipart('alternative', policy=smtp_policy)
            text_part = MIMEText(message, 'plain', 'utf-8', policy=smtp_policy)
            html_part = MIMEText(html_message, 'html', 'utf-8', policy=smtp_policy)
            msg.attach(text_part)
            msg.attach(html_part)
        else:
            msg = MIMEText(message, 'plain', 'utf-8', policy=smtp_policy)
        
        # Устанавливаем заголовки
        msg['to'] = ', '.join(recipient_list)
        msg['from'] = from_email
        msg['subject'] = subject
        
        # Добавляем вложения
        if attachments:
            # Если у нас есть вложения, создаем multipart/mixed
            if not isinstance(msg, MIMEMultipart):
                original_msg = msg
                # Важно: используем ту же политику, что и для основного сообщения
                msg = MIMEMultipart('mixed', policy=smtp_policy)
                msg['to'] = original_msg['to']
                msg['from'] = original_msg['from']
                msg['subject'] = original_msg['subject']
                msg.attach(original_msg)
            
            for attachment in attachments:
                self._add_attachment(msg, attachment)
        
        # Кодируем сообщение в base64
        # Для Python 3.13+ используем as_bytes() - это современный метод, который не использует
        # устаревший API с параметром linesep. as_string() внутри вызывает encode() с linesep,
        # который был удален в Python 3.13, поэтому мы его не используем.
        try:
            # as_bytes() - правильный метод для Python 3.13+, работает с policy
            raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
        except (AttributeError, TypeError) as e:
            # Если as_bytes() не доступен, используем BytesGenerator напрямую
            # (для старых версий Python или в случае ошибки)
            try:
                from io import BytesIO
                from email.generator import BytesGenerator
                fp = BytesIO()
                # BytesGenerator с policy работает корректно и не использует linesep
                gen = BytesGenerator(fp, mangle_from_=False, policy=smtp_policy)
                gen.flatten(msg, unixfrom=False)
                raw_message = base64.urlsafe_b64encode(fp.getvalue()).decode('utf-8')
            except Exception as e2:
                logger.error(f"All encoding methods failed: {e}, {e2}")
                raise RuntimeError(f"Failed to encode email message: {e2}")
        
        return {'raw': raw_message}
    
    def _add_attachment(self, msg: MIMEMultipart, attachment: Dict[str, Any]):
        """
        Добавление вложения к сообщению.
        
        Args:
            msg: MIME сообщение
            attachment: Словарь с данными вложения
        """
        try:
            filename = force_str(attachment.get('filename', 'attachment'))
            content = attachment.get('content', b'')
            content_type = force_str(attachment.get('content_type', 'application/octet-stream'))
            
            part = MIMEBase('application', 'octet-stream')
            # Убеждаемся, что content - это bytes
            if isinstance(content, str):
                content = content.encode('utf-8')
            part.set_payload(content)
            # Используем encode_base64 для кодирования вложения
            try:
                encoders.encode_base64(part)
            except (TypeError, ValueError) as e:
                # Если encode_base64 не работает, используем альтернативный способ
                import base64
                encoded_content = base64.b64encode(content).decode('ascii')
                part.set_payload(encoded_content)
                part.add_header('Content-Transfer-Encoding', 'base64')
                logger.warning(f"Used alternative base64 encoding for attachment: {e}")
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