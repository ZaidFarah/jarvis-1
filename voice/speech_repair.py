from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from config.settings import AppSettings
from services.openai_service import OpenAIService
from voice.wake import clean_command_text


OpenAIRepairer = Callable[[str], str | None]

REPAIR_OPENAI_PROMPT = "Repair this speech transcription without changing the intent."
REPAIR_STRATEGY_DISABLED = "disabled"
REPAIR_STRATEGY_SKIPPED = "skipped"
REPAIR_STRATEGY_UNCHANGED = "unchanged"
REPAIR_STRATEGY_RULE = "rule"
REPAIR_STRATEGY_CONTEXT = "context"
REPAIR_STRATEGY_COMMON_INTENT = "common_intent"
REPAIR_STRATEGY_OPENAI = "openai"
HEY_JARVIS_VARIANTS = {
    "hey jar of this",
    "hey john this",
    "hey john of us",
}
WAKE_UP_JARVIS_VARIANTS = {
    "we cup out of his",
    "wake up out of his",
    "wake up jar of this",
    "we got jarvis",
}
SCREEN_WORD_NUMBERS = {
    "one": "1",
    "first": "1",
    "two": "2",
    "second": "2",
}


@dataclass(frozen=True)
class SpeechRepairResult:
    raw_transcript: str
    cleaned_transcript: str
    repaired_transcript: str
    confidence: float
    strategy: str
    repair_reason: str

    @property
    def changed(self) -> bool:
        return _normalize_for_match(self.cleaned_transcript) != _normalize_for_match(self.repaired_transcript)

    def needs_confirmation(self, threshold: float) -> bool:
        if not self.repaired_transcript:
            return False
        if not self.changed:
            return False
        return self.confidence < threshold


class SpeechRepairer:
    """Repair noisy speech transcripts before command validation."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        openai_repairer: OpenAIRepairer | None = None,
    ) -> None:
        self.settings = settings
        self.openai_repairer = openai_repairer

    def repair(
        self,
        cleaned_transcript: str,
        *,
        raw_transcript: str | None = None,
        recent_commands: Sequence[str] = (),
    ) -> SpeechRepairResult:
        raw = (raw_transcript if raw_transcript is not None else cleaned_transcript).strip()
        cleaned = clean_command_text(cleaned_transcript)

        if not self.settings.voice_speech_repair_enabled:
            return SpeechRepairResult(raw, cleaned, cleaned, 1.0, REPAIR_STRATEGY_DISABLED, "speech repair disabled")

        wake_target = _wake_repair_target(raw, cleaned)
        if wake_target is not None:
            return SpeechRepairResult(
                raw,
                cleaned,
                wake_target,
                0.96,
                REPAIR_STRATEGY_COMMON_INTENT,
                "repaired likely wake phrase transcription",
            )

        if _should_skip_repair(cleaned, reject_phrases=self.settings.voice_command_reject_phrase_list):
            return SpeechRepairResult(raw, cleaned, cleaned, 1.0, REPAIR_STRATEGY_SKIPPED, "speech is empty or filler")

        rule_result = self._repair_from_rules(raw, cleaned)
        if rule_result is not None:
            return rule_result

        context_result = self._repair_from_context(raw, cleaned, recent_commands)
        if context_result is not None:
            return context_result

        intent_result = self._repair_from_common_intents(raw, cleaned)
        if intent_result is not None:
            return intent_result

        openai_result = self._repair_with_openai(raw, cleaned)
        if openai_result is not None:
            return openai_result

        return SpeechRepairResult(raw, cleaned, cleaned, 1.0, REPAIR_STRATEGY_UNCHANGED, "no repair needed")

    def _repair_from_rules(self, raw: str, cleaned: str) -> SpeechRepairResult | None:
        normalized = _normalize_for_match(cleaned)
        raw_normalized = _normalize_for_match(raw)
        for source, target in self.settings.voice_repair_rule_pairs:
            source_normalized = _normalize_for_match(source)
            if not source_normalized:
                continue
            if source_normalized == normalized or source_normalized == raw_normalized:
                return SpeechRepairResult(
                    raw,
                    cleaned,
                    clean_command_text(target),
                    0.92,
                    REPAIR_STRATEGY_RULE,
                    f"matched repair rule: {source}",
                )
            if len(source_normalized.split()) >= 4 and source_normalized in raw_normalized:
                return SpeechRepairResult(
                    raw,
                    cleaned,
                    clean_command_text(target),
                    0.88,
                    REPAIR_STRATEGY_RULE,
                    f"matched partial repair rule: {source}",
                )
        return None

    def _repair_from_context(
        self,
        raw: str,
        cleaned: str,
        recent_commands: Sequence[str],
    ) -> SpeechRepairResult | None:
        normalized = _normalize_for_match(cleaned)
        recent = [command for command in recent_commands if command.strip()]
        last_weather = _last_weather_command(recent)
        if last_weather and normalized in {"whats the", "what is the", "tell me about", "weather in"}:
            city = _extract_weather_city(last_weather) or self.settings.weather_default_city
            return SpeechRepairResult(
                raw,
                cleaned,
                f"what's the weather in {city} today?",
                0.92,
                REPAIR_STRATEGY_CONTEXT,
                "completed weather follow-up from recent command context",
            )

        for command in reversed(recent):
            command_normalized = _normalize_for_match(command)
            if normalized in {"remind me", "tell me about"} and command_normalized.startswith(normalized):
                return SpeechRepairResult(
                    raw,
                    cleaned,
                    command,
                    0.78,
                    REPAIR_STRATEGY_CONTEXT,
                    "completed incomplete command from recent command context",
                )
        return None

    def _repair_from_common_intents(self, raw: str, cleaned: str) -> SpeechRepairResult | None:
        normalized = _normalize_for_match(cleaned)
        screen_repair = _repair_screen_vision_intent(normalized)
        if screen_repair is not None:
            return SpeechRepairResult(
                raw,
                cleaned,
                screen_repair,
                0.94,
                REPAIR_STRATEGY_COMMON_INTENT,
                "repaired likely screen vision command",
            )

        city = self.settings.weather_default_city
        if normalized in {"thats report", "status reports", "start us report", "stat us report"}:
            return SpeechRepairResult(
                raw,
                cleaned,
                "status report",
                0.94,
                REPAIR_STRATEGY_COMMON_INTENT,
                "repaired likely status report transcription",
            )
        if normalized == "weather in":
            return SpeechRepairResult(
                raw,
                cleaned,
                f"what's the weather in {city} today?",
                0.86,
                REPAIR_STRATEGY_COMMON_INTENT,
                "completed common weather intent",
            )
        if normalized in {"whats the", "what is the"}:
            return SpeechRepairResult(
                raw,
                cleaned,
                f"what's the weather in {city} today?",
                0.66,
                REPAIR_STRATEGY_COMMON_INTENT,
                "low-confidence common weather completion",
            )
        if "noting him" in normalized and "weather" in normalized:
            return SpeechRepairResult(
                raw,
                cleaned,
                f"what's the weather in {city} today?",
                0.84,
                REPAIR_STRATEGY_COMMON_INTENT,
                "repaired likely Nottingham weather transcription",
            )
        if "whether" in normalized and _looks_like_weather_command(normalized):
            repaired = re.sub(r"\bwhether\b", "weather", cleaned, flags=re.I)
            return SpeechRepairResult(
                raw,
                cleaned,
                clean_command_text(repaired),
                0.86,
                REPAIR_STRATEGY_COMMON_INTENT,
                "repaired likely weather homophone",
            )
        return None

    def _repair_with_openai(self, raw: str, cleaned: str) -> SpeechRepairResult | None:
        if not self.settings.voice_use_openai_repair:
            return None
        if not _can_attempt_openai_repair(
            cleaned,
            reject_phrases=self.settings.voice_command_reject_phrase_list,
            incomplete_phrases=self.settings.voice_repair_incomplete_phrase_list,
        ):
            return None

        repairer = self.openai_repairer or self._default_openai_repair
        repaired = clean_command_text(repairer(cleaned) or "")
        if not repaired:
            return None
        if _normalize_for_match(repaired) == _normalize_for_match(cleaned):
            return None
        return SpeechRepairResult(
            raw,
            cleaned,
            repaired,
            0.80,
            REPAIR_STRATEGY_OPENAI,
            "OpenAI repair suggestion",
        )

    def _default_openai_repair(self, cleaned: str) -> str | None:
        service = OpenAIService(self.settings)
        result = service.chat(cleaned, system_prompt=REPAIR_OPENAI_PROMPT)
        if not result.success or not result.text:
            return None
        return result.text


def _should_skip_repair(cleaned: str, *, reject_phrases: Sequence[str]) -> bool:
    normalized = _normalize_for_match(cleaned)
    if not normalized:
        return True
    if normalized in {_normalize_for_match(phrase) for phrase in reject_phrases}:
        return True
    return False


def _can_attempt_openai_repair(
    cleaned: str,
    *,
    reject_phrases: Sequence[str],
    incomplete_phrases: Sequence[str],
) -> bool:
    normalized = _normalize_for_match(cleaned)
    if not normalized:
        return False
    if normalized in {_normalize_for_match(phrase) for phrase in reject_phrases}:
        return False
    if normalized in {_normalize_for_match(phrase) for phrase in incomplete_phrases}:
        return False
    return len(normalized.split()) >= 3


def is_confirmation_yes(transcript: str) -> bool:
    normalized = _normalize_for_match(transcript)
    return normalized in {"yes", "yeah", "yep", "correct", "thats right", "that is right", "confirmed"}


def is_confirmation_no(transcript: str) -> bool:
    normalized = _normalize_for_match(transcript)
    return normalized in {"no", "nope", "cancel", "not that", "wrong"}


def _last_weather_command(recent_commands: Sequence[str]) -> str | None:
    for command in reversed(recent_commands):
        if "weather" in _normalize_for_match(command):
            return command
    return None


def _extract_weather_city(command: str) -> str | None:
    match = re.search(r"\bweather\s+(?:in|for)\s+([a-zA-Z\s]+?)(?:\s+today|\s+tomorrow|\s+now|$)", command, re.I)
    if not match:
        return None
    city = " ".join(match.group(1).strip(" ?.!,").split())
    return city or None


def _looks_like_weather_command(normalized: str) -> bool:
    if not normalized:
        return False
    if normalized.startswith(("whats the whether", "what is the whether", "tell me the whether")):
        return True
    if "whether in" in normalized or "whether for" in normalized:
        return True
    return any(word in normalized.split() for word in ("forecast", "temperature", "rain"))


def _repair_screen_vision_intent(normalized: str) -> str | None:
    exact_repairs = {
        "ones whats on the screen on": "what is on screen 1",
        "whats on the screen one": "what is on screen 1",
        "whats on screen one": "what is on screen 1",
        "what is on screen one": "what is on screen 1",
        "what is on the screen one": "what is on screen 1",
        "what is on the first screen": "what is on screen 1",
        "whats on the first screen": "what is on screen 1",
        "whats on first screen": "what is on screen 1",
        "what is on first screen": "what is on screen 1",
        "screen one": "screen 1",
        "screen first": "screen 1",
        "whats on the screen two": "what is on screen 2",
        "whats on screen two": "what is on screen 2",
        "what is on screen two": "what is on screen 2",
        "what is on the screen two": "what is on screen 2",
        "what is on the second screen": "what is on screen 2",
        "whats on the second screen": "what is on screen 2",
        "whats on second screen": "what is on screen 2",
        "what is on second screen": "what is on screen 2",
        "screen two": "screen 2",
        "screen second": "screen 2",
    }
    if normalized in exact_repairs:
        return exact_repairs[normalized]

    match = re.match(
        r"^(?P<action>what is on|whats on|describe|read)\s+(?:the\s+)?screen\s+(?P<number>one|first|two|second)$",
        normalized,
    )
    if match:
        action = "what is on" if match.group("action") == "whats on" else match.group("action")
        return f"{action} screen {SCREEN_WORD_NUMBERS[match.group('number')]}"

    match = re.match(
        r"^(?P<action>what is on|whats on|describe|read)\s+(?:the\s+)?(?P<number>first|second)\s+screen$",
        normalized,
    )
    if match:
        action = "what is on" if match.group("action") == "whats on" else match.group("action")
        return f"{action} screen {SCREEN_WORD_NUMBERS[match.group('number')]}"

    return None


def _normalize_for_match(value: str) -> str:
    lowered = value.lower().replace("’", "'")
    without_apostrophes = lowered.replace("'", "")
    without_punctuation = re.sub(r"[^a-z0-9\s]", " ", without_apostrophes)
    return re.sub(r"\s+", " ", without_punctuation).strip()


def _wake_repair_target(raw: str, cleaned: str) -> str | None:
    normalized_values = {
        _normalize_for_match(raw),
        _normalize_for_match(cleaned),
    }
    if normalized_values.intersection(HEY_JARVIS_VARIANTS):
        return "hey jarvis"
    if normalized_values.intersection(WAKE_UP_JARVIS_VARIANTS):
        return "wake up jarvis"
    return None


def repair_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize_for_match(left), _normalize_for_match(right)).ratio()
