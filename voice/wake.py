from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher


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
            if phrase and phrase in normalized:
                return WakeDetectionResult(True, transcript, phrase, 1.0, self.threshold, "exact")

        best_phrase: str | None = None
        best_score = 0.0
        for phrase in phrases:
            for candidate in self._candidates(normalized, phrase):
                score = SequenceMatcher(None, candidate, phrase).ratio()
                if score > best_score:
                    best_score = score
                    best_phrase = phrase

        return WakeDetectionResult(
            detected=best_score >= self.threshold,
            transcript=transcript,
            matched_phrase=best_phrase,
            score=best_score,
            threshold=self.threshold,
            match_type="fuzzy" if best_score >= self.threshold else "none",
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

    @staticmethod
    def _candidates(transcript: str, phrase: str) -> list[str]:
        transcript_words = transcript.split()
        phrase_words = phrase.split()
        phrase_len = len(phrase_words)
        if not transcript_words or not phrase_words:
            return [transcript]

        min_len = max(1, phrase_len - 1)
        max_len = min(len(transcript_words), phrase_len + 2)
        candidates = [transcript]
        for size in range(min_len, max_len + 1):
            for start in range(0, len(transcript_words) - size + 1):
                candidates.append(" ".join(transcript_words[start : start + size]))
        return candidates
