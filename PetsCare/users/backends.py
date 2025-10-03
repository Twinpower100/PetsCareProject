"""
Кастомные бэкенды аутентификации для пользователей.
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class EmailBackend(ModelBackend):
    """
    Кастомный бэкенд аутентификации, позволяющий входить по email.
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            # Пытаемся найти пользователя по email или username
            user = User.objects.get(
                Q(email=username) | Q(username=username)
            )
            
            # Проверяем пароль
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            # Если найдено несколько пользователей, берем первого
            user = User.objects.filter(
                Q(email=username) | Q(username=username)
            ).first()
            if user and user.check_password(password):
                return user
        return None
    
    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
