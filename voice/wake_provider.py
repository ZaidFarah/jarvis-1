from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

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
    fallback_enabled: bool
    effective_provider: str
    openwakeword_available: bool
    fallback_reason: str | None = None


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
        self._model_instance: object | None = None
        self._import_error: Exception | None = None

    @property
    def available(self) -> bool:
        return bool(
            self.settings.openwakeword_enabled
            and self.settings.openwakeword_model.strip()
            and is_openwakeword_installed()
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

        model = self._load_model()
        score = self._predict_score(model, samples, sample_rate)
        detected = score >= self.settings.openwakeword_threshold
        matched_phrase = self.settings.openwakeword_model.strip() or "openwakeword"
        return WakeDetectionResult(
            detected=detected,
            transcript="",
            matched_phrase=matched_phrase if detected else None,
            score=score,
            threshold=self.settings.openwakeword_threshold,
            match_type="openwakeword" if detected else "none",
        )

    def _load_model(self) -> object:
        if self._model_instance is not None:
            return self._model_instance
        if self._import_error is not None:
            raise RuntimeError(f"OpenWakeWord could not be imported: {self._import_error}") from self._import_error

        model_name = self.settings.openwakeword_model.strip()
        if not model_name:
            raise RuntimeError("OpenWakeWord model is not configured.")

        try:
            model_class = _import_openwakeword_model_class()
            model_kwargs = _build_model_kwargs(model_name)
            self._model_instance = model_class(**model_kwargs)
            return self._model_instance
        except Exception as exc:
            self._import_error = exc
            raise RuntimeError(f"OpenWakeWord model could not be loaded: {exc}") from exc

    def _predict_score(self, model: object, samples: Sequence[float], sample_rate: int) -> float:
        audio = _to_float_list(samples)
        if not audio:
            return 0.0

        methods = [
            ("predict_clip", (audio,)),
            ("predict", (audio,)),
            ("predict", (audio, sample_rate)),
            ("__call__", (audio,)),
        ]

        last_error: Exception | None = None
        for method_name, args in methods:
            try:
                method = getattr(model, method_name) if method_name != "__call__" else model
                result = method(*args)
                score = _extract_score(result, self.settings.openwakeword_model.strip())
                if score is not None:
                    return score
            except TypeError as exc:
                last_error = exc
                continue
            except Exception as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise RuntimeError(f"OpenWakeWord prediction failed: {last_error}") from last_error
        return 0.0


def resolve_wake_provider(settings: AppSettings) -> WakeProviderResolution:
    selected_provider = _normalize_provider_name(settings.wake_provider)
    openwakeword_installed = is_openwakeword_installed()
    model_configured = bool(settings.openwakeword_model.strip())
    openwakeword_enabled = bool(settings.openwakeword_enabled)
    fallback_enabled = bool(settings.openwakeword_fallback_to_whisper)
    openwakeword_available = openwakeword_enabled and openwakeword_installed and model_configured

    if selected_provider == "openwakeword" and openwakeword_available:
        return WakeProviderResolution(
            selected_provider=selected_provider,
            openwakeword_enabled=openwakeword_enabled,
            openwakeword_installed=openwakeword_installed,
            model_configured=model_configured,
            fallback_enabled=fallback_enabled,
            effective_provider="openwakeword",
            openwakeword_available=True,
        )

    fallback_reason = None
    if selected_provider == "openwakeword":
        if not openwakeword_enabled:
            fallback_reason = "OpenWakeWord is disabled."
        elif not openwakeword_installed:
            fallback_reason = "OpenWakeWord is not installed."
        elif not model_configured:
            fallback_reason = "OpenWakeWord model is not configured."
        else:
            fallback_reason = "OpenWakeWord is unavailable."

    effective_provider = "whisper_fuzzy"
    return WakeProviderResolution(
        selected_provider=selected_provider,
        openwakeword_enabled=openwakeword_enabled,
        openwakeword_installed=openwakeword_installed,
        model_configured=model_configured,
        fallback_enabled=fallback_enabled,
        effective_provider=effective_provider,
        openwakeword_available=openwakeword_available,
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


def is_openwakeword_installed() -> bool:
    try:
        return importlib.util.find_spec("openwakeword") is not None
    except Exception:
        return False


def _normalize_provider_name(value: str) -> str:
    cleaned = value.strip().lower().replace("-", "_")
    if cleaned in {"openwakeword", "whisper_fuzzy"}:
        return cleaned
    return "whisper_fuzzy"


def _import_openwakeword_model_class() -> type:
    candidates = [
        ("openwakeword.model", "Model"),
        ("openwakeword", "Model"),
    ]
    errors: list[str] = []
    for module_name, attr_name in candidates:
        try:
            module = importlib.import_module(module_name)
            model_class = getattr(module, attr_name)
        except Exception as exc:
            errors.append(f"{module_name}.{attr_name}: {exc}")
            continue
        if callable(model_class):
            return model_class
        errors.append(f"{module_name}.{attr_name}: not callable")
    raise RuntimeError("Unable to locate an OpenWakeWord Model class. " + "; ".join(errors))


def _build_model_kwargs(model_name: str) -> dict[str, object]:
    candidate_path = Path(model_name)
    if candidate_path.exists():
        return {"wakeword_model_paths": [str(candidate_path)]}
    return {"wakeword_models": [model_name]}


def _to_float_list(samples: Sequence[float]) -> list[float]:
    return [float(sample) for sample in samples]


def _extract_score(result: object, model_name: str) -> float | None:
    if result is None:
        return None

    if isinstance(result, dict):
        if model_name in result:
            return _coerce_score(result[model_name])
        numeric_values = [_coerce_score(value) for value in result.values()]
        numeric_values = [value for value in numeric_values if value is not None]
        return max(numeric_values) if numeric_values else None

    if isinstance(result, (list, tuple, set)):
        numeric_values = [_coerce_score(value) for value in result]
        numeric_values = [value for value in numeric_values if value is not None]
        return max(numeric_values) if numeric_values else None

    return _coerce_score(result)


def _coerce_score(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
