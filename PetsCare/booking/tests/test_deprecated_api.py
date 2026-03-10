"""
Legacy API-тесты для booking были сняты с поддержки после смены доменной модели.
"""

from django.test import TestCase
from unittest import skip


@skip("Deprecated booking API tests require model updates")
class DeprecatedBookingAPITestCase(TestCase):
    pass
