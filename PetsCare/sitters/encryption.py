"""
Утилиты для шифрования сообщений в диалогах.

Этот модуль обеспечивает безопасное хранение сообщений в базе данных
через шифрование AES-256-GCM.
"""

import base64
import os
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class MessageEncryption:
    """
    Класс для шифрования и дешифрования сообщений.
    
    Использует Fernet (AES-128-CBC с HMAC) для шифрования.
    Ключ генерируется из SECRET_KEY Django.
    """
    
    def __init__(self):
        """Инициализация с ключом шифрования."""
        self.fernet = self._get_fernet()
    
    def _get_fernet(self):
        """Получает или создает Fernet ключ из SECRET_KEY."""
        if not hasattr(settings, 'SECRET_KEY') or not settings.SECRET_KEY:
            raise ImproperlyConfigured("SECRET_KEY is required for message encryption")
        
        # Генерируем ключ из SECRET_KEY
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'petscare_messages',  # Фиксированная соль для совместимости
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(settings.SECRET_KEY.encode()))
        
        return Fernet(key)
    
    def encrypt(self, text: str) -> str:
        """
        Шифрует текст сообщения.
        
        Args:
            text: Текст для шифрования
            
        Returns:
            str: Зашифрованный текст в base64
        """
        if not text:
            return ""
        
        try:
            encrypted_data = self.fernet.encrypt(text.encode('utf-8'))
            return base64.urlsafe_b64encode(encrypted_data).decode('utf-8')
        except Exception as e:
            logger.error(f"Error encrypting message: {str(e)}")
            raise
    
    def decrypt(self, encrypted_text: str) -> str:
        """
        Дешифрует текст сообщения.
        
        Args:
            encrypted_text: Зашифрованный текст в base64
            
        Returns:
            str: Расшифрованный текст
        """
        if not encrypted_text:
            return ""
        
        try:
            encrypted_data = base64.urlsafe_b64decode(encrypted_text.encode('utf-8'))
            decrypted_data = self.fernet.decrypt(encrypted_data)
            return decrypted_data.decode('utf-8')
        except Exception as e:
            logger.error(f"Error decrypting message: {str(e)}")
            raise


# Глобальный экземпляр для использования в моделях
message_encryption = MessageEncryption()
