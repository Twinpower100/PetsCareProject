"""
Утилиты для двухшаговой регистрации через Google.
"""

from django.core import signing


GOOGLE_SIGNUP_PENDING_SALT = 'users.google_signup.pending'
GOOGLE_SIGNUP_PENDING_MAX_AGE_SECONDS = 15 * 60


def build_pending_google_signup_token(google_user_data):
    """
    Подписывает краткоживущие данные Google до завершения регистрации.
    """
    payload = {
        'email': google_user_data.get('email'),
        'name': google_user_data.get('name'),
        'picture': google_user_data.get('picture'),
        'google_id': google_user_data.get('google_id'),
        'phone': google_user_data.get('phone'),
        'requires_manual_phone': bool(google_user_data.get('requires_manual_phone')),
    }
    return signing.dumps(payload, salt=GOOGLE_SIGNUP_PENDING_SALT)


def load_pending_google_signup_token(token):
    """
    Загружает и проверяет signed token для незавершённой Google-регистрации.
    """
    return signing.loads(
        token,
        salt=GOOGLE_SIGNUP_PENDING_SALT,
        max_age=GOOGLE_SIGNUP_PENDING_MAX_AGE_SECONDS,
    )
