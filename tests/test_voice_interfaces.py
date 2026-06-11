from __future__ import annotations

import pytest

from config.settings import AppSettings
from voice.interfaces import TranscriptionResult
from voice.stt import InterfaceOnlySpeechToTextProvider
from voice.stt import FasterWhisperSpeechToTextProvider, create_speech_to_text_provider
from voice.tts import Pyttsx3TextToSpeechProvider
from voice.vad import RmsVoiceActivityDetector


def test_rms_vad_detects_signal_above_threshold() -> None:
    vad = RmsVoiceActivityDetector(threshold=0.01)

    result = vad.analyze([0.0, 0.02, -0.02, 0.0], sample_rate=16000)

    assert result.is_speech is True
    assert result.rms > result.threshold


def test_rms_vad_rejects_silence() -> None:
    vad = RmsVoiceActivityDetector(threshold=0.01)

    result = vad.analyze([0.0, 0.0, 0.0], sample_rate=16000)

    assert result.is_speech is False
    assert result.rms == 0.0


def test_stt_provider_is_interface_only_in_phase_2() -> None:
    provider = InterfaceOnlySpeechToTextProvider()

    assert provider.name == "interface-only"
    assert provider.available is False
    with pytest.raises(NotImplementedError):
        provider.transcribe([0.0], sample_rate=16000)


def test_stt_factory_can_select_interface_only_provider() -> None:
    settings = AppSettings(_env_file=None, speech_to_text_provider="interface-only")

    provider = create_speech_to_text_provider(settings)

    assert isinstance(provider, InterfaceOnlySpeechToTextProvider)


def test_faster_whisper_provider_reports_missing_dependency() -> None:
    provider = FasterWhisperSpeechToTextProvider(
        model_name="base.en",
        device="cpu",
        compute_type="int8",
        import_error=ModuleNotFoundError("missing faster_whisper"),
    )

    assert provider.available is False
    with pytest.raises(RuntimeError, match="faster-whisper"):
        provider.transcribe([0.0], sample_rate=16000)


def test_faster_whisper_provider_uses_injected_model() -> None:
    class FakeSegment:
        text = " hello jarvis "

    class FakeInfo:
        duration = 1.25
        language = "en"
        language_probability = 0.99

    class FakeModel:
        def __init__(self, model_name: str, device: str, compute_type: str) -> None:
            assert model_name == "base.en"
            assert device == "cpu"
            assert compute_type == "int8"

        def transcribe(self, audio, language: str):
            assert language == "en"
            assert len(audio) == 2
            return [FakeSegment()], FakeInfo()

    provider = FasterWhisperSpeechToTextProvider(
        model_name="base.en",
        device="cpu",
        compute_type="int8",
        model_class=FakeModel,
    )

    result = provider.transcribe([0.1, -0.1], sample_rate=16000)

    assert isinstance(result, TranscriptionResult)
    assert result.text == "hello jarvis"
    assert result.duration_seconds == 1.25
    assert result.language == "en"


def test_pyttsx3_provider_exposes_availability_without_speaking() -> None:
    provider = Pyttsx3TextToSpeechProvider()

    assert provider.name == "pyttsx3"
    assert isinstance(provider.available, bool)
