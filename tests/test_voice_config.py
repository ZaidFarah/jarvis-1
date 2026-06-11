from __future__ import annotations

from config.settings import AppSettings


def test_voice_settings_defaults_are_lightweight() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.voice_sample_rate == 16000
    assert settings.voice_channels == 1
    assert settings.voice_record_seconds == 5.0
    assert settings.voice_microphone_test_seconds == 5.0
    assert settings.voice_vad_enabled is True
    assert settings.voice_vad_threshold == 0.0015
    assert settings.speech_to_text_provider == "faster_whisper"
    assert settings.whisper_model == "base.en"
    assert settings.whisper_device == "cpu"
    assert settings.whisper_compute_type == "int8"
    assert settings.text_to_speech_provider == "pyttsx3"


def test_voice_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_SAMPLE_RATE", "22050")
    monkeypatch.setenv("VOICE_RECORD_SECONDS", "1.5")
    monkeypatch.setenv("VOICE_VAD_THRESHOLD", "0.02")

    settings = AppSettings(_env_file=None)

    assert settings.voice_sample_rate == 22050
    assert settings.voice_record_seconds == 1.5
    assert settings.voice_vad_threshold == 0.02


def test_voice_settings_keep_previous_jarvis_prefixed_names(monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_VOICE_SAMPLE_RATE", "24000")
    monkeypatch.setenv("JARVIS_VOICE_MICROPHONE_TEST_SECONDS", "3")
    monkeypatch.setenv("JARVIS_VOICE_VAD_THRESHOLD", "0.03")

    settings = AppSettings(_env_file=None)

    assert settings.voice_sample_rate == 24000
    assert settings.voice_record_seconds == 3.0
    assert settings.voice_vad_threshold == 0.03


def test_stt_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("STT_PROVIDER", "interface-only")
    monkeypatch.setenv("WHISPER_MODEL", "tiny.en")
    monkeypatch.setenv("WHISPER_DEVICE", "cpu")
    monkeypatch.setenv("WHISPER_COMPUTE_TYPE", "float32")

    settings = AppSettings(_env_file=None)

    assert settings.speech_to_text_provider == "interface-only"
    assert settings.whisper_model == "tiny.en"
    assert settings.whisper_device == "cpu"
    assert settings.whisper_compute_type == "float32"
