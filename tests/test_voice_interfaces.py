from __future__ import annotations

from types import SimpleNamespace

import pytest

from config.settings import AppSettings
from voice.interfaces import TranscriptionResult
from voice.stt import (
    FallbackSpeechToTextProvider,
    FasterWhisperSpeechToTextProvider,
    InterfaceOnlySpeechToTextProvider,
    OpenAISpeechToTextProvider,
    create_speech_to_text_provider,
    read_wav_samples,
    transcribe_audio_file,
    write_wav_file,
)
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


def test_stt_factory_can_select_openai_with_faster_whisper_fallback() -> None:
    settings = AppSettings(
        _env_file=None,
        speech_to_text_provider="openai-stt",
        stt_fallback_provider="faster-whisper",
        openai_api_key="sk-test",
    )

    provider = create_speech_to_text_provider(settings)

    assert isinstance(provider, FallbackSpeechToTextProvider)
    assert isinstance(provider.primary, OpenAISpeechToTextProvider)
    assert isinstance(provider.fallback, FasterWhisperSpeechToTextProvider)
    assert provider.name == "openai_stt"


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


def test_faster_whisper_provider_reuses_loaded_model() -> None:
    created = 0
    calls: list[dict[str, object]] = []

    class FakeSegment:
        text = " status report "
        avg_logprob = -0.15

    class FakeInfo:
        duration = 0.8
        language = "en"
        language_probability = None

    class FakeModel:
        def __init__(self, model_name: str, device: str, compute_type: str) -> None:
            nonlocal created
            del model_name, device, compute_type
            created += 1

        def transcribe(self, audio, **kwargs):
            calls.append(kwargs)
            return [FakeSegment()], FakeInfo()

    provider = FasterWhisperSpeechToTextProvider(
        model_name="base.en",
        device="cpu",
        compute_type="int8",
        model_class=FakeModel,
    )

    assert provider.warm_up() is True
    first = provider.transcribe([0.1], sample_rate=16000)
    second = provider.transcribe([0.2], sample_rate=16000)

    assert created == 1
    assert first.text == "status report"
    assert second.text == "status report"
    assert calls[0]["beam_size"] == 1
    assert first.confidence is not None


def test_openai_stt_provider_transcribes_wav_audio() -> None:
    captured: dict[str, object] = {}

    class FakeTranscriptions:
        def create(self, **kwargs):
            captured.update(kwargs)
            audio = kwargs["file"].read()
            assert audio.startswith(b"RIFF")
            assert b"WAVE" in audio[:16]
            return SimpleNamespace(
                text="hello jarvis",
                confidence=0.87,
                duration=1.1,
                language="en",
            )

    class FakeAudio:
        transcriptions = FakeTranscriptions()

    class FakeClient:
        audio = FakeAudio()

    provider = OpenAISpeechToTextProvider(
        api_key="sk-test",
        model_name="gpt-4o-mini-transcribe",
        client_factory=lambda api_key: FakeClient(),
    )

    result = provider.transcribe([0.1, -0.1, 0.0], sample_rate=16000)

    assert result.text == "hello jarvis"
    assert result.confidence == 0.87
    assert result.duration_seconds == 1.1
    assert result.language == "en"
    assert captured["model"] == "gpt-4o-mini-transcribe"


def test_openai_stt_provider_reports_missing_key() -> None:
    provider = OpenAISpeechToTextProvider(
        api_key="",
        model_name="gpt-4o-mini-transcribe",
        client_factory=lambda api_key: object(),
    )

    assert provider.available is False
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        provider.transcribe([0.1], sample_rate=16000)


def test_openai_stt_provider_transcribes_existing_wav_file(tmp_path) -> None:
    audio_path = write_wav_file(tmp_path / "sample.wav", [0.1, -0.2, 0.0], 16000)
    captured: dict[str, object] = {}

    class FakeTranscriptions:
        def create(self, **kwargs):
            captured.update(kwargs)
            assert kwargs["file"].read() == audio_path.read_bytes()
            return {"text": "same audio", "confidence": 0.72}

    class FakeAudio:
        transcriptions = FakeTranscriptions()

    class FakeClient:
        audio = FakeAudio()

    provider = OpenAISpeechToTextProvider(
        api_key="sk-test",
        model_name="gpt-4o-mini-transcribe",
        client_factory=lambda api_key: FakeClient(),
    )

    result = provider.transcribe_file(audio_path)

    assert result.text == "same audio"
    assert result.confidence == 0.72
    assert captured["model"] == "gpt-4o-mini-transcribe"


def test_transcribe_audio_file_decodes_wav_for_sample_based_provider(tmp_path) -> None:
    audio_path = write_wav_file(tmp_path / "sample.wav", [0.25, -0.25], 16000)

    class FakeProvider:
        name = "fake_stt"
        available = True

        def transcribe(self, samples, sample_rate: int) -> TranscriptionResult:
            assert sample_rate == 16000
            assert samples == read_wav_samples(audio_path)[0]
            return TranscriptionResult(text="decoded audio", confidence=0.8)

    result = transcribe_audio_file(FakeProvider(), audio_path)

    assert result.text == "decoded audio"
    assert result.confidence == 0.8


def test_stt_fallback_provider_uses_fallback_when_primary_fails() -> None:
    class FailingProvider:
        name = "openai_stt"
        available = True

        def warm_up(self) -> bool:
            return True

        def transcribe(self, samples, sample_rate: int) -> TranscriptionResult:
            del samples, sample_rate
            raise RuntimeError("network failed")

    class FallbackProvider:
        name = "faster_whisper"
        available = True

        def warm_up(self) -> bool:
            return True

        def transcribe(self, samples, sample_rate: int) -> TranscriptionResult:
            assert sample_rate == 16000
            assert samples == [0.1]
            return TranscriptionResult(text="fallback transcript", confidence=0.7)

    provider = FallbackSpeechToTextProvider(FailingProvider(), FallbackProvider())

    result = provider.transcribe([0.1], sample_rate=16000)

    assert result.text == "fallback transcript"
    assert result.confidence == 0.7


def test_pyttsx3_provider_exposes_availability_without_speaking() -> None:
    provider = Pyttsx3TextToSpeechProvider()

    assert provider.name == "pyttsx3"
    assert isinstance(provider.available, bool)
