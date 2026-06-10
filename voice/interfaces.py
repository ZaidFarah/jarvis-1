from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class VadResult:
    is_speech: bool
    rms: float
    threshold: float


class VoiceActivityDetector(Protocol):
    name: str

    def analyze(self, samples: Sequence[float], sample_rate: int) -> VadResult:
        """Return whether the audio samples contain speech-like activity."""


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    confidence: float | None = None


class SpeechToTextProvider(Protocol):
    name: str
    available: bool

    def transcribe(self, samples: Sequence[float], sample_rate: int) -> TranscriptionResult:
        """Transcribe audio samples into text."""


class TextToSpeechProvider(Protocol):
    name: str
    available: bool

    def speak(self, text: str) -> None:
        """Speak text through a local or remote voice provider."""
