from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from config.settings import AppSettings
from diagnostics.openwakeword import format_openwakeword_test_report, run_openwakeword_test


@dataclass
class FakeDetection:
    score: float
    detected: bool


class FakeProvider:
    def __init__(self, detections: list[FakeDetection]) -> None:
        self.detections = detections
        self.calls = 0

    def resolve_model_path(self):
        return Path("C:/fake/hey_jarvis_v0.1.onnx")

    def detect(self, samples, sample_rate: int):
        del samples, sample_rate
        result = self.detections[min(self.calls, len(self.detections) - 1)]
        self.calls += 1
        return type(
            "WakeDetection",
            (),
            {
                "score": result.score,
                "detected": result.detected,
            },
        )()


class FakeSoundDevice:
    def __init__(self, sample_rate: int, channels: int, seconds: float) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.seconds = seconds
        self.checked = False

    def check_input_settings(self, samplerate: int, channels: int) -> None:
        self.checked = True
        assert samplerate == self.sample_rate
        assert channels == self.channels

    def rec(self, frames: int, samplerate: int, channels: int, dtype: str):
        assert samplerate == self.sample_rate
        assert channels == self.channels
        assert dtype == "float32"
        samples = np.zeros((frames, channels), dtype=np.float32)
        samples[:1280] = 0.25
        return samples

    def wait(self) -> None:
        return None


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        openwakeword_enabled=True,
        openwakeword_model="hey_jarvis",
        openwakeword_test_seconds=2.0,
        openwakeword_threshold=0.5,
        openwakeword_listen_chunk_ms=80,
    )


def test_openwakeword_diagnostic_reports_format(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    fake_sd = FakeSoundDevice(sample_rate=settings.voice_sample_rate, channels=settings.voice_channels, seconds=2.0)
    provider = FakeProvider([FakeDetection(score=0.1, detected=False), FakeDetection(score=0.7, detected=True)])

    monkeypatch.setattr("diagnostics.openwakeword.is_openwakeword_installed", lambda: True)
    monkeypatch.setattr("diagnostics.openwakeword.available_openwakeword_models", lambda: ["alexa", "hey_jarvis"])

    report = run_openwakeword_test(
        settings,
        sounddevice_module=fake_sd,
        provider_factory=lambda diag_settings: provider,
    )
    text = format_openwakeword_test_report(report)

    assert report.is_successful is True
    assert report.status == "PASS"
    assert report.detected is True
    assert "Jarvis OpenWakeWord Test" in text
    assert "Package available: yes" in text
    assert "Selected model: hey_jarvis" in text
    assert "Available models: alexa, hey_jarvis" in text
    assert "Detected: yes" in text
    assert "Max score: 0.7000" in text


def test_openwakeword_diagnostic_handles_missing_model_without_crash(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr("diagnostics.openwakeword.is_openwakeword_installed", lambda: True)
    monkeypatch.setattr("diagnostics.openwakeword.available_openwakeword_models", lambda: ["alexa", "weather"])

    report = run_openwakeword_test(settings, provider_factory=lambda diag_settings: FakeProvider([]))

    assert report.status == "WARN"
    assert report.model_available is False
    assert "hey_jarvis" in report.message
    assert "Available built-in models" in " ".join(report.notes)


def test_openwakeword_diagnostic_handles_missing_package_without_crash(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr("diagnostics.openwakeword.is_openwakeword_installed", lambda: False)
    monkeypatch.setattr("diagnostics.openwakeword.available_openwakeword_models", lambda: [])

    report = run_openwakeword_test(settings)

    assert report.status == "WARN"
    assert report.package_available is False
    assert report.detected is False
    assert "not installed" in report.message.lower()
