from __future__ import annotations

import pytest

from voice.stt import InterfaceOnlySpeechToTextProvider
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


def test_pyttsx3_provider_exposes_availability_without_speaking() -> None:
    provider = Pyttsx3TextToSpeechProvider()

    assert provider.name == "pyttsx3"
    assert isinstance(provider.available, bool)
