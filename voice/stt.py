from __future__ import annotations

from collections.abc import Callable
from typing import Sequence

from config.settings import AppSettings
from voice.interfaces import TranscriptionResult


class InterfaceOnlySpeechToTextProvider:
    """Phase 2 STT placeholder.

    Real speech recognition is intentionally not implemented yet.
    """

    name = "interface-only"
    available = False

    def transcribe(self, samples: Sequence[float], sample_rate: int) -> TranscriptionResult:
        del samples, sample_rate
        raise NotImplementedError("Interface-only STT cannot transcribe audio.")


class FasterWhisperSpeechToTextProvider:
    """Faster Whisper STT provider loaded lazily for Phase 3 tests and diagnostics."""

    name = "faster_whisper"

    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        model_class: Callable[..., object] | None = None,
        import_error: Exception | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model_class = model_class
        self._import_error = import_error

        if self._model_class is None and self._import_error is None:
            try:
                from faster_whisper import WhisperModel
            except Exception as exc:  # pragma: no cover - depends on local installation
                self._import_error = exc
            else:
                self._model_class = WhisperModel

    @property
    def available(self) -> bool:
        return self._model_class is not None

    def transcribe(self, samples: Sequence[float], sample_rate: int) -> TranscriptionResult:
        if not self.available:
            detail = f" ({self._import_error})" if self._import_error else ""
            raise RuntimeError(f"faster-whisper is not installed or could not be imported{detail}.")

        if sample_rate != 16000:
            raise ValueError("Faster Whisper transcribe-test expects VOICE_SAMPLE_RATE=16000.")

        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - faster-whisper normally installs numpy
            raise RuntimeError(f"numpy is required for Faster Whisper transcription: {exc}") from exc

        audio = np.asarray(list(samples), dtype=np.float32)
        model = self._model_class(self.model_name, device=self.device, compute_type=self.compute_type)
        segments, info = model.transcribe(audio, language="en")
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        duration = float(getattr(info, "duration", 0.0) or 0.0)
        language = getattr(info, "language", None)
        probability = getattr(info, "language_probability", None)
        confidence = float(probability) if probability is not None else None
        return TranscriptionResult(
            text=text,
            confidence=confidence,
            duration_seconds=duration,
            language=str(language) if language else None,
        )


def create_speech_to_text_provider(settings: AppSettings):
    provider = settings.speech_to_text_provider.replace("-", "_")
    if provider == "faster_whisper":
        return FasterWhisperSpeechToTextProvider(
            model_name=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    if provider == "interface_only":
        return InterfaceOnlySpeechToTextProvider()
    raise ValueError(f"Unsupported STT provider: {settings.speech_to_text_provider}")
