"""
Константы для модуля pets.

Используются для валидации фото питомца и в API для фронтенда.
"""
from django.utils.translation import gettext_lazy as _

# Фото питомца: лимиты
PET_PHOTO_MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 МБ
PET_PHOTO_MAX_SIZE_MB = 5
PET_PHOTO_MAX_WIDTH = 2048
PET_PHOTO_MAX_HEIGHT = 2048
PET_PHOTO_ALLOWED_CONTENT_TYPES = (
    'image/jpeg',
    'image/png',
    'image/webp',
)
PET_PHOTO_ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')


def get_pet_photo_constraints_for_api(language_code=None):
    """Словарь лимитов и подсказки для API (фронт)."""
    from django.utils import translation
    prev = translation.get_language()
    if language_code:
        translation.activate(language_code)
    try:
        hint = _(
            'Photo: JPEG, PNG or WebP. Max size %(max_mb)s MB, '
            'max resolution %(max_width)s×%(max_height)s px.'
        ) % {
            'max_mb': PET_PHOTO_MAX_SIZE_MB,
            'max_width': PET_PHOTO_MAX_WIDTH,
            'max_height': PET_PHOTO_MAX_HEIGHT,
        }
        return {
            'max_size_bytes': PET_PHOTO_MAX_SIZE_BYTES,
            'max_size_mb': PET_PHOTO_MAX_SIZE_MB,
            'max_width': PET_PHOTO_MAX_WIDTH,
            'max_height': PET_PHOTO_MAX_HEIGHT,
            'allowed_content_types': list(PET_PHOTO_ALLOWED_CONTENT_TYPES),
            'allowed_extensions': list(PET_PHOTO_ALLOWED_EXTENSIONS),
            'hint': str(hint),
        }
    finally:
        translation.activate(prev)
