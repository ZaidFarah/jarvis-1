from __future__ import annotations

import io
import wave
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

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


class OpenAISpeechToTextProvider:
    """OpenAI speech-to-text provider for recorded microphone samples."""

    name = "openai_stt"

    def __init__(
        self,
        api_key: str,
        model_name: str,
        client_factory: Callable[..., object] | None = None,
        import_error: Exception | None = None,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self._client_factory = client_factory
        self._import_error = import_error

        if self._client_factory is None and self._import_error is None:
            try:
                from openai import OpenAI
            except Exception as exc:  # pragma: no cover - depends on local installation
                self._import_error = exc
            else:
                self._client_factory = OpenAI

    @property
    def available(self) -> bool:
        return bool(self.api_key) and self._client_factory is not None

    def warm_up(self) -> bool:
        return self.available

    def transcribe(self, samples: Sequence[float], sample_rate: int) -> TranscriptionResult:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI STT.")
        if self._client_factory is None:
            detail = f" ({self._import_error})" if self._import_error else ""
            raise RuntimeError(f"OpenAI STT is unavailable{detail}.")

        audio_file = _samples_to_wav_file(samples, sample_rate)
        return self._transcribe_file_object(audio_file)

    def transcribe_file(self, audio_path: str | Path) -> TranscriptionResult:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI STT.")
        if self._client_factory is None:
            detail = f" ({self._import_error})" if self._import_error else ""
            raise RuntimeError(f"OpenAI STT is unavailable{detail}.")

        with Path(audio_path).open("rb") as audio_file:
            return self._transcribe_file_object(audio_file)

    def _transcribe_file_object(self, audio_file: Any) -> TranscriptionResult:
        client = self._client_factory(api_key=self.api_key)
        response = client.audio.transcriptions.create(
            model=self.model_name,
            file=audio_file,
        )
        text = _extract_openai_transcription_text(response)
        if not text:
            raise RuntimeError("OpenAI STT returned an empty transcription.")
        return TranscriptionResult(
            text=text,
            confidence=_extract_openai_transcription_confidence(response),
            duration_seconds=_extract_optional_float(response, "duration"),
            language=_extract_optional_str(response, "language"),
        )


class FallbackSpeechToTextProvider:
    """Try the selected provider first and fall back to a local provider on failure."""

    def __init__(self, primary: Any, fallback: Any) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name

    @property
    def available(self) -> bool:
        return bool(getattr(self.primary, "available", False) or getattr(self.fallback, "available", False))

    def warm_up(self) -> bool:
        if getattr(self.primary, "available", False):
            return bool(self.primary.warm_up())
        return bool(self.fallback.warm_up())

    def transcribe(self, samples: Sequence[float], sample_rate: int) -> TranscriptionResult:
        if getattr(self.primary, "available", False):
            try:
                return self.primary.transcribe(samples, sample_rate)
            except Exception:
                if not getattr(self.fallback, "available", False):
                    raise
        return self.fallback.transcribe(samples, sample_rate)


def create_speech_to_text_provider(settings: AppSettings):
    provider = settings.speech_to_text_provider.replace("-", "_")
    if provider == "openai_stt":
        primary = OpenAISpeechToTextProvider(
            api_key=settings.openai_api_key,
            model_name=settings.openai_stt_model,
        )
        fallback_name = settings.stt_fallback_provider.replace("-", "_")
        if fallback_name and fallback_name != "openai_stt":
            return FallbackSpeechToTextProvider(primary, _create_base_speech_to_text_provider(settings, fallback_name))
        return primary
    return _create_base_speech_to_text_provider(settings, provider)


def _create_base_speech_to_text_provider(settings: AppSettings, provider: str):
    if provider == "faster_whisper":
        return FasterWhisperSpeechToTextProvider(
            model_name=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    if provider == "interface_only":
        return InterfaceOnlySpeechToTextProvider()
    raise ValueError(f"Unsupported STT provider: {settings.speech_to_text_provider}")


def transcribe_audio_file(provider: Any, audio_path: str | Path) -> TranscriptionResult:
    transcribe_file = getattr(provider, "transcribe_file", None)
    if callable(transcribe_file):
        return transcribe_file(audio_path)

    samples, sample_rate = read_wav_samples(audio_path)
    return provider.transcribe(samples, sample_rate)


def read_wav_samples(audio_path: str | Path) -> tuple[list[float], int]:
    path = Path(audio_path)
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        raw_frames = wav_file.readframes(frame_count)

    if channels < 1:
        raise ValueError("WAV file has no audio channels.")
    if sample_width != 2:
        raise ValueError("Only 16-bit PCM WAV files are supported for STT benchmark.")

    values = [
        int.from_bytes(raw_frames[index : index + 2], byteorder="little", signed=True) / 32768.0
        for index in range(0, len(raw_frames), 2)
    ]
    if channels == 1:
        return values, sample_rate

    mono_samples: list[float] = []
    for index in range(0, len(values), channels):
        frame = values[index : index + channels]
        if frame:
            mono_samples.append(sum(frame) / len(frame))
    return mono_samples, sample_rate


def write_wav_file(audio_path: str | Path, samples: Sequence[float], sample_rate: int) -> Path:
    path = Path(audio_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(_samples_to_pcm16_bytes(samples))
    return path


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


def _samples_to_wav_file(samples: Sequence[float], sample_rate: int) -> io.BytesIO:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(_samples_to_pcm16_bytes(samples))
    buffer.seek(0)
    buffer.name = "jarvis-stt.wav"  # type: ignore[attr-defined]
    return buffer


def _samples_to_pcm16_bytes(samples: Sequence[float]) -> bytes:
    frames = bytearray()
    for sample in samples:
        clamped = max(-1.0, min(1.0, float(sample)))
        value = int(clamped * 32767) if clamped >= 0 else int(clamped * 32768)
        frames.extend(value.to_bytes(2, byteorder="little", signed=True))
    return bytes(frames)


def _extract_openai_transcription_text(response: object) -> str:
    if isinstance(response, dict):
        return str(response.get("text", "")).strip()
    return str(getattr(response, "text", "") or "").strip()


def _extract_openai_transcription_confidence(response: object) -> float | None:
    direct = _extract_optional_float(response, "confidence")
    if direct is not None:
        return max(0.0, min(1.0, direct))

    segments = _extract_response_value(response, "segments")
    if not isinstance(segments, Sequence):
        return None
    scores: list[float] = []
    for segment in segments:
        avg_logprob = _extract_optional_float(segment, "avg_logprob")
        if avg_logprob is not None:
            scores.append(avg_logprob)
    if not scores:
        return None
    average_logprob = sum(scores) / len(scores)
    return max(0.0, min(1.0, (average_logprob + 1.5) / 1.5))


def _extract_optional_float(response: object, name: str) -> float | None:
    value = _extract_response_value(response, name)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_optional_str(response: object, name: str) -> str | None:
    value = _extract_response_value(response, name)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_response_value(response: object, name: str) -> object | None:
    if isinstance(response, dict):
        return response.get(name)
    return getattr(response, name, None)
