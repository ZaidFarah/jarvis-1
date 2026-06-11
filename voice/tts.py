from __future__ import annotations

import ctypes
import importlib
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from loguru import logger

from config.settings import AppSettings
from voice.interfaces import TextToSpeechProvider


_TTS_LOG_SINK_ID: int | None = None
_TTS_LOG_FILE: Path | None = None


class AudioPlayer(Protocol):
    def play(self, path: Path, audio_format: str) -> None:
        """Play a generated audio file and return only after playback finishes."""


@dataclass(frozen=True)
class TextToSpeechResult:
    provider_name: str
    provider_available: bool
    requested: bool
    spoken: bool
    log_file: Path
    requested_provider_name: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    audio_file: Path | None = None
    error: str | None = None


class WindowsMciAudioPlayer:
    """Small blocking audio player for local generated audio on Windows."""

    def play(self, path: Path, audio_format: str) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Generated audio playback is currently supported only on Windows.")

        if not path.exists():
            raise RuntimeError(f"Generated audio file does not exist: {path}")

        alias = f"jarvis_tts_{uuid.uuid4().hex}"
        file_path = str(path.resolve()).replace('"', "")
        media_type = " type mpegvideo" if audio_format.lower() in {"mp3", "aac"} else ""
        self._mci(f'open "{file_path}"{media_type} alias {alias}')
        try:
            self._mci(f"play {alias} wait")
        finally:
            self._mci(f"close {alias}", raise_on_error=False)

    @staticmethod
    def _mci(command: str, raise_on_error: bool = True) -> None:
        error_code = ctypes.windll.winmm.mciSendStringW(command, None, 0, None)
        if error_code == 0 or not raise_on_error:
            return

        buffer = ctypes.create_unicode_buffer(255)
        ctypes.windll.winmm.mciGetErrorStringW(error_code, buffer, len(buffer))
        message = buffer.value or f"MCI error {error_code}"
        raise RuntimeError(message)


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
        self.last_audio_file: Path | None = None
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


class OpenAITextToSpeechProvider:
    """OpenAI TTS provider that generates temporary audio and plays it locally."""

    name = "openai"

    def __init__(
        self,
        settings: AppSettings,
        client_factory: Any | None = None,
        audio_player: AudioPlayer | None = None,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory or self._default_client_factory
        self.audio_player = audio_player or WindowsMciAudioPlayer()
        self.audio_dir = self.settings.log_dir / "audio"
        self.last_audio_file: Path | None = None

    @property
    def available(self) -> bool:
        return bool(self.settings.openai_enabled and self.settings.has_openai_api_key)

    def speak(self, text: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("TTS text cannot be empty.")

        if not self.settings.openai_enabled:
            raise RuntimeError("OpenAI TTS is disabled because OpenAI is disabled.")

        if not self.settings.has_openai_api_key:
            raise RuntimeError("OpenAI TTS requires an API key, but no API key is configured.")

        self.audio_dir.mkdir(parents=True, exist_ok=True)
        audio_file = self._next_audio_file()
        client = self.client_factory(api_key=self.settings.openai_api_key)
        request = {
            "model": self.settings.openai_tts_model,
            "voice": self.settings.openai_tts_voice,
            "input": cleaned,
            "response_format": self.settings.openai_tts_format,
        }
        if self.settings.openai_tts_model not in {"tts-1", "tts-1-hd"}:
            request["instructions"] = self.settings.openai_tts_instructions

        response = client.audio.speech.create(**request)
        self._write_response_to_file(response, audio_file)
        if not audio_file.exists() or audio_file.stat().st_size == 0:
            raise RuntimeError("OpenAI TTS returned an empty audio file.")

        self.last_audio_file = audio_file
        self.audio_player.play(audio_file, self.settings.openai_tts_format)

    def _next_audio_file(self) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = self.settings.openai_tts_format
        return self.audio_dir / f"jarvis_tts_{timestamp}_{uuid.uuid4().hex}.{suffix}"

    @staticmethod
    def _write_response_to_file(response: Any, path: Path) -> None:
        if hasattr(response, "write_to_file"):
            response.write_to_file(path)
            return

        content = getattr(response, "content", None)
        if content is None and hasattr(response, "read"):
            content = response.read()
        if not content:
            raise RuntimeError("OpenAI TTS response did not include audio bytes.")
        path.write_bytes(bytes(content))

    @staticmethod
    def _default_client_factory(api_key: str) -> Any:
        from openai import OpenAI

        return OpenAI(api_key=api_key)


def create_text_to_speech_provider(
    settings: AppSettings,
    provider_name: str | None = None,
    *,
    client_factory: Any | None = None,
    audio_player: AudioPlayer | None = None,
) -> TextToSpeechProvider:
    provider = _normalize_provider_name(provider_name or settings.tts_provider)
    if provider == "openai":
        return OpenAITextToSpeechProvider(
            settings=settings,
            client_factory=client_factory,
            audio_player=audio_player,
        )
    if provider == "pyttsx3":
        return create_pyttsx3_text_to_speech_provider(settings)
    raise ValueError(f"Unsupported TTS provider: {provider_name or settings.tts_provider}")


def create_pyttsx3_text_to_speech_provider(settings: AppSettings) -> Pyttsx3TextToSpeechProvider:
    return Pyttsx3TextToSpeechProvider(
        voice_name=settings.tts_voice_name,
        rate=settings.tts_rate,
        volume=settings.tts_volume,
        comtypes_cache_dir=settings.log_dir / "comtypes_gen",
    )


def should_speak(settings: AppSettings, speak_requested: bool = False) -> bool:
    return bool(speak_requested or settings.tts_enabled)


def speak_text(
    text: str,
    settings: AppSettings,
    speak_requested: bool = False,
    provider: TextToSpeechProvider | None = None,
    fallback_provider: TextToSpeechProvider | None = None,
    provider_name: str | None = None,
) -> TextToSpeechResult:
    log_file = ensure_tts_log_sink(settings)
    tts_logger = logger.bind(tts=True)
    requested_provider_name = _normalize_provider_name(
        provider_name or (provider.name if provider is not None else settings.tts_provider)
    )
    requested = should_speak(settings, speak_requested)

    if not requested:
        tts_logger.info("TTS skipped because it is disabled and no explicit speak flag was provided")
        return TextToSpeechResult(
            provider_name=requested_provider_name,
            provider_available=False,
            requested=False,
            spoken=False,
            log_file=log_file,
            requested_provider_name=requested_provider_name,
        )

    cleaned = text.strip()
    if not cleaned:
        message = "TTS failed: no text was supplied."
        tts_logger.error(message)
        return TextToSpeechResult(
            provider_name=requested_provider_name,
            provider_available=False,
            requested=True,
            spoken=False,
            log_file=log_file,
            requested_provider_name=requested_provider_name,
            error=message,
        )

    try:
        tts_provider = provider or create_text_to_speech_provider(settings, provider_name=provider_name)
    except Exception as exc:
        message = _format_safe_exception("TTS provider selection failed", exc)
        tts_logger.error(message)
        return TextToSpeechResult(
            provider_name=requested_provider_name,
            provider_available=False,
            requested=True,
            spoken=False,
            log_file=log_file,
            requested_provider_name=requested_provider_name,
            error=message,
        )

    provider_available = bool(tts_provider.available)
    if not provider_available:
        message = f"TTS provider '{tts_provider.name}' is not available."
        if _can_fallback_to_pyttsx3(tts_provider, requested_provider_name):
            return _speak_with_fallback(
                cleaned,
                settings,
                log_file,
                tts_logger,
                requested_provider_name,
                message,
                fallback_provider=fallback_provider,
            )

        tts_logger.error("{} Install pyttsx3 and verify local audio output.", message)
        return TextToSpeechResult(
            provider_name=tts_provider.name,
            provider_available=False,
            requested=True,
            spoken=False,
            log_file=log_file,
            requested_provider_name=requested_provider_name,
            error=f"{message} Install pyttsx3 and verify local audio output.",
        )

    try:
        tts_logger.info("Speaking response through provider={}", tts_provider.name)
        tts_provider.speak(cleaned)
    except Exception as exc:
        message = _format_safe_exception("TTS audio output failed", exc)
        if _can_fallback_to_pyttsx3(tts_provider, requested_provider_name):
            return _speak_with_fallback(
                cleaned,
                settings,
                log_file,
                tts_logger,
                requested_provider_name,
                message,
                fallback_provider=fallback_provider,
            )

        tts_logger.error(message)
        return TextToSpeechResult(
            provider_name=tts_provider.name,
            provider_available=provider_available,
            requested=True,
            spoken=False,
            log_file=log_file,
            requested_provider_name=requested_provider_name,
            audio_file=getattr(tts_provider, "last_audio_file", None),
            error=message,
        )

    tts_logger.info("TTS completed through provider={}", tts_provider.name)
    return TextToSpeechResult(
        provider_name=tts_provider.name,
        provider_available=provider_available,
        requested=True,
        spoken=True,
        log_file=log_file,
        requested_provider_name=requested_provider_name,
        audio_file=getattr(tts_provider, "last_audio_file", None),
    )


def _speak_with_fallback(
    text: str,
    settings: AppSettings,
    log_file: Path,
    tts_logger: Any,
    requested_provider_name: str,
    fallback_reason: str,
    fallback_provider: TextToSpeechProvider | None = None,
) -> TextToSpeechResult:
    tts_logger.warning("Falling back to pyttsx3 TTS: {}", fallback_reason)
    provider = fallback_provider or create_pyttsx3_text_to_speech_provider(settings)

    if not provider.available:
        message = f"{fallback_reason}; fallback provider 'pyttsx3' is not available."
        tts_logger.error(message)
        return TextToSpeechResult(
            provider_name=provider.name,
            provider_available=False,
            requested=True,
            spoken=False,
            log_file=log_file,
            requested_provider_name=requested_provider_name,
            fallback_used=True,
            fallback_reason=fallback_reason,
            error=message,
        )

    try:
        provider.speak(text)
    except Exception as exc:
        fallback_error = _format_safe_exception("pyttsx3 fallback failed", exc)
        message = f"{fallback_reason}; {fallback_error}"
        tts_logger.error(message)
        return TextToSpeechResult(
            provider_name=provider.name,
            provider_available=True,
            requested=True,
            spoken=False,
            log_file=log_file,
            requested_provider_name=requested_provider_name,
            fallback_used=True,
            fallback_reason=fallback_reason,
            audio_file=getattr(provider, "last_audio_file", None),
            error=message,
        )

    tts_logger.info("TTS completed through fallback provider={}", provider.name)
    return TextToSpeechResult(
        provider_name=provider.name,
        provider_available=True,
        requested=True,
        spoken=True,
        log_file=log_file,
        requested_provider_name=requested_provider_name,
        fallback_used=True,
        fallback_reason=fallback_reason,
        audio_file=getattr(provider, "last_audio_file", None),
    )


def format_tts_result(result: TextToSpeechResult) -> str:
    lines = [
        "Jarvis TTS Test",
        "===============",
        f"provider: {result.provider_name}",
        f"requested provider: {result.requested_provider_name or result.provider_name}",
        f"provider available: {_yes_no(result.provider_available)}",
        f"fallback used: {_yes_no(result.fallback_used)}",
        f"requested: {_yes_no(result.requested)}",
        f"spoken: {_yes_no(result.spoken)}",
        f"diagnostic log: {result.log_file}",
    ]
    if result.audio_file:
        lines.append(f"audio file: {result.audio_file}")
    if result.fallback_reason:
        lines.extend(["", "Fallback reason:", f"  {result.fallback_reason}"])
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


def _can_fallback_to_pyttsx3(provider: TextToSpeechProvider, requested_provider_name: str) -> bool:
    return provider.name == "openai" or requested_provider_name == "openai"


def _normalize_provider_name(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _format_safe_exception(prefix: str, error: Exception) -> str:
    message = str(error).strip() or "No error details provided."
    return f"{prefix}: {type(error).__name__}: {_redact_secret_like_text(message)}"


def _redact_secret_like_text(text: str) -> str:
    redacted = re.sub(r"sk-[A-Za-z0-9_\-]+", "[redacted]", text)
    return redacted.replace("OPENAI_API_KEY", "[redacted]")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
