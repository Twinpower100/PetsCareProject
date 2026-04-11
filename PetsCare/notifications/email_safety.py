from __future__ import annotations

from collections.abc import Iterable
from email.utils import parseaddr

RESERVED_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "invalid",
    "localhost",
    "test",
}

RESERVED_EMAIL_SUFFIXES = (
    ".example",
    ".invalid",
    ".localhost",
    ".test",
)


def normalize_email_address(value: str | None) -> str:
    if not value:
        return ""
    _, address = parseaddr(value)
    return address.strip().lower()


def is_reserved_demo_recipient(value: str | None) -> bool:
    address = normalize_email_address(value)
    if not address or "@" not in address:
        return False

    domain = address.rsplit("@", 1)[1]
    return domain in RESERVED_EMAIL_DOMAINS or domain.endswith(RESERVED_EMAIL_SUFFIXES)


def split_safe_recipients(values: Iterable[str] | None) -> tuple[list[str], list[str]]:
    safe: list[str] = []
    skipped: list[str] = []

    for raw_value in values or []:
        if is_reserved_demo_recipient(raw_value):
            skipped.append(raw_value)
            continue
        safe.append(raw_value)

    return safe, skipped
