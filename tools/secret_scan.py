#!/usr/bin/env python3
"""Lightweight tracked-file secret scanner for CI and pre-commit."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


BLOCKED_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.md",
    "token.json",
    "keys_found.txt",
}

BLOCKED_SUFFIXES = (
    ".pem",
    ".p12",
    ".pfx",
    ".key",
    ".backup",
    ".dump",
    ".sqlite3",
)

SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |)?PRIVATE KEY-----"),
    "google api key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "openai api key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "github token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{30,}"),
    "aws access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if line.strip()]


def is_binary(path: Path) -> bool:
    try:
        return b"\0" in path.read_bytes()[:4096]
    except OSError:
        return True


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        normalized = path.as_posix().lower()
        name = path.name.lower()
        if name in BLOCKED_FILENAMES or normalized.endswith(BLOCKED_SUFFIXES):
            findings.append(f"{path}: blocked sensitive filename")
            continue
        if not path.exists() or is_binary(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path}: possible {label}")

    if findings:
        print("Secret scan failed:")
        for finding in findings:
            print(f" - {finding}")
        return 1
    print("Secret scan passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
