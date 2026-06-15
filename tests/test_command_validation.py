from __future__ import annotations

from voice.command_validation import validate_cleaned_command


REJECT_PHRASES = ["you", "uh", "um", "hmm", "yeah", "okay"]


def test_empty_command_rejected() -> None:
    result = validate_cleaned_command("", reject_phrases=REJECT_PHRASES)

    assert result.accepted is False
    assert result.rejection_reason == "empty command"


def test_punctuation_only_command_rejected() -> None:
    result = validate_cleaned_command(". . . . .", reject_phrases=REJECT_PHRASES)

    assert result.accepted is False
    assert result.rejection_reason == "punctuation-only command"


def test_you_command_rejected() -> None:
    result = validate_cleaned_command("you", reject_phrases=REJECT_PHRASES)

    assert result.accepted is False
    assert result.rejection_reason == "rejected phrase: you"


def test_filler_commands_rejected() -> None:
    for phrase in ["uh", "um", "hmm", "yeah", "okay"]:
        result = validate_cleaned_command(phrase, reject_phrases=REJECT_PHRASES)

        assert result.accepted is False
        assert result.rejection_reason == f"rejected phrase: {phrase}"


def test_valid_command_accepted() -> None:
    result = validate_cleaned_command("status report", reject_phrases=REJECT_PHRASES)

    assert result.accepted is True
    assert result.rejection_reason is None
