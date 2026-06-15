from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass


COMMAND_REJECTED_MESSAGE = "I didn’t catch that, please repeat."


@dataclass(frozen=True)
class CommandValidationResult:
    accepted: bool
    cleaned_command: str
    rejection_reason: str | None = None


def validate_cleaned_command(
    cleaned_command: str,
    *,
    min_words: int = 2,
    reject_phrases: Sequence[str] | str = (),
) -> CommandValidationResult:
    command = " ".join(str(cleaned_command).strip().split())
    if not command:
        return CommandValidationResult(False, "", "empty command")

    if not re.search(r"[a-zA-Z0-9]", command):
        return CommandValidationResult(False, command, "punctuation-only command")

    normalized = _normalize_phrase(command)
    if not normalized:
        return CommandValidationResult(False, command, "punctuation-only command")

    rejected = set(_normalize_reject_phrases(reject_phrases))
    if normalized in rejected:
        return CommandValidationResult(False, command, f"rejected phrase: {normalized}")

    word_count = len(normalized.split())
    if word_count < max(1, min_words):
        return CommandValidationResult(
            False,
            command,
            f"too short: {word_count} word{'s' if word_count != 1 else ''}",
        )

    return CommandValidationResult(True, command)


def parse_reject_phrases(value: Sequence[str] | str) -> list[str]:
    if isinstance(value, str):
        parts = value.replace("\n", ",").split(",")
    else:
        parts = [str(item) for item in value]

    phrases: list[str] = []
    for part in parts:
        cleaned = " ".join(part.strip().split())
        if cleaned and cleaned not in phrases:
            phrases.append(cleaned)
    return phrases


def _normalize_reject_phrases(value: Sequence[str] | str) -> list[str]:
    normalized: list[str] = []
    for phrase in parse_reject_phrases(value):
        cleaned = _normalize_phrase(phrase)
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def _normalize_phrase(value: str) -> str:
    lowered = value.lower()
    without_punctuation = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", without_punctuation).strip()
