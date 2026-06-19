from __future__ import annotations

import pytest

from config.settings import AppSettings


def test_voice_settings_defaults_are_lightweight() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.voice_sample_rate == 16000
    assert settings.voice_channels == 1
    assert settings.voice_input_device == ""
    assert settings.voice_health_speech_seconds == 6.0
    assert settings.voice_record_seconds == 5.0
    assert settings.voice_microphone_test_seconds == 5.0
    assert settings.voice_vad_enabled is True
    assert settings.voice_vad_threshold == 0.0015
    assert settings.voice_vad_window_ms == 80
    assert settings.voice_vad_noise_multiplier == 3.0
    assert settings.voice_vad_silence_ms == 650
    assert settings.fast_voice_enabled is True
    assert settings.fast_voice_activation == "enter"
    assert settings.fast_voice_record_seconds == 4.0
    assert settings.fast_voice_max_seconds == 1.8
    assert settings.fast_voice_min_speech_ms == 300
    assert settings.fast_voice_silence_ms == 300
    assert settings.fast_voice_fast_stop_enabled is True
    assert settings.fast_voice_short_command_silence_ms == 250
    assert settings.fast_voice_long_command_silence_ms == 450
    assert settings.fast_voice_preroll_ms == 250
    assert settings.fast_voice_tts_enabled is False
    assert settings.fast_voice_wake_only_response == "I'm listening."
    assert settings.fast_voice_empty_audio_response == "I heard sound but could not understand it."
    assert settings.fast_voice_warm_stt_on_start is True
    assert settings.fast_voice_concise_responses is True
    assert settings.fast_voice_concise_instruction == (
        "Respond in one short sentence. Be direct unless the user asks for detail."
    )
    assert settings.speech_to_text_provider == "faster_whisper"
    assert settings.whisper_model == "base.en"
    assert settings.whisper_device == "cpu"
    assert settings.whisper_compute_type == "int8"
    assert settings.wake_phrase == "hey jarvis"
    assert settings.wake_alias_list == [
        "jarvis",
        "hey jarvis",
        "hi jarvis",
        "okay jarvis",
        "wake up jarvis",
        "yo jarvis",
        "jarvis please",
        "service",
        "jervis",
        "travis",
        "charities",
        "office",
        "jar of this",
        "out of this",
        "turn this",
    ]
    assert settings.wake_match_threshold == 0.72
    assert settings.wake_listen_seconds == 2.0
    assert settings.wake_provider == "openwakeword"
    assert settings.wake_fallback_provider == "whisper_fuzzy"
    assert settings.openwakeword_enabled is True
    assert settings.openwakeword_model == "hey_jarvis"
    assert settings.openwakeword_threshold == 0.5
    assert settings.openwakeword_listen_chunk_ms == 80
    assert settings.openwakeword_test_seconds == 10.0
    assert settings.openwakeword_fallback_to_whisper is True
    assert settings.voice_command_start_delay_seconds == 0.0
    assert settings.voice_command_record_seconds == 5.0
    assert settings.voice_command_min_words == 2
    assert settings.voice_command_reject_phrase_list == ["you", "uh", "um", "hmm", "yeah", "okay"]
    assert settings.voice_command_incomplete_phrase_list == [
        "what's the",
        "what is the",
        "tell me about",
        "can you",
        "could you",
        "weather in",
        "remind me",
        "please",
    ]
    assert settings.voice_speech_repair_enabled is True
    assert settings.voice_use_openai_repair is False
    assert settings.voice_repair_rule_pairs == [
        ("did it noting him today whats the", "what's the weather in Nottingham today"),
        ("did it nottingham today whats the", "what's the weather in Nottingham today"),
    ]
    assert settings.voice_repair_incomplete_phrase_list == [
        "what's the",
        "what is the",
        "tell me about",
        "can you",
        "could you",
        "weather in",
        "remind me",
        "please",
    ]
    assert settings.voice_repair_confirmation_threshold == 0.75
    assert settings.voice_repair_confirmation_seconds == 3.0
    assert settings.voice_command_retry_on_reject is True
    assert settings.voice_command_max_retries == 1
    assert settings.voice_loop_enabled is False
    assert settings.voice_loop_max_empty_commands == 3
    assert settings.voice_loop_wake_cooldown_seconds == 1.5
    assert settings.voice_loop_speak_status is True
    assert settings.voice_loop_speak_wake_ack is False
    assert settings.voice_loop_speak_responses is True
    assert settings.voice_follow_up_timeout_seconds == 10.0
    assert settings.voice_response_mode == "concise"
    assert settings.voice_concise_instruction == "Answer voice commands in one or two short sentences unless the user asks for detail."
    assert settings.voice_loop_speak_standby is False
    assert settings.voice_loop_standby_message == "Standing by."
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
    monkeypatch.setenv("VOICE_INPUT_DEVICE", "  USB Microphone  ")
    monkeypatch.setenv("VOICE_HEALTH_SPEECH_SECONDS", "7.5")
    monkeypatch.setenv("VOICE_RECORD_SECONDS", "1.5")
    monkeypatch.setenv("VOICE_VAD_THRESHOLD", "0.02")
    monkeypatch.setenv("VOICE_VAD_WINDOW_MS", "60")
    monkeypatch.setenv("VOICE_VAD_NOISE_MULTIPLIER", "2.5")
    monkeypatch.setenv("VOICE_VAD_SILENCE_MS", "500")
    monkeypatch.setenv("FAST_VOICE_ENABLED", "false")
    monkeypatch.setenv("FAST_VOICE_ACTIVATION", "direct")
    monkeypatch.setenv("FAST_VOICE_RECORD_SECONDS", "3.5")
    monkeypatch.setenv("FAST_VOICE_MAX_SECONDS", "2.75")
    monkeypatch.setenv("FAST_VOICE_MIN_SPEECH_MS", "260")
    monkeypatch.setenv("FAST_VOICE_SILENCE_MS", "320")
    monkeypatch.setenv("FAST_VOICE_FAST_STOP_ENABLED", "false")
    monkeypatch.setenv("FAST_VOICE_SHORT_COMMAND_SILENCE_MS", "210")
    monkeypatch.setenv("FAST_VOICE_LONG_COMMAND_SILENCE_MS", "510")
    monkeypatch.setenv("FAST_VOICE_PREROLL_MS", "180")
    monkeypatch.setenv("FAST_VOICE_TTS_ENABLED", "true")
    monkeypatch.setenv("FAST_VOICE_WAKE_ONLY_RESPONSE", "  Ready.  ")
    monkeypatch.setenv("FAST_VOICE_EMPTY_AUDIO_RESPONSE", "  Please repeat.  ")
    monkeypatch.setenv("FAST_VOICE_WARM_STT_ON_START", "false")
    monkeypatch.setenv("FAST_VOICE_CONCISE_RESPONSES", "false")
    monkeypatch.setenv("FAST_VOICE_CONCISE_INSTRUCTION", "  Give one brief answer.  ")
    monkeypatch.setenv("WAKE_THRESHOLD", "0.81")
    monkeypatch.setenv("WAKE_FALLBACK_PROVIDER", "manual")

    settings = AppSettings(_env_file=None)

    assert settings.voice_sample_rate == 22050
    assert settings.voice_input_device == "USB Microphone"
    assert settings.voice_health_speech_seconds == 7.5
    assert settings.voice_record_seconds == 1.5
    assert settings.voice_vad_threshold == 0.02
    assert settings.voice_vad_window_ms == 60
    assert settings.voice_vad_noise_multiplier == 2.5
    assert settings.voice_vad_silence_ms == 500
    assert settings.fast_voice_enabled is False
    assert settings.fast_voice_activation == "direct"
    assert settings.fast_voice_record_seconds == 3.5
    assert settings.fast_voice_max_seconds == 2.75
    assert settings.fast_voice_min_speech_ms == 260
    assert settings.fast_voice_silence_ms == 320
    assert settings.fast_voice_fast_stop_enabled is False
    assert settings.fast_voice_short_command_silence_ms == 210
    assert settings.fast_voice_long_command_silence_ms == 510
    assert settings.fast_voice_preroll_ms == 180
    assert settings.fast_voice_tts_enabled is True
    assert settings.fast_voice_wake_only_response == "Ready."
    assert settings.fast_voice_empty_audio_response == "Please repeat."
    assert settings.fast_voice_warm_stt_on_start is False
    assert settings.fast_voice_concise_responses is False
    assert settings.fast_voice_concise_instruction == "Give one brief answer."
    assert settings.wake_match_threshold == 0.81
    assert settings.wake_fallback_provider == "manual"


def test_voice_settings_keep_previous_jarvis_prefixed_names(monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_VOICE_SAMPLE_RATE", "24000")
    monkeypatch.setenv("JARVIS_VOICE_MICROPHONE_TEST_SECONDS", "3")
    monkeypatch.setenv("JARVIS_VOICE_VAD_THRESHOLD", "0.03")

    settings = AppSettings(_env_file=None)

    assert settings.voice_sample_rate == 24000
    assert settings.voice_record_seconds == 3.0
    assert settings.voice_vad_threshold == 0.03


def test_fast_voice_activation_aliases_and_validation() -> None:
    assert AppSettings(_env_file=None, fast_voice_activation="push-to-talk").fast_voice_activation == "enter"
    assert AppSettings(_env_file=None, fast_voice_activation="immediate").fast_voice_activation == "direct"
    with pytest.raises(ValueError, match="Unsupported fast voice activation"):
        AppSettings(_env_file=None, fast_voice_activation="wake")


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
    monkeypatch.setenv("WAKE_FALLBACK_PROVIDER", "manual")
    monkeypatch.setenv("OPENWAKEWORD_ENABLED", "true")
    monkeypatch.setenv("OPENWAKEWORD_MODEL", "hey.jarvis")
    monkeypatch.setenv("OPENWAKEWORD_THRESHOLD", "0.7")
    monkeypatch.setenv("OPENWAKEWORD_LISTEN_CHUNK_MS", "120")
    monkeypatch.setenv("OPENWAKEWORD_TEST_SECONDS", "12")
    monkeypatch.setenv("OPENWAKEWORD_FALLBACK_TO_WHISPER", "false")
    monkeypatch.setenv("VOICE_COMMAND_START_DELAY_SECONDS", "1.25")
    monkeypatch.setenv("VOICE_COMMAND_RECORD_SECONDS", "8")
    monkeypatch.setenv("VOICE_COMMAND_MIN_WORDS", "3")
    monkeypatch.setenv("VOICE_COMMAND_REJECT_PHRASES", "you, nope")
    monkeypatch.setenv("VOICE_COMMAND_INCOMPLETE_PHRASES", "what's the, can you")
    monkeypatch.setenv("VOICE_SPEECH_REPAIR_ENABLED", "false")
    monkeypatch.setenv("VOICE_USE_OPENAI_REPAIR", "true")
    monkeypatch.setenv("VOICE_REPAIR_RULES", "bad words=>good words")
    monkeypatch.setenv("VOICE_REPAIR_INCOMPLETE_PHRASES", "weather in, remind me")
    monkeypatch.setenv("VOICE_REPAIR_CONFIRMATION_THRESHOLD", "0.6")
    monkeypatch.setenv("VOICE_REPAIR_CONFIRMATION_SECONDS", "2.5")
    monkeypatch.setenv("VOICE_COMMAND_RETRY_ON_REJECT", "false")
    monkeypatch.setenv("VOICE_COMMAND_MAX_RETRIES", "2")
    monkeypatch.setenv("VOICE_LOOP_ENABLED", "true")
    monkeypatch.setenv("VOICE_LOOP_MAX_EMPTY_COMMANDS", "5")
    monkeypatch.setenv("VOICE_LOOP_WAKE_COOLDOWN_SECONDS", "2.5")
    monkeypatch.setenv("VOICE_LOOP_SPEAK_STATUS", "false")
    monkeypatch.setenv("VOICE_LOOP_SPEAK_WAKE_ACK", "true")
    monkeypatch.setenv("VOICE_LOOP_SPEAK_RESPONSES", "false")
    monkeypatch.setenv("VOICE_FOLLOW_UP_TIMEOUT_SECONDS", "6.5")
    monkeypatch.setenv("VOICE_RESPONSE_MODE", "normal")
    monkeypatch.setenv("VOICE_CONCISE_INSTRUCTION", "  Keep voice answers short.  ")
    monkeypatch.setenv("VOICE_LOOP_SPEAK_STANDBY", "false")
    monkeypatch.setenv("VOICE_LOOP_STANDBY_MESSAGE", "  Awaiting wake phrase.  ")

    settings = AppSettings(_env_file=None)

    assert settings.wake_phrase == "hello jarvis"
    assert settings.wake_alias_list == ["hello jarvis", "jarvis hello"]
    assert settings.wake_match_threshold == 0.8
    assert settings.wake_listen_seconds == 4.0
    assert settings.wake_provider == "whisper_fuzzy"
    assert settings.wake_fallback_provider == "manual"
    assert settings.openwakeword_enabled is True
    assert settings.openwakeword_model == "hey.jarvis"
    assert settings.openwakeword_threshold == 0.7
    assert settings.openwakeword_listen_chunk_ms == 120
    assert settings.openwakeword_test_seconds == 12.0
    assert settings.openwakeword_fallback_to_whisper is False
    assert settings.voice_command_start_delay_seconds == 1.25
    assert settings.voice_command_record_seconds == 8.0
    assert settings.voice_command_min_words == 3
    assert settings.voice_command_reject_phrase_list == ["you", "nope"]
    assert settings.voice_command_incomplete_phrase_list == ["what's the", "can you"]
    assert settings.voice_speech_repair_enabled is False
    assert settings.voice_use_openai_repair is True
    assert settings.voice_repair_rule_pairs == [("bad words", "good words")]
    assert settings.voice_repair_incomplete_phrase_list == ["weather in", "remind me"]
    assert settings.voice_repair_confirmation_threshold == 0.6
    assert settings.voice_repair_confirmation_seconds == 2.5
    assert settings.voice_command_retry_on_reject is False
    assert settings.voice_command_max_retries == 2
    assert settings.voice_loop_enabled is True
    assert settings.voice_loop_max_empty_commands == 5
    assert settings.voice_loop_wake_cooldown_seconds == 2.5
    assert settings.voice_loop_speak_status is False
    assert settings.voice_loop_speak_wake_ack is True
    assert settings.voice_loop_speak_responses is False
    assert settings.voice_follow_up_timeout_seconds == 6.5
    assert settings.voice_response_mode == "normal"
    assert settings.voice_concise_instruction == "Keep voice answers short."
    assert settings.voice_loop_speak_standby is False
    assert settings.voice_loop_standby_message == "Awaiting wake phrase."
