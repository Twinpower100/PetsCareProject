from __future__ import annotations

import copy
import logging
from typing import Any

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend
from django.utils.module_loading import import_string

from .email_safety import split_safe_recipients

logger = logging.getLogger(__name__)


class SafeEmailBackend(BaseEmailBackend):
    """Filters reserved demo recipients before delegating to the real backend."""

    def __init__(self, fail_silently: bool = False, **kwargs: Any) -> None:
        super().__init__(fail_silently=fail_silently, **kwargs)
        backend_path = getattr(settings, "ACTUAL_EMAIL_BACKEND", None)
        if not backend_path:
            raise ValueError("ACTUAL_EMAIL_BACKEND is not configured")

        backend_cls = import_string(backend_path)
        self.delegate = backend_cls(fail_silently=fail_silently, **kwargs)

    def send_messages(self, email_messages: list[EmailMessage]) -> int:
        prepared_messages: list[EmailMessage] = []

        for message in email_messages or []:
            filtered = copy.copy(message)
            skipped: list[str] = []

            filtered.to, skipped_to = split_safe_recipients(getattr(message, "to", None))
            filtered.cc, skipped_cc = split_safe_recipients(getattr(message, "cc", None))
            filtered.bcc, skipped_bcc = split_safe_recipients(getattr(message, "bcc", None))
            skipped.extend(skipped_to)
            skipped.extend(skipped_cc)
            skipped.extend(skipped_bcc)

            if skipped:
                logger.warning(
                    "Skipped reserved demo email recipients %s for subject %r",
                    skipped,
                    getattr(message, "subject", ""),
                )

            if not filtered.recipients():
                logger.info(
                    "Dropped email with subject %r because all recipients were reserved demo addresses",
                    getattr(message, "subject", ""),
                )
                continue

            prepared_messages.append(filtered)

        if not prepared_messages:
            return 0

        return self.delegate.send_messages(prepared_messages)
