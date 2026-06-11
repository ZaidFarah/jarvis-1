from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import AppSettings
from voice.interfaces import TextToSpeechProvider


_TTS_LOG_SINK_ID: int | None = None
_TTS_LOG_FILE: Path | None = None


@dataclass(frozen=True)
class TextToSpeechResult:
    provider_name: str
    provider_available: bool
    requested: bool
    spoken: bool
    log_file: Path
    error: str | None = None


class Pyttsx3TextToSpeechProvider:
    """Local pyttsx3 TTS provider loaded lazily with safe fallback behavior."""

    name = "pyttsx3"

    def __init__(
        self,
        voice_name: str = "",
        rate: int = 175,
        volume: float = 1.0,
        comtypes_cache_dir: Path | None = None,
        pyttsx3_module: Any | None = None,
        import_error: Exception | None = None,
    ) -> None:
        self.voice_name = voice_name.strip()
        self.rate = rate
        self.volume = volume
        self.comtypes_cache_dir = comtypes_cache_dir
        self._pyttsx3 = pyttsx3_module
        self._import_error = import_error

        if self._pyttsx3 is None and self._import_error is None:
            try:
                self._pyttsx3 = importlib.import_module("pyttsx3")
            except Exception as exc:  # pragma: no cover - depends on local installation
                self._import_error = exc

    @property
    def available(self) -> bool:
        return self._pyttsx3 is not None

    def speak(self, text: str) -> None:
        if not self.available:
            detail = f" ({self._import_error})" if self._import_error else ""
            raise RuntimeError(f"pyttsx3 is not installed or could not be imported{detail}.")

        cleaned = text.strip()
        if not cleaned:
            raise ValueError("TTS text cannot be empty.")

        self._configure_comtypes_cache()
        engine = self._pyttsx3.init()
        self._configure_engine(engine)
        engine.say(cleaned)
        engine.runAndWait()

    def _configure_comtypes_cache(self) -> None:
        if self.comtypes_cache_dir is None:
            return

        try:
            self.comtypes_cache_dir.mkdir(parents=True, exist_ok=True)
            (self.comtypes_cache_dir / "__init__.py").touch(exist_ok=True)
            import comtypes.client  # type: ignore[import-not-found]
            import comtypes.gen  # type: ignore[import-not-found]
        except Exception:
            return

        cache_path = str(self.comtypes_cache_dir)
        comtypes.client.gen_dir = cache_path
        if cache_path in comtypes.gen.__path__:
            comtypes.gen.__path__.remove(cache_path)
        comtypes.gen.__path__.insert(0, cache_path)

    def _configure_engine(self, engine: Any) -> None:
        engine.setProperty("rate", self.rate)
        engine.setProperty("volume", self.volume)
        if not self.voice_name:
            return

        requested_voice = self.voice_name.lower()
        try:
            voices = engine.getProperty("voices") or []
        except Exception:
            return

        for voice in voices:
            voice_id = str(getattr(voice, "id", ""))
            voice_name = str(getattr(voice, "name", ""))
            if requested_voice in voice_name.lower() or requested_voice in voice_id.lower():
                if voice_id:
                    engine.setProperty("voice", voice_id)
                return


def create_text_to_speech_provider(settings: AppSettings) -> TextToSpeechProvider:
    provider = settings.tts_provider.replace("-", "_")
    if provider == "pyttsx3":
        return Pyttsx3TextToSpeechProvider(
            voice_name=settings.tts_voice_name,
            rate=settings.tts_rate,
            volume=settings.tts_volume,
            comtypes_cache_dir=settings.log_dir / "comtypes_gen",
        )
    raise ValueError(f"Unsupported TTS provider: {settings.tts_provider}")


def should_speak(settings: AppSettings, speak_requested: bool = False) -> bool:
    return bool(speak_requested or settings.tts_enabled)


def speak_text(
    text: str,
    settings: AppSettings,
    speak_requested: bool = False,
    provider: TextToSpeechProvider | None = None,
) -> TextToSpeechResult:
    log_file = ensure_tts_log_sink(settings)
    tts_logger = logger.bind(tts=True)
    requested = should_speak(settings, speak_requested)

    if not requested:
        tts_logger.info("TTS skipped because it is disabled and no explicit speak flag was provided")
        return TextToSpeechResult(
            provider_name=settings.tts_provider,
            provider_available=False,
            requested=False,
            spoken=False,
            log_file=log_file,
        )

    cleaned = text.strip()
    if not cleaned:
        message = "TTS failed: no text was supplied."
        tts_logger.error(message)
        return TextToSpeechResult(
            provider_name=settings.tts_provider,
            provider_available=False,
            requested=True,
            spoken=False,
            log_file=log_file,
            error=message,
        )

    try:
        tts_provider = provider or create_text_to_speech_provider(settings)
    except Exception as exc:
        message = f"TTS provider selection failed: {type(exc).__name__}: {exc}"
        tts_logger.error(message)
        return TextToSpeechResult(
            provider_name=settings.tts_provider,
            provider_available=False,
            requested=True,
            spoken=False,
            log_file=log_file,
            error=message,
        )

    provider_available = bool(tts_provider.available)
    if not provider_available:
        message = f"TTS provider '{tts_provider.name}' is not available. Install pyttsx3 and verify local audio output."
        tts_logger.error(message)
        return TextToSpeechResult(
            provider_name=tts_provider.name,
            provider_available=False,
            requested=True,
            spoken=False,
            log_file=log_file,
            error=message,
        )

    try:
        tts_logger.info("Speaking response through provider={}", tts_provider.name)
        tts_provider.speak(cleaned)
    except Exception as exc:
        message = f"TTS audio output failed: {type(exc).__name__}: {exc}"
        tts_logger.exception(message)
        return TextToSpeechResult(
            provider_name=tts_provider.name,
            provider_available=provider_available,
            requested=True,
            spoken=False,
            log_file=log_file,
            error=message,
        )

    tts_logger.info("TTS completed through provider={}", tts_provider.name)
    return TextToSpeechResult(
        provider_name=tts_provider.name,
        provider_available=provider_available,
        requested=True,
        spoken=True,
        log_file=log_file,
    )


def format_tts_result(result: TextToSpeechResult) -> str:
    lines = [
        "Jarvis TTS Test",
        "===============",
        f"provider: {result.provider_name}",
        f"provider available: {_yes_no(result.provider_available)}",
        f"requested: {_yes_no(result.requested)}",
        f"spoken: {_yes_no(result.spoken)}",
        f"diagnostic log: {result.log_file}",
    ]
    if result.error:
        lines.extend(["", "Errors:", f"  - {result.error}"])
    return "\n".join(lines)


def ensure_tts_log_sink(settings: AppSettings) -> Path:
    global _TTS_LOG_FILE, _TTS_LOG_SINK_ID
    log_file = settings.log_dir / "tts.log"
    if _TTS_LOG_SINK_ID is not None and _TTS_LOG_FILE == log_file:
        return log_file

    if _TTS_LOG_SINK_ID is not None:
        try:
            logger.remove(_TTS_LOG_SINK_ID)
        except ValueError:
            pass

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    _TTS_LOG_SINK_ID = logger.add(
        log_file,
        level="DEBUG",
        rotation="1 MB",
        retention="7 days",
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
        filter=lambda record: bool(record["extra"].get("tts")),
    )
    _TTS_LOG_FILE = log_file
    return log_file


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
