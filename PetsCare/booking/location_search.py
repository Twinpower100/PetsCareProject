from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Sequence

from providers.models import ProviderLocation


CYRILLIC_TO_LATIN_MAP = {
    'а': 'a',
    'б': 'b',
    'в': 'v',
    'г': 'g',
    'д': 'd',
    'е': 'e',
    'ё': 'e',
    'ж': 'zh',
    'з': 'z',
    'и': 'i',
    'й': 'y',
    'к': 'k',
    'л': 'l',
    'м': 'm',
    'н': 'n',
    'о': 'o',
    'п': 'p',
    'р': 'r',
    'с': 's',
    'т': 't',
    'у': 'u',
    'ф': 'f',
    'х': 'kh',
    'ц': 'ts',
    'ч': 'ch',
    'ш': 'sh',
    'щ': 'sch',
    'ъ': '',
    'ы': 'y',
    'ь': '',
    'э': 'e',
    'ю': 'yu',
    'я': 'ya',
}

LATIN_TO_CYRILLIC_KEYBOARD_MAP = str.maketrans({
    'q': 'й',
    'w': 'ц',
    'e': 'у',
    'r': 'к',
    't': 'е',
    'y': 'н',
    'u': 'г',
    'i': 'ш',
    'o': 'щ',
    'p': 'з',
    '[': 'х',
    ']': 'ъ',
    'a': 'ф',
    's': 'ы',
    'd': 'в',
    'f': 'а',
    'g': 'п',
    'h': 'р',
    'j': 'о',
    'k': 'л',
    'l': 'д',
    ';': 'ж',
    "'": 'э',
    'z': 'я',
    'x': 'ч',
    'c': 'с',
    'v': 'м',
    'b': 'и',
    'n': 'т',
    'm': 'ь',
    ',': 'б',
    '.': 'ю',
    '`': 'ё',
})

CYRILLIC_TO_LATIN_KEYBOARD_MAP = str.maketrans({
    value: key for key, value in LATIN_TO_CYRILLIC_KEYBOARD_MAP.items()
})


@dataclass(frozen=True)
class LocationSearchPayload:
    raw_query: str = ''
    label: str = ''
    place_id: str = ''
    city: str = ''
    country: str = ''
    source: str = ''
    lat: float | None = None
    lon: float | None = None

    @property
    def has_text(self) -> bool:
        return any([self.raw_query, self.label, self.city, self.country])


def normalize_location_text(value: str) -> str:
    """Приводит пользовательский текст к сопоставимой форме для location search."""
    if not value:
        return ''

    normalized = unicodedata.normalize('NFKD', value)
    normalized = ''.join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold().replace('ß', 'ss')
    normalized = re.sub(r'[\s,;|/\\]+', ' ', normalized)
    normalized = re.sub(r'[^0-9a-zа-яё\-\s]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def transliterate_cyrillic_to_latin(value: str) -> str:
    """Транслитерирует кириллицу в латиницу для мультиязычного поиска."""
    if not value:
        return ''
    return ''.join(CYRILLIC_TO_LATIN_MAP.get(char, char) for char in value.casefold())


def swap_keyboard_layout(value: str) -> set[str]:
    """Генерирует варианты строки при ошибочной EN/RU раскладке."""
    if not value:
        return set()

    lowered = value.casefold()
    variants = {
        lowered.translate(LATIN_TO_CYRILLIC_KEYBOARD_MAP),
        lowered.translate(CYRILLIC_TO_LATIN_KEYBOARD_MAP),
    }
    return {variant for variant in variants if variant and variant != lowered}


def _tokenize(value: str) -> list[str]:
    if not value:
        return []

    tokens = [value]
    comma_tokens = [chunk.strip() for chunk in value.split(',') if chunk.strip()]
    space_tokens = [chunk.strip() for chunk in value.split(' ') if chunk.strip()]
    tokens.extend(comma_tokens)
    tokens.extend(space_tokens)
    return tokens


def build_location_variants(payload: LocationSearchPayload) -> list[str]:
    """Строит набор канонических вариантов location input для поиска."""
    variants: list[str] = []
    seen: set[str] = set()

    raw_values = [
        payload.raw_query,
        payload.label,
        payload.city,
        payload.country,
    ]

    for raw_value in raw_values:
        for token in _tokenize(raw_value):
            candidates = {
                token,
                normalize_location_text(token),
                transliterate_cyrillic_to_latin(token),
                normalize_location_text(transliterate_cyrillic_to_latin(token)),
            }
            for swapped in swap_keyboard_layout(token):
                candidates.add(swapped)
                candidates.add(normalize_location_text(swapped))
                transliterated = transliterate_cyrillic_to_latin(swapped)
                candidates.add(transliterated)
                candidates.add(normalize_location_text(transliterated))

            for candidate in candidates:
                normalized_candidate = normalize_location_text(candidate)
                if not normalized_candidate:
                    continue
                if len(normalized_candidate) < 2 and not normalized_candidate.isdigit():
                    continue
                if normalized_candidate in seen:
                    continue
                seen.add(normalized_candidate)
                variants.append(normalized_candidate)

    return variants


def _location_search_fields(location: ProviderLocation) -> list[str]:
    address = getattr(location, 'structured_address', None)
    return [
        location.name or '',
        getattr(location.provider, 'name', '') or '',
        getattr(address, 'formatted_address', '') or '',
        getattr(address, 'city', '') or '',
        getattr(address, 'district', '') or '',
        getattr(address, 'street', '') or '',
        getattr(address, 'postal_code', '') or '',
        getattr(address, 'country', '') or '',
    ]


def matches_location_payload(location: ProviderLocation, variants: Sequence[str]) -> bool:
    """Проверяет, матчится ли локация по любому из нормализованных вариантов."""
    if not variants:
        return True

    normalized_fields = [
        normalize_location_text(value)
        for value in _location_search_fields(location)
        if value
    ]

    for variant in variants:
        for field in normalized_fields:
            if variant in field or field in variant:
                return True
    return False


def filter_locations_by_payload(
    locations: Iterable[ProviderLocation],
    payload: LocationSearchPayload,
) -> list[ProviderLocation]:
    """Фильтрует queryset/list локаций с учетом нормализации, транслитерации и label-based search."""
    variants = build_location_variants(payload)
    if not variants:
        return list(locations)
    return [location for location in locations if matches_location_payload(location, variants)]
