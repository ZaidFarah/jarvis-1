from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher


_WAKE_TOKEN_CONFUSIONS = {
    "service": "jarvis",
    "jervis": "jarvis",
    "jarves": "jarvis",
    "jarvus": "jarvis",
    "jarviss": "jarvis",
    "jarvish": "jarvis",
    "charvis": "jarvis",
    "travis": "jarvis",
    "charities": "jarvis",
    "office": "jarvis",
}


@dataclass(frozen=True)
class WakeDetectionResult:
    detected: bool
    transcript: str
    matched_phrase: str | None
    score: float
    threshold: float
    match_type: str


class WakeDetector:
    """Detects a configured wake phrase in a single transcribed utterance."""

    def __init__(self, wake_phrase: str, aliases: list[str], threshold: float) -> None:
        self.wake_phrase = self._normalize(wake_phrase)
        self.aliases = [self._normalize(alias) for alias in aliases]
        self.threshold = threshold

    def detect(self, transcript: str) -> WakeDetectionResult:
        normalized = self._normalize(transcript)
        phrases = self._phrases()
        if not normalized or not phrases:
            return WakeDetectionResult(False, transcript, None, 0.0, self.threshold, "none")

        for phrase in phrases:
            if phrase and _starts_with_phrase(normalized, phrase):
                return WakeDetectionResult(True, transcript, phrase, 1.0, self.threshold, "exact")

        phonetic_normalized = self._phonetic_normalize(normalized)
        if phonetic_normalized != normalized:
            for phrase in phrases:
                phonetic_phrase = self._phonetic_normalize(phrase)
                if phrase and _starts_with_phrase(phonetic_normalized, phonetic_phrase):
                    score = 0.94
                    if score >= self.threshold or self._close_match_allowed(score, self.threshold, phrase, phonetic_phrase):
                        return WakeDetectionResult(True, transcript, phrase, score, self.threshold, "phonetic")

        best_phrase: str | None = None
        best_score = 0.0
        best_match_type = "none"
        for phrase in phrases:
            candidate = self._prefix_candidate(normalized, phrase)
            if not candidate or not _has_anchor_token(candidate, phrase):
                continue
            score = SequenceMatcher(None, candidate, phrase).ratio()
            phonetic_candidate = self._phonetic_normalize(candidate)
            phonetic_phrase = self._phonetic_normalize(phrase)
            phonetic_score = SequenceMatcher(None, phonetic_candidate, phonetic_phrase).ratio()
            close_match = self._close_match_allowed(score, self.threshold, phrase, phonetic_phrase) or self._close_match_allowed(
                phonetic_score,
                self.threshold,
                phrase,
                phonetic_phrase,
            )
            if score > best_score:
                best_score = score
                best_phrase = phrase
                best_match_type = "fuzzy" if score >= self.threshold else "none"
            if best_phrase == phrase and best_score < self.threshold and close_match:
                best_score = max(best_score, phonetic_score, score)
                best_match_type = "phonetic"

        return WakeDetectionResult(
            detected=best_score >= self.threshold or best_match_type == "phonetic",
            transcript=transcript,
            matched_phrase=best_phrase,
            score=best_score,
            threshold=self.threshold,
            match_type=best_match_type,
        )

    def _phrases(self) -> list[str]:
        phrases = [self.wake_phrase, *self.aliases]
        unique: list[str] = []
        for phrase in phrases:
            if phrase and phrase not in unique:
                unique.append(phrase)
        return unique

    @classmethod
    def _normalize(cls, text: str) -> str:
        lowered = text.lower()
        without_punctuation = re.sub(r"[^a-z0-9\s]", " ", lowered)
        return re.sub(r"\s+", " ", without_punctuation).strip()

    @classmethod
    def _phonetic_normalize(cls, text: str) -> str:
        words = [cls._normalize(word) for word in text.split()]
        mapped = [_WAKE_TOKEN_CONFUSIONS.get(word, word) for word in words if word]
        return " ".join(mapped)

    @staticmethod
    def _prefix_candidate(transcript: str, phrase: str) -> str:
        transcript_words = transcript.split()
        phrase_words = phrase.split()
        phrase_len = len(phrase_words)
        if not transcript_words or not phrase_words:
            return ""

        min_len = max(1, phrase_len - 1)
        max_len = min(len(transcript_words), phrase_len + 1)
        best_candidate = ""
        for size in range(min_len, max_len + 1):
            candidate = " ".join(transcript_words[:size])
            if len(candidate) > len(best_candidate):
                best_candidate = candidate
        return best_candidate

    @staticmethod
    def _close_match_allowed(score: float, threshold: float, phrase: str, phonetic_phrase: str) -> bool:
        if not phrase:
            return False
        phrase_len = len(phrase.split())
        if phrase_len <= 0:
            return False
        if threshold > 0.85:
            return False
        return score >= 0.90 and score >= max(0.90, min(1.0, 1.0 - (phrase_len * 0.05))) and bool(phonetic_phrase)


def remove_wake_phrase_prefix(command_text: str, wake_phrase: str, aliases: list[str]) -> str:
    """Remove a configured wake phrase from the beginning of a command transcript."""

    phrases = _unique_phrases([wake_phrase, *aliases])
    for phrase in sorted(phrases, key=len, reverse=True):
        pattern = _wake_prefix_pattern(phrase)
        match = pattern.match(command_text)
        if match:
            return clean_command_text(command_text[match.end() :])

    fuzzy_cleaned = _remove_fuzzy_wake_prefix(command_text, phrases)
    if fuzzy_cleaned is not None:
        return fuzzy_cleaned

    return clean_command_text(command_text)


def clean_command_text(command_text: str) -> str:
    cleaned = re.sub(r"\s+", " ", command_text).strip()
    if not re.search(r"[a-zA-Z0-9]", cleaned):
        return ""
    cleaned = re.sub(r"\s+([?.!,;:])", r"\1", cleaned)
    cleaned = re.sub(r"^[\s,.;:!?\"'()\[\]-]+", "", cleaned)
    cleaned = re.sub(r"[\s,.;:!\"'()\[\]-]+$", "", cleaned)
    return cleaned.strip()


def _unique_phrases(phrases: list[str]) -> list[str]:
    unique: list[str] = []
    for phrase in phrases:
        normalized = WakeDetector._normalize(phrase)
        if normalized and normalized not in unique:
            unique.append(normalized)
    return unique


def _wake_prefix_pattern(phrase: str) -> re.Pattern[str]:
    words = phrase.split()
    separator = r"[\s,.;:!?\"'()\[\]-]+"
    body = separator.join(re.escape(word) for word in words)
    return re.compile(rf"^\s*{body}(?=$|[\s,.;:!?\"'()\[\]-])", re.IGNORECASE)


def _contains_phrase(transcript: str, phrase: str) -> bool:
    transcript_words = transcript.split()
    phrase_words = phrase.split()
    if not transcript_words or not phrase_words:
        return False

    phrase_len = len(phrase_words)
    for start in range(0, len(transcript_words) - phrase_len + 1):
        if transcript_words[start : start + phrase_len] == phrase_words:
            return True
    return False


def _starts_with_phrase(transcript: str, phrase: str) -> bool:
    transcript_words = transcript.split()
    phrase_words = phrase.split()
    if not transcript_words or not phrase_words:
        return False
    if len(transcript_words) < len(phrase_words):
        return False
    return transcript_words[: len(phrase_words)] == phrase_words


def _has_anchor_token(candidate: str, phrase: str) -> bool:
    anchor_words = [word for word in phrase.split() if len(word) >= 4]
    if not anchor_words:
        return True

    candidate_words = candidate.split()
    for candidate_word in candidate_words:
        phonetic_candidate = _WAKE_TOKEN_CONFUSIONS.get(candidate_word, candidate_word)
        for anchor in anchor_words:
            phonetic_anchor = _WAKE_TOKEN_CONFUSIONS.get(anchor, anchor)
            if phonetic_candidate == phonetic_anchor:
                return True
            if SequenceMatcher(None, phonetic_candidate, phonetic_anchor).ratio() >= 0.78:
                return True
    return False


def _remove_fuzzy_wake_prefix(command_text: str, phrases: list[str]) -> str | None:
    cleaned = clean_command_text(command_text)
    words = re.findall(r"[a-zA-Z0-9']+", cleaned)
    if not words:
        return None

    normalized_words = [WakeDetector._normalize(word) for word in words]
    for phrase in sorted(phrases, key=len, reverse=True):
        phrase_words = phrase.split()
        min_len = max(1, len(phrase_words) - 1)
        max_len = min(len(normalized_words), len(phrase_words) + 1)
        for size in range(min_len, max_len + 1):
            candidate = " ".join(normalized_words[:size])
            phonetic_candidate = WakeDetector._phonetic_normalize(candidate)
            phonetic_phrase = WakeDetector._phonetic_normalize(phrase)
            score = max(
                SequenceMatcher(None, candidate, phrase).ratio(),
                SequenceMatcher(None, phonetic_candidate, phonetic_phrase).ratio(),
            )
            if score >= 0.84 and _has_anchor_token(candidate, phrase):
                return clean_command_text(" ".join(words[size:]))
    return None
