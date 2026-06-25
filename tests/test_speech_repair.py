from __future__ import annotations

import pytest

from config.settings import AppSettings
from voice.speech_repair import (
    REPAIR_STRATEGY_COMMON_INTENT,
    REPAIR_STRATEGY_CONTEXT,
    REPAIR_STRATEGY_OPENAI,
    REPAIR_STRATEGY_RULE,
    REPAIR_STRATEGY_SKIPPED,
    SpeechRepairer,
    is_confirmation_no,
    is_confirmation_yes,
)


def test_speech_repair_rule_repairs_observed_weather_transcript() -> None:
    settings = AppSettings(_env_file=None, weather_default_city="Nottingham")

    result = SpeechRepairer(settings).repair("Did it noting him today? What's the")

    assert result.repaired_transcript == "what's the weather in Nottingham today"
    assert result.confidence == 0.92
    assert result.strategy == REPAIR_STRATEGY_RULE
    assert result.changed is True


def test_speech_repair_uses_weather_context_for_incomplete_phrase() -> None:
    settings = AppSettings(_env_file=None, weather_default_city="Nottingham")

    result = SpeechRepairer(settings).repair(
        "what's the",
        recent_commands=["what's the weather in Nottingham today"],
    )

    assert result.repaired_transcript == "what's the weather in Nottingham today?"
    assert result.confidence == 0.92
    assert result.strategy == REPAIR_STRATEGY_CONTEXT


def test_speech_repair_common_weather_intent_needs_confirmation() -> None:
    settings = AppSettings(_env_file=None, weather_default_city="Nottingham")

    result = SpeechRepairer(settings).repair("what's the")

    assert result.repaired_transcript == "what's the weather in Nottingham today?"
    assert result.strategy == REPAIR_STRATEGY_COMMON_INTENT
    assert result.needs_confirmation(settings.voice_repair_confirmation_threshold) is True


def test_speech_repair_repairs_weather_homophone_without_rewriting_other_whether_phrases() -> None:
    settings = AppSettings(_env_file=None)
    repairer = SpeechRepairer(settings)

    weather = repairer.repair("what is the whether in London")
    ordinary = repairer.repair("whether I should go")

    assert weather.repaired_transcript == "what is the weather in London"
    assert weather.confidence == 0.86
    assert weather.strategy == REPAIR_STRATEGY_COMMON_INTENT
    assert ordinary.repaired_transcript == "whether I should go"


@pytest.mark.parametrize(
    "transcript",
    ["that's report", "status reports", "start us report", "stat us report"],
)
def test_speech_repair_repairs_status_report_variants(transcript: str) -> None:
    result = SpeechRepairer(AppSettings(_env_file=None)).repair(transcript)

    assert result.repaired_transcript == "status report"
    assert result.confidence == 0.94
    assert result.strategy == REPAIR_STRATEGY_COMMON_INTENT


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        ("hey john this", "hey jarvis"),
        ("hey john of us", "hey jarvis"),
        ("hey jar of this", "hey jarvis"),
        ("we cup out of his", "wake up jarvis"),
        ("wake up out of his", "wake up jarvis"),
        ("wake up jar of this", "wake up jarvis"),
        ("we got jarvis", "wake up jarvis"),
    ],
)
def test_speech_repair_repairs_wake_phrase_variants(
    transcript: str,
    expected: str,
) -> None:
    result = SpeechRepairer(AppSettings(_env_file=None)).repair(transcript)

    assert result.repaired_transcript == expected
    assert result.confidence == 0.96
    assert result.strategy == REPAIR_STRATEGY_COMMON_INTENT


def test_speech_repair_does_not_replace_wake_variant_inside_longer_command() -> None:
    result = SpeechRepairer(AppSettings(_env_file=None)).repair(
        "hey john of us tell me the weather"
    )

    assert result.repaired_transcript == "hey john of us tell me the weather"
    assert result.strategy != REPAIR_STRATEGY_COMMON_INTENT


def test_speech_repair_context_completes_recent_reminder() -> None:
    settings = AppSettings(_env_file=None)

    result = SpeechRepairer(settings).repair(
        "remind me",
        recent_commands=["remind me to drink water at 6 pm"],
    )

    assert result.repaired_transcript == "remind me to drink water at 6 pm"
    assert result.strategy == REPAIR_STRATEGY_CONTEXT


def test_speech_repair_openai_disabled_does_not_call_repairer() -> None:
    settings = AppSettings(_env_file=None, voice_use_openai_repair=False, voice_repair_rules="")
    calls: list[str] = []

    result = SpeechRepairer(settings, openai_repairer=lambda text: calls.append(text) or "fixed").repair(
        "please summarize the meting notes"
    )

    assert calls == []
    assert result.repaired_transcript == "please summarize the meting notes"


def test_speech_repair_openai_enabled_uses_repairer_for_valid_input() -> None:
    settings = AppSettings(_env_file=None, voice_use_openai_repair=True, voice_repair_rules="")
    calls: list[str] = []

    def repairer(text: str) -> str:
        calls.append(text)
        return "please summarize the meeting notes"

    result = SpeechRepairer(settings, openai_repairer=repairer).repair("please summarize the meting notes")

    assert calls == ["please summarize the meting notes"]
    assert result.repaired_transcript == "please summarize the meeting notes"
    assert result.strategy == REPAIR_STRATEGY_OPENAI
    assert result.confidence == 0.80


def test_speech_repair_skips_openai_for_filler_and_empty_text() -> None:
    settings = AppSettings(_env_file=None, voice_use_openai_repair=True)
    calls: list[str] = []
    repairer = SpeechRepairer(settings, openai_repairer=lambda text: calls.append(text) or "fixed")

    filler = repairer.repair("you")
    empty = repairer.repair(". . .")

    assert calls == []
    assert filler.strategy == REPAIR_STRATEGY_SKIPPED
    assert empty.strategy == REPAIR_STRATEGY_SKIPPED


def test_confirmation_helpers_parse_yes_and_no() -> None:
    assert is_confirmation_yes("Yes") is True
    assert is_confirmation_yes("that's right") is True
    assert is_confirmation_no("No") is True
    assert is_confirmation_no("not that") is True
