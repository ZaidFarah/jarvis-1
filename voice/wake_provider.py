from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from config.settings import AppSettings
from voice.wake import WakeDetectionResult, WakeDetector


class WakeProvider(Protocol):
    name: str
    available: bool

    def detect(self, samples: Sequence[float], sample_rate: int) -> WakeDetectionResult:
        """Detect a configured wake phrase from audio samples."""


@dataclass(frozen=True)
class WakeProviderResolution:
    selected_provider: str
    openwakeword_enabled: bool
    openwakeword_installed: bool
    model_configured: bool
    wake_fallback_provider: str
    fallback_enabled: bool
    effective_provider: str
    openwakeword_available: bool
    manual_mode_required: bool
    fallback_reason: str | None = None


def available_openwakeword_models() -> list[str]:
    if not is_openwakeword_installed():
        return []

    try:
        import openwakeword
    except Exception:
        return []

    return sorted(str(name) for name in getattr(openwakeword, "MODELS", {}).keys())


def is_openwakeword_installed() -> bool:
    try:
        return importlib.util.find_spec("openwakeword") is not None
    except Exception:
        return False


def resolve_wake_provider(settings: AppSettings) -> WakeProviderResolution:
    selected_provider = _normalize_provider_name(settings.wake_provider)
    wake_fallback_provider = _normalize_fallback_provider_name(settings.wake_fallback_provider)
    openwakeword_installed = is_openwakeword_installed()
    model_configured = bool(settings.openwakeword_model.strip())
    model_available = _is_model_available(settings.openwakeword_model.strip())
    openwakeword_enabled = bool(settings.openwakeword_enabled)
    fallback_enabled = bool(settings.openwakeword_fallback_to_whisper)
    openwakeword_available = openwakeword_enabled and openwakeword_installed and model_configured and model_available

    if selected_provider == "openwakeword" and openwakeword_available:
        return WakeProviderResolution(
            selected_provider=selected_provider,
            openwakeword_enabled=openwakeword_enabled,
            openwakeword_installed=openwakeword_installed,
            model_configured=model_configured,
            wake_fallback_provider=wake_fallback_provider,
            fallback_enabled=fallback_enabled,
            effective_provider="openwakeword",
            openwakeword_available=True,
            manual_mode_required=False,
        )

    fallback_reason = None
    if selected_provider == "openwakeword":
        if not openwakeword_enabled:
            fallback_reason = "OpenWakeWord is disabled."
        elif not openwakeword_installed:
            fallback_reason = "OpenWakeWord is not installed."
        elif not model_configured:
            fallback_reason = "OpenWakeWord model is not configured."
        elif not model_available:
            fallback_reason = (
                f"OpenWakeWord model '{settings.openwakeword_model.strip()}' is not available."
            )
        else:
            fallback_reason = "OpenWakeWord is unavailable."

    effective_provider = selected_provider
    manual_mode_required = False
    if selected_provider == "openwakeword" and not openwakeword_available:
        manual_mode_required = True
        if wake_fallback_provider == "whisper_fuzzy":
            effective_provider = "whisper_fuzzy"
        else:
            effective_provider = "manual"

    return WakeProviderResolution(
        selected_provider=selected_provider,
        openwakeword_enabled=openwakeword_enabled,
        openwakeword_installed=openwakeword_installed,
        model_configured=model_configured,
        wake_fallback_provider=wake_fallback_provider,
        fallback_enabled=fallback_enabled,
        effective_provider=effective_provider,
        openwakeword_available=openwakeword_available,
        manual_mode_required=manual_mode_required,
        fallback_reason=fallback_reason,
    )


def create_whisper_fuzzy_wake_provider(settings: AppSettings) -> WhisperFuzzyWakeProvider:
    return WhisperFuzzyWakeProvider(
        wake_phrase=settings.wake_phrase,
        aliases=settings.wake_alias_list,
        threshold=settings.wake_match_threshold,
    )


def create_openwakeword_provider(settings: AppSettings) -> OpenWakeWordWakeProvider:
    return OpenWakeWordWakeProvider(settings)


class WhisperFuzzyWakeProvider:
    name = "whisper_fuzzy"
    available = True

    def __init__(self, wake_phrase: str, aliases: list[str], threshold: float) -> None:
        self.detector = WakeDetector(wake_phrase=wake_phrase, aliases=aliases, threshold=threshold)

    def detect(self, samples: Sequence[float], sample_rate: int) -> WakeDetectionResult:
        del samples, sample_rate
        raise NotImplementedError("Whisper fuzzy wake detection requires a transcript.")

    def detect_from_transcript(self, transcript: str) -> WakeDetectionResult:
        return self.detector.detect(transcript)


class OpenWakeWordWakeProvider:
    name = "openwakeword"

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.model_name = self._resolve_model_name(settings.openwakeword_model)
        self._model: Any | None = None
        self._model_path: Path | None = None
        self._last_error: Exception | None = None

    @property
    def available(self) -> bool:
        return bool(
            self.settings.openwakeword_enabled
            and is_openwakeword_installed()
            and self.model_name
            and _is_model_available(self.model_name)
        )

    def detect(self, samples: Sequence[float], sample_rate: int) -> WakeDetectionResult:
        if not self.available:
            return WakeDetectionResult(
                detected=False,
                transcript="",
                matched_phrase=None,
                score=0.0,
                threshold=self.settings.openwakeword_threshold,
                match_type="none",
            )

        if sample_rate != 16000:
            raise ValueError("OpenWakeWord detection expects VOICE_SAMPLE_RATE=16000.")

        model = self._load_model()
        scores = self._predict_scores(model, samples)
        score = self._score_for_current_model(scores)
        detected = score >= self.settings.openwakeword_threshold
        return WakeDetectionResult(
            detected=detected,
            transcript="",
            matched_phrase=self.model_name if detected else None,
            score=score,
            threshold=self.settings.openwakeword_threshold,
            match_type="openwakeword" if detected else "none",
        )

    def available_model_names(self) -> list[str]:
        return available_openwakeword_models()

    def resolve_model_path(self) -> Path | None:
        if not self.available:
            return None
        if self._model_path is not None:
            return self._model_path

        candidate = Path(self.model_name)
        if candidate.exists():
            self._model_path = candidate.resolve()
            return self._model_path

        if self.model_name not in available_openwakeword_models():
            return None

        try:
            import openwakeword
            from openwakeword.utils import download_models
        except Exception as exc:  # pragma: no cover - import varies by install
            self._last_error = exc
            raise RuntimeError(f"OpenWakeWord model downloader is unavailable: {exc}") from exc

        package_models_dir = (
            Path(openwakeword.__file__).resolve().parent / "resources" / "models"
        ).resolve()
        package_models_dir.mkdir(parents=True, exist_ok=True)
        download_models([self.model_name], target_directory=str(package_models_dir))
        matches = sorted(package_models_dir.glob(f"*{self.model_name}*.onnx"))
        if not matches:
            matches = sorted(package_models_dir.glob(f"*{self.model_name}*.tflite"))
        if not matches:
            raise RuntimeError(
                f"OpenWakeWord model '{self.model_name}' could not be located after download."
            )

        self._model_path = matches[0].resolve()
        return self._model_path

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        model_path = self.resolve_model_path()
        if model_path is None:
            available = ", ".join(self.available_model_names()) or "none"
            raise RuntimeError(
                f"OpenWakeWord model '{self.model_name}' is not available. Available models: {available}"
            )

        try:
            from openwakeword.model import Model
        except Exception as exc:  # pragma: no cover - import varies by install
            self._last_error = exc
            raise RuntimeError(f"OpenWakeWord model class could not be imported: {exc}") from exc

        try:
            self._model = Model(wakeword_models=[str(model_path)], inference_framework="onnx")
        except Exception as exc:
            self._last_error = exc
            raise RuntimeError(f"OpenWakeWord model could not be loaded: {exc}") from exc

        return self._model

    def _predict_scores(self, model: Any, samples: Sequence[float]) -> dict[str, float]:
        audio = self._to_int16_array(samples)
        if audio.size == 0:
            return {}

        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - numpy is already present locally
            raise RuntimeError(f"numpy is required for OpenWakeWord detection: {exc}") from exc

        if not isinstance(audio, np.ndarray):
            audio = np.asarray(audio, dtype=np.int16)

        predictions = model.predict(audio)
        if not isinstance(predictions, dict):
            return {}

        numeric_scores: dict[str, float] = {}
        for key, value in predictions.items():
            try:
                numeric_scores[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return numeric_scores

    def _score_for_current_model(self, scores: dict[str, float]) -> float:
        if not scores:
            return 0.0

        if self.model_name in scores:
            return float(scores[self.model_name])

        for key, value in scores.items():
            if self.model_name in key:
                return float(value)

        return max(float(value) for value in scores.values())

    @staticmethod
    def _resolve_model_name(value: str) -> str:
        cleaned = value.strip()
        if cleaned:
            return cleaned
        return "hey_jarvis"

    @staticmethod
    def _to_int16_array(samples: Sequence[float]):
        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - numpy is already present locally
            raise RuntimeError(f"numpy is required for OpenWakeWord detection: {exc}") from exc

        audio = np.asarray(list(samples), dtype=np.float32)
        if audio.size == 0:
            return np.asarray([], dtype=np.int16)
        clipped = np.clip(audio, -1.0, 1.0)
        return (clipped * 32767).astype(np.int16)


def _is_model_available(model_name: str) -> bool:
    cleaned = model_name.strip()
    if not cleaned:
        return False
    if Path(cleaned).exists():
        return True
    return cleaned in available_openwakeword_models()


def _normalize_provider_name(value: str) -> str:
    cleaned = value.strip().lower().replace("-", "_")
    if cleaned in {"openwakeword", "whisper_fuzzy"}:
        return cleaned
    return "whisper_fuzzy"


def _normalize_fallback_provider_name(value: str) -> str:
    cleaned = value.strip().lower().replace("-", "_")
    if cleaned in {"manual", "whisper_fuzzy"}:
        return cleaned
    return "whisper_fuzzy"
