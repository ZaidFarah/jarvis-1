from __future__ import annotations

import re


APP_VERSION = "0.1.0"
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def is_valid_version(value: str) -> bool:
    return bool(VERSION_PATTERN.fullmatch(value.strip()))


def normalize_version(value: str) -> str:
    cleaned = value.strip()
    if not is_valid_version(cleaned):
        raise ValueError(f"Unsupported version format: {value}")
    return cleaned


def format_version(app_name: str = "Jarvis", version: str = APP_VERSION) -> str:
    return f"{app_name} {normalize_version(version)}"
