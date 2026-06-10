from __future__ import annotations

from math import sqrt
from typing import Sequence

from voice.interfaces import VadResult


class RmsVoiceActivityDetector:
    """Small RMS-based VAD layer used only for Phase 2 microphone testing."""

    name = "rms-vad"

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold

    def analyze(self, samples: Sequence[float], sample_rate: int) -> VadResult:
        del sample_rate
        if len(samples) == 0:
            return VadResult(is_speech=False, rms=0.0, threshold=self.threshold)

        total = sum(float(sample) * float(sample) for sample in samples)
        rms = sqrt(total / len(samples))
        return VadResult(is_speech=rms >= self.threshold, rms=rms, threshold=self.threshold)
