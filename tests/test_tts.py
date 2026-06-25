from __future__ import annotations

import threading
from pathlib import Path

from config.settings import AppSettings
from voice.tts import (
    OpenAITextToSpeechProvider,
    Pyttsx3TextToSpeechProvider,
    SpeechInterrupted,
    create_text_to_speech_provider,
    format_tts_result,
    interrupt_active_speech,
    speak_text,
)


class FakeTtsProvider:
    name = "fake_tts"
    available = True

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


class FailingTtsProvider:
    name = "failing_tts"
    available = True

    def speak(self, text: str) -> None:
        del text
        raise RuntimeError("audio device unavailable")


class MissingTtsProvider:
    name = "missing_tts"
    available = False

    def speak(self, text: str) -> None:
        del text
        raise AssertionError("unavailable providers should not be called")


class FakeOpenAITtsProvider:
    name = "openai"
    available = True

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        if self.error:
            raise self.error
        self.spoken.append(text)


class InterruptibleTtsProvider:
    name = "interruptible"
    available = True

    def __init__(self) -> None:
        self.started = threading.Event()
        self.stopped = threading.Event()

    def speak(self, text: str) -> None:
        assert text
        self.started.set()
        self.stopped.wait(timeout=2.0)
        raise SpeechInterrupted("stopped")

    def stop(self) -> bool:
        self.stopped.set()
        return True


def settings_for_tts(tmp_path: Path, **overrides) -> AppSettings:
    return AppSettings(_env_file=None, log_dir=tmp_path, **overrides)


def test_tts_disabled_does_not_speak_without_flag(tmp_path: Path) -> None:
    provider = FakeTtsProvider()
    settings = settings_for_tts(tmp_path, tts_enabled=False)

    result = speak_text("Hello", settings, provider=provider)

    assert result.requested is False
    assert result.spoken is False
    assert provider.spoken == []


def test_tts_enabled_speaks_without_flag(tmp_path: Path) -> None:
    provider = FakeTtsProvider()
    settings = settings_for_tts(tmp_path, tts_enabled=True)

    result = speak_text("Hello", settings, provider=provider)

    assert result.requested is True
    assert result.spoken is True
    assert provider.spoken == ["Hello"]


def test_tts_provider_selection_uses_openai_by_default(tmp_path: Path) -> None:
    settings = settings_for_tts(
        tmp_path,
        openai_enabled=True,
        openai_api_key="sk-test",
    )

    provider = create_text_to_speech_provider(settings)

    assert isinstance(provider, OpenAITextToSpeechProvider)
    assert provider.audio_dir == tmp_path / "audio"


def test_tts_provider_selection_can_use_pyttsx3_settings(tmp_path: Path) -> None:
    settings = settings_for_tts(
        tmp_path,
        tts_provider="pyttsx3",
        tts_voice_name="David",
        tts_rate=190,
        tts_volume=0.8,
    )

    provider = create_text_to_speech_provider(settings)

    assert isinstance(provider, Pyttsx3TextToSpeechProvider)
    assert provider.voice_name == "David"
    assert provider.rate == 190
    assert provider.volume == 0.8
    assert provider.comtypes_cache_dir == tmp_path / "comtypes_gen"


def test_speak_flag_overrides_disabled_tts(tmp_path: Path) -> None:
    provider = FakeTtsProvider()
    settings = settings_for_tts(tmp_path, tts_enabled=False)

    result = speak_text("Hello", settings, speak_requested=True, provider=provider)

    assert result.requested is True
    assert result.spoken is True
    assert provider.spoken == ["Hello"]


def test_tts_safe_failure_for_missing_provider(tmp_path: Path) -> None:
    settings = settings_for_tts(tmp_path, tts_enabled=True)

    result = speak_text("Hello", settings, provider=MissingTtsProvider())

    assert result.spoken is False
    assert result.error is not None
    assert "not available" in result.error


def test_tts_safe_failure_for_audio_output_error(tmp_path: Path) -> None:
    settings = settings_for_tts(tmp_path, tts_enabled=True, tts_provider="pyttsx3")

    result = speak_text("Hello", settings, provider=FailingTtsProvider())

    assert result.spoken is False
    assert result.error is not None
    assert "audio output failed" in result.error


def test_openai_tts_disabled_falls_back_to_pyttsx3(tmp_path: Path) -> None:
    fallback = FakeTtsProvider()
    settings = settings_for_tts(tmp_path, openai_enabled=False, openai_api_key="")

    result = speak_text(
        "Hello",
        settings,
        speak_requested=True,
        provider=MissingTtsProvider(),
        provider_name="openai",
        fallback_provider=fallback,
    )

    assert result.spoken is True
    assert result.provider_name == "fake_tts"
    assert result.requested_provider_name == "openai"
    assert result.fallback_used is True
    assert fallback.spoken == ["Hello"]


def test_openai_tts_failure_falls_back_to_pyttsx3(tmp_path: Path) -> None:
    fallback = FakeTtsProvider()
    settings = settings_for_tts(tmp_path, openai_enabled=True, openai_api_key="sk-secret")

    result = speak_text(
        "Hello",
        settings,
        speak_requested=True,
        provider=FakeOpenAITtsProvider(error=RuntimeError("network failed")),
        fallback_provider=fallback,
    )

    assert result.spoken is True
    assert result.provider_name == "fake_tts"
    assert result.requested_provider_name == "openai"
    assert result.fallback_used is True
    assert "network failed" in (result.fallback_reason or "")
    assert fallback.spoken == ["Hello"]


def test_openai_tts_errors_do_not_expose_api_keys(tmp_path: Path) -> None:
    fallback = FakeTtsProvider()
    settings = settings_for_tts(tmp_path, openai_enabled=True, openai_api_key="sk-secret")

    result = speak_text(
        "Hello",
        settings,
        speak_requested=True,
        provider=FakeOpenAITtsProvider(error=RuntimeError("bad key sk-secret OPENAI_API_KEY")),
        fallback_provider=fallback,
    )
    text = format_tts_result(result)
    log_text = (tmp_path / "tts.log").read_text(encoding="utf-8")

    assert result.spoken is True
    assert "sk-secret" not in text
    assert "OPENAI_API_KEY" not in text
    assert "sk-secret" not in log_text
    assert "OPENAI_API_KEY" not in log_text
    assert "[redacted]" in text


def test_active_tts_can_be_interrupted(tmp_path: Path) -> None:
    provider = InterruptibleTtsProvider()
    settings = settings_for_tts(tmp_path, tts_enabled=True)
    results = []
    worker = threading.Thread(
        target=lambda: results.append(speak_text("Hello", settings, provider=provider)),
        daemon=True,
    )

    worker.start()
    assert provider.started.wait(timeout=1.0)
    assert interrupt_active_speech() is True
    worker.join(timeout=2.0)

    assert worker.is_alive() is False
    assert len(results) == 1
    assert results[0].interrupted is True
    assert results[0].spoken is False
    assert results[0].error is None
