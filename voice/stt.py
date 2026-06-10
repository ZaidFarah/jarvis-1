from __future__ import annotations

from typing import Sequence

from voice.interfaces import TranscriptionResult


class InterfaceOnlySpeechToTextProvider:
    """Phase 2 STT placeholder.

    Real speech recognition is intentionally not implemented yet.
    """

    name = "interface-only"
    available = False

    def transcribe(self, samples: Sequence[float], sample_rate: int) -> TranscriptionResult:
        del samples, sample_rate
        raise NotImplementedError("Speech-to-text is not implemented in Phase 2.")
