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
    assert settings.wake_phrase == "hey jarvis"
    assert settings.wake_alias_list == [
        "hey jarvis",
        "hi jarvis",
        "wake up jarvis",
        "jarvis wake up",
        "okay jarvis",
        "yo jarvis",
    ]
    assert settings.wake_match_threshold == 0.72
    assert settings.wake_listen_seconds == 5.0
    assert settings.wake_provider == "openwakeword"
    assert settings.openwakeword_enabled is False
    assert settings.openwakeword_model == "hey_jarvis"
    assert settings.openwakeword_threshold == 0.5
    assert settings.openwakeword_listen_chunk_ms == 80
    assert settings.openwakeword_test_seconds == 10.0
    assert settings.openwakeword_fallback_to_whisper is True
    assert settings.voice_command_start_delay_seconds == 1.0
    assert settings.voice_command_record_seconds == 7.0
    assert settings.voice_loop_enabled is False
    assert settings.voice_loop_max_empty_commands == 3
    assert settings.voice_loop_wake_cooldown_seconds == 1.5
    assert settings.voice_loop_speak_status is True
    assert settings.tts_enabled is False
    assert settings.tts_provider == "openai"
    assert settings.tts_voice_name == ""
    assert settings.tts_rate == 175
    assert settings.tts_volume == 1.0
    assert settings.openai_tts_model == "gpt-4o-mini-tts"
    assert settings.openai_tts_voice == "cedar"
    assert settings.openai_tts_format == "mp3"
    assert settings.openai_tts_instructions == (
        "Speak as a calm, mature, professional British-inspired desktop AI assistant. "
        "Use a confident, clear, cinematic tone. Do not sound childish. "
        "Keep the pace natural and efficient."
    )
    assert settings.text_to_speech_provider == "openai"


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


def test_tts_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("TTS_ENABLED", "true")
    monkeypatch.setenv("TTS_PROVIDER", "pyttsx3")
    monkeypatch.setenv("TTS_VOICE_NAME", " David ")
    monkeypatch.setenv("TTS_RATE", "190")
    monkeypatch.setenv("TTS_VOLUME", "0.75")
    monkeypatch.setenv("OPENAI_TTS_MODEL", "gpt-test-tts")
    monkeypatch.setenv("OPENAI_TTS_VOICE", "cedar")
    monkeypatch.setenv("OPENAI_TTS_FORMAT", "wav")
    monkeypatch.setenv("OPENAI_TTS_INSTRUCTIONS", "  Speak clearly.  ")

    settings = AppSettings(_env_file=None)

    assert settings.tts_enabled is True
    assert settings.tts_provider == "pyttsx3"
    assert settings.tts_voice_name == "David"
    assert settings.tts_rate == 190
    assert settings.tts_volume == 0.75
    assert settings.openai_tts_model == "gpt-test-tts"
    assert settings.openai_tts_voice == "cedar"
    assert settings.openai_tts_format == "wav"
    assert settings.openai_tts_instructions == "Speak clearly."


def test_wake_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("WAKE_PHRASE", "hello jarvis")
    monkeypatch.setenv("WAKE_ALIASES", "hello jarvis,jarvis hello")
    monkeypatch.setenv("WAKE_MATCH_THRESHOLD", "0.8")
    monkeypatch.setenv("WAKE_LISTEN_SECONDS", "4")
    monkeypatch.setenv("WAKE_PROVIDER", "whisper_fuzzy")
    monkeypatch.setenv("OPENWAKEWORD_ENABLED", "true")
    monkeypatch.setenv("OPENWAKEWORD_MODEL", "hey.jarvis")
    monkeypatch.setenv("OPENWAKEWORD_THRESHOLD", "0.7")
    monkeypatch.setenv("OPENWAKEWORD_LISTEN_CHUNK_MS", "120")
    monkeypatch.setenv("OPENWAKEWORD_TEST_SECONDS", "12")
    monkeypatch.setenv("OPENWAKEWORD_FALLBACK_TO_WHISPER", "false")
    monkeypatch.setenv("VOICE_COMMAND_START_DELAY_SECONDS", "1.25")
    monkeypatch.setenv("VOICE_COMMAND_RECORD_SECONDS", "8")
    monkeypatch.setenv("VOICE_LOOP_ENABLED", "true")
    monkeypatch.setenv("VOICE_LOOP_MAX_EMPTY_COMMANDS", "5")
    monkeypatch.setenv("VOICE_LOOP_WAKE_COOLDOWN_SECONDS", "2.5")
    monkeypatch.setenv("VOICE_LOOP_SPEAK_STATUS", "false")

    settings = AppSettings(_env_file=None)

    assert settings.wake_phrase == "hello jarvis"
    assert settings.wake_alias_list == ["hello jarvis", "jarvis hello"]
    assert settings.wake_match_threshold == 0.8
    assert settings.wake_listen_seconds == 4.0
    assert settings.wake_provider == "whisper_fuzzy"
    assert settings.openwakeword_enabled is True
    assert settings.openwakeword_model == "hey.jarvis"
    assert settings.openwakeword_threshold == 0.7
    assert settings.openwakeword_listen_chunk_ms == 120
    assert settings.openwakeword_test_seconds == 12.0
    assert settings.openwakeword_fallback_to_whisper is False
    assert settings.voice_command_start_delay_seconds == 1.25
    assert settings.voice_command_record_seconds == 8.0
    assert settings.voice_loop_enabled is True
    assert settings.voice_loop_max_empty_commands == 5
    assert settings.voice_loop_wake_cooldown_seconds == 2.5
    assert settings.voice_loop_speak_status is False
