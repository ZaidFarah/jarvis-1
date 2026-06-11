from __future__ import annotations

from pathlib import Path

from config.settings import AppSettings
from voice.tts import (
    Pyttsx3TextToSpeechProvider,
    create_text_to_speech_provider,
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


def test_tts_provider_selection_uses_pyttsx3_settings(tmp_path: Path) -> None:
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
    settings = settings_for_tts(tmp_path, tts_enabled=True)

    result = speak_text("Hello", settings, provider=FailingTtsProvider())

    assert result.spoken is False
    assert result.error is not None
    assert "audio output failed" in result.error
