from __future__ import annotations

from config.settings import AppSettings


def test_voice_settings_defaults_are_lightweight() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.voice_sample_rate == 16000
    assert settings.voice_channels == 1
    assert settings.voice_microphone_test_seconds == 2.0
    assert settings.voice_vad_enabled is True
    assert settings.voice_vad_threshold == 0.01
    assert settings.speech_to_text_provider == "interface-only"
    assert settings.text_to_speech_provider == "pyttsx3"


def test_voice_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_VOICE_SAMPLE_RATE", "22050")
    monkeypatch.setenv("JARVIS_VOICE_MICROPHONE_TEST_SECONDS", "1.5")
    monkeypatch.setenv("JARVIS_VOICE_VAD_THRESHOLD", "0.02")

    settings = AppSettings(_env_file=None)

    assert settings.voice_sample_rate == 22050
    assert settings.voice_microphone_test_seconds == 1.5
    assert settings.voice_vad_threshold == 0.02
