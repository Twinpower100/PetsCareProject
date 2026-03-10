from __future__ import annotations

import hashlib

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _


class RoutingUnavailableError(Exception):
    """Ошибка недоступности routing API."""


class RoutingService:
    """Сервис для получения travel time только через routing API."""

    @classmethod
    def get_travel_duration_seconds(cls, source, destination, mode: str | None = None) -> int:
        """Возвращает длительность поездки в секундах между двумя точками."""
        source_point = cls._extract_point(source)
        destination_point = cls._extract_point(destination)

        if source_point.x == destination_point.x and source_point.y == destination_point.y:
            return 0

        cache_key = cls._build_cache_key(source_point, destination_point, mode)
        cached_duration = cache.get(cache_key)
        if cached_duration is not None:
            return int(cached_duration)

        api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', '')
        if not api_key:
            raise RoutingUnavailableError(_('Routing API is not configured.'))

        response = requests.get(
            getattr(
                settings,
                'BOOKING_ROUTING_API_URL',
                'https://maps.googleapis.com/maps/api/distancematrix/json',
            ),
            params={
                'origins': f'{source_point.y},{source_point.x}',
                'destinations': f'{destination_point.y},{destination_point.x}',
                'mode': mode or getattr(settings, 'BOOKING_ROUTING_MODE', 'driving'),
                'key': api_key,
            },
            timeout=getattr(settings, 'BOOKING_ROUTING_TIMEOUT_SECONDS', 10),
        )

        try:
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise RoutingUnavailableError(_('Routing API request failed.')) from exc
        except ValueError as exc:
            raise RoutingUnavailableError(_('Routing API returned an invalid response.')) from exc

        if payload.get('status') != 'OK':
            raise RoutingUnavailableError(_('Routing data is unavailable.'))

        rows = payload.get('rows') or []
        if not rows or not rows[0].get('elements'):
            raise RoutingUnavailableError(_('Routing data is unavailable.'))

        element = rows[0]['elements'][0]
        if element.get('status') != 'OK' or 'duration' not in element:
            raise RoutingUnavailableError(_('Routing data is unavailable.'))

        duration_seconds = int(element['duration']['value'])
        cache.set(
            cache_key,
            duration_seconds,
            getattr(settings, 'BOOKING_ROUTING_CACHE_TIMEOUT_SECONDS', 3600),
        )
        return duration_seconds

    @staticmethod
    def _extract_point(entity):
        """Извлекает координаты из адреса, локации или модели с полем point."""
        if entity is None:
            raise RoutingUnavailableError(_('Routing requires coordinates for both locations.'))

        if hasattr(entity, 'structured_address') and entity.structured_address is not None:
            entity = entity.structured_address

        point = getattr(entity, 'point', None)
        if point is None:
            raise RoutingUnavailableError(_('Routing requires coordinates for both locations.'))
        return point

    @staticmethod
    def _build_cache_key(source_point, destination_point, mode: str | None) -> str:
        """Формирует ключ кеша для routing API."""
        raw_key = (
            f'{source_point.y:.7f}:{source_point.x:.7f}:'
            f'{destination_point.y:.7f}:{destination_point.x:.7f}:{mode or "default"}'
        )
        return f'booking_routing:{hashlib.sha256(raw_key.encode("utf-8")).hexdigest()}'
