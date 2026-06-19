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

    def warm_up(self) -> bool:
        return False

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
        self._model: object | None = None

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

    def warm_up(self) -> bool:
        """Load the configured model once so the first transcription is not cold."""
        if not self.available:
            return False
        self._load_model()
        return True

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
        model = self._load_model()
        try:
            segments, info = model.transcribe(
                audio,
                language="en",
                beam_size=1,
                condition_on_previous_text=False,
                vad_filter=False,
            )
        except TypeError:
            segments, info = model.transcribe(audio, language="en")

        segment_list = list(segments)
        text = " ".join(segment.text.strip() for segment in segment_list if segment.text.strip())
        duration = float(getattr(info, "duration", 0.0) or 0.0)
        language = getattr(info, "language", None)
        probability = getattr(info, "language_probability", None)
        confidence = _transcription_confidence(segment_list, probability)
        return TranscriptionResult(
            text=text,
            confidence=confidence,
            duration_seconds=duration,
            language=str(language) if language else None,
        )

    def _load_model(self) -> object:
        if self._model is None:
            if self._model_class is None:
                raise RuntimeError("faster-whisper model class is unavailable.")
            self._model = self._model_class(self.model_name, device=self.device, compute_type=self.compute_type)
        return self._model


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


def _transcription_confidence(segments: Sequence[object], language_probability: object | None) -> float | None:
    if language_probability is not None:
        try:
            return max(0.0, min(1.0, float(language_probability)))
        except (TypeError, ValueError):
            pass

    scored_segments: list[float] = []
    for segment in segments:
        value = getattr(segment, "avg_logprob", None)
        if value is None:
            continue
        try:
            scored_segments.append(float(value))
        except (TypeError, ValueError):
            continue
    if not scored_segments:
        return None

    average_logprob = sum(scored_segments) / len(scored_segments)
    return max(0.0, min(1.0, (average_logprob + 1.5) / 1.5))
